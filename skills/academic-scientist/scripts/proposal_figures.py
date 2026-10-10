"""Editable draw.io primitives and a local SVG preview parsed from the same XML.

The limited renderer supports only shapes emitted here, and refuses other shapes.
It is not a native diagrams.net rendering or an importer of arbitrary user edits.
"""
import html
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from literature_output import preserved_text,digest

PALETTE={'borrowed':('#EAF0F6','#63758A'),'proposal':('#F1D7D4','#B44948'),'unknown':('#F4EEDC','#9A7B3F')}
PHASE={'input':'输入','training':'训练 / 微调','inference':'推理','evaluation':'评估 / 核查','output':'输出','shared':'流程协调'}
FONT='Microsoft YaHei'

def build_xml(plan,plan_digest):
    nodes=plan['graph']['nodes']; edges=plan['graph']['edges']
    if not 2<=len(nodes)<=8: raise ValueError('Overview supports 2–8 nodes; simplify overview before drawing')
    content_width=len(nodes)*220+(len(nodes)-1)*52
    width=max(1440,80+content_width); height=560
    mx=ET.Element('mxfile',host='app.diagrams.net',agent='academic-scientist',version='26.0.9')
    diagram=ET.SubElement(mx,'diagram',id='research-framework',name='研究方案（待验证）')
    model=ET.SubElement(diagram,'mxGraphModel',page='1',pageWidth=str(width),pageHeight=str(height),grid='1',gridSize='8')
    root=ET.SubElement(model,'root'); ET.SubElement(root,'mxCell',id='0');ET.SubElement(root,'mxCell',id='1',parent='0')
    def box(cid,value,x,y,w,h,fill='none',stroke='none',size=24,bold=False,extra=''):
        cell=ET.SubElement(root,'mxCell',id=cid,value=value,vertex='1',parent='1',
            style=f'rounded=1;arcSize=12;whiteSpace=wrap;html=0;fillColor={fill};strokeColor={stroke};strokeWidth=2;fontFamily={FONT};fontSize={size};fontStyle={1 if bold else 0};fontColor=#223342;align=center;verticalAlign=middle;'+extra)
        ET.SubElement(cell,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),attrib={'as':'geometry'})
        return cell
    box('heading',plan['graph']['title'],32,20,width-64,50,size=36,bold=True)
    box('disclaimer','拟议研究框架 · 尚未执行实验 · 不代表已验证的改进或新颖性',32,76,width-64,36,size=24)
    positions={}
    for i,n in enumerate(nodes):
        x=(width-content_width)/2+i*272;y=216;positions[n['id']]=(x,y,220,130)
        fill,stroke=PALETTE[n['kind']]
        cell=box('node-'+n['id'],n['label'],x,y,220,130,fill,stroke,size=28,bold=True)
        cell.set('semantic_id',n['id']);cell.set('statement_refs',json.dumps(n['statement_refs']));cell.set('semantic_kind',n['kind'])
        cell.set('phase',n['phase'])
    lanes={'top':0,'bottom':0}
    for i,e in enumerate(edges):
        a=positions[e['source']];b=positions[e['target']]
        consecutive=abs(a[0]-b[0])==272 and e['relation']=='data'
        if consecutive:
            right=b[0]>a[0];start=(a[0]+(a[2] if right else 0),281);end=(b[0]+(0 if right else b[2]),281)
            points=[start,end];exitx='1' if right else '0';entryx='0' if right else '1';exity=entryy='0.5'
        else:
            # Nonlocal data flows travel above; feedback/control below. Stable separate lanes.
            top=e['relation']=='data';side='top' if top else 'bottom';lane=lanes[side];lanes[side]+=1
            routey=164-lane*30 if top else 428+lane*30
            if routey<118 or routey>480: raise ValueError('Too many nonlocal lanes; simplify graph or author a custom layout')
            sy=a[1] if top else a[1]+a[3];ty=b[1] if top else b[1]+b[3]
            start=(a[0]+110,sy);end=(b[0]+110,ty);points=[start,(start[0],routey),(end[0],routey),end]
            exitx=entryx='0.5';exity=entryy='0' if top else '1'
        style=f'edgeStyle=none;rounded=0;html=0;endArrow=block;endFill=1;strokeWidth=2;fontFamily={FONT};fontSize=18;strokeColor=#263238;exitX={exitx};exitY={exity};entryX={entryx};entryY={entryy};'
        if e['relation']!='data':style+='dashed=1;dashPattern=7 5;strokeColor=#6B7280;'
        cell=ET.SubElement(root,'mxCell',id='edge-'+e['id'],value='',edge='1',parent='1',source='node-'+e['source'],target='node-'+e['target'],style=style)
        cell.set('semantic_id',e['id']);cell.set('statement_refs',json.dumps(e['statement_refs']));cell.set('relation',e['relation'])
        cell.set('preview_points',json.dumps(points))
        geo=ET.SubElement(cell,'mxGeometry',relative='1',attrib={'as':'geometry'})
        if len(points)>2:
            array=ET.SubElement(geo,'Array',attrib={'as':'points'})
            for px,py in points[1:-1]:ET.SubElement(array,'mxPoint',x=str(px),y=str(py))
            box('edge-label-'+e['id'],e['label'],min(start[0],end[0])+20,points[1][1]-38,abs(start[0]-end[0])-40,32,size=22)
        # Short adjacent labels omitted visually; explicit relation retained in XML and plan.
        cell.set('relation_label',e['label'])
    legend=[('borrowed','文献已有组件'),('proposal','拟议设计 / 待验证'),('unknown','条件未明确')]
    for i,(kind,label) in enumerate(legend):
        fill,stroke=PALETTE[kind];x=40+i*290
        box('legend-'+kind,label,x,506,260,40,fill,stroke,size=22)
    box('legend-lines','实线：数据流　　虚线：控制 / 反馈',920,506,width-960,40,size=22)
    model.set('proposal_digest',plan_digest)
    return ET.tostring(mx,encoding='unicode')+'\n'

def parse_style(style):
    return dict(p.split('=',1) for p in style.split(';') if '=' in p)

def render_svg(xml):
    tree=ET.fromstring(xml);model=tree.find('.//mxGraphModel')
    if model is None: raise ValueError('Missing graph model')
    width,height=float(model.get('pageWidth')),float(model.get('pageHeight'))
    cells=model.findall('root/mxCell');ids=[c.get('id') for c in cells]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate draw.io IDs')
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:g}" height="{height:g}" viewBox="0 0 {width:g} {height:g}">',
         '<rect width="100%" height="100%" fill="white"/>',
         '<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 Z" fill="#263238"/></marker><marker id="arrow-aux" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 Z" fill="#6B7280"/></marker></defs>']
    for c in cells:
        if c.get('edge')=='1':
            if c.get('source') not in ids or c.get('target') not in ids: raise ValueError('Missing edge endpoint')
            pts=json.loads(c.get('preview_points','[]'))
            if len(pts)<2:raise ValueError('Local preview requires explicit route geometry')
            style=parse_style(c.get('style',''));dash=' stroke-dasharray="7 5"' if style.get('dashed')=='1' else ''
            arrow='arrow-aux' if style.get('dashed')=='1' else 'arrow'
            svg.append(f'<polyline data-cell="{html.escape(c.get("id"))}" points="'+ ' '.join(f'{x},{y}' for x,y in pts)+f'" fill="none" stroke="{style.get("strokeColor","#263238")}" stroke-width="2"{dash} marker-end="url(#{arrow})"/>')
    for c in cells:
        if c.get('vertex')!='1':continue
        style=parse_style(c.get('style',''))
        if style.get('html')!='0' or 'image' in style or 'shape' in style:raise ValueError('Unsupported native shape; use draw.io export for arbitrary edits')
        g=c.find('mxGeometry');x,y,w,h=[float(g.get(k,'0')) for k in ['x','y','width','height']]
        if x<0 or y<0 or x+w>width or y+h>height:raise ValueError('Off-page vertex')
        size=float(style['fontSize']);lines=c.get('value','').split('\n')
        if len(lines)*size*1.3>h:raise ValueError('Text exceeds node height')
        for line in lines:
            estimated=sum(1 if ord(char)>255 else .6 for char in line)*size
            if estimated>w-12:raise ValueError('Label too long: '+c.get('id'))
        svg.append(f'<g data-cell="{html.escape(c.get("id"))}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{style.get("fillColor","none")}" stroke="{style.get("strokeColor","none")}" stroke-width="2"/>')
        for j,line in enumerate(lines):
            ty=y+h/2+(j-(len(lines)-1)/2)*size*1.3
            svg.append(f'<text x="{x+w/2}" y="{ty}" text-anchor="middle" dominant-baseline="central" font-family="{FONT},sans-serif" font-size="{size}" font-weight="{700 if style.get("fontStyle")=="1" else 400}" fill="#223342">{html.escape(line)}</text>')
        svg.append('</g>')
    svg.append('</svg>');return '\n'.join(svg)+'\n'

def write_figure(folder,plan,plan_digest):
    xml=build_xml(plan,plan_digest)
    # Parse and validate bounded primitives before creating any preview.
    svg=render_svg(xml)
    preserved_text(folder/'framework.drawio',xml)
    preserved_text(folder/'framework.svg',svg)
    metadata={'proposal_digest':plan_digest,'xml_digest':digest(xml),'svg_digest':digest(svg),
              'renderer':'local_limited_xml_renderer','native_drawio_render_verified':False,
              'nodes':{n['id']:n['statement_refs'] for n in plan['graph']['nodes']},
              'edges':{e['id']:e['statement_refs'] for e in plan['graph']['edges']}}
    preserved_text(folder/'figure-manifest.json',json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    return {'drawio_path':str(folder/'framework.drawio'),'svg_path':str(folder/'framework.svg'),'figure_manifest':str(folder/'figure-manifest.json')}
