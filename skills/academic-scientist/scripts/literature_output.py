"""Versioned literature collection, editable workbook baseline and reviewed merges.

No network or inference. XLSX authoring lives in workbook.mjs; reading uses OOXML.
"""
import argparse
import copy
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from runtime import inside, now, read_json, write_json, atomic_text, sha256, workspace_lock, check_schema
from validate_record import validate, CATALOG
import venue_cards as vc

BASE = Path(__file__).resolve().parents[1]
LABELS = read_json(BASE / 'assets/export-labels.json')
STATUS = {'supported': '原文支持', 'uncertain': '无法确认', 'not_reported': '未报告',
          'not_applicable': '不适用', 'not_checked': '未检查'}
IDENTITY = ['title', 'authors', 'publication_year', 'venue']


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def key(paper, subject, field):
    return digest([paper, subject, field])[:24]


def slots(record):
    present = {(a['subject_id'], a['field']): a for a in record['assertions']}
    result = {}
    for entity in record['entities']:
        for field, definition in CATALOG.items():
            if definition['scope'] == entity['kind']:
                a = present.get((entity['id'], field), {'id': entity['id'] + ':' + field,
                    'subject_id': entity['id'], 'field': field, 'status': 'not_checked', 'value': None,
                    'evidence_ids': [], 'review_status': 'unreviewed', 'note': '', 'checked_scope': ''})
                result[key(record['paper_id'], entity['id'], field)] = a
    return result


def shown(a):
    if a['status'] != 'supported' or a['review_status'] == 'unreviewed':
        return None
    value = a['value']
    return '\n'.join(value) if isinstance(value, list) else value


def typed(field, value):
    if value in (None, ''):
        return None
    definition = CATALOG[field]
    if definition['type'] == 'integer':
        if isinstance(value, bool) or not re.fullmatch(r'\d{4}', str(value)):
            raise ValueError('正式发表年份须为四位整数')
        return int(value)
    if not isinstance(value, str):
        raise ValueError('此字段须为文本；多项用单元格内换行分隔')
    if definition['type'] == 'array':
        return value.splitlines()
    return value


def checked(record):
    errors = validate(record)
    if errors:
        raise ValueError('; '.join(errors))
    if any(a['status'] != 'not_checked' and a['review_status'] == 'unreviewed' for a in record['assertions']):
        raise ValueError('Import reviewed stage-3 exports, not unreviewed candidates')


def load_state(folder):
    revisions = sorted((folder / 'revisions').glob('*.json'))
    if not revisions:
        return {'schema_version': '0.5.0', 'revision': 0, 'saved_at': now(), 'reason': 'Empty collection',
                'papers': {}, 'notes': {}, 'changes': [], 'imports': [], 'venues': []}
    value = read_json(revisions[-1])
    check_schema('literature-collection.schema.json', value)
    return value


def save(folder, state, expected, reason):
    previous = load_state(folder)
    if type(expected) is not int or previous['revision'] != expected:
        raise ValueError('Stale expected_revision')
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('Revision reason required')
    state.update(revision=expected + 1, saved_at=now(), reason=reason)
    check_schema('literature-collection.schema.json', state)
    target = folder / 'revisions' / f'{state["revision"]:06d}.json'
    if target.exists():
        raise ValueError('Revision exists')
    write_json(target, state)
    return state


def verify_sources(root, paper):
    for s in paper['record']['sources']:
        if sha256(inside(root, paper['source_files'][s['id']])) != s['sha256']:
            raise ValueError('Source file changed: ' + s['id'])


def three_way(base, local, incoming):
    if incoming == base or incoming == local:
        return local, False
    if local == base:
        return incoming, False
    return local, True


def invalidate_links(state, paper_ids):
    for entry in state['venues']:
        for link in entry['links']:
            if link['paper_id'] in paper_ids:
                link['status'] = 'unresolved'


def merge_records(base, local, incoming):
    """Conservative three-way record merge. Any conflict preserves the entire local record."""
    merged = copy.deepcopy(incoming)
    conflicts = []
    for section in ('sources', 'entities', 'evidence', 'assertions'):
        identity = (lambda x: (x['subject_id'], x['field'])) if section == 'assertions' else (lambda x: x['id'])
        maps = [{identity(x): x for x in r[section]} for r in (base, local, incoming)]
        rows = []
        for item in sorted(set().union(*maps), key=str):
            row, conflict = three_way(*(m.get(item) for m in maps))
            if conflict:
                conflicts.append(section + ':' + str(item))
            if row is not None:
                rows.append(row)
        merged[section] = rows
    for section in ('record_status', 'review_note'):
        merged[section], conflict = three_way(base[section], local[section], incoming[section])
        if conflict:
            conflicts.append(section)
    if not conflicts and validate(merged):
        conflicts.append('Merged record violates evidence/entity constraints')
    return (copy.deepcopy(local) if conflicts else merged), conflicts


def sync(root, folder, state, payload):
    updated, reused = [], []
    seen = set()
    for item in payload['records']:
        path = inside(root, item['record_path'])
        record = read_json(path)
        checked(record)
        pid = record['paper_id']
        if pid in seen:
            raise ValueError('Duplicate paper ID in batch')
        seen.add(pid)
        source_root = inside(root, item['source_root'])
        source_files = {s['id']: inside(source_root, s['path']).relative_to(root).as_posix() for s in record['sources']}
        incoming = {'record': record, 'upstream_record': record, 'record_path': item['record_path'],
                    'record_sha256': sha256(path), 'source_files': source_files}
        verify_sources(root, incoming)
        old = state['papers'].get(pid)
        if old:
            if old['upstream_record']['sources'][0]['sha256'] != record['sources'][0]['sha256']:
                raise ValueError('Paper ID reused for a different primary document')
            if old['record_sha256'] == incoming['record_sha256']:
                reused.append(pid)
                continue
            merged, conflicts = merge_records(old['upstream_record'], old['record'], record)
            if conflicts:
                raise ValueError('Upstream conflict for ' + pid + ': ' + ', '.join(conflicts)
                                 + '; collection unchanged; review both records before retrying')
            incoming['record'] = merged
            incoming['source_files'].update(old['source_files'])
            verify_sources(root, incoming)
        state['papers'][pid] = incoming
        state['notes'].setdefault(pid, '')
        updated.append(pid)
    # Import failure is transactional: nothing is persisted until the complete batch validates.
    if not updated:
        return {'revision': state['revision'], 'updated': [], 'reused': reused}
    invalidate_links(state, updated)
    save(folder, state, payload['expected_revision'], payload['reason'])
    return {'revision': state['revision'], 'updated': updated, 'reused': reused}


def make_sheet(name, header, rows, widths, editable=None):
    return {'name': name, 'header': header, 'rows': rows, 'widths': widths, 'editable': editable or []}


def build_bundle(state):
    overview, facts, evidence, external, changes = [], [], [], [], []
    cells = {}
    for pid, p in sorted(state['papers'].items()):
        record = p['record']
        aa = slots(record)
        row = [pid]
        for col, field in enumerate(IDENTITY, 1):
            k = key(pid, pid, field)
            a = aa[k]
            row.append(shown(a))
            cells[f'论文总览|{pid}|{col}'] = {'kind': 'fact', 'paper_id': pid, 'key': k, 'assertion': a, 'base': shown(a)}
        row.extend(['局部抽取' if record['record_status'] == 'partial' else '完整记录', state['notes'].get(pid, '')])
        cells[f'论文总览|{pid}|6'] = {'kind': 'note', 'paper_id': pid, 'base': row[6]}
        row.append('\n'.join(LABELS[f] + '：' + STATUS[aa[key(pid, pid, f)]['status']] for f in IDENTITY))
        row.append('\n'.join(LABELS[f] + '：' + ('、'.join(aa[key(pid, pid, f)]['evidence_ids']) or '无') for f in IDENTITY))
        overview.append(row)
        for k, a in aa.items():
            if a['subject_id'] == pid and a['field'] in IDENTITY:
                continue
            row = [k, pid, a['subject_id'], LABELS[a['field']], shown(a), STATUS[a['status']],
                   '、'.join(a['evidence_ids']), a['note']]
            facts.append(row)
            cells[f'论文事实|{k}|4'] = {'kind': 'fact', 'paper_id': pid, 'key': k, 'assertion': a, 'base': shown(a)}
        used = {eid for a in record['assertions'] for eid in a['evidence_ids']}
        for e in record['evidence']:
            if e['id'] in used:
                source = next(s for s in record['sources'] if s['id'] == e['source_id'])
                evidence.append([key(pid, e['id'], 'evidence'), pid, e['id'], Path(p['source_files'][source['id']]).name,
                                 e['page'], e['locator'], e['excerpt']])
    for v in state['venues']:
        card = v['view']['card']
        for r in card['ratings']:
            external.append([key(card['venue_id'], r['id'], 'rating'), card['name'], card['positioning']['text'],
                             r['system'], r['edition'], r['release_year'], r['category'],
                             r['display_value'] or ('不适用' if r['status'] == 'not_applicable' else vc.POLICY['missing_rating_text']),
                             v['view']['as_of'], '\n'.join(s['url'] for s in card['sources']),
                             '；'.join(x['paper_id'] + '：' + x['status'] for x in v['links'])])
    for c in state['changes']:
        changes.append([c['id'], c['paper_id'], c['kind'], c['field'], c['base'], c['proposed'], c['status'], c['review_note']])
    if not external:
        external = [['无平台资料', '', '尚未导入官方平台卡', '', '', None, '', '', '', '', '']]
    if not changes:
        changes = [['无修订记录', '', '', '', '', '', '', '尚未导入用户修改']]
    instructions = [
        ['记录版本', f'{state["revision"]} / {digest(state)[:16]}'],
        ['用途', '基于已核查的文献记录整理；空白不表示未报告，详见字段状态。'],
        ['修改', '论文总览的标题、作者、年份、期刊会议，以及论文事实的内容可直接修改。事实修改经原文核查后才合并。'],
        ['笔记', '个人笔记栏可自由填写；不作为论文事实或官方评价。'],
        ['证据', '修改后请在个人笔记中注明字段、PDF 物理页码、图表或原文依据，便于 Agent 核查。'],
        ['数组', '作者、模型清单、模型来源类别用单元格内换行分项；类别保留原有英文标签。'],
        ['清空', '清空事实单元格仅提出删除建议，不自动变成未报告；清空笔记表示删除笔记。'],
        ['排序', '可筛选和整行排序；保留第一列编号、表头和工作表名称，不删除行或增加事实行。'],
        ['保存', '将修改后的工作簿交给 Agent 导入；旧工作簿、Markdown 与所有修订历史保留。'],
        ['冲突', '你与 Agent 同时修改同一内容时暂停该项合并；新的无关内容仍可更新。'],
        ['范围', '现有五篇样本仅局部阅读；不要把空白补成模型推断答案。'],
        ['平台', '官方评级独立保存；候选关联 unresolved 不证明论文发表于该平台。'],
        ['来源', '证据表包含原文短摘录、物理页码与定位；完整上下文请回看所提供的论文。']]
    sheets = [
        make_sheet('论文总览', ['论文编号', '标题', '作者', '正式发表年份', '期刊或会议', '覆盖范围', '个人笔记', '身份字段状态', '身份字段证据'], overview, [14, 68, 25, 16, 36, 16, 50, 32, 32], [1, 2, 3, 4, 6]),
        make_sheet('论文事实', ['条目编号', '论文编号', '模型或实验编号', '字段', '内容', '事实状态', '证据编号', '原记录说明'], facts, [28, 14, 28, 24, 78, 18, 24, 45], [4]),
        make_sheet('原文证据', ['条目编号', '论文编号', '证据编号', '来源文件', 'PDF物理页', '章节或图表定位', '原文或图表转录'], evidence, [28, 14, 24, 20, 14, 55, 85]),
        make_sheet('平台认知', ['条目编号', '平台', '官方研究领域', '评价体系', '评价版本', '发行年份', '学科', '官方评价', '展示日期', '官方来源', '论文关联'], external, [28, 45, 65, 16, 20, 14, 22, 40, 16, 70, 30]),
        make_sheet('修订记录', ['修订编号', '论文编号', '修订类型', '字段', '导出原值', '修改建议', '处理状态', '核查说明'], changes, [28, 14, 18, 24, 50, 50, 20, 60]),
        make_sheet('使用说明', ['项目', '说明'], instructions, [18, 115])]
    return {'schema_version': '0.5.0', 'collection_revision': state['revision'], 'state_digest': digest(state),
            'sheets': sheets, 'cells': cells}


def md_escape(value):
    text = str(value if value is not None else '')
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '\\|').replace('\n', '<br>')


def paper_markdown(pid, paper, note):
    record = paper['record']
    aa = slots(record)
    title = shown(aa[key(pid, pid, 'title')]) or '标题尚未核实'
    lines = ['# ' + md_escape(title), '', f'论文编号：{pid}；覆盖：' + ('局部抽取' if record['record_status'] == 'partial' else '完整记录'), '',
             '## 论文事实', '', '| 对象 | 字段 | 内容 | 状态 | 证据 | 说明 |', '|---|---|---|---|---|---|']
    for a in aa.values():
        lines.append('| ' + ' | '.join(md_escape(x) for x in [a['subject_id'], LABELS[a['field']], shown(a), STATUS[a['status']], '、'.join(a['evidence_ids']), a['note']]) + ' |')
    lines += ['', '## 原文证据', '']
    for e in record['evidence']:
        lines += [f'- {md_escape(e["id"])}：物理页 {e["page"] or "不适用"}；{md_escape(e["locator"])}。{md_escape(e["excerpt"])}']
    lines += ['', '## 个人笔记', '', md_escape(note) or '暂无笔记。', '',
              '事实仅来自提供文献；本卡为当前记录的可读快照，修改本卡不会自动回填事实。', '']
    return '\n'.join(lines)


def preserved_text(path, content):
    if path.exists() and path.read_text(encoding='utf-8') != content:
        raise ValueError('Preserve manually modified output: ' + str(path))
    if not path.exists():
        atomic_text(path, content)


def prepare(folder, state):
    if not state['papers']:
        raise ValueError('No reviewed papers in collection')
    bundle = build_bundle(state)
    eid = digest(bundle)[:24]
    target = folder / 'exports' / eid
    text = json.dumps(bundle, ensure_ascii=False, indent=2) + '\n'
    preserved_text(target / 'baseline.json', text)
    index = ['# 文献阅读卡', '', '论文事实、外部评价与个人笔记分别保存。现有记录的局部覆盖不会因导出而变完整。', '']
    for pid, p in sorted(state['papers'].items()):
        filename = digest(pid)[:20] + '.md'
        preserved_text(target / 'papers' / filename, paper_markdown(pid, p, state['notes'].get(pid, '')))
        index.append(f'- [{md_escape(pid)}](papers/{filename})')
    preserved_text(target / 'INDEX.md', '\n'.join(index) + '\n')
    return {'export_id': eid, 'folder': str(target), 'baseline_path': str(target / 'baseline.json')}


def read_xlsx(path):
    """Read values only. Never evaluate formulas, macros or external workbook links."""
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist()) > 100_000_000:
            raise ValueError('Workbook exceeds 100 MB uncompressed limit')
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            shared = [''.join(t.text or '' for t in e.iter('{'+ns['s']+'}t')) for e in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        rels = {e.attrib['Id']: e.attrib['Target'] for e in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        result = {}
        for sheet in ET.fromstring(z.read('xl/workbook.xml')).find('s:sheets', ns):
            rid = sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
            target = rels[rid]
            target = target.lstrip('/') if target.startswith('/') else 'xl/' + target
            rows = []
            for row in ET.fromstring(z.read(target)).findall('s:sheetData/s:row', ns):
                values = []
                for cell in row:
                    if cell.find('s:f', ns) is not None:
                        raise ValueError('Formula found in data workbook; replace with literal values')
                    letters = re.match(r'[A-Z]+', cell.attrib['r']).group()
                    col = 0
                    for char in letters:
                        col = col * 26 + ord(char) - 64
                    while len(values) < col:
                        values.append(None)
                    kind = cell.attrib.get('t')
                    v = cell.find('s:v', ns)
                    value = v.text if v is not None else None
                    if kind == 's':
                        value = shared[int(value)]
                    elif kind == 'inlineStr':
                        value = ''.join(t.text or '' for t in cell.findall('.//s:t', ns))
                    elif kind == 'e':
                        raise ValueError('Excel error cell')
                    elif kind == 'b':
                        value = value == '1'
                    elif value is not None and kind not in ('str', 'd'):
                        n = float(value)
                        value = int(n) if n.is_integer() else n
                    values[col-1] = value
                if any(v not in (None, '') for v in values):
                    rows.append(values)
            result[sheet.attrib['name']] = rows
    return result


def compare_workbook(bundle, tables):
    if set(tables) != {s['name'] for s in bundle['sheets']}:
        raise ValueError('Workbook sheets changed; keep original names and all sheets')
    edits = []
    blank = lambda x: None if x == '' else x
    for sheet in bundle['sheets']:
        rows = tables[sheet['name']]
        if not rows or rows[0] != sheet['header']:
            raise ValueError('Workbook header changed: ' + sheet['name'])
        base = {str(r[0]): r for r in sheet['rows']}
        seen = set()
        for row in rows[1:]:
            rid = str(row[0])
            if rid not in base or rid in seen:
                raise ValueError('Unknown or duplicate row ID: ' + rid)
            seen.add(rid)
            if len(row) > len(sheet['header']):
                raise ValueError('Unexpected extra columns')
            row = row + [None] * (len(sheet['header']) - len(row))
            for col, (old, new) in enumerate(zip(base[rid], row)):
                if blank(old) == blank(new):
                    continue
                address = f'{sheet["name"]}|{rid}|{col}'
                if address not in bundle['cells']:
                    raise ValueError('Read-only content changed: ' + address)
                edits.append(dict(bundle['cells'][address], proposed=new))
        if seen != set(base):
            raise ValueError('Rows deleted; missing rows are not deletion instructions')
    return edits


def import_edits(root, folder, state, payload):
    eid = payload['export_id']
    if not re.fullmatch(r'[a-f0-9]{24}', eid):
        raise ValueError('Invalid export ID')
    bundle = read_json(folder / 'exports' / eid / 'baseline.json')
    if digest(bundle)[:24] != eid:
        raise ValueError('Baseline changed')
    path = inside(root, payload['workbook_path'])
    file_hash = sha256(path)
    import_id = digest([eid, file_hash])
    if import_id in state['imports']:
        return {'revision': state['revision'], 'reused': True, 'changes': []}
    edits = compare_workbook(bundle, read_xlsx(path))
    new_changes = []
    for i, edit in enumerate(edits):
        pid = edit['paper_id']
        if pid not in state['papers']:
            raise ValueError('Paper no longer exists')
        if edit['kind'] == 'note':
            current = state['notes'].get(pid, '')
            value = '' if edit['proposed'] is None else str(edit['proposed'])
            merged, conflict = three_way(edit['base'] or '', current, value)
            if not conflict:
                state['notes'][pid] = merged
            status = 'conflict' if conflict else 'accepted'
            field, slot = 'personal_note', None
            current_assertion = None
        else:
            field, slot = edit['assertion']['field'], edit['key']
            current_assertion = slots(state['papers'][pid]['record']).get(slot)
            current = shown(current_assertion) if current_assertion else None
            # Compare full assertion, not only displayed value: evidence/status may have changed.
            conflict = current_assertion != edit['assertion']
            status = 'conflict' if conflict else 'pending'
            value = edit['proposed']
        c = {'id': digest([import_id, i])[:24], 'paper_id': pid, 'kind': edit['kind'], 'key': slot,
             'field': field, 'base': edit['base'], 'current': current, 'proposed': value,
             'base_assertion': edit.get('assertion'), 'current_assertion': current_assertion,
             'status': status, 'import_id': import_id, 'export_id': eid,
             'review_note': '独立个人笔记已合并' if status == 'accepted' else '等待原文核查或冲突处理',
             'reviewer': None, 'reviewed_at': None, 'decision_ref': None}
        state['changes'].append(c)
        new_changes.append(c)
    state['imports'].append(import_id)
    # Preserve the exact returned file, including styling and user changes, before saving state.
    target = folder / 'returned-workbooks' / (file_hash + '.xlsx')
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and sha256(target) != file_hash:
        raise ValueError('Archived workbook changed')
    if not target.exists():
        shutil.copyfile(path, target)
    save(folder, state, payload['expected_revision'], payload['reason'])
    return {'revision': state['revision'], 'reused': False, 'changes': new_changes}


def review(root, folder, state, payload):
    change = next((c for c in state['changes'] if c['id'] == payload['change_id']), None)
    if not change or change['status'] not in ('pending', 'conflict'):
        raise ValueError('Change is missing or already resolved')
    for field in ('reviewer', 'review_note', 'decision_ref'):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise ValueError('Review requires ' + field)
    decision = payload['decision']
    if decision not in ('accept', 'reject'):
        raise ValueError('Decision must be accept or reject')
    if change['status'] == 'conflict' and not payload.get('conflict_resolution_ref', '').strip():
        raise ValueError('Conflict requires explicit user resolution reference')
    pid = change['paper_id']
    if decision == 'accept' and change['kind'] == 'note':
        if state['notes'].get(pid, '') != change['current']:
            raise ValueError('Note changed again; reimport or resolve against current version')
        state['notes'][pid] = '' if change['proposed'] is None else str(change['proposed'])
    elif decision == 'accept':
        paper = state['papers'][pid]
        verify_sources(root, paper)
        current = slots(paper['record']).get(change['key'])
        if current != change['current_assertion']:
            raise ValueError('Fact changed since import; reimport a fresh workbook')
        replacement = read_json(inside(root, payload['reviewed_record_path']))
        checked(replacement)
        if replacement['paper_id'] != pid:
            raise ValueError('Reviewed record belongs to another paper')
        after = slots(replacement).get(change['key'])
        if after is None or after['value'] != typed(change['field'], change['proposed']):
            raise ValueError('Reviewed value must match the submitted proposal')
        if after['status'] == 'not_checked' or after['review_status'] != 'agent_checked':
            raise ValueError('Reviewed correction requires agent_checked and a checked status')
        if after['status'] == 'supported' and not after['evidence_ids']:
            raise ValueError('Correction requires evidence')
        # Evidence and coverage must already exist in the current stage-3 record.
        # New evidence is added through stage-3 review + sync before a new workbook revision.
        before_slots = slots(paper['record'])
        after_slots = slots(replacement)
        if set(before_slots) != set(after_slots) or any(before_slots[k] != after_slots[k] for k in before_slots if k != change['key']):
            raise ValueError('One correction cannot change other facts or entities')
        for field in ('sources', 'entities', 'evidence', 'record_status'):
            if replacement[field] != paper['record'][field]:
                raise ValueError('New evidence/coverage must first pass stage-3 review and sync')
        if after['status'] == 'not_reported' and current['status'] != 'not_reported':
            raise ValueError('New not_reported claims require the complete stage-3 coverage audit')
        paper['record'] = replacement
        invalidate_links(state, [pid])
    change.update(status='accepted' if decision == 'accept' else 'rejected', review_note=payload['review_note'],
                  reviewer=payload['reviewer'], reviewed_at=now(), decision_ref=payload['decision_ref'])
    if payload.get('conflict_resolution_ref'):
        change['review_note'] += '\n冲突决定：' + payload['conflict_resolution_ref']
    save(folder, state, payload['expected_revision'], payload['reason'])
    return {'revision': state['revision'], 'change': change}


def execute(root, collection, action, payload):
    with workspace_lock(root) as root:
        folder = inside(root, collection)
        state = load_state(folder)
        if action == 'show':
            return state
        if action == 'prepare':
            return prepare(folder, state)
        if type(payload.get('expected_revision')) is not int or payload['expected_revision'] != state['revision']:
            raise ValueError('Stale expected_revision')
        if action == 'sync':
            return sync(root, folder, state, payload)
        if action == 'import-edits':
            return import_edits(root, folder, state, payload)
        if action == 'review':
            return review(root, folder, state, payload)
        if action == 'resolve-upstream':
            for required in ('conflict_resolution_ref', 'reviewer', 'reason'):
                if not isinstance(payload.get(required), str) or not payload[required].strip():
                    raise ValueError('Upstream conflict requires ' + required)
            if payload['choice'] not in ('keep_local', 'use_incoming'):
                raise ValueError('Choose keep_local or use_incoming after user confirmation')
            path = inside(root, payload['record_path'])
            record = read_json(path)
            checked(record)
            pid = record['paper_id']
            old = state['papers'][pid]
            if old['upstream_record']['sources'][0]['sha256'] != record['sources'][0]['sha256']:
                raise ValueError('Paper ID reused for a different primary document')
            _, conflicts = merge_records(old['upstream_record'], old['record'], record)
            if not conflicts:
                raise ValueError('No upstream conflict; use sync')
            source_root = inside(root, payload['source_root'])
            files = {s['id']: inside(source_root, s['path']).relative_to(root).as_posix() for s in record['sources']}
            incoming = {'record': record, 'source_files': files}
            verify_sources(root, incoming)
            chosen = old['record'] if payload['choice'] == 'keep_local' else record
            combined = dict(old['source_files'], **files)
            verify_sources(root, {'record': chosen, 'source_files': combined})
            state['papers'][pid] = {'record': chosen, 'upstream_record': record, 'record_path': payload['record_path'],
                                     'record_sha256': sha256(path), 'source_files': combined}
            state['changes'].append({'id': digest([state['revision'], pid, sha256(path)])[:24],
                'paper_id': pid, 'kind': 'upstream', 'key': None, 'field': 'whole_record',
                'base': digest(old['upstream_record']), 'current': digest(old['record']), 'proposed': digest(record),
                'base_assertion': None, 'current_assertion': None, 'status': 'accepted', 'import_id': '', 'export_id': '',
                'review_note': payload['choice'] + '；' + payload['reason'], 'reviewer': payload['reviewer'],
                'reviewed_at': now(), 'decision_ref': payload['conflict_resolution_ref']})
            invalidate_links(state, [pid])
            save(folder, state, payload['expected_revision'], payload['reason'])
            return {'revision': state['revision'], 'choice': payload['choice'], 'conflicts': conflicts}
        if action == 'venues':
            entries = []
            for item in payload['entries']:
                venue_root = inside(root, item['workspace'])
                view = vc.execute(venue_root, 'view', item['view_request'])
                links = []
                for relative in item['link_paths']:
                    link = read_json(inside(venue_root, relative))
                    if link['venue_id'] != view['venue_id'] or link['venue_revision'] != view['revision']:
                        raise ValueError('Venue link version mismatch')
                    p = state['papers'][link['paper_id']]
                    # A prior match becomes unresolved after edits to the underlying facts.
                    match = link['status'] == 'matched' and p['record_sha256'] == link['record_sha256'] and p['record'] == p['upstream_record']
                    links.append({'paper_id': link['paper_id'], 'status': 'matched' if match else 'unresolved'})
                entries.append({'view': view, 'links': links})
            if state['venues'] == entries:
                return {'revision': state['revision'], 'reused': True}
            state['venues'] = entries
            save(folder, state, payload['expected_revision'], payload['reason'])
            return {'revision': state['revision']}
        raise ValueError('Unknown action')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--collection', required=True)
    parser.add_argument('action', choices=['show', 'sync', 'prepare', 'venues', 'import-edits', 'review', 'resolve-upstream'])
    parser.add_argument('--input', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(execute(args.root, args.collection, args.action, read_json(inside(args.root, args.input))), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
