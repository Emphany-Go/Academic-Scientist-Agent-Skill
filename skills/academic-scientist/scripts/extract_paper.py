"""Agent-led extraction with pinned inputs, review gates and immutable checkpoints.

No LLM/network calls. A text match checks provenance, not scientific entailment.
"""
import argparse
import copy
import json
import re
from pathlib import Path
from jsonschema.exceptions import ValidationError

from runtime import atomic_text, check_schema, inside, now, read_json, sha256, workspace_lock, write_json
from validate_record import CATALOG, validate


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value):
        raise ValueError('Use a 1-80 character job/paper ID: letters, digits, _ or -')
    return value


def job_dir(root, job_id):
    return inside(root, 'extraction/' + identifier(job_id))


def load(root, job_id):
    files = sorted((job_dir(root, job_id) / 'revisions').glob('*.json'))
    if not files:
        raise ValueError('Job not found; start it first')
    state = read_json(files[-1])
    check_schema('extraction-job.schema.json', state)
    return state


def save(root, state, action):
    state['revision'] += 1
    state['updated_at'] = now()
    state['last_action'] = action
    check_schema('extraction-job.schema.json', state)
    target = job_dir(root, state['job_id']) / 'revisions' / f'{state["revision"]:06d}.json'
    if target.exists():
        raise ValueError('Revision already exists')
    write_json(target, state)
    return state


def associated(manifest, main):
    if main not in manifest['documents']:
        raise ValueError('Unknown main document')
    ids = {main}
    for key, doc in manifest['documents'].items():
        if any(r['role'] == 'supplement' and r['parent_doc_id'] == main for r in doc['roles']):
            ids.add(key)
    expectations = [x for x in manifest['expectations'] if x['parent_doc_id'] == main]
    ids.update(x['supplied_doc_id'] for x in expectations if x['supplied_doc_id'])
    return sorted(ids), expectations


def manifest_at(root):
    value = read_json(inside(root, 'library/manifest.json'))
    check_schema('library-manifest.schema.json', value)
    return value


def fresh(root, state):
    """Reject changed source/parse/attachment context. Historical show remains possible."""
    manifest = manifest_at(root)
    ids, expectations = associated(manifest, state['main_doc_id'])
    if ids != sorted(state['sources']) or expectations != state['expectations']:
        raise ValueError('Attachment context changed; start a new job and recheck facts')
    for key, source in state['sources'].items():
        doc = manifest['documents'][key]
        if doc['active_parse'] != source['parse_path']:
            raise ValueError('Active parse changed; start a new job')
        if sha256(inside(root, source['source_path'])) != key:
            raise ValueError('Source hash mismatch')
        if sha256(inside(root, source['parse_path'])) != source['parse_sha256']:
            raise ValueError('Parse snapshot changed; start a new job after parsing finishes')
        for page in source['pages']:
            for kind in ('text', 'preview'):
                if page[kind + '_path']:
                    if sha256(inside(root, page[kind + '_path'])) != page[kind + '_sha256']:
                        raise ValueError('Page artifact hash mismatch')


def start(root, job_id, payload):
    if list((job_dir(root, job_id) / 'revisions').glob('*.json')):
        raise ValueError('Job already exists; use show to resume')
    manifest = manifest_at(root)
    main = payload['doc_id']
    ids, expectations = associated(manifest, main)
    sources = {}
    for key in ids:
        doc = manifest['documents'][key]
        if not doc['active_parse']:
            raise ValueError('Parse each linked document before extraction')
        parse_path = inside(root, doc['active_parse'])
        parsed = read_json(parse_path)
        check_schema('document-parse.schema.json', parsed)
        if parsed['doc_id'] != key or not parsed['page_count'] or not parsed['pages']:
            raise ValueError('Document has no usable page inventory')
        sources[key] = {'source_path': doc['source_path'], 'parse_path': doc['active_parse'],
                        'parse_sha256': sha256(parse_path), 'page_count': parsed['page_count'],
                        'pages': parsed['pages']}
    state = {'schema_version': '0.3.0', 'job_id': identifier(job_id),
             'paper_id': identifier(payload.get('paper_id', job_id)), 'main_doc_id': main,
             'revision': 0, 'created_at': now(), 'updated_at': now(), 'last_action': 'start',
             'sources': sources, 'expectations': expectations, 'inspections': {},
             'candidate_number': 0, 'candidate': None, 'reviews': {}}
    fresh(root, state)
    return save(root, state, 'start')


def page_at(state, source_id, number):
    if source_id not in state['sources']:
        raise ValueError('Unknown source')
    pages = [p for p in state['sources'][source_id]['pages'] if p['number'] == number]
    if len(pages) != 1:
        raise ValueError('Page is not present in pinned parse')
    return pages[0]


def inspect(state, payload):
    sid, number = payload['source_id'], payload['page']
    if type(number) is not int:
        raise ValueError('Page must be a physical integer page number')
    page = page_at(state, sid, number)
    mode = payload['mode']
    if mode not in ('text', 'visual', 'both', 'unreadable') or not payload.get('note', '').strip():
        raise ValueError('Inspection requires mode and a concrete reading note')
    if mode in ('text', 'both') and (not page['text_path'] or page['status'] != 'text_extracted'):
        raise ValueError('Text is unavailable/suspect; inspect visually instead')
    if mode in ('visual', 'both') and not page['preview_path']:
        raise ValueError('Visual inspection requires a page preview')
    scope = payload.get('scope', 'partial_page')
    if scope not in ('partial_page', 'full_page'):
        raise ValueError('Inspection scope must be partial_page or full_page')
    state['inspections'][f'{sid}:{number}'] = {'source_id': sid, 'page': number, 'mode': mode,
                                             'scope': scope, 'note': payload['note'], 'time': now()}
    # Even a coverage-only change requires candidate resubmission and new reviews.
    state['reviews'] = {}


def record_sources(state):
    result = []
    for sid, source in state['sources'].items():
        entries = [x for x in state['inspections'].values() if x['source_id'] == sid]
        result.append({'id': sid, 'path': source['source_path'], 'sha256': sid, 'format': 'pdf',
                       'page_count': source['page_count'],
                       'inspected_pages': sorted(x['page'] for x in entries if x['mode'] != 'unreadable'),
                       'unreadable_pages': sorted(x['page'] for x in entries if x['mode'] == 'unreadable'),
                       'coverage_note': '实际检查页面见作业 inspections；解析成功不等于已阅读。'})
    return result


def blank_assertion(entity, field):
    return {'id': entity['id'] + ':' + field, 'field': field, 'subject_id': entity['id'],
            'status': 'not_checked', 'value': None, 'evidence_ids': [],
            'note': '尚未抽取或复核。', 'checked_scope': '', 'review_status': 'unreviewed'}


def template(state):
    entity = {'id': state['paper_id'], 'kind': 'paper'}
    return {'schema_version': '0.1.0', 'paper_id': state['paper_id'], 'source_kind': 'provided_document',
            'record_status': 'partial', 'sources': record_sources(state), 'entities': [entity], 'evidence': [],
            'assertions': [blank_assertion(entity, field) for field, d in CATALOG.items() if d['scope'] == 'paper'],
            'review_note': 'Agent 候选；未完成人工验收。'}


def full_coverage(state):
    # A whole-corpus absence claim needs full visual + text-aware reading, including appendices.
    for sid, source in state['sources'].items():
        for number in range(1, source['page_count'] + 1):
            entry = state['inspections'].get(f'{sid}:{number}')
            if not entry or entry['mode'] not in ('visual', 'both') or entry['scope'] != 'full_page':
                return False
    return not any(x['supplied_doc_id'] is None for x in state['expectations'])


def candidate_errors(state, record):
    errors = validate(record)
    if errors:
        return errors
    if record['paper_id'] != state['paper_id']:
        errors.append('paper_id differs from job')
    if record['sources'] != record_sources(state):
        errors.append('Source coverage differs from inspection ledger; obtain a fresh template')
    if record['record_status'] != 'partial':
        errors.append('Candidates must be partial; export computes completion')
    if any(a['review_status'] != 'unreviewed' for a in record['assertions']):
        errors.append('Candidates cannot predeclare agent/human review')
    if any(a['status'] == 'not_reported' for a in record['assertions']) and not full_coverage(state):
        errors.append('not_reported needs all source pages visually checked and no missing attachments; use uncertain')
    return errors


def submit(state, record):
    record = copy.deepcopy(record)
    # Missing fields remain visible, including fields on newly declared model/experiment entities.
    for entity in record.get('entities', []):
        for field, definition in CATALOG.items():
            if definition['scope'] == entity.get('kind') and not any(
                    a.get('subject_id') == entity.get('id') and a.get('field') == field
                    for a in record.get('assertions', [])):
                record['assertions'].append(blank_assertion(entity, field))
    errors = candidate_errors(state, record)
    if errors:
        raise ValueError('; '.join(errors))
    state['candidate'] = record
    state['candidate_number'] += 1
    state['reviews'] = {}


def normal(text):
    # Preserve case, punctuation, numbers, units and accents; only collapse whitespace.
    return ' '.join(text.split())


def audit_evidence(root, state, record):
    result = {}
    for evidence in record['evidence']:
        sid, number = evidence['source_id'], evidence['page']
        page = page_at(state, sid, number)
        entry = state['inspections'].get(f'{sid}:{number}')
        visual = bool(entry and entry['mode'] in ('visual', 'both'))
        matched = False
        if evidence['kind'] == 'text' and page['text_path']:
            matched = normal(evidence['excerpt']) in normal(inside(root, page['text_path']).read_text(encoding='utf-8'))
        mode = 'text_match' if matched and page['status'] == 'text_extracted' else 'visual_confirmation_required'
        if evidence['kind'] != 'text':
            mode = 'visual_confirmation_required'
        result[evidence['id']] = {'mode': mode, 'text_match': matched, 'visual_inspected': visual,
                                 'eligible': mode == 'text_match' or visual}
    return result


def review(root, state, payload):
    record = state['candidate']
    if record is None:
        raise ValueError('Submit a candidate first')
    errors = candidate_errors(state, record)
    if errors:
        raise ValueError('; '.join(errors))
    audit = audit_evidence(root, state, record)
    assertions = {a['id']: a for a in record['assertions']}
    items = payload['items']
    if not items or len({i['assertion_id'] for i in items}) != len(items):
        raise ValueError('Review items must be nonempty and unique')
    for item in items:
        key = item['assertion_id']
        if key not in assertions:
            raise ValueError('Unknown assertion')
        assertion = assertions[key]
        if item['decision'] not in ('accept', 'reject') or not item.get('rationale', '').strip():
            raise ValueError('Each review needs a decision and substantive rationale')
        confirmations = item.get('visual_confirmations', {})
        if any(eid not in assertion['evidence_ids'] for eid in confirmations):
            raise ValueError('Visual confirmation must refer to this assertion evidence')
        if item['decision'] == 'accept':
            if assertion['status'] == 'not_checked':
                raise ValueError('Cannot accept not_checked')
            if set(item.get('checks', [])) != {'support', 'attribution', 'conditions', 'faithfulness'}:
                raise ValueError('Review support, attribution, conditions and faithfulness explicitly')
            for eid in assertion['evidence_ids']:
                evidence_audit = audit[eid]
                if not evidence_audit['eligible']:
                    raise ValueError('Evidence unmatched and not visually inspected: ' + eid)
                if evidence_audit['mode'] == 'visual_confirmation_required' and not confirmations.get(eid, '').strip():
                    raise ValueError('Table/figure/unmatched text needs an explicit visual confirmation: ' + eid)
        state['reviews'][key] = {'decision': item['decision'], 'rationale': item['rationale'],
                                  'checks': item.get('checks', []), 'visual_confirmations': confirmations,
                                  'reviewer': 'agent', 'time': now()}


def report(root, state):
    record = state['candidate'] or template(state)
    audit = audit_evidence(root, state, record)
    missing = []
    for assertion in record['assertions']:
        decision = state['reviews'].get(assertion['id'], {}).get('decision')
        if decision != 'accept':
            missing.append({'assertion_id': assertion['id'], 'field': assertion['field'],
                            'status': assertion['status'], 'review': decision or 'pending'})
    return {'job_id': state['job_id'], 'revision': state['revision'],
            'candidate_number': state['candidate_number'], 'evidence_audit': audit,
            'full_source_coverage': full_coverage(state), 'pending_fields': missing,
            'inspected_pages': sum(len(x['inspected_pages']) for x in record_sources(state)),
            'total_pages': sum(x['page_count'] for x in state['sources'].values()),
            'missing_attachments': [x['label'] for x in state['expectations'] if x['supplied_doc_id'] is None],
            'candidate_errors': candidate_errors(state, record) if state['candidate'] else [],
            'limitation': 'Matching and review logs do not independently prove scientific truth.'}


def export_record(root, state):
    if not state['candidate']:
        raise ValueError('Submit a candidate first')
    errors = candidate_errors(state, state['candidate'])
    if errors:
        raise ValueError('; '.join(errors))
    record = copy.deepcopy(state['candidate'])
    for i, assertion in enumerate(record['assertions']):
        decision = state['reviews'].get(assertion['id'], {}).get('decision')
        if decision == 'accept':
            assertion['review_status'] = 'agent_checked'
        else:
            record['assertions'][i] = {**assertion, 'status': 'not_checked', 'value': None,
                                      'evidence_ids': [], 'review_status': 'unreviewed',
                                      'note': '尚未通过逐项复核；候选与拒绝原因保留在作业历史。', 'checked_scope': ''}
    # A numerical result must not be exported while any of its context assertions is pending.
    for assertion in record['assertions']:
        if assertion['field'] == 'result' and assertion['status'] == 'supported':
            companions = {a['field']: a for a in record['assertions'] if a['subject_id'] == assertion['subject_id']}
            if any(companions[f]['status'] == 'not_checked' for f in ('metric', 'dataset', 'conditions')):
                assertion.update(status='not_checked', value=None, evidence_ids=[], review_status='unreviewed',
                                 note='结果上下文未全部通过复核；暂缓导出该数值。', checked_scope='')
    used = {eid for a in record['assertions'] for eid in a['evidence_ids']}
    record['evidence'] = [e for e in record['evidence'] if e['id'] in used]
    all_reviewed = all(a['review_status'] == 'agent_checked' for a in record['assertions'])
    record['record_status'] = 'complete' if all_reviewed and full_coverage(state) else 'partial'
    record['review_note'] = '仅含已接受的 Agent 复核事实；非独立人工验收。未通过项见同目录 report.json 与作业历史。'
    errors = validate(record)
    if errors:
        raise ValueError('; '.join(errors))
    # Deterministic, immutable export keyed to the exact job revision. Retry repairs partial export.
    folder = job_dir(root, state['job_id']) / 'exports' / f'r{state["revision"]:06d}'
    result = report(root, state)
    result['export_deferred_fields'] = [a['id'] for a in record['assertions'] if a['status'] == 'not_checked']
    result['record_status'] = record['record_status']
    values = {'record.json': json.dumps(record, ensure_ascii=False, indent=2) + '\n',
              'report.json': json.dumps(result, ensure_ascii=False, indent=2) + '\n'}
    lines = ['# 事实抽取复核报告', '', f'作业：{state["job_id"]}；快照：{state["revision"]}；状态：{record["record_status"]}。',
             f'检查页面：{result["inspected_pages"]}/{result["total_pages"]}。独立人工验收：未进行。', '',
             '## 待处理字段', '']
    lines.extend('- ' + a['id'] + '：' + a['note'] for a in record['assertions'] if a['status'] == 'not_checked')
    if result['missing_attachments']:
        lines += ['', '## 缺失附件', ''] + ['- ' + x for x in result['missing_attachments']]
    lines += ['', '候选、原文页定位、拒绝理由及历史版本保存在作业 revisions 中。',
              '逐字匹配只检查片段出现位置；Agent 复核可能出错，不能作为独立正确率评测。', '']
    values['report.md'] = '\n'.join(lines)
    for name, content in values.items():
        target = folder / name
        if target.exists() and target.read_text(encoding='utf-8') != content:
            raise ValueError('Export was modified; preserve it and create a new job revision')
    for name, content in values.items():
        target = folder / name
        if not target.exists():
            atomic_text(target, content)
    return {'record_path': str(folder / 'record.json'), 'report_path': str(folder / 'report.md'), **result}


def execute(root, job_id, action, payload=None):
    payload = payload or {}
    with workspace_lock(root) as root:
        if action == 'start':
            return start(root, job_id, payload)
        state = load(root, job_id)
        if action == 'show':
            # Still readable when source material is unavailable; not a fresh audit.
            return state
        fresh(root, state)
        if action == 'template':
            return template(state)
        if action == 'audit':
            return report(root, state)
        if payload.get('expected_revision') != state['revision']:
            raise ValueError('Stale or missing expected_revision; show and retry')
        if action == 'inspect':
            inspect(state, payload)
        elif action == 'submit':
            submit(state, payload['record'])
        elif action == 'review':
            review(root, state, payload)
        elif action == 'export':
            return export_record(root, state)
        else:
            raise ValueError('Unknown action')
        return save(root, state, action)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', '--root', required=True, type=Path)
    parser.add_argument('--job', required=True)
    parser.add_argument('action', choices=['start', 'show', 'template', 'inspect', 'submit', 'audit', 'review', 'export'])
    parser.add_argument('--input', type=Path, help='JSON payload; paths resolve against workspace')
    args = parser.parse_args()
    try:
        payload = read_json(inside(args.workspace, str(args.input))) if args.input else {}
        print(json.dumps(execute(args.workspace, args.job, args.action, payload), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, ValidationError) as exc:
        print('ERROR: ' + str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
