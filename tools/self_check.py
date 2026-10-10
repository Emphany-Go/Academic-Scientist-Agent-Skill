"""Verify the release without importing development fixtures or creating a study."""
import argparse,ast,hashlib,json,re,sys
from pathlib import Path

def verify(root):
    root=Path(root).resolve();expected=json.loads((root/'SHA256SUMS.json').read_text(encoding='utf-8'))
    actual={p.relative_to(root).as_posix():p for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='SHA256SUMS.json' and '.git' not in p.parts}
    errors=[]
    if set(expected)!=set(actual):errors.append('Release file list changed')
    for n,h in expected.items():
        p=(root/n).resolve()
        if not p.is_relative_to(root) or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:errors.append('Checksum mismatch: '+n)
    skill=root/'skills/academic-scientist'
    for p in skill.rglob('*.py'):
        try:ast.parse(p.read_text(encoding='utf-8'))
        except SyntaxError:errors.append('Invalid Python: '+p.name)
    for p in skill.rglob('*.md'):
        for link in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
            if '://' not in link and not link.startswith('#') and not (p.parent/link.split('#')[0]).exists():errors.append('Broken skill link: '+link)
    try:
        from jsonschema import Draft202012Validator
        for p in (skill/'schemas').glob('*.schema.json'):Draft202012Validator.check_schema(json.loads(p.read_text(encoding='utf-8')))
        schemas='passed'
    except ImportError:schemas='not_checked: jsonschema missing'
    except Exception as exc:schemas='failed';errors.append(str(exc))
    return dict(passed=not errors,files=len(actual),schemas=schemas,errors=errors,scope='package integrity and structure, not full workflow or model accuracy')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',type=Path,default=Path(__file__).resolve().parents[1]);a=p.parse_args()
    r=verify(a.package);print(json.dumps(r,ensure_ascii=False,indent=2))
    if not r['passed']:raise SystemExit(1)
if __name__=='__main__':main()
