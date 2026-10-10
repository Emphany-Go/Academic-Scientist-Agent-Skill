"""Read-only capability check; never install or change global configuration."""
import argparse,importlib.metadata,importlib.util,json,shutil,subprocess,sys
from pathlib import Path

def inspect(node=None,runtime=None,browser=None):
    packages={}
    for module,dist in [('jsonschema','jsonschema'),('pypdf','pypdf'),('pypdfium2','pypdfium2'),('PIL','Pillow')]:
        available=importlib.util.find_spec(module) is not None
        try:version=importlib.metadata.version(dist) if available else None
        except importlib.metadata.PackageNotFoundError:version=None
        packages[module]=dict(available=available,version=version)
    executable=node or shutil.which('node');js={k:False for k in ('playwright','@oai/artifact-tool')};error=None
    if executable and runtime:
        code="const {createRequire}=require('node:module');const r=createRequire(require('node:path').resolve(process.argv[1]));let out={};for(const n of ['playwright','@oai/artifact-tool']){try{r.resolve(n);out[n]=true}catch{out[n]=false}}console.log(JSON.stringify(out));"
        try:
            p=subprocess.run([str(executable),'-e',code,str(Path(runtime).resolve())],capture_output=True,text=True,encoding='utf-8',timeout=20)
            if p.returncode==0:js=json.loads(p.stdout)
            else:error=p.stderr.strip()
        except (OSError,subprocess.TimeoutExpired,ValueError) as exc:error=str(exc)
    pyok=sys.version_info>=(3,10)
    return dict(python=sys.version.split()[0],python_supported=pyok,packages=packages,node=str(executable) if executable else None,
      node_modules=js,browser_exists=bool(browser and Path(browser).is_file()),probe_error=error,
      capabilities=dict(state_and_validation=pyok and packages['jsonschema']['available'],
       pdf_ingestion=pyok and all(v['available'] for v in packages.values()),
       excel_export=bool(executable and js['@oai/artifact-tool']),
       figure_render=bool(executable and js['playwright'] and browser and Path(browser).is_file())),
      note='Discovery only, not a render test. Missing runtime paths are unknown/unavailable until supplied. No dependencies installed.')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--node');p.add_argument('--runtime-package');p.add_argument('--browser');p.add_argument('--output',type=Path);a=p.parse_args()
    r=inspect(a.node,a.runtime_package,a.browser);t=json.dumps(r,ensure_ascii=False,indent=2)+'\n'
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(t,encoding='utf-8')
    print(t)
    if not r['capabilities']['state_and_validation']:raise SystemExit(1)
if __name__=='__main__':main()
