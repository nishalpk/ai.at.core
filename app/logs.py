"""Local-only redacted event viewer. Never exposes process stdout or .env."""
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
app=FastAPI(title='Agent event viewer')
@app.get('/api/logs')
def logs():
    events=[]
    for owner in ('A','B'):
        path=Path(f'runtime/{owner}.jsonl')
        if path.exists():
            for line in path.read_text(encoding='utf-8').splitlines()[-200:]:
                try:
                    e=json.loads(line)
                    e={k:v for k,v in e.items() if k in ('time','owner','event','operation','model','role','label','confidence','usage','latency_ms','success','error','scopes')}
                    events.append(e)
                except ValueError: pass
    return sorted(events,key=lambda e:e['time'])[-300:]
@app.get('/',response_class=HTMLResponse)
def home(): return Path('web/logs.html').read_text(encoding='utf-8')
