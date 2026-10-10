"""Install the bundled skill without downloading dependencies or overwriting skills."""
import argparse,hashlib,json,os,shutil
from pathlib import Path

def install(package,skills_dir):
    package=Path(package).resolve();source=package/'skills/academic-scientist'
    manifest=json.loads((package/'SHA256SUMS.json').read_text(encoding='utf-8'))
    expected={k:v for k,v in manifest.items() if k.startswith('skills/academic-scientist/')}
    actual={p.relative_to(package).as_posix():p for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    if set(actual)!=set(expected):raise ValueError('Skill file list differs from release manifest')
    for name,p in actual.items():
        if p.is_symlink() or not p.resolve().is_relative_to(source.resolve()):raise ValueError('Do not install linked source files')
        if hashlib.sha256(p.read_bytes()).hexdigest()!=expected[name]:raise ValueError('Release file changed: '+name)
    target=Path(skills_dir).expanduser().resolve()/'academic-scientist'
    if target.exists():raise ValueError('Existing skill preserved: '+str(target)+'; review/backup it before upgrading')
    if target.is_relative_to(package) or package.is_relative_to(target):raise ValueError('Installation directory must be separate from the package')
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(source,target,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    return dict(installed_to=str(target),name='academic-scientist',version='V0.1',dependencies_installed=False,
                next_step='Open a new Codex turn; if the skill does not appear, restart Codex. Run the environment check before research.')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--skills-dir',type=Path,help='Custom skills root (skill subfolder is added)')
    p.add_argument('--legacy-codex-home',action='store_true',help='Use CODEX_HOME/skills, or ~/.codex/skills, for clients with this local layout')
    a=p.parse_args()
    if a.skills_dir and a.legacy_codex_home:p.error('Choose one destination option')
    dest=a.skills_dir or ((Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'skills') if a.legacy_codex_home else Path.home()/'.agents/skills')
    print(json.dumps(install(Path(__file__).resolve().parents[1],dest),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
