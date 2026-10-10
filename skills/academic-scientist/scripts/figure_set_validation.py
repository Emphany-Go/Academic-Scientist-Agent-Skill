"""Shared semantics and explicit, editable layouts for three research views."""
import math
from runtime import check_schema

VIEWS = ('overview', 'module_detail', 'experiment')

def overlaps(a, b, pad=0):
    return (a['x'] < b['x']+b['width']+pad and b['x'] < a['x']+a['width']+pad
            and a['y'] < b['y']+b['height']+pad and b['y'] < a['y']+a['height']+pad)

def contains(a, b):
    return (a['x'] <= b['x'] and a['y'] <= b['y'] and
            a['x']+a['width'] >= b['x']+b['width'] and a['y']+a['height'] >= b['y']+b['height'])

def port(rect, side):
    x,y,w,h = (rect[k] for k in ('x','y','width','height'))
    return {'left':(x,y+h/2), 'right':(x+w,y+h/2), 'top':(x+w/2,y), 'bottom':(x+w/2,y+h)}[side]

def points(view, edge):
    r = view['routes'][edge['id']]
    return [port(view['positions'][edge['source']],r['source_port']),
            *[(p['x'],p['y']) for p in r['waypoints']],
            port(view['positions'][edge['target']],r['target_port'])]

def crosses(a,b,r):
    # Orthogonal segment intersects the OPEN interior of a node.
    if a[0]==b[0]:
        return r['x']<a[0]<r['x']+r['width'] and max(min(a[1],b[1]),r['y'])<min(max(a[1],b[1]),r['y']+r['height'])
    if a[1]==b[1]:
        return r['y']<a[1]<r['y']+r['height'] and max(min(a[0],b[0]),r['x'])<min(max(a[0],b[0]),r['x']+r['width'])
    raise ValueError('Use explicit orthogonal edge waypoints')

def validate(figure_set, statements):
    check_schema('figure-set.schema.json',figure_set)
    ns={n['id']:n for n in figure_set['nodes']}; es={e['id']:e for e in figure_set['edges']}
    if len(ns)!=len(figure_set['nodes']) or len(es)!=len(figure_set['edges']) or ns.keys()&es.keys():
        raise ValueError('Duplicate canonical figure IDs')
    for n in ns.values():
        refs=n['statement_refs']
        if not set(refs)<=statements.keys(): raise ValueError('Unknown figure statement')
        if n['kind']=='borrowed' and any(statements[s]['kind']!='borrowed' for s in refs):
            raise ValueError('Proposed logic cannot be displayed as borrowed')
        if n['kind']!='unknown' and all(statements[s]['kind']=='unknown' for s in refs):
            raise ValueError('Unknown figure component must remain unknown')
        seen={n['id']}; parent=n['parent_id']
        while parent is not None:
            if parent not in ns: raise ValueError('Missing semantic parent')
            if parent in seen: raise ValueError('Semantic parent cycle')
            seen.add(parent); parent=ns[parent]['parent_id']
    for e in es.values():
        if e['source'] not in ns or e['target'] not in ns or e['source']==e['target']: raise ValueError('Invalid canonical edge endpoint')
        if not set(e['statement_refs'])<=statements.keys(): raise ValueError('Unknown edge statement')
        if e['relation']=='reference' and not any(statements[s]['kind']=='borrowed' for s in e['statement_refs']):raise ValueError('Reference edge requires a literature statement')
    used_n=set(); used_e=set()
    for name,v in figure_set['views'].items():
        chosen=set(v['node_ids']); edges=set(v['edge_ids']); pos=v['positions']
        if not chosen<=ns.keys() or not edges<=es.keys(): raise ValueError('Unknown view ID')
        if set(pos)!=chosen or set(v['routes'])!=edges: raise ValueError('Layout keys must exactly match view selection')
        used_n |= chosen; used_e |= edges
        if v['focus_id'] is not None and v['focus_id'] not in ns: raise ValueError('Unknown detail focus')
        if name=='module_detail':
            if not v['focus_id'] or not any(ns[n]['parent_id']==v['focus_id'] for n in chosen):
                raise ValueError('Detail view must expand children of a named focus')
            if v['focus_id'] not in figure_set['views']['overview']['node_ids']:
                raise ValueError('Detail focus must appear in overview')
        canvas={'x':0,'y':0,**v['canvas']}
        for n,r in pos.items():
            if not all(math.isfinite(x) for x in r.values()) or not contains(canvas,r) or r['y']<110 or r['y']+r['height']>canvas['height']-85:
                raise ValueError('Node outside drawing area reserved for title and legend')
            if r['width']<160 or r['height']<80: raise ValueError('Node too small for readable labels')
            for other in chosen-{n}:
                if overlaps(r,pos[other]): raise ValueError('Overlapping nodes')
        grouped=set(); gids=set()
        for g in v['groups']:
            if g['id'] in gids or g['id'] in ns or g['id'] in es: raise ValueError('Duplicate group ID')
            gids.add(g['id'])
            if not set(g['node_ids'])<=chosen or grouped&set(g['node_ids']): raise ValueError('Invalid or multiply grouped node')
            grouped.update(g['node_ids'])
            if not contains(canvas,g['bounds']): raise ValueError('Group outside canvas')
            for n in g['node_ids']:
                if not contains(g['bounds'],pos[n]) or pos[n]['y']<g['bounds']['y']+40: raise ValueError('Node outside group or inside its heading')
            for h in v['groups']:
                if h['id']!=g['id'] and overlaps(g['bounds'],h['bounds']): raise ValueError('Overlapping groups')
        adj={n:set() for n in chosen}
        for eid in v['edge_ids']:
            e=es[eid]; r=v['routes'][eid]
            if e['source'] not in chosen or e['target'] not in chosen: raise ValueError('View edge endpoint absent')
            adj[e['source']].add(e['target']);adj[e['target']].add(e['source'])
            ps=points(v,e)
            for x,y in ps:
                if not math.isfinite(x+y) or not 0<=x<=canvas['width'] or not 100<=y<=canvas['height']-80: raise ValueError('Edge outside drawing area')
            for a,b in zip(ps,ps[1:]):
                for n,rect in pos.items():
                    if crosses(a,b,rect): raise ValueError('Edge crosses node: '+eid+'/'+n)
            if r['label_box']:
                box=r['label_box']
                if not contains(canvas,box) or any(overlaps(box,rect) for rect in pos.values()): raise ValueError('Edge label overlaps node or canvas')
                for other in v['edge_ids']:
                    other_box=v['routes'][other]['label_box']
                    if other!=eid and other_box and overlaps(box,other_box): raise ValueError('Overlapping edge labels')
                for other in v['edge_ids']:
                    ps_other=points(v,es[other])
                    if any(crosses(a,b,box) for a,b in zip(ps_other,ps_other[1:])):raise ValueError('Edge crosses label: '+other+'/'+eid)
        visited=set(); todo=[next(iter(chosen))]
        while todo:
            n=todo.pop()
            if n not in visited: visited.add(n);todo.extend(adj[n]-visited)
        if visited!=chosen: raise ValueError('Disconnected view')
    if used_n!=set(ns) or used_e!=set(es): raise ValueError('Unused canonical components')
    return True
