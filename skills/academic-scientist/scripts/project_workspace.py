"""Keep reviewed deliverables visible and all workflow state inside the project.

No automatic migration, deletion, fact review, or replacement of user edits.
"""
import argparse,hashlib,json,re
from pathlib import Path
from urllib.parse import quote
from runtime import inside,read_json,write_json,atomic_text,sha256,workspace_lock,check_schema

INTERNAL='.academic-scientist'
TOP={'workbook':'文献整理.xlsx','recommendations':'阅读建议.md','proposal':'研究方案.md','research_profile':'研究档案.md'}

def paths(project):
    project=Path(project).resolve();backend=inside(project,INTERNAL)
    return project,backend,backend/'project.json'

def state(project):
    p,b,m=paths(project);s=read_json(m);check_schema('project-workspace.schema.json',s);return p,b,m,s

def destination(project,target,kind):
    if kind in TOP:
        if target!=TOP[kind]:raise ValueError('Unexpected public filename for '+kind)
    elif kind in ('figure','card'):
        rel=Path(target);prefix='流程图' if kind=='figure' else '论文阅读卡'
        suffixes={'.drawio','.svg','.png','.pdf'} if kind=='figure' else {'.md','.json'}
        if len(rel.parts)!=2 or rel.parts[0]!=prefix or rel.suffix.lower() not in suffixes:raise ValueError('Invalid deliverable path')
    else:raise ValueError('Unknown deliverable kind')
    return inside(project,target)

def navigation(s):
    lines=['# 阅读入口','','本项目使用 Academic-Scientist Agent Skill V0.1。','',
      '可直接查看以下成果；事实、证据、工作状态和修订历史保存在 `.academic-scientist/`。',
      'Excel 事实修改需原文核查后合并；修改原稿或图时，先保留用户版本。','']
    lines += [f'- [{t}]({quote(t,safe="/")})' for t in sorted(s['files'])]
    if not s['files']:lines+=['尚无已交付成果。']
    return '\n'.join(lines)+'\n'

def init(project):
    p,b,m=paths(project)
    if m.exists():return status(project)
    if b.exists() and any(b.iterdir()):raise ValueError('Existing internal data: do not auto-migrate')
    nav=p/'阅读入口.md'
    if nav.exists():raise ValueError('Preserve existing 阅读入口.md')
    with workspace_lock(b):
        if m.exists():return status(project)
        s=dict(schema_version='0.1.0',release='V0.1',revision=0,files={},index_sha256=None)
        text=navigation(s);s['index_sha256']=hashlib.sha256(text.encode()).hexdigest()
        check_schema('project-workspace.schema.json',s);write_json(m,s);atomic_text(nav,text)
    return status(project)

def status(project):
    p,b,m,s=state(project);files={}
    for t,e in s['files'].items():
        f=destination(p,t,e['kind']);files[t]=dict(exists=f.is_file(),user_modified=f.is_file() and sha256(f)!=e['sha256'])
    return dict(project=str(p),workspace_root=str(b),revision=s['revision'],files=files)

def publish(project,payload):
    check_schema('project-publish.schema.json',payload)
    p,b,m,s=state(project)
    with workspace_lock(b):
        p,b,m,s=state(project);nav=p/'阅读入口.md'
        if nav.exists() and sha256(nav)!=s['index_sha256']:raise ValueError('Preserve edited 阅读入口.md; reconcile explicitly')
        planned=[];seen=set()
        for entry in payload['artifacts']:
            target=entry['target'];dest=destination(p,target,entry['kind']);src=inside(b,entry['source'])
            if target.casefold() in seen:raise ValueError('Duplicate output path')
            seen.add(target.casefold())
            if not src.is_file():raise ValueError('Source is not a file: '+entry['source'])
            content=src.read_bytes();sig=hashlib.sha256(content).hexdigest();old=s['files'].get(target)
            if old and old['kind']!=entry['kind']:raise ValueError('Output kind changed')
            if dest.exists() and (not old or sha256(dest)!=old['sha256']):raise ValueError('Preserve user file: '+target)
            if entry['kind']=='workbook':
                from literature_output import digest
                for key in ('export_id','collection'):
                    if key not in entry:raise ValueError('Workbook publication requires '+key)
                collection=inside(b,entry['collection'])
                if src!=collection/'exports'/entry['export_id']/'literature.xlsx':raise ValueError('Workbook collection does not match source export')
                baseline=src.parent/'baseline.json';seal=read_json(src.parent/'workbook-seal.json')
                if digest(read_json(baseline))[:24]!=entry['export_id'] or sha256(baseline)!=seal['baseline_sha256'] or sig!=seal['workbook_sha256']:
                    raise ValueError('Workbook is not the sealed export for this baseline')
            planned.append((entry,dest,content,sig,old))
        # All user-modification and source checks complete before writing any public file.
        for entry,dest,content,sig,old in planned:
            if dest.exists() and old:
                archive=inside(b,'deliveries/history/'+old['sha256']+'/'+entry['target']);archive.parent.mkdir(parents=True,exist_ok=True)
                if archive.exists() and sha256(archive)!=old['sha256']:raise ValueError('Archive changed')
                if not archive.exists():archive.write_bytes(dest.read_bytes())
            dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists() or sha256(dest)!=sig:dest.write_bytes(content)
            s['files'][entry['target']]={**entry,'sha256':sig}
        s['revision']+=1;text=navigation(s);s['index_sha256']=hashlib.sha256(text.encode()).hexdigest()
        check_schema('project-workspace.schema.json',s)
        write_json(b/'deliveries'/f'r{s["revision"]:06d}.json',s)
        write_json(m,s);atomic_text(nav,text)
    return status(project)

def collect_edits(project,target):
    p,b,m,s=state(project)
    with workspace_lock(b):
        p,b,m,s=state(project);e=s['files'].get(target)
        if not e or e['kind']!='workbook':raise ValueError('Select a published workbook')
        src=destination(p,target,e['kind']);data=src.read_bytes();sig=hashlib.sha256(data).hexdigest()
        dst=inside(b,'inbox/'+sig+'.xlsx');dst.parent.mkdir(parents=True,exist_ok=True)
        if dst.exists() and dst.read_bytes()!=data:raise ValueError('Inbox file changed')
        if not dst.exists():dst.write_bytes(data)
        return dict(workspace_root=str(b),collection=e['collection'],export_id=e['export_id'],
                    workbook_path=dst.relative_to(b).as_posix(),changed=sig!=e['sha256'],next_action='import-edits then evidence review; public workbook remains untouched')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path,required=True)
    p.add_argument('action',choices=['init','status','publish','collect-edits']);p.add_argument('--input',type=Path);p.add_argument('--target',default='文献整理.xlsx');a=p.parse_args()
    if a.action=='publish':result=publish(a.project,read_json(a.input))
    elif a.action=='collect-edits':result=collect_edits(a.project,a.target)
    else:result=globals()[a.action](a.project)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
