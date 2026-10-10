"""Semantic references and proposal/graph invariants, without generating scientific claims."""
from runtime import check_schema
from recommendation_sources import evidence_context

SECTIONS = {'problem':'研究问题','hypothesis':'待检验假设','approach':'方法框架','data_plan':'数据与适用条件',
            'baselines':'对照基线','evaluation':'评价指标与记录','ablations':'消融/控制变量',
            'minimal_experiment':'最小实验','failure_criteria':'失败与停止判据','limitations':'局限与未知'}

def check_goals(state, refs):
    card = state['upstream']['snapshot']['card']
    answers = {d['id']:d['answer'] for d in state['dialogue'] if d['answer']}
    for ref in refs:
        if ref['source'] == 'card':
            if not ref['ref'].isdigit() or not 1 <= int(ref['ref']) <= len(card['entries']):
                raise ValueError('Invalid research-card reference')
        elif ref['ref'] not in answers:
            raise ValueError('Reference needs an actual supplemental answer')

def validate_route(state):
    route = state['route']
    if route is None:
        return
    answer = next((d['answer'] for d in state['dialogue'] if d['id'] == route['answer_ref']), None)
    if not answer or route['quote'] not in answer['text']:
        raise ValueError('Route selection must quote an actual supplemental answer')
    if any(d['answer'] is None for d in state['dialogue']):
        raise ValueError('Unanswered question cannot count as agreement')

def validate_plan(state, plan):
    check_schema('research-proposal.schema.json',plan)
    validate_route(state)
    if not state['route'] or plan['route_id'] != state['route']['id']:
        raise ValueError('Confirm one route from actual answers before proposing a framework')
    statements = [s for group in plan['sections'].values() for s in group]
    ids = {s['id']:s for s in statements}
    if len(ids) != len(statements):
        raise ValueError('Duplicate statement ID')
    snapshot = state['upstream']['snapshot']
    supported = False
    for statement in statements:
        check_goals(state, statement['goal_refs'])
        contexts = []
        for ref in statement['fact_refs']:
            if ref['paper_id'] not in snapshot['papers']:
                raise ValueError('Unknown paper reference')
            contexts.extend(evidence_context(snapshot,ref['paper_id'],[{'assertion_id':ref['assertion_id'],'evidence_ids':ref['evidence_ids']}]))
        good = any(c['assertion']['status']=='supported' for c in contexts)
        supported |= good
        if statement['kind']=='borrowed' and not good:
            raise ValueError('Borrowed component requires supported paper evidence')
    if not supported:
        raise ValueError('Research framework needs at least one supported literature foundation')
    if any(s['kind']=='borrowed' for s in plan['sections']['hypothesis']):
        raise ValueError('New research hypothesis must remain a proposal or unknown')
    nodes = {n['id']:n for n in plan['graph']['nodes']}
    edges = plan['graph']['edges']
    if len(nodes)!=len(plan['graph']['nodes']) or len({e['id'] for e in edges})!=len(edges) or set(nodes)&{e['id'] for e in edges}:
        raise ValueError('Duplicate graph IDs')
    for node in nodes.values():
        if not set(node['statement_refs']) <= ids.keys():
            raise ValueError('Graph node lacks a proposal statement')
        if node['kind']=='borrowed' and any(ids[s]['kind']!='borrowed' for s in node['statement_refs']):
            raise ValueError('Proposed or unknown logic cannot be colored as established')
        if node['kind']!='unknown' and all(ids[s]['kind']=='unknown' for s in node['statement_refs']):
            raise ValueError('Unknown component must stay visibly unknown')
    adjacency = {n:set() for n in nodes}
    for edge in edges:
        if edge['source'] not in nodes or edge['target'] not in nodes or edge['source']==edge['target']:
            raise ValueError('Graph edge has missing endpoint or ambiguous self-loop')
        if not set(edge['statement_refs']) <= ids.keys():
            raise ValueError('Graph edge lacks a proposal statement')
        adjacency[edge['source']].add(edge['target']); adjacency[edge['target']].add(edge['source'])
    visited, todo = set(), [next(iter(nodes))]
    while todo:
        n=todo.pop()
        if n not in visited:
            visited.add(n); todo.extend(adjacency[n]-visited)
    if visited != set(nodes):
        raise ValueError('Disconnected framework nodes')
    if not any(n['phase']=='input' for n in nodes.values()) or not any(n['phase']=='output' for n in nodes.values()):
        raise ValueError('Framework needs explicit input and output')
    if 'figure_set' in plan:
        from figure_set_validation import validate
        validate(plan['figure_set'],ids)
        canonical={n['id']:n for n in plan['figure_set']['nodes']}
        for nid in nodes.keys() & canonical.keys():
            if any(nodes[nid][k]!=canonical[nid][k] for k in ('label','kind','phase','statement_refs')):
                raise ValueError('Legacy overview and figure_set disagree on a shared component')
