"""Validate structure and cross references; NEVER certifies scientific truth."""
import argparse
import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:
    raise SystemExit('Missing jsonschema; ask before installing dependencies.')

BASE = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((BASE / 'schemas/paper-record.schema.json').read_text(encoding='utf-8'))
CATALOG = json.loads((BASE / 'schemas/field-catalog.json').read_text(encoding='utf-8'))

def validate(record):
    errors = [f'{"/".join(map(str, e.absolute_path))}: {e.message}' for e in Draft202012Validator(SCHEMA).iter_errors(record)]
    if errors:
        return errors
    for name in ['sources', 'entities', 'evidence', 'assertions']:
        ids = [x['id'] for x in record[name]]
        if len(ids) != len(set(ids)):
            errors.append(f'{name}: duplicate ID')
    sources = {x['id']: x for x in record['sources']}
    entities = {x['id']: x for x in record['entities']}
    evidence = {x['id']: x for x in record['evidence']}
    papers = [x['id'] for x in record['entities'] if x['kind'] == 'paper']
    if papers != [record['paper_id']]:
        errors.append('entities: exactly one paper entity matching paper_id required')
    for s in sources.values():
        if s['format'] == 'pdf' and s['page_count'] is None:
            errors.append(f'{s["id"]}: PDF page_count required')
        if s['page_count'] is not None and any(p > s['page_count'] for p in s['inspected_pages'] + s['unreadable_pages']):
            errors.append(f'{s["id"]}: coverage page out of range')
        if set(s['inspected_pages']) & set(s['unreadable_pages']):
            errors.append(f'{s["id"]}: same page marked inspected and unreadable')
    for e in evidence.values():
        s = sources.get(e['source_id'])
        if not s:
            errors.append(f'{e["id"]}: unknown source_id')
            continue
        if s['format'] == 'pdf':
            if s['page_count'] is None or e['page'] is None or e['page'] > s['page_count']:
                errors.append(f'{e["id"]}: invalid PDF page')
            elif e['page'] not in s['inspected_pages']:
                errors.append(f'{e["id"]}: evidence page not marked inspected')
        elif e['page'] is not None:
            errors.append(f'{e["id"]}: text source uses locator, not fabricated PDF page')
        expected = {'table': 'table_transcription', 'figure': 'visual_transcription', 'text': 'verbatim'}[e['kind']]
        if e['representation'] != expected:
            errors.append(f'{e["id"]}: incompatible evidence representation')
    pairs = set()
    for a in record['assertions']:
        key = (a['subject_id'], a['field'])
        if key in pairs:
            errors.append(f'{a["id"]}: duplicate subject/field; create separate experiment or atomic claim group')
        pairs.add(key)
        entity = entities.get(a['subject_id'])
        if not entity or entity['kind'] != CATALOG[a['field']]['scope']:
            errors.append(f'{a["id"]}: invalid field scope or unknown entity')
        if any(eid not in evidence for eid in a['evidence_ids']):
            errors.append(f'{a["id"]}: dangling evidence reference')
        if a['status'] == 'uncertain':
            allowed = a['field'] == 'model_origin' and a['value'] == ['undetermined']
            if a['value'] is not None and not allowed:
                errors.append(f'{a["id"]}: uncertain cannot contain a guessed value')
        if a['field'] == 'model_origin' and a['value'] and 'undetermined' in a['value']:
            if a['value'] != ['undetermined'] or a['status'] != 'uncertain':
                errors.append(f'{a["id"]}: undetermined must stand alone with uncertain status')
        if a['status'] == 'not_checked' and a['review_status'] != 'unreviewed':
            errors.append(f'{a["id"]}: unchecked field cannot be reviewed')
        if a['status'] == 'not_applicable' and not a['evidence_ids'] and not a['checked_scope'].strip():
            errors.append(f'{a["id"]}: not_applicable needs evidence or checked scope')
        if a['field'] == 'model_inventory' and a['status'] == 'supported':
            actual = {x['id'] for x in record['entities'] if x['kind'] == 'model'}
            if set(a['value']) != actual:
                errors.append(f'{a["id"]}: model inventory does not match model entities')
        if a['field'] == 'model_inventory' and a['status'] == 'not_applicable':
            if any(x['kind'] == 'model' for x in entities.values()):
                errors.append(f'{a["id"]}: nonapplicable inventory conflicts with model entities')
    for a in record['assertions']:
        if a['field'] == 'result' and a['status'] == 'supported':
            companions = {x['field']: x for x in record['assertions'] if x['subject_id'] == a['subject_id']}
            for field in ['metric', 'dataset', 'conditions']:
                other = companions.get(field)
                if not other or other['status'] not in ['supported', 'uncertain', 'not_reported']:
                    errors.append(f'{a["id"]}: result requires checked {field}, unknown must be explicit')
    if record['record_status'] == 'complete':
        for entity in entities.values():
            for field, definition in CATALOG.items():
                if definition['scope'] == entity['kind'] and (entity['id'], field) not in pairs:
                    errors.append(f'{entity["id"]}: complete record missing {field}')
        if any(a['status'] == 'not_checked' or a['review_status'] == 'unreviewed' for a in record['assertions']):
            errors.append('complete record has unchecked or unreviewed fields')
    return errors

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('records', nargs='+', type=Path)
    args = parser.parse_args()
    Draft202012Validator.check_schema(SCHEMA)
    failed = False
    for path in args.records:
        try:
            errors = validate(json.loads(path.read_text(encoding='utf-8')))
        except (OSError, ValueError) as exc:
            errors = [str(exc)]
        print(f'{"FAIL" if errors else "PASS"}: {path.name}')
        for error in errors:
            print('  ' + error)
        failed |= bool(errors)
    print('Structure only; source fidelity and scientific validity require source review.')
    return int(failed)

if __name__ == '__main__':
    sys.exit(main())
