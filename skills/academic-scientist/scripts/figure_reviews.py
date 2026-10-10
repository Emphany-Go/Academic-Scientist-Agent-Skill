"""Bind visual review evidence to exact figure bytes and current proposal, not just a filename."""
from pathlib import Path
from runtime import inside,read_json,sha256,now,check_schema
from jsonschema.exceptions import ValidationError
from literature_output import digest,preserved_text
import json

def inspect(root,state,folder,current):
    folder=inside(root,folder)
    try:
        manifest=read_json(folder/'figure-manifest.json')
        saved=read_json(folder/'proposal.json')
        unchanged=(manifest['proposal_digest']==digest(state['plan'])==digest(saved['plan'])
                   and manifest['xml_digest']==digest((folder/'framework.drawio').read_text(encoding='utf-8'))
                   and manifest['svg_digest']==digest((folder/'framework.svg').read_text(encoding='utf-8')))
        review_path=folder/'visual-review.json'
        reviewed=False
        if review_path.exists():
            review=read_json(review_path)
            check_schema('figure-review.schema.json',review)
            reviewed=review['proposal_digest']==digest(state['plan']) and all(sha256(inside(root,p))==h for p,h in review['file_hashes'].items())
        return {'figure_current':bool(current and unchanged),'visual_review_current':reviewed,
                'delivery_ready':bool(current and unchanged and reviewed),'native_drawio_render_verified':False,
                'error':None}
    except (OSError,KeyError,TypeError,ValueError,ValidationError) as exc:
        return {'figure_current':False,'visual_review_current':False,'delivery_ready':False,
                'native_drawio_render_verified':False,'error':str(exc)}

def record(root,state,folder,payload,current):
    if not inspect(root,state,folder,current)['figure_current']:raise ValueError('Current unmodified figure required')
    cycles=payload['cycles']
    if len(cycles)<3 or len({c['screenshot'] for c in cycles})!=len(cycles):raise ValueError('Three distinct visual review cycles required')
    for f in ['text_readable','arrows_clear','semantics_match','paper_scale_checked']:
        if payload.get(f) is not True:raise ValueError('All visual review checks required')
    if not payload.get('reviewer') or not payload.get('notes'):raise ValueError('Actual reviewer and notes required')
    export=inside(root,folder)
    paths=[export/'framework.drawio',export/'framework.svg',export/'proposal.json',export/'figure-manifest.json']
    for cycle in cycles:
        if not cycle.get('notes'):raise ValueError('Cycle notes required')
        image=inside(root,cycle['screenshot']);source=inside(root,cycle['source_drawio'])
        if image.suffix.lower()!='.png' or image.read_bytes()[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Actual PNG evidence required')
        paths.extend([image,source])
    if sha256(inside(root,cycles[-1]['source_drawio']))!=sha256(export/'framework.drawio'):raise ValueError('Last review must cover latest diagram')
    pdf=inside(root,payload['pdf']);paper=inside(root,payload['paper_scale_image'])
    if pdf.read_bytes()[:5]!=b'%PDF-' or paper.read_bytes()[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('PDF and paper-scale PNG required')
    paths.extend([pdf,paper])
    value={'proposal_digest':digest(state['plan']),'reviewer':payload['reviewer'],'notes':payload['notes'],'at':now(),
           'cycles':cycles,'renderer':'local_limited_xml_renderer','native_drawio_render_verified':False,
           'checks':{f:payload[f] for f in ['text_readable','arrows_clear','semantics_match','paper_scale_checked']},
           'file_hashes':{p.relative_to(Path(root).resolve()).as_posix():sha256(p) for p in paths}}
    check_schema('figure-review.schema.json',value)
    path=export/'visual-review.json'
    if path.exists():
        old=read_json(path)
        # Reuse only identical evidence/review text, retaining the original time.
        candidate=dict(value,at=old['at'])
        if old!=candidate:raise ValueError('Preserve earlier visual review; use a new export/version')
        return old
    preserved_text(path,json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    return value
