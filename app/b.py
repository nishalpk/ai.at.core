import uuid
from typing import TypedDict
from fastapi import FastAPI,Request,HTTPException
from langgraph.graph import StateGraph,START,END
from app.common import *
from app.security import verify,authorize
from app.store import Store
app=FastAPI(title="Airline Agent B")
store=Store()
class State(TypedDict,total=False):
    operation:str
    args:dict
    claims:dict
    result:dict
def execute(s):
    authorize(s["claims"],SCOPES[s["operation"]])
    owner=s["claims"]["iss"]+"|"+s["claims"]["sub"]
    trace("B","authorized",operation=s["operation"],subject=s["claims"]["sub"])
    return {"result":store.run(s["operation"],s["args"],owner)}
g=StateGraph(State); g.add_node("execute",execute); g.add_edge(START,"execute"); g.add_edge("execute",END)
graph=g.compile()
tasks={}
@app.get("/.well-known/agent-card.json")
def card():
    return {"name":"Airline Agent","description":"Search and manage airline bookings","url":B_URL+"/a2a","version":"1.0.0","protocolVersion":"0.3.0","preferredTransport":"JSONRPC","capabilities":{"streaming":False,"pushNotifications":False},"defaultInputModes":["application/json"],"defaultOutputModes":["application/json"],"skills":[{"id":op,"name":op,"description":scope,"tags":["flights"]} for op,scope in SCOPES.items()],"securitySchemes":{"oauth":{"type":"oauth2","flows":{"authorizationCode":{"authorizationUrl":ISSUER+"/protocol/openid-connect/auth","tokenUrl":ISSUER+"/protocol/openid-connect/token","scopes":{s:s for s in SCOPES.values()}}}}},"security":[{"oauth":["flights:search"]}]}
@app.post("/a2a")
async def rpc(request:Request):
    claims=verify(request.headers.get("authorization","").removeprefix("Bearer "))
    body=await request.json(); rid=body.get("id"); method=body.get("method"); p=body.get("params",{})
    def error(code,msg): return {"jsonrpc":"2.0","id":rid,"error":{"code":code,"message":msg}}
    if body.get("jsonrpc")!="2.0": return error(-32600,"Invalid request")
    owner=(claims["iss"],claims["sub"])
    if method in ("tasks/get","tasks/cancel"):
        entry=tasks.get(p.get("id"))
        if not entry or entry[0]!=owner: return error(-32001,"Task not found")
        if method=="tasks/cancel": return error(-32002,"Terminal task cannot be cancelled; use cancel_booking for reservations")
        return {"jsonrpc":"2.0","id":rid,"result":entry[1]}
    if method!="message/send": return error(-32601,"Method not found")
    try:
        msg=p["message"]; data=next(x["data"] for x in msg["parts"] if x.get("kind")=="data")
        op=data["operation"]; args=data["args"]
        if op not in SCOPES: return error(-32602,"Unknown operation")
        authorize(claims,SCOPES[op])
        needed={"search_flights":["origin","destination","date"],"book_flight":["flight_id","idempotency_key"],"cancel_booking":["booking_id","idempotency_key"]}[op]
        if any(not isinstance(args.get(k),str) or not args[k] for k in needed): return error(-32602,"Missing or invalid operation fields")
        result=graph.invoke({"operation":op,"args":args,"claims":claims})["result"]
        tid=str(uuid.uuid4())
        task={"id":tid,"contextId":msg.get("contextId") or str(uuid.uuid4()),"kind":"task","status":{"state":"completed"},"artifacts":[{"artifactId":str(uuid.uuid4()),"parts":[{"kind":"data","data":result}]}]}
        tasks[tid]=(owner,task)
        return {"jsonrpc":"2.0","id":rid,"result":task}
    except HTTPException: raise
    except (KeyError,StopIteration,TypeError): return error(-32602,"Invalid message")
    except ValueError as e: return error(-32000,str(e))
