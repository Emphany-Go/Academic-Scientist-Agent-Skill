"""Local PDF registration, page text/previews, honest quality flags and resumable parsing."""
import argparse
import importlib.metadata
import os
import shutil
from pathlib import Path
from uuid import uuid4
from jsonschema.exceptions import ValidationError

from pypdf import PdfReader
import pypdfium2 as pdfium

from runtime import atomic_text, check_schema, inside, now, read_json, sha256, workspace_lock, write_json

PROFILE = 'page-text-preview-v1;pypdf=' + importlib.metadata.version('pypdf') + ';pdfium=' + importlib.metadata.version('pypdfium2')

def load(root):
    path = inside(root, 'library/manifest.json')
    if path.exists():
        state = read_json(path)
        check_schema('library-manifest.schema.json', state)
        return state
    return {'schema_version': '0.2.0', 'created_at': now(), 'updated_at': now(), 'documents': {}, 'expectations': [], 'events': []}

def save(root, state):
    state['updated_at'] = now()
    check_schema('library-manifest.schema.json', state)
    write_json(inside(root, 'library/manifest.json'), state)

def event(state, action, detail):
    state['events'].append({'time': now(), 'action': action, 'detail': detail})

def register(root, state, path, role='main', parent=None):
    path = Path(path).resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != '.pdf':
        raise ValueError('Expected an existing PDF file')
    if role not in ['main', 'supplement']:
        raise ValueError('role must be main or supplement')
    if role == 'supplement' and parent not in state['documents']:
        raise ValueError('Supplement requires a registered parent document')
    if role == 'main' and parent is not None:
        raise ValueError('Main document cannot have a parent')
    with path.open('rb') as stream:
        if b'%PDF-' not in stream.read(1024):
            raise ValueError('PDF header not found; no contents copied')
    digest = sha256(path)
    if digest == parent:
        raise ValueError('A PDF cannot be its own supplement')
    relative = f'library/documents/{digest}/source.pdf'
    target = inside(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_name(uuid4().hex + '.tmp')
        try:
            shutil.copyfile(path, temporary)
            if sha256(temporary) != digest:
                raise ValueError('Source changed during copy; retry from stable input')
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    elif sha256(target) != digest:
        raise ValueError('Registered source copy hash mismatch; refusing to overwrite')
    duplicate = digest in state['documents']
    document = state['documents'].setdefault(digest, {'id': digest, 'sha256': digest, 'source_path': relative,
        'original_paths': [], 'roles': [], 'status': 'registered', 'page_count': None, 'parse_runs': [], 'active_parse': None, 'error': None})
    if str(path) not in document['original_paths']:
        document['original_paths'].append(str(path))
    relation = {'role': role, 'parent_doc_id': parent}
    if relation not in document['roles']:
        document['roles'].append(relation)
    event(state, 'duplicate' if duplicate else 'register', digest)
    return {'doc_id': digest, 'duplicate': duplicate}

def reusable(root, page):
    if page['status'] == 'failed':
        return False
    for path_key, digest_key in [('text_path', 'text_sha256'), ('preview_path', 'preview_sha256')]:
        if not page[path_key] or not page[digest_key]:
            return False
        path = inside(root, page[path_key])
        if not path.exists() or sha256(path) != page[digest_key]:
            return False
    return True

def render(document, index, target):
    page = document[index]
    bitmap = None
    temporary = target.with_name(target.name + '.' + uuid4().hex + '.tmp')
    try:
        width, height = page.get_size()
        scale = min(1.6, 1600 / max(width, height))
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil()
        try:
            image.save(temporary, format='PNG')
        finally:
            image.close()
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
        if bitmap is not None:
            bitmap.close()
        page.close()

def parse_document(root, state, doc_id, max_pages=None, reparse=False):
    if doc_id not in state['documents']:
        raise ValueError('Unknown document')
    document = state['documents'][doc_id]
    source = inside(root, document['source_path'])
    if not source.exists() or sha256(source) != document['sha256']:
        document.update(status='failed', error='Source copy missing or hash mismatch; original and previous parses preserved')
        event(state, 'source_integrity_failure', doc_id); save(root, state)
        return {'doc_id': doc_id, 'status': 'failed', 'processed_pages': 0, 'reused_pages': 0}
    if document['active_parse'] and not reparse:
        result_path = inside(root, document['active_parse'])
        result = read_json(result_path)
        check_schema('document-parse.schema.json', result)
        if result['profile'] != PROFILE:
            raise ValueError('Parser profile changed; explicit reparse required and old attempt will be retained')
    else:
        attempt = len(document['parse_runs']) + 1
        relative = f'library/documents/{doc_id}/attempt-{attempt:04d}/parse.json'
        result_path = inside(root, relative)
        # Interrupted before manifest commit: keep any orphan attempt instead of overwriting it.
        while result_path.parent.exists():
            attempt += 1
            relative = f'library/documents/{doc_id}/attempt-{attempt:04d}/parse.json'
            result_path = inside(root, relative)
        result = {'schema_version': '0.2.0', 'doc_id': doc_id, 'profile': PROFILE, 'page_count': None,
                  'status': 'processing', 'pages': [], 'error': None, 'updated_at': now(),
                  'tables': 'not_structured', 'figures': 'page_preview_only'}
        write_json(result_path, result)
        document['parse_runs'].append(relative)
        document['active_parse'] = relative
    document.update(status='processing', error=None)
    save(root, state)
    reader = None
    rendering = None
    processed = 0
    reused = 0
    try:
        reader = PdfReader(source)
        if reader.is_encrypted:
            result.update(status='password_required', error='Encrypted PDF; password handling not implemented, provide an authorized readable copy')
        else:
            count = len(reader.pages)
            if count == 0:
                raise ValueError('PDF has no pages')
            document['page_count'] = result['page_count'] = count
            rendering = pdfium.PdfDocument(str(source))
            stored = {p['number']: p for p in result['pages']}
            for index in range(count):
                number = index + 1
                if number in stored and reusable(root, stored[number]):
                    reused += 1
                    continue
                if max_pages is not None and processed >= max_pages:
                    break
                page = {'number': number, 'status': 'failed', 'text_path': None, 'text_sha256': None,
                        'preview_path': None, 'preview_sha256': None, 'char_count': 0, 'issues': [],
                        'error': None, 'semantic_review': 'not_started'}
                errors = []
                try:
                    text = reader.pages[index].extract_text() or ''
                    text_path = result_path.parent / f'page-{number:04d}.txt'
                    atomic_text(text_path, text)
                    page.update(text_path=text_path.relative_to(root).as_posix(), text_sha256=sha256(text_path), char_count=len(text.strip()))
                    if len(text.strip()) < 40:
                        page['status'] = 'needs_visual_review'
                        page['issues'].append('Sparse/empty text layer: blank, image-only or extraction problem; OCR not performed')
                    elif '\ufffd' in text or '\x00' in text:
                        page['status'] = 'text_suspect'
                        page['issues'].append('Suspicious replacement/control characters; compare with page image')
                    else:
                        page['status'] = 'text_extracted'
                    page['issues'].append('Reading order, figures, tables and symbols require semantic/visual checking')
                except Exception as exc:
                    errors.append(f'text: {type(exc).__name__}: {exc}')
                try:
                    preview = result_path.parent / f'page-{number:04d}.png'
                    render(rendering, index, preview)
                    page.update(preview_path=preview.relative_to(root).as_posix(), preview_sha256=sha256(preview))
                except Exception as exc:
                    errors.append(f'preview: {type(exc).__name__}: {exc}')
                    page['status'] = 'failed'
                if errors:
                    page['error'] = '; '.join(errors)
                stored[number] = page
                result['pages'] = [stored[n] for n in sorted(stored)]
                result.update(status='processing', updated_at=now())
                check_schema('document-parse.schema.json', result)
                write_json(result_path, result)
                processed += 1
            if len(stored) != count:
                status = 'partial'
            elif any(p['status'] != 'text_extracted' for p in stored.values()):
                status = 'review_required'
            else:
                status = 'parsed_text'
            result.update(status=status, error=None)
    except Exception as exc:
        result.update(status='failed', error=f'{type(exc).__name__}: {exc}')
    finally:
        if rendering is not None:
            rendering.close()
        if reader is not None:
            reader.close()
        result['updated_at'] = now()
        check_schema('document-parse.schema.json', result)
        write_json(result_path, result)
        document.update(status=result['status'], error=result['error'])
        event(state, 'parse', f'{doc_id}: {result["status"]}; new={processed}; reused={reused}')
        save(root, state)
    return {'doc_id': doc_id, 'status': result['status'], 'processed_pages': processed, 'reused_pages': reused}

def execute(root, action, payload=None):
    payload = payload or {}
    with workspace_lock(root) as root:
        state = load(root)
        if action == 'show':
            return state
        if action == 'add':
            files = payload.get('paths')
            if not isinstance(files, list) or not files or any(not isinstance(p, str) or not p.strip() for p in files):
                raise ValueError('paths must be a nonempty list of PDF paths')
            results = []
            for path in files:
                try:
                    results.append(register(root, state, path, payload.get('role', 'main'), payload.get('parent_doc_id')))
                except (ValueError, OSError) as exc:
                    results.append({'path': str(path), 'error': str(exc)})
                    event(state, 'registration_failure', f'{path}: {exc}')
                save(root, state)
            return {'results': results}
        if action == 'parse':
            if type(payload.get('reparse', False)) is not bool:
                raise ValueError('reparse must be true or false, not a string')
            maximum = payload.get('max_pages')
            if maximum is not None and (type(maximum) is not int or maximum < 1):
                raise ValueError('max_pages must be a positive integer per document')
            ids = payload.get('doc_ids', list(state['documents']))
            if not isinstance(ids, list) or not ids or any(not isinstance(x, str) for x in ids):
                raise ValueError('doc_ids must be a nonempty list of registered IDs')
            results = []
            for doc_id in ids:
                try:
                    results.append(parse_document(root, state, doc_id, maximum, payload.get('reparse', False)))
                except (ValueError, OSError) as exc:
                    results.append({'doc_id': doc_id, 'error': str(exc)})
                    event(state, 'parse_failure', f'{doc_id}: {exc}'); save(root, state)
            return {'results': results}
        if action == 'expect':
            parent = payload.get('parent_doc_id')
            label = payload.get('label')
            if parent not in state['documents'] or not isinstance(label, str) or not label.strip():
                raise ValueError('Registered parent and explicit attachment label required')
            expectation = {'id': f'attachment{len(state["expectations"])+1}', 'parent_doc_id': parent, 'label': label, 'supplied_doc_id': None}
            state['expectations'].append(expectation)
            event(state, 'expect_attachment', expectation['id'])
            save(root, state)
            return expectation
        if action == 'link':
            expectation = next((x for x in state['expectations'] if x['id'] == payload.get('expectation_id')), None)
            doc_id = payload.get('doc_id')
            if not expectation or doc_id not in state['documents'] or doc_id == expectation['parent_doc_id']:
                raise ValueError('Valid expectation and distinct supplied document required')
            if expectation['supplied_doc_id'] not in [None, doc_id]:
                raise ValueError('Attachment already linked; do not overwrite it silently')
            expectation['supplied_doc_id'] = doc_id
            relation = {'role': 'supplement', 'parent_doc_id': expectation['parent_doc_id']}
            if relation not in state['documents'][doc_id]['roles']:
                state['documents'][doc_id]['roles'].append(relation)
            event(state, 'link_attachment', expectation['id']); save(root, state)
            return expectation
        raise ValueError('Unknown action')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('action', choices=['add', 'parse', 'expect', 'link', 'show'])
    parser.add_argument('--input', type=Path, help='UTF-8 JSON payload')
    args = parser.parse_args()
    try:
        result = execute(args.root, args.action, read_json(args.input) if args.input else {})
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if 'results' in result and any('error' in r or r.get('status') in ['failed', 'password_required'] for r in result['results']):
            return 1
        return 0
    except (ValueError, OSError, RuntimeError, ValidationError) as exc:
        parser.exit(1, str(exc) + '\n')

if __name__ == '__main__':
    raise SystemExit(main())
