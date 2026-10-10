"""Clarify one research route, then version an evidence-linked unexecuted proposal."""
import argparse
import copy
import json
from pathlib import Path
from jsonschema.exceptions import ValidationError
from runtime import inside,read_json,write_json,check_schema,now,workspace_lock
from literature_output import digest,preserved_text,md_escape
import recommendations as rec
from proposal_validation import validate_route,validate_plan,SECTIONS

def upstream(root,run):
    state=rec.load(inside(root,run))
    if not rec.status(root,state)['recommendation_ready']:
        raise ValueError('Current reviewed stage-6 learning recommendations required')
    for entry in state['entries'].values():
        rec.validate_entry(state,entry)
    return state

def load(folder,revision=None):
    files=sorted((folder/'revisions').glob('*.json'))
    if not files: raise ValueError('Proposal run does not exist')
    if revision is not None and (type(revision)!=int or revision<1): raise ValueError('Invalid revision')
    state=read_json(files[-1] if revision is None else folder/'revisions'/f'{revision:06d}.json')
    check_schema('proposal-run.schema.json',state)
    return state

def save(folder,state,reason):
    if not isinstance(reason,str) or not reason.strip(): raise ValueError('Revision reason required')
    state.update(revision=state['revision']+1,reason=reason,saved_at=now())
    check_schema('proposal-run.schema.json',state)
    validate_route(state)
    if state['plan']: validate_plan(state,state['plan'])
    path=folder/'revisions'/f'{state["revision"]:06d}.json'
    if path.exists(): raise ValueError('Refusing to overwrite revision')
    write_json(path,state)
    return state

def status(root,state):
    error=None
    try: current=digest(upstream(root,state['recommendation_run']))==state['upstream_digest']
    except (ValueError,OSError,KeyError,TypeError,ValidationError) as exc: current=False; error=str(exc)
    review=state['review']
    accepted=bool(state['plan'] and review and review['decision']=='accepted' and review['digest']==digest(state['plan']))
    pending=[d['id'] for d in state['dialogue'] if d['answer'] is None]
    return {'revision':state['revision'],'current':current,'input_error':error,'pending_questions':pending,
            'route_confirmed':bool(state['route']),'plan_reviewed':accepted,'export_ready':current and accepted and not pending,
            'execution_status':'not_run','novelty_status':'not_assessed'}

def export_plan(root,folder,state):
    if not status(root,state)['export_ready']: raise ValueError('Review current proposal before export')
    if 'figure_set' in state['plan']:
        from figure_sets import export
        return export(root,folder,state,True)
    from proposal_figures import write_figure
    plan=state['plan']
    # Renderer fingerprint creates new output on layout changes and never replaces manual edits.
    from runtime import sha256
    renderer=sha256(Path(__file__).with_name('proposal_figures.py'))[:10]
    target=folder/'exports'/f'r{state["revision"]:06d}-{renderer}'
    lines=['# '+md_escape(plan['title']),'','这是一条用户已明确选择路线下的待验证研究方案；尚未执行实验，未完成外部新颖性检索，不声称首次提出或预期性能提升。',
           f'方案版本 {state["revision"]}；依赖阅读分析版本 {state["upstream"]["revision"]}。复用前检查 status。','',
           '## 补充澄清与路线','']
    for d in state['dialogue']:
        lines += ['- 问：'+md_escape(d['question']),'- 答：'+md_escape(d['answer']['text'] if d['answer'] else '尚未回答')]
    lines += ['', '确认路线：'+md_escape(state['route']['label']),'用户依据：'+md_escape(state['route']['quote']),'']
    for section,label in SECTIONS.items():
        lines += ['## '+label,'']
        for s in plan['sections'][section]:
            kind={'borrowed':'文献已有做法','proposal':'本方案拟采用/待验证','unknown':'尚未明确'}[s['kind']]
            lines += [f'**{s["id"]} · {kind}**','',md_escape(s['text']),'','核查/验证：'+md_escape(s['verification']),
                      '目标依据：'+', '.join(g['source']+':'+g['ref'] for g in s['goal_refs']),'']
            for ref in s['fact_refs']:
                record=state['upstream']['snapshot']['papers'][ref['paper_id']]['record']
                evidence={e['id']:e for e in record['evidence']}
                loc='；'.join(f'PDF 物理页 {evidence[e]["page"]}，{evidence[e]["locator"]} [{e}]' for e in ref['evidence_ids'])
                lines += ['- 文献依据：'+md_escape(ref['paper_id']+' / '+ref['assertion_id']+'；'+(loc or '该项无可定位证据，保持原未知状态'))]
            lines.append('')
    lines += ['## 假设与待确认条件','']
    for a in plan['assumptions']:
        lines += [f'- {md_escape(a["text"])} 风险：{md_escape(a["risk"])} 验证：{md_escape(a["verify"])}']
    lines += ['','## 图文对应','', '| 图节点 | 状态 | 方案段落 |','|---|---|---|']
    lines += ['| '+ ' | '.join([md_escape(n['label']),n['kind'],', '.join(n['statement_refs'])])+' |' for n in plan['graph']['nodes']]
    lines += ['','图中的实线表示数据流，虚线表示控制/反馈/更新；配色区分文献组件、拟议设计和未知项。图不是实验成果。','']
    preserved_text(target/'proposal.json',json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    preserved_text(target/'proposal.md','\n'.join(lines)+'\n')
    figure=write_figure(target,plan,digest(plan))
    return {'folder':str(target),'markdown_path':str(target/'proposal.md'),'json_path':str(target/'proposal.json'),**figure,
            'visual_review_required':True}

def execute(root,run,action,payload):
    with workspace_lock(root) as root:
        folder=inside(root,run)
        if action=='start':
            if any((folder/'revisions').glob('*.json')): raise ValueError('Run exists; resume instead')
            source=upstream(root,payload['recommendation_run'])
            state={'schema_version':'0.7.0','source_kind':'agent_proposal','revision':0,'saved_at':now(),'reason':payload['reason'],
                   'purpose':source['purpose'],'recommendation_run':payload['recommendation_run'],'upstream':source,'upstream_digest':digest(source),
                   'dialogue':[],'route':None,'plan':None,'review':None}
            return save(folder,state,payload['reason'])
        state=load(folder,payload.get('revision') if action=='show' else None)
        if action=='show': return {'run':state,'status':status(root,state)}
        if action=='status': return status(root,state)
        if action=='export': return export_plan(root,folder,state)
        if action=='export-set':
            import figure_sets
            return figure_sets.export(root,folder,state,status(root,state)['export_ready'])
        if action=='figure-set-status':
            import figure_set_reviews
            return figure_set_reviews.inspect(root,state,payload['export_folder'],status(root,state)['export_ready'])
        if action=='figure-status':
            import figure_reviews
            return figure_reviews.inspect(root,state,payload['export_folder'],status(root,state)['export_ready'])
        if type(payload.get('expected_revision'))!=int or payload['expected_revision']!=state['revision']: raise ValueError('Stale expected_revision')
        if action=='refresh':
            source=upstream(root,state['recommendation_run'])
            if source['snapshot']['card_digest']!=state['upstream']['snapshot']['card_digest']:
                state.update(dialogue=[],route=None)
            state.update(upstream=source,upstream_digest=digest(source),purpose=source['purpose'],plan=None,review=None)
            return save(folder,state,payload['reason'])
        if not status(root,state)['current']: raise ValueError('Upstream changed; refresh first')
        if action=='review-figure-set':
            import figure_set_reviews
            return figure_set_reviews.record(root,state,payload,status(root,state)['export_ready'])
        if action=='review-figure':
            import figure_reviews
            return figure_reviews.record(root,state,payload['export_folder'],payload,status(root,state)['export_ready'])
        if action=='ask':
            if any(d['answer'] is None for d in state['dialogue']): raise ValueError('Wait for actual reply before next question')
            q={'id':f'q{len(state["dialogue"])+1}','question':payload['question'],'reason':payload['reason'],'at':now(),'answer':None}
            state['dialogue'].append(q)
            state.update(route=None,plan=None,review=None)
        elif action=='answer':
            pending=[d for d in state['dialogue'] if d['answer'] is None]
            if len(pending)!=1 or pending[0]['id']!=payload['question_id']: raise ValueError('No matching pending question')
            pending[0]['answer']={'text':payload['text'],'user_ref':payload['user_ref'],'at':now()}
        elif action=='select':
            state.update(route=copy.deepcopy(payload['route']),plan=None,review=None)
            validate_route(state)
        elif action=='submit':
            validate_plan(state,payload['plan'])
            if state['plan']==payload['plan']: return state
            state.update(plan=copy.deepcopy(payload['plan']),review=None)
        elif action=='review':
            if not state['plan']: raise ValueError('No submitted plan')
            validate_plan(state,state['plan'])
            if payload['decision']=='accepted' and any(payload[f] is not True for f in ('evidence','feasibility','graph_alignment')):
                raise ValueError('All review checks required for acceptance')
            state['review']={'digest':digest(state['plan']),'reviewer':payload['reviewer'],'note':payload['note'],'at':now(),
                             'decision':payload['decision'],**{f:payload[f] for f in ('evidence','feasibility','graph_alignment')}}
        else: raise ValueError('Unknown action')
        return save(folder,state,payload['reason'])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True); parser.add_argument('--run',required=True)
    parser.add_argument('action',choices=['start','show','status','ask','answer','select','submit','review','refresh','export','figure-status','review-figure','export-set','figure-set-status','review-figure-set'])
    parser.add_argument('--input',required=True)
    args=parser.parse_args()
    try: print(json.dumps(execute(args.root,args.run,args.action,read_json(inside(args.root,args.input))),ensure_ascii=False,indent=2))
    except (ValueError,OSError,KeyError,TypeError,RuntimeError,ValidationError) as exc: parser.exit(1,str(exc)+'\n')

if __name__=='__main__': main()
