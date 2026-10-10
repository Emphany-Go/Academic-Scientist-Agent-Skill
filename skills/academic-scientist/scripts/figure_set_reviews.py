"""Whole-set freshness and rendered evidence, independent of scientific review."""
import json
from pathlib import Path
from runtime import inside,read_json,sha256,now,check_schema
from jsonschema import ValidationError
from literature_output import digest,preserved_text
from figure_set_validation import VIEWS

CHECKS=('semantics','readability','connectors','paper_scale')

def sources(root,state,folder,current):
    if not current:raise ValueError('Proposal or upstream is stale')
    path=inside(root,folder);m=read_json(path/'figure-set-manifest.json')
    if m['proposal_digest']!=digest(state['plan']) or m['revision']!=state['revision']:raise ValueError('Figure set belongs to another proposal')
    if set(m['views'])!=set(VIEWS):raise ValueError('All three views required')
    for name,value in m['files'].items():
        p=inside(path,name)
        if sha256(p)!=value:raise ValueError('Edited or stale figure source: '+name)
    from drawio_routes import require_safe
    for name in VIEWS:require_safe((path/(name+'.drawio')).read_text(encoding='utf-8'))
    require_safe((path/'research-figures.drawio').read_text(encoding='utf-8'))
    return path,m

def inspect(root,state,folder,current):
    try:
        path,m=sources(root,state,folder,current)
        review=read_json(path/'figure-set-review.json')
        check_schema('figure-set-review.schema.json',review)
        if review['proposal_digest']!=digest(state['plan']) or review['manifest_sha256']!=sha256(path/'figure-set-manifest.json'):raise ValueError('Stale visual review')
        if set(review['views'])!=set(VIEWS):raise ValueError('Partial visual review')
        for file,value in review['files'].items():
            if sha256(inside(root,file))!=value:raise ValueError('Changed visual evidence: '+file)
        return {'delivery_ready':True,'views':list(VIEWS),'native_drawio_render_verified':False,'reviewer':review['reviewer']}
    except (ValueError,OSError,KeyError,TypeError,ValidationError) as exc:
        return {'delivery_ready':False,'reason':str(exc),'native_drawio_render_verified':False}

def record(root,state,payload,current):
    path,m=sources(root,state,payload['export_folder'],current)
    if not isinstance(payload.get('reviewer'),str) or not payload['reviewer'].strip():raise ValueError('Reviewer required')
    if set(payload['views'])!=set(VIEWS):raise ValueError('Review all three views together')
    files={};views={};seen=set()
    def bind(rel,sig=None):
        p=inside(root,rel)
        if sig and not p.read_bytes().startswith(sig):raise ValueError('Invalid visual artifact signature')
        if sig and sig.startswith(b'\x89PNG'):
            from PIL import Image
            with Image.open(p) as image:image.verify()
        files[rel]=sha256(p);return p
    for name,req in payload['views'].items():
        if set(req['checks'])!=set(CHECKS) or any(req['checks'][c] is not True for c in CHECKS):raise ValueError('All visual checks must pass')
        if len(req['cycles'])!=3:raise ValueError('Three actual screenshot reviews required per view')
        for index,cycle in enumerate(req['cycles']):
            if not cycle.get('note','').strip() or cycle['screenshot'] in seen:raise ValueError('Distinct screenshot and review note required')
            seen.add(cycle['screenshot']);png=bind(cycle['screenshot'],b'\x89PNG\r\n\x1a\n'); render=read_json(bind(cycle['render_record']))
            source=bind(cycle['source_drawio']);svg=bind(cycle['source_svg'])
            import xml.etree.ElementTree as ET
            if ET.parse(source).find('diagram').get('id')!=name or render['view']!=name or render['source_drawio_sha256']!=sha256(source) or render['source_svg_sha256']!=sha256(svg):
                raise ValueError('Screenshot must bind the correct view and source')
            if index==2 and (sha256(source)!=m['files'][name+'.drawio'] or sha256(svg)!=m['files'][name+'.svg']):raise ValueError('Last review must use the current source')
            if render['screenshot_sha256']!=sha256(png):raise ValueError('Screenshot hash differs from render record')
        bind(req['png'],b'\x89PNG\r\n\x1a\n');bind(req['paper_scale'],b'\x89PNG\r\n\x1a\n');bind(req['pdf'],b'%PDF-')
        final=read_json(inside(root,req['cycles'][-1]['render_record']))
        if files[req['png']]!=final['screenshot_sha256'] or files[req['pdf']]!=final['pdf_sha256'] or files[req['paper_scale']]!=final['paper_scale_sha256']:
            raise ValueError('Final exports differ from latest rendered evidence')
        views[name]=req
    merged=bind(payload['combined_pdf'],b'%PDF-')
    from pypdf import PdfReader
    merged_pages=PdfReader(merged).pages
    if len(merged_pages)!=3:raise ValueError('Combined PDF must contain exactly three pages')
    for i,name in enumerate(VIEWS):
        pages=PdfReader(inside(root,views[name]['pdf'])).pages
        if len(pages)!=1:raise ValueError('Each view PDF must contain one page')
        a,b=pages[0],merged_pages[i]
        def content(page):
            c=page.get_contents();return c.get_data() if c else b''
        if content(a)!=content(b) or list(a.mediabox)!=list(b.mediabox) or a.extract_text()!=b.extract_text():raise ValueError('Combined PDF differs from reviewed view pages')
    review={'schema_version':'0.7.1','proposal_digest':digest(state['plan']),'manifest_sha256':sha256(path/'figure-set-manifest.json'),
            'reviewer':payload['reviewer'],'at':now(),'views':views,'files':files,'combined_pdf':payload['combined_pdf'],
            'native_drawio_render_verified':False}
    check_schema('figure-set-review.schema.json',review)
    preserved_text(path/'figure-set-review.json',json.dumps(review,ensure_ascii=False,indent=2)+'\n')
    return inspect(root,state,payload['export_folder'],current)
