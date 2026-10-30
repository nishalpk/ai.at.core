"""Local airline operator observer. Read-only access to B's booking ledger."""
import json,sqlite3,hashlib
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
app=FastAPI(title='Airline booking desk')
DB=Path('runtime/b.sqlite')
@app.get('/api/bookings')
def snapshot():
    if not DB.exists(): return {'bookings':[],'flights':[],'events':[]}
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True) as c:
        flights={fid:{**json.loads(data),'seats_left':seats} for fid,data,seats in c.execute('SELECT id,data,seats FROM flights')}
        bookings=[{'booking_id':bid,'user':'user-'+hashlib.sha256(owner.encode()).hexdigest()[:10],'flight_id':fid,'status':status,'flight':flights.get(fid,{})} for bid,owner,fid,status in c.execute('SELECT id,owner,flight,status FROM bookings ORDER BY rowid DESC')]
        exists=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='booking_events'").fetchone()
        events=[{'booking_id':bid,'event':event,'time':at} for bid,event,at in c.execute('SELECT booking_id,event,at FROM booking_events ORDER BY id DESC LIMIT 200')] if exists else []
    return {'bookings':bookings,'flights':list(flights.values()),'events':events}
@app.get('/',response_class=HTMLResponse)
def home(): return Path('web/bookings.html').read_text(encoding='utf-8')
