import sqlite3,json,uuid
from datetime import timezone
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
class Store:
    def __init__(self,path="runtime/b.sqlite"):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.path=path
        with self.db() as c:
            c.execute("CREATE TABLE IF NOT EXISTS flights(id TEXT PRIMARY KEY,data TEXT,seats INTEGER)")
            c.execute("CREATE TABLE IF NOT EXISTS bookings(id TEXT PRIMARY KEY,owner TEXT,flight TEXT,status TEXT,request_key TEXT,UNIQUE(owner,request_key))")
            c.execute("CREATE TABLE IF NOT EXISTS booking_events(id INTEGER PRIMARY KEY AUTOINCREMENT,booking_id TEXT,event TEXT,at TEXT)")
            if not c.execute("SELECT 1 FROM flights").fetchone():
                tomorrow=(datetime.now(ZoneInfo("Asia/Dubai"))+timedelta(days=1)).date().isoformat()
                for f in json.load(open("airline-flights.json"))["flights"]:
                    if f["date"]=="tomorrow": f["date"]=tomorrow
                    c.execute("INSERT INTO flights VALUES(?,?,?)",(f["id"],json.dumps(f),f["seats_left"]))
    def db(self): return sqlite3.connect(self.path,timeout=10)
    def run(self,op,args,owner):
        with self.db() as c:
            if op=="search_flights":
                out=[]
                for data,seats in c.execute("SELECT data,seats FROM flights"):
                    f=json.loads(data); f["seats_left"]=seats
                    if all(f.get(k)==args.get(k) for k in ("origin","destination","date")): out.append(f)
                return {"flights":out}
            c.execute("BEGIN IMMEDIATE")
            if op=="book_flight":
                old=c.execute("SELECT id,flight,status FROM bookings WHERE owner=? AND request_key=?",(owner,args["idempotency_key"])).fetchone()
                if old:
                    if old[1]!=args["flight_id"]: raise ValueError("Idempotency key reused for another flight")
                    return dict(zip(("booking_id","flight_id","status"),old))
                if c.execute("UPDATE flights SET seats=seats-1 WHERE id=? AND seats>0",(args["flight_id"],)).rowcount!=1: raise ValueError("Flight unavailable")
                bid=str(uuid.uuid4())
                c.execute("INSERT INTO bookings VALUES(?,?,?,?,?)",(bid,owner,args["flight_id"],"confirmed",args["idempotency_key"]))
                c.execute("INSERT INTO booking_events(booking_id,event,at) VALUES(?,?,?)",(bid,"confirmed",datetime.now(timezone.utc).isoformat()))
                return {"booking_id":bid,"flight_id":args["flight_id"],"status":"confirmed"}
            row=c.execute("SELECT flight,status FROM bookings WHERE id=? AND owner=?",(args["booking_id"],owner)).fetchone()
            if not row: raise ValueError("Booking not found")
            if row[1]!="cancelled":
                c.execute("UPDATE bookings SET status='cancelled' WHERE id=?",(args["booking_id"],))
                c.execute("UPDATE flights SET seats=seats+1 WHERE id=?",(row[0],))
                c.execute("INSERT INTO booking_events(booking_id,event,at) VALUES(?,?,?)",(args["booking_id"],"cancelled",datetime.now(timezone.utc).isoformat()))
            return {"booking_id":args["booking_id"],"status":"cancelled"}
