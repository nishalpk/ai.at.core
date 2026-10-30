import os,json,uuid,secrets,hashlib,base64,time
from pathlib import Path
from typing import TypedDict
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import httpx
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse
from langgraph.graph import StateGraph,START,END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt,Command
from app.common import *
from app.security import verify
app=FastAPI(title='Travel Agent A')
sessions={}; pending={}
CALLBACK='http://localhost:8000/oauth/callback'
class State(TypedDict,total=False):
    sid:str
    intent:dict
    result:dict

def consent(s):
    session=sessions[s['sid']]
    scopes={'search':{'flights:search'},'book':{'flights:search','flights:book'},'cancel':{'flights:cancel'}}[s['intent']['action']]
    claims=session.get('claims',{})
    if claims.get('exp',0)<time.time()+15 or not scopes.issubset(set(claims.get('scope','').split())):
        interrupt({'type':'consent','url':'/oauth/start','scopes':sorted(scopes)})
    return {}
async def call_b(s,op,args):
    session=sessions[s['sid']]
    from a2a.client.transports.jsonrpc import JsonRpcTransport
    from a2a.types import AgentCard,MessageSendParams,Message,Part,DataPart,Role,Task
    async with httpx.AsyncClient(timeout=60,headers={'Authorization':'Bearer '+session['token']}) as client:
        transport=JsonRpcTransport(client,agent_card=AgentCard.model_validate(session['card']))
        task=await transport.send_message(MessageSendParams(message=Message(role=Role.user,message_id=str(uuid.uuid4()),parts=[Part(root=DataPart(data={'operation':op,'args':args}))])))
    trace('A','a2a_result',operation=op,success=True)
    if not isinstance(task,Task) or not task.artifacts: raise ValueError('Airline returned no task artifact')
    return task.artifacts[0].parts[0].root.data

async def search(s):
    if s['intent']['action']=='cancel': return {}
    result=await call_b(s,'search_flights',{k:s['intent'][k] for k in ('origin','destination','date')})
    preference=s['intent']['time']
    def matches(f):
        hour=int(f['depart'].split(':')[0])
        windows={'any':(0,24),'daytime':(6,18),'morning':(6,12),'afternoon':(12,18),'evening':(18,24)}
        return windows[preference][0]<=hour<windows[preference][1] if preference in windows else f['depart']==preference
    flights=[f for f in result['flights'] if matches(f) and f['seats_left']>0]
    if not flights:
        i=s['intent']
        raise ValueError(f"The airline returned no available flights from {i['origin']} to {i['destination']} on {i['date']} matching {preference}. This demo has limited sample inventory, not live worldwide flights. Try a different route, date or time; the supplied sample includes BOM to DXB tomorrow.")
    if s['intent']['action']=='search': return {'result':{'flights':flights}}
    if len(flights)>1:
        choice=interrupt({'type':'select','flights':flights,'message':'I found these available flights. Choose one to review before booking.'})
        flights=[f for f in flights if f['id']==choice]
        if len(flights)!=1: raise ValueError('Please choose one of the returned flight options.')
    return {'result':{'flight':flights[0]}}

def confirm(s):
    if s['intent']['action']=='book':
        if interrupt({'type':'confirm','flight':s['result']['flight']}) is not True: raise ValueError('Booking declined')
    return {}
async def execute(s):
    session=sessions[s['sid']]; intent=s['intent']
    if intent['action']=='search': return {'result':s['result']}
    if intent['action']=='cancel':
        bid=intent.get('booking_id') or session.get('booking_id')
        if not bid: raise ValueError('Please provide the booking reference to cancel.')
        result=await call_b(s,'cancel_booking',{'booking_id':bid,'idempotency_key':intent['key']})
    else:
        result=await call_b(s,'book_flight',{'flight_id':s['result']['flight']['id'],'idempotency_key':intent['key']})
        session['booking_id']=result['booking_id']
    return {'result':result}
g=StateGraph(State)
for name,fn in [('consent',consent),('search',search),('confirm',confirm),('execute',execute)]: g.add_node(name,fn)
g.add_edge(START,'consent'); g.add_edge('consent','search'); g.add_edge('search','confirm'); g.add_edge('confirm','execute'); g.add_edge('execute',END)
graph=g.compile(checkpointer=InMemorySaver())
def session(request):
    sid=request.cookies.get('sid')
    if sid not in sessions: raise HTTPException(401,'Open the home page first')
    return sid,sessions[sid]
def csrf(request):
    if request.headers.get('origin')!='http://localhost:8000': raise HTTPException(403,'Invalid origin')
def record(s,view):
    if 'message' not in view:
        if view['type']=='consent': view['message']='Please authorize '+', '.join(view['scopes'])+' with the airline to continue. Search permission does not allow booking.'
        elif view['type']=='confirm':
            f=view['flight']; view['message']=f"I found {f['id']} from {f['origin']} to {f['destination']} on {f['date']} at {f['depart']}, for USD {f['price_usd']}. Approve this purchase to ask the airline to confirm your booking?"
        elif view['type']=='result' and 'flights' in view['data']:
            view['message']='Here are the available flights:\n'+'\n'.join(f"{f['id']} · {f['origin']} to {f['destination']} · {f['date']} {f['depart']} · USD {f['price_usd']}" for f in view['data']['flights'])+'\nNo booking has been made. Tell me if you would like to book one.'
        elif view['type']=='result': view['message']=f"The airline confirmed your booking status: {view['data']['status']}. Reference: {view['data']['booking_id']}."
    s.setdefault('history',[]).append({'role':'assistant','content':view.get('message','')})
    s['view']=view
    return {**view,'history':s['history']}
async def run(sid,value):
    cfg={'configurable':{'thread_id':sessions[sid]['thread']}}
    try:
        result=await graph.ainvoke(value,cfg)
        pauses=result.get('__interrupt__',())
        sessions[sid]['view']=pauses[0].value if pauses else {'type':'result','data':result.get('result')}
    except Exception as e:
        trace('A','operation_failed',error=type(e).__name__)
        sessions[sid]['view']={'type':'error','message':str(e) if isinstance(e,ValueError) else 'Service request failed. Check both services and retry.'}
    return record(sessions[sid],sessions[sid]['view'])
@app.get('/',response_class=HTMLResponse)
def home(request:Request):
    sid=request.cookies.get('sid')
    if sid not in sessions: sid=secrets.token_urlsafe(32); sessions[sid]={'view':{'type':'ready'}}
    response=HTMLResponse(Path('web/index.html').read_text(encoding='utf-8')); response.set_cookie('sid',sid,httponly=True,samesite='lax',max_age=3600)
    return response
@app.get('/api/status')
def status(request:Request):
    s=session(request)[1]; return {**s['view'],'history':s.get('history',[])}
@app.post('/api/chat')
async def chat(request:Request):
    csrf(request); sid,s=session(request)
    waiting=s['view'] if s['view'].get('type') in ('consent','confirm','select') else None
    text=(await request.json()).get('message','')[:2000]
    if not os.getenv('OPENROUTER_API_KEY'): raise HTTPException(503,'Set OPENROUTER_API_KEY in .env and restart A')
    s.setdefault('history',[]).append({'role':'user','content':text})
    if waiting:
        return record(s,{**waiting,'message':'Please use the pending airline authorization, flight selection, or booking confirmation buttons. Chat cannot approve these steps.'})
    try:
        from app.travel_agent import respond
        return await respond(sid)
    except Exception as e:
        trace('A','agent_failed',error=type(e).__name__)
        return record(s,{'type':'error','message':'The agent could not complete this turn. Please try again; no additional action was approved.'})
@app.post('/api/reset')
async def reset(request:Request):
    csrf(request); sid,s=session(request)
    for state in [k for k,v in pending.items() if v['sid']==sid]: pending.pop(state,None)
    sessions[sid]={'view':{'type':'ready'}}
    trace('A','chat_reset')
    return {'type':'ready','history':[]}
@app.post('/api/select')
async def selection(request:Request):
    csrf(request); sid,s=session(request)
    if s['view'].get('type')!='select': raise HTTPException(409,'No selection pending')
    choice=(await request.json()).get('flight_id')
    if choice not in [f['id'] for f in s['view']['flights']]: raise HTTPException(400,'Invalid flight selection')
    return await run(sid,Command(resume=choice))
@app.post('/api/confirm')
async def confirmation(request:Request):
    csrf(request); sid,s=session(request)
    if s['view'].get('type')!='confirm': raise HTTPException(409,'No confirmation pending')
    return await run(sid,Command(resume=(await request.json()).get('approve') is True))
@app.get('/oauth/start')
def oauth_start(request:Request):
    sid,s=session(request)
    if s['view'].get('type')!='consent': raise HTTPException(409,'No consent pending')
    state=secrets.token_urlsafe(32); verifier=secrets.token_urlsafe(48)
    pending[state]={'sid':sid,'verifier':verifier,'expires':time.time()+300,'thread':s['thread']}
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    from urllib.parse import urlencode
    url=ISSUER+'/protocol/openid-connect/auth?'+urlencode({'client_id':CLIENT,'redirect_uri':CALLBACK,'response_type':'code','scope':'openid '+' '.join(s['view']['scopes']),'state':state,'code_challenge':challenge,'code_challenge_method':'S256','prompt':'consent'})
    return RedirectResponse(url)
@app.get('/oauth/callback')
async def callback(request:Request):
    sid=request.cookies.get('sid'); s=sessions.get(sid)
    state=request.query_params.get('state',''); p=pending.get(state)
    def recovery(message):
        return HTMLResponse('<!doctype html><html><head><title>Restart airline authorization</title></head><body style="font:18px system-ui;max-width:650px;margin:80px auto;padding:24px"><h1>Airline authorization needs restarting</h1><p>'+message+'</p><p>No operation was resumed from this callback.</p><a href="/">Return to chat</a></body></html>',status_code=400)
    if not s or not p or p['sid']!=sid or p['thread']!=s.get('thread'):
        return recovery('This login link is stale or belongs to an earlier chat. Return to chat and start authorization again. A server restart or New chat invalidates old links.')
    pending.pop(state,None)
    if p['expires']<time.time() or request.query_params.get('error')=='temporarily_unavailable':
        if s['view'].get('type')=='consent':
            record(s,{**s['view'],'message':'The airline login timed out. Please click Authorize with airline again to start a fresh login. No action was performed.'})
        trace('A','oauth_expired')
        return RedirectResponse('/')
    if 'error' in request.query_params:
        record(s,{'type':'error','message':'Authorization denied; no action performed.'}); return RedirectResponse('/')
    async with httpx.AsyncClient(timeout=20) as client:
        r=await client.post(ISSUER+'/protocol/openid-connect/token',data={'grant_type':'authorization_code','client_id':CLIENT,'client_secret':os.environ['OAUTH_CLIENT_SECRET'],'redirect_uri':CALLBACK,'code':request.query_params.get('code',''),'code_verifier':p['verifier']})
        if r.status_code!=200: raise HTTPException(400,'Token exchange failed')
        token=r.json()['access_token']; claims=verify(token)
    old=s.get('claims')
    if old and (old['iss'],old['sub'])!=(claims['iss'],claims['sub']): raise HTTPException(403,'Use the same airline account for this session')
    if not set(s['view']['scopes']).issubset(claims.get('scope','').split()): raise HTTPException(403,'Required permission was not granted')
    s['token']=token; s['claims']=claims
    trace('A','consent_granted',scopes=claims['scope'])
    await run(sid,Command(resume=True))
    return RedirectResponse('/')

