"""Audit actual editable XML routes, including third-party/manual exports.

Uncompressed draw.io only. Fixed native ports/waypoints are authoritative;
an SVG preview or an auto-router style alone does not prove a safe path.
"""
import argparse,json,math,xml.etree.ElementTree as ET
from pathlib import Path

def styles(cell):
    return dict(x.split('=',1) for x in cell.get('style','').split(';') if '=' in x)

def rectangle(cell,cells,seen=None):
    seen=set() if seen is None else seen
    if cell.get('id') in seen:raise ValueError('Cyclic visual parent')
    seen=seen|{cell.get('id')};g=cell.find('mxGeometry')
    if g is None:raise ValueError('Missing geometry')
    if g.get('relative')=='1':raise ValueError('Relative vertex geometry requires native-engine inspection')
    r={k:float(g.get(k,'0')) for k in ('x','y','width','height')}
    if not all(math.isfinite(v) for v in r.values()):raise ValueError('Nonfinite geometry')
    parent=cell.get('parent')
    if parent not in (None,'0','1'):
        if parent not in cells:raise ValueError('Unknown visual parent')
        p=rectangle(cells[parent],cells,seen);r['x']+=p['x'];r['y']+=p['y']
    return r

def endpoint(edge,which,cells):
    prefix='exit' if which=='source' else 'entry';s=styles(edge)
    if not all(prefix+k in s for k in ('X','Y')):raise ValueError('Missing explicit '+which+' port')
    if s.get(prefix+'Perimeter')!='0':raise ValueError('Disable perimeter projection for fixed '+which+' port')
    x,y=(float(s[prefix+k]) for k in ('X','Y'))
    if not all(math.isfinite(v) and 0<=v<=1 for v in (x,y)) or not (x in (0,1) or y in (0,1)):
        raise ValueError('Port must lie on a boundary, never at box center')
    r=rectangle(cells[edge.get(which)],cells)
    return (r['x']+r['width']*x,r['y']+r['height']*y)

def native_points(edge,cells):
    if edge.get('source') not in cells or edge.get('target') not in cells:raise ValueError('Missing endpoint node')
    if edge.get('parent') not in (None,'1'):raise ValueError('Edges must use page coordinates')
    g=edge.find('mxGeometry')
    if g is None:raise ValueError('Missing edge geometry')
    ps=[endpoint(edge,'source',cells),*[(float(p.get('x')),float(p.get('y'))) for p in g.findall("Array[@as='points']/mxPoint")],endpoint(edge,'target',cells)]
    if not all(math.isfinite(x+y) for x,y in ps):raise ValueError('Nonfinite route')
    for which,p in [('sourcePoint',ps[0]),('targetPoint',ps[-1])]:
        explicit=g.find("mxPoint[@as='"+which+"']")
        if explicit is not None and any(abs(float(explicit.get(k))-v)>.001 for k,v in zip(('x','y'),p)):
            raise ValueError('Explicit point disagrees with connected port')
    cache=edge.get('preview_points')
    if cache is not None and json.loads(cache)!=[list(p) for p in ps]:raise ValueError('Preview cache disagrees with native route')
    return ps

def intersects(a,b,r,pad=0):
    x,y,w,h=r['x']-pad,r['y']-pad,r['width']+2*pad,r['height']+2*pad
    # Liang-Barsky open-interior intersection; includes diagonal legacy routes.
    lo,hi=0.,1.
    for start,delta,mn,mx in ((a[0],b[0]-a[0],x,x+w),(a[1],b[1]-a[1],y,y+h)):
        if abs(delta)<1e-9:
            if not mn<start<mx:return False
        else:
            t1,t2=sorted(((mn-start)/delta,(mx-start)/delta));lo=max(lo,t1);hi=min(hi,t2)
    return hi-lo>1e-8

def is_container(c):return styles(c).get('container')=='1'

def inspect_xml(source,clearance=8):
    if not math.isfinite(clearance) or clearance<0:raise ValueError('Clearance must be finite and nonnegative')
    try:tree=ET.fromstring(source)
    except ET.ParseError as exc:raise ValueError('Malformed draw.io XML: '+str(exc)) from exc
    errors=[];warnings=[];counts=[]
    def error(page,edge,rule,detail):errors.append(dict(page=page,edge=edge,rule=rule,detail=detail))
    diagrams=tree.findall('diagram')
    if not diagrams:raise ValueError('No uncompressed draw.io pages')
    for d in diagrams:
        page=d.get('id');model=d.find('mxGraphModel')
        if model is None:raise ValueError('Compressed pages need decoding before route review')
        entries=model.findall('root/mxCell');cells={c.get('id'):c for c in entries}
        if len(cells)!=len(entries):error(page,None,'duplicate_id','Duplicate cell IDs')
        rects={}
        for c in entries:
            if c.get('vertex')=='1' and not is_container(c):rects[c.get('id')]=rectangle(c,cells)
        routes={};edges={c.get('id'):c for c in entries if c.get('edge')=='1'}
        for eid,e in edges.items():
            try:
                if styles(e).get('noEdgeStyle')!='1':error(page,eid,'implicit_routing','Lock native path with noEdgeStyle=1; do not depend on auto routing')
                if styles(e).get('curved')=='1' or styles(e).get('rounded')=='1':error(page,eid,'unsupported_route','Use straight orthogonal segments for this audit')
                ps=native_points(e,cells);routes[eid]=ps
                for a,b in zip(ps,ps[1:]):
                    if a==b:error(page,eid,'zero_segment','Duplicate consecutive waypoint')
                    if abs(a[0]-b[0])>.001 and abs(a[1]-b[1])>.001:error(page,eid,'diagonal','Use explicit orthogonal corridor')
                    for nid,r in rects.items():
                        pad=0 if nid in (e.get('source'),e.get('target')) else clearance
                        if intersects(a,b,r,pad):error(page,eid,'obstacle_collision',nid)
                w=float(model.get('pageWidth'));h=float(model.get('pageHeight'))
                if any(not 0<=x<=w or not 0<=y<=h for x,y in ps):error(page,eid,'out_of_bounds','Route outside canvas')
            except (ValueError,KeyError,TypeError) as exc:error(page,eid,'unverifiable_route',str(exc))
        # Report line-line intersections separately; an unconnected crossing is not a junction.
        for i,(aid,aa) in enumerate(routes.items()):
            for bid,bb in list(routes.items())[i+1:]:
                same_end=bool({edges[aid].get('source'),edges[aid].get('target')}&{edges[bid].get('source'),edges[bid].get('target')})
                for a,b in zip(aa,aa[1:]):
                    for c,e in zip(bb,bb[1:]):
                        av=a[0]==b[0];bv=c[0]==e[0]
                        if av!=bv:
                            v1,v2,h1,h2=(a,b,c,e) if av else (c,e,a,b)
                            if min(v1[1],v2[1])<h1[1]<max(v1[1],v2[1]) and min(h1[0],h2[0])<v1[0]<max(h1[0],h2[0]):
                                warnings.append(dict(page=page,rule='edge_crossing',edges=[aid,bid],point=[v1[0],h1[1]]))
                        elif (a[0]==c[0] if av else a[1]==c[1]):
                            axis=1 if av else 0
                            overlap=min(max(a[axis],b[axis]),max(c[axis],e[axis]))-max(min(a[axis],b[axis]),min(c[axis],e[axis]))
                            if overlap>1e-6:warnings.append(dict(page=page,rule='shared_trunk' if same_end else 'unrelated_edge_overlap',edges=[aid,bid],length=overlap))
        counts.append(dict(page=page,nodes=len(rects),edges=len(edges),explicit_routes=len(routes)))
    # Deduplicate repeated segment findings.
    unique=lambda rows:list({json.dumps(r,sort_keys=True):r for r in rows}.values())
    errors=unique(errors);warnings=unique(warnings)
    return dict(passed=not errors,errors=errors,warnings=warnings,pages=counts,clearance=clearance,native_engine_verified=False)

def require_safe(source):
    report=inspect_xml(source,clearance=0)
    if not report['passed']:raise ValueError('Unsafe draw.io routes: '+json.dumps(report['errors'],ensure_ascii=False))
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('drawio',type=Path);p.add_argument('--clearance',type=float,default=8);p.add_argument('--output',type=Path)
    a=p.parse_args();report=inspect_xml(a.drawio.read_text(encoding='utf-8'),a.clearance);content=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(content,encoding='utf-8')
    print(content)
    if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main()
