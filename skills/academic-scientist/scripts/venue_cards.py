"""External venue profiles, strict provenance, immutable history and dated views.

The host Agent browses and reviews sources. This script does not browse, infer
quartiles, authenticate screenshots, or modify paper facts.
"""
import argparse
import copy
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker
from runtime import inside, now, read_json, sha256, workspace_lock, write_json, atomic_text
from validate_record import validate as validate_paper

SCHEMA = read_json(Path(__file__).resolve().parents[1] / 'schemas/venue-profile.schema.json')
POLICY = read_json(Path(__file__).resolve().parents[1] / 'assets/venue-policy.json')
DOMAINS = {'JCR': ('clarivate.com', 'clarivate.com.cn'), 'CAS': ('fenqubiao.com',), 'CCF': ('ccf.org.cn',)}
VALUES = {'JCR': {'Q1', 'Q2', 'Q3', 'Q4'}, 'CAS': {'1区', '2区', '3区', '4区'}, 'CCF': {'A', 'B', 'C'}}


def day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Expected ISO calendar date YYYY-MM-DD')
    return date.fromisoformat(value)


def url_host(value):
    parsed = urlparse(value)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Expected public HTTP(S) URL without credentials')
    return parsed.hostname.lower()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', value):
        raise ValueError('Invalid venue ID')
    return value


def normal(value):
    return ' '.join(value.casefold().split())


def require_official_only(card):
    if any(s['authority'] == 'third_party' for s in card['sources']) or any(r['status'] == 'third_party' for r in card['ratings']):
        raise ValueError('Official-only policy: third-party records cannot be saved or displayed')


def validate(card, as_of, root=None):
    errors = [e.message for e in Draft202012Validator(SCHEMA, format_checker=FormatChecker()).iter_errors(card)]
    if errors:
        return errors
    try:
        require_official_only(card)
        cutoff = day(as_of)
        if day(card['checked_on']) > cutoff:
            errors.append('Card checked_on is in the future')
        url_host(card['homepage'])
        sources = {s['id']: s for s in card['sources']}
        if len(sources) != len(card['sources']):
            errors.append('Duplicate source ID')
        if len({r['id'] for r in card['ratings']}) != len(card['ratings']):
            errors.append('Duplicate rating ID')
        for source in sources.values():
            host = url_host(source['url'])
            if day(source['retrieved_on']) > day(card['checked_on']):
                errors.append('Source date exceeds card check date')
            if source['authority'] == 'rating_official':
                allowed = DOMAINS.get(source['system'], ())
                if not any(host == domain or host.endswith('.' + domain) for domain in allowed):
                    errors.append('Rating issuer domain/system mismatch')
            if source['access'] in ('read', 'user_supplied') and not source['excerpt'].strip():
                errors.append('Read sources need a short evidence excerpt')
            if bool(source['artifact_path']) != bool(source['artifact_sha256']):
                errors.append('Artifact path and hash must be supplied together')
            if source['access'] == 'user_supplied' and not source['artifact_path']:
                errors.append('User-supplied evidence requires preserved artifact')
            if root is not None and source['artifact_path']:
                if sha256(inside(root, source['artifact_path'])) != source['artifact_sha256']:
                    errors.append('Source artifact hash mismatch')
        def evidence(ids):
            if any(sid not in sources for sid in ids):
                errors.append('Unknown source reference')
            return [sources[sid] for sid in ids if sid in sources]
        for key in ('identity', 'positioning'):
            claim = card[key]
            ss = evidence(claim['source_ids'])
            if claim['status'] == 'verified':
                if not claim['text'] or not ss or not any(s['authority'] == 'venue_official' and s['access'] in ('read', 'user_supplied') for s in ss):
                    errors.append(key + ': official read evidence required')
            elif claim['text'] is not None:
                errors.append(key + ': unverified claim must not contain guessed text')
        pairs = set()
        for rating in card['ratings']:
            ss = evidence(rating['source_ids'])
            system, status = rating['system'], rating['status']
            if day(rating['checked_on']) > day(card['checked_on']):
                errors.append('Rating check date exceeds card date')
            if any(day(s['retrieved_on']) > day(rating['checked_on']) for s in ss):
                errors.append('Rating predates its evidence')
            if rating['release_year'] and rating['release_year'] > cutoff.year:
                errors.append('Future edition cannot be verified as current')
            if rating['metric_year'] and rating['release_year'] and rating['metric_year'] > rating['release_year']:
                errors.append('Metric year cannot follow release year')
            key = (system, rating['edition'], rating['category_level'], rating['category'])
            if key in pairs:
                errors.append('Duplicate system/edition/category; consolidate conflict explicitly')
            pairs.add(key)
            if status in ('verified', 'third_party'):
                if rating['value'] not in VALUES[system]:
                    errors.append('Wrong value for rating system')
                if not rating['edition'] or not rating['release_year'] or not rating['category'] or not ss:
                    errors.append('A rating needs edition, release year, category and sources')
                if rating['coverage'] == 'unknown':
                    errors.append('Declare whether all or selected categories were checked')
                levels = {'JCR': {'jcr_category'}, 'CAS': {'major', 'minor'}, 'CCF': {'ccf_area'}}
                if rating['category_level'] not in levels[system]:
                    errors.append('Category level does not match rating system')
                if status == 'verified':
                    if card['identity']['status'] != 'verified':
                        errors.append('Verify venue identity before ratings')
                    if not any(s['authority'] == 'rating_official' and s['system'] == system and s['access'] in ('read', 'user_supplied') for s in ss):
                        errors.append('Verified rating requires readable evidence from its issuing body')
                elif not any(s['access'] in ('read', 'user_supplied') for s in ss):
                    errors.append('Third-party value cannot come only from a search snippet')
            elif rating['value'] is not None:
                errors.append('Unverified/conflicting/not-applicable rating must be null')
            if system in ('CAS', 'JCR') and card['kind'] != 'journal' and status in ('verified', 'third_party'):
                errors.append('Do not apply journal quartiles to a conference/workshop')
            if system == 'CCF' and card['kind'] == 'conference' and status in ('verified', 'third_party') and rating['applies_to'] != 'full_regular_papers':
                errors.append('CCF conference grade needs full/regular-paper scope')
            if system == 'CCF' and card['kind'] == 'workshop' and status in ('verified', 'third_party'):
                errors.append('A workshop cannot inherit the parent conference grade')
            if card['kind'] == 'journal' and status in ('verified', 'third_party') and rating['applies_to'] != 'journal':
                errors.append('Journal rating requires journal applicability')
    except (ValueError, OSError) as exc:
        errors.append(str(exc))
    return errors


def revisions(root, venue_id):
    return sorted(inside(root, 'venues/' + identifier(venue_id) + '/revisions').glob('*.json'))


def load(root, venue_id, revision=None):
    files = revisions(root, venue_id)
    if not files:
        raise ValueError('Venue card not found')
    if revision is not None:
        if type(revision) is not int or revision < 1:
            raise ValueError('Invalid historical revision')
        path = files[0].parent / f'{revision:06d}.json'
        if not path.exists():
            raise ValueError('Historical revision not found')
        return read_json(path)
    return read_json(files[-1])


def put(root, card, expected_revision, as_of, reason):
    errors = validate(card, as_of, root)
    if errors:
        raise ValueError('; '.join(errors))
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('A new version needs a reason')
    files = revisions(root, card['venue_id'])
    old = read_json(files[-1]) if files else None
    current = old['revision'] if old else 0
    if type(expected_revision) is not int or expected_revision != current:
        raise ValueError('Stale expected_revision')
    if old and day(card['checked_on']) < day(old['card']['checked_on']):
        raise ValueError('Do not replace a newer check with an older check')
    if old and old['card'] == card:
        return old
    state = {'revision': current + 1, 'saved_at': now(), 'as_of': as_of, 'reason': reason, 'card': card}
    path = inside(root, f'venues/{card["venue_id"]}/revisions/{current + 1:06d}.json')
    if path.exists():
        raise ValueError('Revision exists')
    write_json(path, state)
    return state


def view(root, state, as_of, max_age_days, time_basis, source_policy, publication_year=None):
    if time_basis not in ('latest_verified', 'publication_year', 'both'):
        raise ValueError('Explicit time_basis required')
    if source_policy != POLICY['source_policy']:
        raise ValueError('Official-only policy: third-party display is disabled')
    if type(max_age_days) is not int or max_age_days < 0:
        raise ValueError('max_age_days must be a nonnegative integer')
    if time_basis in ('publication_year', 'both') and (type(publication_year) is not int or not 1000 <= publication_year <= day(as_of).year):
        raise ValueError('Publication-year view needs a known publication year')
    card = state['card']
    errors = validate(card, as_of, root)
    if errors:
        raise ValueError('; '.join(errors))
    rendered = copy.deepcopy(card)
    latest = {system: max((r['release_year'] for r in card['ratings']
                          if r['system'] == system and r['status'] == 'verified'), default=None)
              for system in {r['system'] for r in card['ratings']}}
    for claim in ('identity', 'positioning'):
        ss = [s for s in card['sources'] if s['id'] in card[claim]['source_ids']]
        dates = [day(s['retrieved_on']) for s in ss] or [day(card['checked_on'])]
        rendered[claim]['cache_stale'] = (day(as_of) - min(dates)).days > max_age_days
    for rating in rendered['ratings']:
        ss = [s for s in card['sources'] if s['id'] in rating['source_ids']]
        dates = [day(rating['checked_on'])] + [day(s['retrieved_on']) for s in ss]
        rating['cache_stale'] = (day(as_of) - min(dates)).days > max_age_days
        rating['display_value'] = rating['value']
        rating['labels'] = []
        if time_basis in ('latest_verified', 'both'):
            year = latest[rating['system']]
            if rating['status'] == 'verified' and rating['release_year'] == year:
                rating['labels'].append('latest_verified_edition')
            elif rating['status'] != 'verified' and (year is None or rating['release_year'] is None or rating['release_year'] >= year):
                rating['labels'].append('official_rating_unresolved')
        if time_basis in ('publication_year', 'both') and rating['release_year'] == publication_year:
            rating['labels'].append('publication_year_edition')
    rendered['ratings'] = [r for r in rendered['ratings'] if r['labels']]
    # Export only evidence used by the chosen view; full official history stays in revisions.
    used = {sid for key in ('identity', 'positioning') for sid in rendered[key]['source_ids']}
    used.update(sid for r in rendered['ratings'] for sid in r['source_ids'])
    rendered['sources'] = [s for s in rendered['sources'] if s['id'] in used]
    missing = []
    if time_basis in ('publication_year', 'both'):
        missing = [system for system in sorted({r['system'] for r in card['ratings']})
                   if not any(r['system'] == system and r['release_year'] == publication_year
                              and r['display_value'] is not None for r in rendered['ratings'])]
    return {'venue_id': card['venue_id'], 'revision': state['revision'], 'as_of': as_of,
            'time_basis': time_basis, 'source_policy': source_policy, 'publication_year': publication_year,
            'max_age_days': max_age_days, 'card': rendered, 'missing_publication_year_systems': missing,
            'notice': '评价只描述发表平台，不代表单篇论文质量。最新指已保存官方证据中最新核实的发行版本，并非保证当前最新版；较新未核实版本单列，旧版不冒充当前评级。历史口径按发行年精确匹配。'}


def markdown(result):
    card = result['card']
    states = {'verified': '已核实', 'unverified': '未核实', 'third_party': '第三方信息，未官方核实',
              'conflicting': '来源冲突', 'not_applicable': '不适用'}
    kinds = {'journal': '期刊', 'conference': '会议', 'workshop': '研讨会', 'unknown': '类型待确认'}
    levels = {'jcr_category': 'JCR 学科', 'major': '大类', 'minor': '小类', 'ccf_area': 'CCF 领域', 'unknown': '层级未核实'}
    access = {'read': '已读页面', 'search_only': '仅检索线索', 'blocked': '本次访问未成功', 'user_supplied': '用户提供材料'}
    coverage = {'all_categories_checked': '已检查全部学科', 'selected_categories': '仅检查所列学科', 'unknown': '学科覆盖未知'}
    applies = {'journal': '期刊', 'full_regular_papers': '主会正式长文范围', 'unknown': '适用范围待确认'}
    lines = ['# ' + card['name'] + '｜发表平台认知卡', '',
             f'类型：{kinds[card["kind"]]}；查询日期：{card["checked_on"]}；展示日期：{result["as_of"]}。', '',
             '## 定位与研究领域', '', card['positioning']['text'] or '官方定位尚未核实。',
             '定位状态：' + states[card['positioning']['status']] + ('；信息需重新查询。' if card['positioning']['cache_stale'] else '。'),
             card['positioning']['review_note'], '',
             '## 评价记录', '', '| 体系 | 版本 / 指标年 | 学科及层级 | 评价 | 核实状态 | 时间口径 / 缓存 |',
             '|---|---|---|---|---|---|']
    def escape(value):
        return str(value if value is not None else '未核实').replace('|', '\\|').replace('\n', ' ')
    for rating in card['ratings']:
        labels = {'latest_verified_edition': '最新已核实版本', 'official_rating_unresolved': '官方评级待核实', 'publication_year_edition': '发表年发行版本'}
        value = rating['display_value'] or ('不适用' if rating['status'] == 'not_applicable' else POLICY['missing_rating_text'])
        values = [rating['system'], f'{rating["edition"] or "版本未核实"}（发行年：{rating["release_year"] or "未核实"}） / {rating["metric_year"] or "指标年未核实或不适用"}',
                  f'{rating["category"] or "学科未核实"} ({levels[rating["category_level"]]})', value,
                  states[rating['status']], '、'.join(labels[x] for x in rating['labels']) or '历史/非选定口径']
        if rating['cache_stale']:
            values[-1] += '；需重新查询'
        lines.append('| ' + ' | '.join(escape(v) for v in values) + ' |')
    lines += ['', '不把 JCR Q1 与中科院 1区互换；不同学科并列展示。', '']
    if result['missing_publication_year_systems']:
        lines += ['发表年口径尚无可展示评价：' + '、'.join(result['missing_publication_year_systems']) + '；不拿邻近年份代替。', '']
    for rating in card['ratings']:
        lines += [f'- {rating["system"]}：{rating["review_note"]} {coverage[rating["coverage"]]}；适用：{applies[rating["applies_to"]]}。时间说明：{rating["period_note"]}']
    lines += ['', '## 来源', '']
    for source in card['sources']:
        lines.append(f'- [{source["title"]}]({source["url"]})；{source["retrieved_on"]}；{access[source["access"]]}；定位：{source["locator"]}。{source["note"]}')
    lines += ['', result['notice'], '“已核实”表示 Agent 已对照来源检查；人工验收另行记录。', '']
    return '\n'.join(lines)


def link_paper(root, payload):
    path = inside(root, payload['record_path'])
    record = read_json(path)
    errors = validate_paper(record)
    if errors:
        raise ValueError('; '.join(errors))
    state = load(root, payload['venue_id'])
    card = state['card']
    errors = validate(card, state['as_of'], root)
    if errors:
        raise ValueError('; '.join(errors))
    assertion = next((a for a in record['assertions'] if a['field'] == 'venue' and a['subject_id'] == record['paper_id']), None)
    matched = bool(assertion and assertion['status'] == 'supported' and assertion['review_status'] in ('agent_checked', 'human_checked')
                   and card['identity']['status'] == 'verified'
                   and normal(assertion['value']) in {normal(n) for n in [card['name']] + card['aliases']})
    status = 'matched' if matched else 'unresolved'
    if not payload.get('note', '').strip():
        raise ValueError('Link requires a matching note')
    # Write association only; no venue/year backfill, grade transfer, or paper-file modification.
    data = {'paper_id': record['paper_id'], 'record_path': payload['record_path'], 'record_sha256': sha256(path),
            'venue_id': card['venue_id'], 'venue_revision': state['revision'], 'status': status,
            'venue_assertion_id': assertion['id'] if assertion else None, 'note': payload['note'],
            'paper_grade_assigned': False}
    import hashlib
    key = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    destination = inside(root, 'venue-links/' + key + '.json')
    if destination.exists() and read_json(destination) != data:
        raise ValueError('Link artifact was modified')
    if not destination.exists():
        write_json(destination, data)
    return data


def execute(root, action, payload):
    with workspace_lock(root) as root:
        if action == 'put':
            return put(root, payload['card'], payload['expected_revision'], payload['as_of'], payload['reason'])
        if action == 'link':
            return link_paper(root, payload)
        state = load(root, payload['venue_id'], payload.get('revision'))
        require_official_only(state['card'])
        if action == 'show':
            return state
        result = view(root, state, payload['as_of'], payload['max_age_days'], payload.get('time_basis', POLICY['time_basis']), payload.get('source_policy', POLICY['source_policy']), payload.get('publication_year'))
        if action == 'view':
            return result
        if action != 'export':
            raise ValueError('Unknown action')
        # View policy contributes to output identity: separate dates and choices cannot overwrite.
        import hashlib
        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(encoded.encode()).hexdigest()[:16]
        folder = inside(root, f'venues/{state["card"]["venue_id"]}/exports/r{state["revision"]:06d}-{digest}')
        for name, content in {'card.json': json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'card.md': markdown(result)}.items():
            target = folder / name
            if target.exists() and target.read_text(encoding='utf-8') != content:
                raise ValueError('Preserve manually modified export; create a new profile revision')
        for name, content in {'card.json': json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'card.md': markdown(result)}.items():
            target = folder / name
            if not target.exists():
                atomic_text(target, content)
        return {'json_path': str(folder / 'card.json'), 'markdown_path': str(folder / 'card.md')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('action', choices=['put', 'show', 'view', 'export', 'link'])
    parser.add_argument('--input', required=True, help='Workspace-relative JSON payload')
    args = parser.parse_args()
    try:
        print(json.dumps(execute(args.root, args.action, read_json(inside(args.root, args.input))), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
