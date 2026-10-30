import os, json, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
ISSUER=os.getenv("OAUTH_ISSUER","http://localhost:8080/realms/airline-demo")
B_URL=os.getenv("B_URL","http://localhost:8001")
CLIENT="travel-agent-a"
SCOPES={"search_flights":"flights:search","book_flight":"flights:book","cancel_booking":"flights:cancel"}
def trace(owner,event,**details):
    Path("runtime").mkdir(exist_ok=True)
    with open(f"runtime/{owner}.jsonl","a") as f:
        f.write(json.dumps(dict(time=time.time(),owner=owner,event=event,**details))+"\n")
