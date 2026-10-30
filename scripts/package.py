import argparse,zipfile,re
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--id',required=True); args=p.parse_args()
if not re.fullmatch(r'[A-Za-z0-9_-]+',args.id): p.error('Use letters, digits, underscores or hyphens')
roots=['app','web','tests','scripts','docs']
files=[Path(x) for x in ['README.md','requirements.txt','requirements.lock.txt','.env.example','compose.yaml','Dockerfile','.dockerignore','.gitignore','airline-flights.json']]
for root in roots: files += [f for f in Path(root).rglob('*') if f.is_file() and not f.name.startswith('~$') and (f.suffix!='.pptx' or f.name=='approach.pptx') and '__pycache__' not in f.parts and f.suffix in ('.py','.ps1','.md','.html','.pptx','.json','.csv','.svg','.mmd','.json','.csv','.svg','.mmd')]
with zipfile.ZipFile(args.id+'_challenge-4.zip','w',zipfile.ZIP_DEFLATED) as z:
    for f in files: z.write(f,f.as_posix())
print('Created submission archive; review before sending.')
