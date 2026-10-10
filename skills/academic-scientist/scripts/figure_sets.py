"""Three coherent views; draw.io XML is the editable source of SVG previews."""
import copy,json,hashlib,xml.etree.ElementTree as ET
from pathlib import Path
from html import escape
from literature_output import digest,preserved_text,md_escape
from runtime import sha256
from figure_set_validation import validate,VIEWS,points

COLORS={'borrowed':('#EAF0F6','#63758A'),'proposal':('#F1D7D4','#B44948'),'unknown':('#F4EEDC','#9A7B3F')}
KINDS={'borrowed':'文献做法','proposal':'拟议设计','unknown':'尚未明确'}
PORTS={'left':(0,.5),'right':(1,.5),'top':(.5,0),'bottom':(.5,1)}

def wrap(text,width,size):
    lines=[]
    for paragraph in text.split('\n'):
        line=''; units=0
        for ch in paragraph:
            u=1 if ord(ch)>255 else .56
            if units+u>(width-24)/size and line: lines.append(line);line='';units=0
            line+=ch;units+=u
        lines.append(line)
    return lines

def cell(root,id,value,rect,style,**attrs):
    c=ET.SubElement(root,'mxCell',{'id':id,'value':value,'style':style,'vertex':'1','parent':'1',**attrs})
    ET.SubElement(c,'mxGeometry',{k:str(v) for k,v in rect.items()}|{'as':'geometry'})
    return c

def diagram(fs,name):
    v=fs['views'][name]; ns={n['id']:n for n in fs['nodes']}; es={e['id']:e for e in fs['edges']}
    d=ET.Element('diagram',id=name,name=v['title'])
    model=ET.SubElement(d,'mxGraphModel',page='1',pageScale='1',pageWidth=str(v['canvas']['width']),pageHeight=str(v['canvas']['height']),grid='1',gridSize='8',math='0')
    root=ET.SubElement(model,'root');ET.SubElement(root,'mxCell',id='0');ET.SubElement(root,'mxCell',id='1',parent='0')
    base='html=0;whiteSpace=wrap;fontFamily=Microsoft YaHei;fontColor=#263238;'
    cell(root,'title',v['title'],{'x':32,'y':20,'width':v['canvas']['width']-64,'height':42},base+'text;align=left;fontStyle=1;fontSize=32;',role='title')
    cell(root,'purpose',v['purpose'],{'x':32,'y':66,'width':v['canvas']['width']-64,'height':36},base+'text;align=left;fontSize=21;',role='subtitle')
    parents={}
    for g in v['groups']:
        cell(root,'group-'+g['id'],g['label'],g['bounds'],base+'rounded=1;arcSize=6;fillColor=none;dashed=1;strokeColor=#B8C3CD;strokeWidth=1.5;verticalAlign=top;spacingTop=10;align=left;spacingLeft=16;fontSize=23;fontStyle=1;container=1;',role='group')
        for n in g['node_ids']: parents[n]=g
    # Edges precede nodes in both renderers; route points are also native draw.io waypoints.
    for eid in v['edge_ids']:
        e=es[eid]; r=v['routes'][eid]; a,b=PORTS[r['source_port']],PORTS[r['target_port']]
        style=f'noEdgeStyle=1;rounded=0;html=0;endArrow=block;endFill=1;strokeWidth=2;strokeColor=#52616B;exitX={a[0]};exitY={a[1]};entryX={b[0]};entryY={b[1]};exitPerimeter=0;entryPerimeter=0;'
        if e['relation']!='data':style+='dashed=1;dashPattern=6 4;'
        c=ET.SubElement(root,'mxCell',id='edge-'+eid,value='',style=style,edge='1',parent='1',source=e['source'],target=e['target'],semantic_id=eid,relation=e['relation'],statement_refs=','.join(e['statement_refs']),preview_points=json.dumps(points(v,e)))
        geom=ET.SubElement(c,'mxGeometry',relative='1',attrib={'as':'geometry'})
        ps=points(v,e)
        for key,p in [('sourcePoint',ps[0]),('targetPoint',ps[-1])]:ET.SubElement(geom,'mxPoint',x=str(p[0]),y=str(p[1]),attrib={'as':key})
        array=ET.SubElement(geom,'Array',attrib={'as':'points'})
        for p in r['waypoints']:ET.SubElement(array,'mxPoint',x=str(p['x']),y=str(p['y']))
        if r['label_box']:
            cell(root,'label-'+eid,e['label'],r['label_box'],base+'text;fillColor=#FFFFFF;strokeColor=none;fontSize=21;',role='edge-label',semantic_id=eid)
    for nid in v['node_ids']:
        n=ns[nid]; rect=copy.deepcopy(v['positions'][nid]); fill,stroke=COLORS[n['kind']]
        shape={'process':'rounded=1;arcSize=12;','decision':'shape=rhombus;','data':'shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=12;','artifact':'shape=note;size=14;'}[n['shape']]
        size=25
        if len(wrap(n['label'],rect['width']*(.7 if n['shape']=='decision' else 1),size))*size*1.25>rect['height']-18:
            raise ValueError('Shorten or enlarge node label: '+nid)
        attrs={'role':'node','semantic_id':nid,'semantic_parent':n['parent_id'] or '', 'kind':n['kind'],'statement_refs':','.join(n['statement_refs'])}
        if nid in parents:
            g=parents[nid];rect['x']-=g['bounds']['x'];rect['y']-=g['bounds']['y'];attrs['parent']='group-'+g['id']
        cell(root,nid,n['label'],rect,base+shape+f'fillColor={fill};strokeColor={stroke};strokeWidth=2;fontSize={size};',**attrs)
    y=v['canvas']['height']-65
    for i,(kind,(fill,stroke)) in enumerate(COLORS.items()):
        cell(root,'legend-'+kind,KINDS[kind],{'x':32+i*170,'y':y,'width':156,'height':40},base+f'rounded=1;fillColor={fill};strokeColor={stroke};fontSize=21;',role='legend')
    cell(root,'legend-flow','实线：数据 · 虚线：控制 / 反馈 / 更新 / 借鉴',{'x':545,'y':y,'width':v['canvas']['width']-565,'height':40},base+'text;fontSize=21;',role='legend')
    return d

def xml(diagrams):
    root=ET.Element('mxfile',host='app.diagrams.net',type='device',version='24.7.17')
    root.extend(diagrams)
    return '<?xml version="1.0" encoding="UTF-8"?>\n'+ET.tostring(root,encoding='unicode')+'\n'

def svg_from_xml(source):
    """Restricted local preview, NOT the draw.io engine. Resolve editable group parents."""
    from drawio_routes import native_points,require_safe
    require_safe(source)
    d=ET.fromstring(source).find('diagram'); model=d.find('mxGraphModel'); w=float(model.get('pageWidth'));h=float(model.get('pageHeight'))
    cells={c.get('id'):c for c in model.findall('root/mxCell')}
    def rect(c):
        g=c.find('mxGeometry');r={k:float(g.get(k,'0')) for k in ('x','y','width','height')}
        parent=c.get('parent')
        if parent not in (None,'0','1'):
            p=rect(cells[parent]);r['x']+=p['x'];r['y']+=p['y']
        return r
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:g}" height="{h:g}" viewBox="0 0 {w:g} {h:g}">',
         '<defs><marker id="arrow" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L9,3.5 L0,7 Z" fill="#52616B"/></marker></defs>',
         '<rect width="100%" height="100%" fill="white"/>']
    for c in cells.values():
        if c.get('edge')=='1':
            ps=native_points(c,cells); dashed=' stroke-dasharray="6 4"' if 'dashed=1' in c.get('style','') else ''
            out.append('<polyline points="'+' '.join(f'{x:g},{y:g}' for x,y in ps)+'" fill="none" stroke="#52616B" stroke-width="2" marker-end="url(#arrow)"'+dashed+'/>');continue
        if c.get('vertex')!='1':continue
        r=rect(c);x,y,bw,bh=(r[k] for k in ('x','y','width','height')); role=c.get('role');styles=dict(s.split('=',1) for s in c.get('style','').split(';') if '=' in s)
        fill=styles.get('fillColor','none');stroke=styles.get('strokeColor','none'); size=float(styles.get('fontSize','25'));shape=styles.get('shape','')
        attrs=f'fill="{fill}" stroke="{stroke}" stroke-width="{styles.get("strokeWidth","1.5")}"'+(' stroke-dasharray="6 4"' if role=='group' else '')
        if shape=='rhombus':out.append(f'<polygon points="{x+bw/2},{y} {x+bw},{y+bh/2} {x+bw/2},{y+bh} {x},{y+bh/2}" {attrs}/>')
        elif shape=='note':
            out.append(f'<path d="M{x},{y} H{x+bw-14} L{x+bw},{y+14} V{y+bh} H{x} Z M{x+bw-14},{y} V{y+14} H{x+bw}" {attrs}/>')
        elif shape=='cylinder3':
            out.append(f'<path d="M{x},{y+12} C{x},{y-4} {x+bw},{y-4} {x+bw},{y+12} V{y+bh-12} C{x+bw},{y+bh+4} {x},{y+bh+4} {x},{y+bh-12} Z M{x},{y+12} C{x},{y+28} {x+bw},{y+28} {x+bw},{y+12}" {attrs}/>')
        elif fill!='none' or stroke!='none':out.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="10" {attrs}/>')
        lines=wrap(c.get('value',''),bw*(.7 if shape=='rhombus' else 1),size)
        left=role in ('title','subtitle','group'); tx=x+(16 if role=='group' else 0) if left else x+bw/2
        ty=y+30 if role=='group' else y+bh/2-(len(lines)-1)*size*.625+size*.35
        if role=='group': lines=[c.get('value','')]
        out.append(f'<text x="{tx}" y="{ty}" text-anchor="{"start" if left else "middle"}" font-family="Microsoft YaHei,Arial,sans-serif" font-size="{size}" font-weight="{"600" if role in ("title","group") else "400"}" fill="#263238">')
        for i,line in enumerate(lines):out.append(f'<tspan x="{tx}" dy="{0 if i==0 else size*1.25}">{escape(line)}</tspan>')
        out.append('</text>')
    return '\n'.join(out+['</svg>'])+'\n'

def proposal_text(state):
    from proposal_validation import SECTIONS
    plan=state['plan'];lines=['# '+md_escape(plan['title']),'','待验证研究方案；未执行实验，未核查新颖性。','',
        '## 已确认路线','',md_escape(state['route']['label']),'']
    for d in state['dialogue']:
        lines+=['- 问：'+md_escape(d['question']),'- 用户原话：'+md_escape(d['answer']['text']),'']
    for key,title in SECTIONS.items():
        lines+=['## '+title,'']
        for s in plan['sections'][key]:
            lines += [f'**{s["id"]} · {KINDS[s["kind"]]}**','',md_escape(s['text']),'','核查/验证：'+md_escape(s['verification']),
                      '目标依据：'+', '.join(r['source']+':'+r['ref'] for r in s['goal_refs']),'']
            for ref in s['fact_refs']:
                evidence={e['id']:e for e in state['upstream']['snapshot']['papers'][ref['paper_id']]['record']['evidence']}
                loc='；'.join(f'PDF物理页 {evidence[e]["page"]}，{evidence[e]["locator"]} [{e}]' for e in ref['evidence_ids'])
                lines+=['- 文献依据：'+md_escape(ref['paper_id']+' / '+ref['assertion_id']+'；'+loc)]
            lines.append('')
    lines+=['## 假设与待确认条件','']
    for a in plan['assumptions']:lines+=['- '+md_escape(a['text']+' 风险：'+a['risk']+' 验证：'+a['verify'])]
    lines+=['','## 三图语义映射','', '| 组件 ID | 图中文字 | 状态 | 方案段落 |','|---|---|---|---|']
    for n in plan['figure_set']['nodes']:
        lines+=['| '+' | '.join([n['id'],md_escape(n['label']),KINDS[n['kind']],', '.join(n['statement_refs'])])+' |']
    lines+=['','布局与线条不能证明研究假设；原文证据与 Agent 拟议设计独立记录。','']
    return '\n'.join(lines)

def export(root,folder,state,current):
    if not current:raise ValueError('Current reviewed proposal required')
    plan=state['plan'];fs=plan.get('figure_set')
    if not fs:raise ValueError('Author all three views in figure_set before export-set')
    validate(fs,{s['id']:s for group in plan['sections'].values() for s in group})
    fingerprint=digest({p:sha256(Path(__file__).with_name(p)) for p in ('figure_sets.py','figure_set_validation.py','render_figure_set.mjs','drawio_routes.py')})[:10]
    target=folder/'exports'/f'r{state["revision"]:06d}-set-{fingerprint}'
    content={};diagrams=[];entries={}
    for name in VIEWS:
        d=diagram(fs,name);diagrams.append(d);source=xml([copy.deepcopy(d)])
        content[name+'.drawio']=source;content[name+'.svg']=svg_from_xml(source)
        entries[name]={'title':fs['views'][name]['title'],'drawio':name+'.drawio','svg':name+'.svg'}
    content['research-figures.drawio']=xml(diagrams)
    content['proposal.json']=json.dumps(state,ensure_ascii=False,indent=2)+'\n'
    content['proposal.md']=proposal_text(state)
    manifest={'schema_version':'0.7.1','proposal_digest':digest(plan),'revision':state['revision'],'views':entries,
              'combined_drawio':'research-figures.drawio','native_drawio_render_verified':False,
              'renderer':'restricted local XML-to-SVG; native draw.io validation remains separate',
              'files':{name:hashlib.sha256(value.encode('utf-8')).hexdigest() for name,value in content.items()}}
    content['figure-set-manifest.json']=json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'
    content['README.md']='# 三视图研究框架\n\n同一待验证方案的整体框架、关键模块与实验流程。尚未执行实验；未知条件保留。\n\n'+''.join(f'- [{entries[n]["title"]}]({n}.drawio)：[SVG]({n}.svg)\n' for n in VIEWS)+'\n[三页可编辑总文件](research-figures.drawio)。PNG、PDF 与审查记录由批量渲染/复核阶段补齐；没有整组审查通过前不报告最终交付。\n\n本地 SVG 预览不是 draw.io 原生渲染验证。组件/连线均引用 proposal.json 中的段落及其证据。\n'
    # Preflight ALL content before writing ANY file; manual edits are never replaced.
    for name,value in content.items():
        p=target/name
        if p.exists() and p.read_text(encoding='utf-8')!=value:raise ValueError('Refusing to overwrite edited figure set: '+name)
    for name,value in content.items():preserved_text(target/name,value)
    return {'folder':str(target),'combined_drawio':str(target/'research-figures.drawio'),'views':entries,'visual_review_required':True}
