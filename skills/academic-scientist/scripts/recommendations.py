"""Evidence-bound relevance analysis. Host Agent reasons; this script checks and versions it."""
import argparse
import copy
import json
from pathlib import Path
from jsonschema.exceptions import ValidationError

from runtime import inside, read_json, write_json, check_schema, now, workspace_lock
from literature_output import digest, md_escape, preserved_text
from recommendation_sources import capture, freshness, evidence_context

DIMENSIONS = {'problem_fit', 'data_fit', 'method_transfer', 'resource_fit', 'reading_goal_fit'}
DIMENSION_LABELS = {'problem_fit': '研究问题', 'data_fit': '数据适配', 'method_transfer': '方法迁移', 'resource_fit': '资源可行性', 'reading_goal_fit': '阅读目的'}
RELATION_LABELS = {'direct': '直接相关', 'partial': '部分相关', 'transferable': '有条件可迁移', 'mismatch': '已知条件不匹配', 'unknown': '尚无法判断'}
USE_LABELS = {'background': '入门背景', 'close_reading': '精读用途', 'baseline': '基线参考', 'method_borrowing': '方法借鉴', 'counterexample': '反例与限制'}
ASPECT_LABELS = {'method': '方法', 'background': '背景', 'experimental_design': '实验设计', 'model_selection': '模型选择'}


def entry_key(direction_id, paper_id):
    return digest([direction_id, paper_id])[:24]


def goal_entries(card, indices):
    if not indices or any(type(i) is not int or not 1 <= i <= len(card['entries']) for i in indices):
        raise ValueError('Goal references must be valid 1-based research-card entry indices')
    return [card['entries'][i-1] for i in indices]


def validate_directions(snapshot, directions):
    if len({d['id'] for d in directions}) != len(directions):
        raise ValueError('Duplicate direction ID')
    for d in directions:
        refs = goal_entries(snapshot['card'], d['goal_refs'])
        if d['origin'] == 'user_explicit' and any(e['origin'] != 'user_explicit' for e in refs):
            raise ValueError('Agent proposals and unresolved goals cannot be user-confirmed directions')
        if not any(e['category'] in ('interest', 'candidate_direction', 'reading_goal') for e in refs):
            raise ValueError('Direction needs an interest, candidate direction or reading goal')


def validate_entry(state, entry):
    check_schema('relevance-entry.schema.json', entry)
    snapshot = state['snapshot']
    if entry['paper_id'] not in snapshot['papers']:
        raise ValueError('Paper is not in the bound collection')
    direction = next((d for d in state['directions'] if d['id'] == entry['direction_id']), None)
    if direction is None:
        raise ValueError('Unknown direction')
    if len(entry['assessments']) != 5 or {a['dimension'] for a in entry['assessments']} != DIMENSIONS:
        raise ValueError('Exactly five distinct assessment dimensions required')
    pid = entry['paper_id']

    def claim(c):
        goals = goal_entries(snapshot['card'], c['goal_refs'])
        context = evidence_context(snapshot, pid, c['fact_refs'])
        return goals, context

    for a in entry['assessments']:
        goals, refs = claim(a['explanation'])
        supported = any(x['assertion']['status'] == 'supported' for x in refs)
        if a['relation'] == 'unknown':
            if not a['unknowns']:
                raise ValueError('Unknown assessment needs an explicit missing condition')
        else:
            if not supported:
                raise ValueError('Non-unknown relationship requires supported paper facts')
            if not any(g['origin'] == 'user_explicit' and g['category'] != 'unknown' for g in goals):
                raise ValueError('Known alignment/mismatch needs an explicit user goal')
        if a['relation'] == 'transferable' and not a['conditions']:
            raise ValueError('Transferable method requires explicit transfer conditions')
    _, context = claim(entry['summary'])
    if not context:
        raise ValueError('Summary needs reviewed evidence, including explicit unknown evidence where appropriate')
    if not set(entry['summary']['goal_refs']) & set(direction['goal_refs']):
        raise ValueError('Summary must connect to this direction, not an unrelated goal')
    for use in entry['use_cases']:
        _, refs = claim(use['reason'])
        if not any(x['assertion']['status'] == 'supported' for x in refs):
            raise ValueError('Suggested reading use requires supported facts')
    if len({u['use'] for u in entry['use_cases']}) != len(entry['use_cases']):
        raise ValueError('Duplicate reading use')
    if entry['use_cases'] and not entry['reading_targets']:
        raise ValueError('Suggested reading use needs an evidence-linked reading target')
    for limitation in entry['limitations']:
        claim(limitation)
    points = entry.get('learning_points', [])
    if 'learning_points' in entry:
        if len(points) != 4 or {p['aspect'] for p in points} != set(ASPECT_LABELS):
            raise ValueError('Four distinct learning aspects required')
        for point in points:
            goals, refs = claim(point['explanation'])
            if point['status'] == 'actionable':
                if not any(x['assertion']['status'] == 'supported' for x in refs):
                    raise ValueError('Actionable learning point needs supported facts')
                if not any(g['origin'] == 'user_explicit' and g['category'] != 'unknown' for g in goals):
                    raise ValueError('Learning value needs an explicit user goal')
                if not entry['reading_targets']:
                    raise ValueError('Actionable learning needs reading targets')
            elif not point['questions_to_check']:
                raise ValueError('Insufficient learning evidence needs missing-information questions')
    cited = {eid for a in entry['assessments'] for r in a['explanation']['fact_refs'] for eid in r['evidence_ids']}
    cited.update(eid for r in entry['summary']['fact_refs'] for eid in r['evidence_ids'])
    for use in entry['use_cases']:
        cited.update(eid for r in use['reason']['fact_refs'] for eid in r['evidence_ids'])
    for limitation in entry['limitations']:
        cited.update(eid for r in limitation['fact_refs'] for eid in r['evidence_ids'])
    for point in points:
        cited.update(eid for r in point['explanation']['fact_refs'] for eid in r['evidence_ids'])
    for target in entry['reading_targets']:
        if target['evidence_id'] not in cited:
            raise ValueError('Reading target must be a cited evidence location, not a fabricated chapter')


def load(folder, revision=None):
    paths = sorted((folder / 'revisions').glob('*.json'))
    if not paths:
        raise ValueError('Recommendation run does not exist')
    if revision is not None and (type(revision) is not int or revision < 1):
        raise ValueError('Invalid historical revision')
    path = paths[-1] if revision is None else folder / 'revisions' / f'{revision:06d}.json'
    state = read_json(path)
    check_schema('recommendation-run.schema.json', state)
    return state


def save(folder, state, reason):
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('Nonempty revision reason required')
    state['revision'] += 1
    state.update(saved_at=now(), reason=reason)
    check_schema('recommendation-run.schema.json', state)
    validate_directions(state['snapshot'], state['directions'])
    for e in state['entries'].values():
        validate_entry(state, e)
    path = folder / 'revisions' / f'{state["revision"]:06d}.json'
    if path.exists():
        raise ValueError('Refusing to overwrite revision')
    write_json(path, state)
    return state


def status(root, state):
    pending = []
    accepted = []
    for d in state['directions']:
        for pid in state['snapshot']['papers']:
            k = entry_key(d['id'], pid)
            e, r = state['entries'].get(k), state['reviews'].get(k)
            item = {'direction_id': d['id'], 'paper_id': pid}
            if e and r and r['decision'] == 'accepted' and r['candidate_digest'] == digest(e):
                accepted.append(item)
            else:
                pending.append(dict(item, state='missing' if not e else 'rejected' if r and r['decision'] == 'rejected' else 'unreviewed'))
    fresh = freshness(root, state['snapshot'])
    learning_pending = [item for item in accepted if 'learning_points' not in state['entries'][entry_key(item['direction_id'], item['paper_id'])]]
    return {'revision': state['revision'], 'freshness': fresh, 'accepted': accepted, 'pending': pending,
            'analysis_ready': fresh['current'] and not pending, 'learning_pending': learning_pending,
            'recommendation_ready': fresh['current'] and not pending and not learning_pending}


def export_analysis(root, folder, state):
    report = status(root, state)
    if not report['analysis_ready']:
        raise ValueError('Complete and review every paper/direction; refresh stale inputs before export')
    target = folder / 'analysis-exports' / f'r{state["revision"]:06d}'
    snapshot = state['snapshot']
    lines = ['# 文献相关性分析底稿', '',
             '本文件是 Agent 分析，不是论文原文结论。呈现方式尚未应用，不含最终优先级、总分或排序。',
             f'研究探索卡 v{snapshot["card"]["version"]}；分析版本 {state["revision"]}。先检查 status 再用于新任务，文件本身不会自动刷新。', '']
    if state['purpose'] == 'synthetic_test':
        lines += ['合成测试档案，不代表真实用户研究目标。', '']
    lines += ['## 研究目标与未知条件', '']
    for i, goal in enumerate(snapshot['card']['entries'], 1):
        lines += [f'- G{i}（{goal["origin"]}）：{md_escape(goal["text"])}']
        for quote in goal['source_quotes']:
            lines.append('  - 用户原话（' + quote['source_ref'] + '）：' + md_escape(quote['quote']))
    for d in state['directions']:
        lines += ['', '## ' + md_escape(d['label']), '', '阅读切入点来源：' + d['origin'] + '；不是已经确定的研究技术路线。', '',
                  '| 论文 | 研究问题 | 数据适配 | 方法迁移 | 资源可行性 | 阅读目的 |', '|---|---|---|---|---|---|']
        entries = [state['entries'][entry_key(d['id'], pid)] for pid in sorted(snapshot['papers'])]
        for e in entries:
            dimensions = {a['dimension']: a for a in e['assessments']}
            lines.append('| ' + ' | '.join([md_escape(e['paper_id'])] + [RELATION_LABELS[dimensions[k]['relation']] for k in DIMENSION_LABELS]) + ' |')
        for e in entries:
            pid = e['paper_id']
            record = snapshot['papers'][pid]['record']
            title = next((a['value'] for a in record['assertions'] if a['field'] == 'title' and a['status'] == 'supported'), '标题未核实')
            lines += ['', f'### {md_escape(pid)} · {md_escape(title)}', '', '覆盖状态：' + record['record_status'] + '；详见原文记录的覆盖说明。', '']

            def display_claim(c):
                refs = []
                for context in evidence_context(snapshot, pid, c['fact_refs']):
                    a = context['assertion']
                    locations = [f'{x["id"]}（物理页 {x["page"] if x["page"] is not None else "不适用"}，{x["locator"]}）' for x in context['evidence']]
                    refs.append(a['id'] + ' [' + a['status'] + ']：' + ('；'.join(locations) or a['note']))
                return md_escape(c['text']) + '\n\n依据：' + '、'.join('G'+str(i) for i in c['goal_refs']) + '；' + md_escape(' | '.join(refs) or '仅为目标侧未知条件，未断言论文事实。')

            lines += [display_claim(e['summary']), '']
            for a in e['assessments']:
                lines += ['**' + DIMENSION_LABELS[a['dimension']] + '：' + RELATION_LABELS[a['relation']] + '**', '', display_claim(a['explanation']), '']
                if a['conditions']:
                    lines += ['适用条件：' + md_escape('；'.join(a['conditions'])), '']
                if a['unknowns']:
                    lines += ['待明确：' + md_escape('；'.join(a['unknowns'])), '']
            for use in e['use_cases']:
                lines += ['阅读用途：' + USE_LABELS[use['use']], '', display_claim(use['reason']), '']
            evidence = {x['id']: x for x in record['evidence']}
            lines += ['阅读位置：', '']
            for t in e['reading_targets']:
                ev = evidence[t['evidence_id']]
                lines += [f'- 物理页 {ev["page"] if ev["page"] is not None else "不适用"}，{md_escape(ev["locator"])}：{md_escape(t["purpose"])}']
            for limitation in e['limitations']:
                lines += ['', '局限/不可直接套用：', '', display_claim(limitation)]
            lines += ['', '后续需明确：' + md_escape('；'.join(e['open_questions']) or '当前未新增问题。'), '']
    preserved_text(target / 'analysis.json', json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    preserved_text(target / 'analysis.md', '\n'.join(lines) + '\n')
    return {'json_path': str(target / 'analysis.json'), 'markdown_path': str(target / 'analysis.md'), 'kind': 'unranked_analysis_only'}


def export_guide(root, folder, state):
    if not status(root, state)['recommendation_ready']:
        raise ValueError('Reviewed four-aspect learning points and current inputs required before final export')
    target = folder / 'exports' / f'r{state["revision"]:06d}-reading-v2'
    snapshot = state['snapshot']
    lines = ['# 文献阅读与借鉴建议', '',
             '以下为结合用户研究目标的 Agent 分析，按方法、背景、实验设计、模型选择说明学习理由；不计算分数、不设优先级、不按推荐强弱排序。',
             f'研究探索卡 v{snapshot["card"]["version"]}；分析版本 {state["revision"]}；保存时间 {state["saved_at"]}。',
             '本文件为固定版本，目标或论文变化后须先检查 status 并更新。论文按内部 ID 展示，顺序没有评价含义。', '']
    if state['purpose'] == 'synthetic_test':
        lines += ['合成测试档案，不代表真实用户目标。', '']
    lines += ['## 研究目标与待明确条件', '']
    for i, goal in enumerate(snapshot['card']['entries'], 1):
        lines += [f'- G{i}（{goal["origin"]}）：{md_escape(goal["text"])}']
    for direction in state['directions']:
        lines += ['', '## ' + md_escape(direction['label']), '',
                  '切入点来源：' + direction['origin'] + '；此处是阅读组织，不是已确定的研究路线。', '',
                  '| 论文 | 研究问题 | 数据适配 | 方法迁移 | 资源可行性 | 阅读目的 |', '|---|---|---|---|---|---|']
        for pid in sorted(snapshot['papers']):
            entry = state['entries'][entry_key(direction['id'], pid)]
            axes = {a['dimension']: a for a in entry['assessments']}
            lines.append('| ' + ' | '.join([md_escape(pid)] + [RELATION_LABELS[axes[k]['relation']] for k in DIMENSION_LABELS]) + ' |')
        for pid in sorted(snapshot['papers']):
            entry = state['entries'][entry_key(direction['id'], pid)]
            record = snapshot['papers'][pid]['record']
            title = next((a['value'] for a in record['assertions'] if a['field'] == 'title' and a['status'] == 'supported'), '标题未核实')
            lines += ['', f'### {md_escape(pid)} · {md_escape(title)}', '', '原文覆盖状态：' + record['record_status'] + '。', '']
            source_files = snapshot['papers'][pid]['source_files']
            source_labels = {sid: f'S{i}' for i, sid in enumerate(sorted(source_files), 1)}
            for sid, label in source_labels.items():
                path = inside(root, source_files[sid]).as_posix()
                lines += [f'原文文件：[{label}](<{path}>)（本篇内部编号）。', '']

            def add_claim(claim):
                lines.extend([md_escape(claim['text']), '', '目标依据：' + '、'.join('G'+str(i) for i in claim['goal_refs']) + '。', ''])
                contexts = evidence_context(snapshot, pid, claim['fact_refs'])
                for ctx in contexts:
                    assertion = ctx['assertion']
                    loc = '；'.join(f'{source_labels[ev["source_id"]]}，PDF 物理页 {ev["page"] if ev["page"] is not None else "不适用"}，{ev["locator"]} [{ev["id"]}]' for ev in ctx['evidence'])
                    lines.append('- 原文依据：' + md_escape(assertion['id'] + ' [' + assertion['status'] + ']；' + (loc or assertion['note'])))
                if not contexts:
                    lines.append('依据仅为用户目标/未知条件，没有新增论文事实。')
                lines.append('')

            add_claim(entry['summary'])
            points = {p['aspect']: p for p in entry['learning_points']}
            for aspect, label in ASPECT_LABELS.items():
                point = points[aspect]
                lines += ['**' + label + ('：值得学习/借鉴' if point['status'] == 'actionable' else '：当前证据不足') + '**', '']
                add_claim(point['explanation'])
                if point['questions_to_check']:
                    lines += ['阅读时核对：' + md_escape('；'.join(point['questions_to_check'])), '']
            lines += ['**借鉴条件与未知项**', '']
            for axis in entry['assessments']:
                if axis['conditions'] or axis['unknowns']:
                    lines.append('- ' + DIMENSION_LABELS[axis['dimension']] + '：' + md_escape('；'.join(axis['conditions'] + axis['unknowns'])))
            lines += ['', '**具体阅读位置**', '']
            evidence = {ev['id']: ev for ev in record['evidence']}
            for reading in entry['reading_targets']:
                ev = evidence[reading['evidence_id']]
                lines.append('- ' + md_escape(f'{source_labels[ev["source_id"]]}，PDF 物理页 {ev["page"] if ev["page"] is not None else "不适用"}，{ev["locator"]}：{reading["purpose"]}'))
            lines += ['', '**不可直接套用的部分**', '']
            for limitation in entry['limitations']:
                add_claim(limitation)
            lines += ['后续待明确：' + md_escape('；'.join(entry['open_questions']) or '暂无新增问题。'), '']
    bundle = {'presentation': 'learning_reasons', 'scoring': False, 'priority_tiers': False, 'run': state}
    preserved_text(target / 'reading-guide.json', json.dumps(bundle, ensure_ascii=False, indent=2) + '\n')
    preserved_text(target / 'reading-guide.md', '\n'.join(lines) + '\n')
    return {'json_path': str(target / 'reading-guide.json'), 'markdown_path': str(target / 'reading-guide.md'), 'kind': 'learning_reasons'}


def execute(root, run, action, payload):
    with workspace_lock(root) as root:
        folder = inside(root, run)
        if action == 'start':
            if any((folder / 'revisions').glob('*.json')):
                raise ValueError('Run exists; use show/refresh instead of restarting')
            snapshot = capture(root, payload['binding'])
            state = {'schema_version': '0.6.0', 'source_kind': 'agent_analysis', 'revision': 0,
                     'saved_at': now(), 'reason': payload['reason'], 'purpose': snapshot['card']['purpose'],
                     'snapshot': snapshot, 'directions': payload['directions'], 'entries': {}, 'reviews': {}}
            return save(folder, state, payload['reason'])
        state = load(folder, payload.get('revision') if action == 'show' else None)
        if action == 'show':
            return {'run': state, 'status': status(root, state)}
        if action == 'status':
            return status(root, state)
        if action == 'export-analysis':
            return export_analysis(root, folder, state)
        if action == 'export':
            return export_guide(root, folder, state)
        if type(payload.get('expected_revision')) is not int or payload['expected_revision'] != state['revision']:
            raise ValueError('Stale expected_revision')
        if action == 'refresh':
            current = capture(root, state['snapshot']['binding'])
            directions = payload.get('directions', state['directions'])
            changed_goal = current['card_digest'] != state['snapshot']['card_digest'] or directions != state['directions']
            keep = {pid for pid,h in current['paper_digests'].items() if h == state['snapshot']['paper_digests'].get(pid)}
            state['entries'] = {k:e for k,e in state['entries'].items() if not changed_goal and e['paper_id'] in keep}
            state['reviews'] = {k:r for k,r in state['reviews'].items() if k in state['entries']}
            state.update(snapshot=current, directions=directions, purpose=current['card']['purpose'])
            return save(folder, state, payload['reason'])
        if not freshness(root, state['snapshot'])['current']:
            raise ValueError('Inputs changed; refresh before analysis or review')
        if action == 'submit':
            e = payload['entry']
            validate_entry(state, e)
            k = entry_key(e['direction_id'], e['paper_id'])
            if state['entries'].get(k) == e:
                return state
            state['entries'][k] = copy.deepcopy(e)
            state['reviews'].pop(k, None)
        elif action == 'review':
            k = entry_key(payload['direction_id'], payload['paper_id'])
            if k not in state['entries']:
                raise ValueError('No submitted candidate to review')
            validate_entry(state, state['entries'][k])
            r = {'candidate_digest': digest(state['entries'][k]), 'decision': payload['decision'],
                 'reviewer': payload['reviewer'], 'review_note': payload['review_note'], 'reviewed_at': now(),
                 **{f: payload[f] for f in ('evidence_fidelity', 'goal_alignment', 'uncertainty_handling')}}
            if r['decision'] == 'accepted' and any(r[f] is not True for f in ('evidence_fidelity','goal_alignment','uncertainty_handling')):
                raise ValueError('Accepted analysis requires all review checks to be true')
            state['reviews'][k] = r
        else:
            raise ValueError('Unknown action')
        return save(folder, state, payload['reason'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--run', required=True)
    parser.add_argument('action', choices=['start', 'show', 'status', 'refresh', 'submit', 'review', 'export-analysis', 'export'])
    parser.add_argument('--input', required=True)
    args = parser.parse_args()
    try:
        result = execute(args.root, args.run, args.action, read_json(inside(args.root, args.input)))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, ValidationError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
