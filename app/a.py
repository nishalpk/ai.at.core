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
    scopes={'flights:cancel'} if s['intent']['action']=='cancel' else {'flights:search','flights:book'}
    claims=session.get('claims',{})
    if claims.get('exp',0)<time.time()+15 or not scopes.issubset(set(claims.get('scope','').split())):
        interrupt({'type':'consent','url':'/oauth/start','scopes':sorted(scopes)})
    return {}
async def call_b(s,op,args):
    session=sessions[s['sid']]
    async with httpx.AsyncClient(timeout=20) as client:
        response=await client.post(session['card']['url'],headers={'Authorization':'Bearer '+session['token']},json={'jsonrpc':'2.0','id':str(uuid.uuid4()),'method':'message/send','params':{'message':{'kind':'message','role':'user','messageId':str(uuid.uuid4()),'parts':[{'kind':'data','data':{'operation':op,'args':args}}]}}})
        response.raise_for_status(); payload=response.json()
    trace('A','a2a_result',operation=op,success='error' not in payload)
    if 'error' in payload: raise ValueError(payload['error']['message'])
    return payload['result']['artifacts'][0]['parts'][0]['data']
async def search(s):
    if s['intent']['action']=='cancel': return {}
    result=await call_b(s,'search_flights',{k:s['intent'][k] for k in ('origin','destination','date')})
    flights=[f for f in result['flights'] if f['depart']==s['intent']['time'] and f['seats_left']>0]
    if len(flights)!=1: raise ValueError('No unique available flight. Specify route, date and departure time.')
    return {'result':{'flight':flights[0]}}
def confirm(s):
    if s['intent']['action']=='book':
        if interrupt({'type':'confirm','flight':s['result']['flight']}) is not True: raise ValueError('Booking declined')
    return {}
async def execute(s):
    session=sessions[s['sid']]; intent=s['intent']
    if intent['action']=='cancel':
        bid=session.get('booking_id')
        if not bid: raise ValueError('No booking in this session')
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
async def run(sid,value):
    cfg={'configurable':{'thread_id':sessions[sid]['thread']}}
    try:
        result=await graph.ainvoke(value,cfg)
        pauses=result.get('__interrupt__',())
        sessions[sid]['view']=pauses[0].value if pauses else {'type':'result','data':result.get('result')}
    except Exception as e:
        trace('A','operation_failed',error=type(e).__name__)
        sessions[sid]['view']={'type':'error','message':str(e) if isinstance(e,ValueError) else 'Service request failed. Check both services and retry.'}
    return sessions[sid]['view']
@app.get('/',response_class=HTMLResponse)
def home(request:Request):
    sid=request.cookies.get('sid')
    if sid not in sessions: sid=secrets.token_urlsafe(32); sessions[sid]={'view':{'type':'ready'}}
    response=HTMLResponse(Path('web/index.html').read_text(encoding='utf-8')); response.set_cookie('sid',sid,httponly=True,samesite='lax',max_age=3600)
    return response
@app.get('/api/status')
def status(request:Request): return session(request)[1]['view']
@app.post('/api/chat')
async def chat(request:Request):
    csrf(request); sid,s=session(request)
    if s['view'].get('type') in ('consent','confirm'): raise HTTPException(409,'Complete the pending step first')
    text=(await request.json()).get('message','')[:2000]
    if not os.getenv('OPENROUTER_API_KEY'): raise HTTPException(503,'Set OPENROUTER_API_KEY in .env and restart A')
    today=datetime.now(ZoneInfo('Asia/Dubai')).date()
    async with httpx.AsyncClient(timeout=30) as client:
        r=await client.post('https://openrouter.ai/api/v1/chat/completions',headers={'Authorization':'Bearer '+os.environ['OPENROUTER_API_KEY']},json={'model':os.getenv('OPENROUTER_MODEL','google/gemini-2.5-flash-lite'),'temperature':0,'response_format':{'type':'json_object'},'messages':[{'role':'system','content':f'Extract flight intent as JSON: action (book or cancel), origin IATA, destination IATA, date YYYY-MM-DD, time HH:MM. Today is {today}. For missing booking details return action clarify and question. Do not assume departure origin. Cancellation refers to current session booking.'},{'role':'user','content':text}]})
        r.raise_for_status(); data=r.json(); intent=json.loads(data['choices'][0]['message']['content'])
        trace('A','model_usage',model=os.getenv('OPENROUTER_MODEL','google/gemini-2.5-flash-lite'),usage=data.get('usage',{}))
        card=(await client.get(B_URL+'/.well-known/agent-card.json')).json()
    if intent.get('action') not in ('book','cancel'): return {'type':'error','message':intent.get('question','Please provide origin, destination, date and departure time.')}
    if intent['action']=='book' and any(not intent.get(k) for k in ('origin','destination','date','time')): raise HTTPException(400,'Please specify route, date and departure time')
    if card.get('protocolVersion')!='0.3.0' or card.get('url')!=B_URL+'/a2a': raise HTTPException(502,'Unexpected airline card')
    s['card']=card; s['thread']=str(uuid.uuid4()); intent['key']=str(uuid.uuid4())
    return await run(sid,{'sid':sid,'intent':intent})
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
    sid,s=session(request); p=pending.pop(request.query_params.get('state',''),None)
    if not p or p['sid']!=sid or p['expires']<time.time() or p['thread']!=s.get('thread'): raise HTTPException(400,'Invalid OAuth state')
    if 'error' in request.query_params:
        s['view']={'type':'error','message':'Authorization denied; no action performed.'}; return RedirectResponse('/')
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

