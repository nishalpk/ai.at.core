import time,uuid
import pytest,jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from app import b,security
from app.store import Store
@pytest.fixture
def env(tmp_path,monkeypatch):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    class Keys:
        def get_signing_key_from_jwt(self,token):
            class K: pass
            k=K(); k.key=key.public_key(); return k
    monkeypatch.setattr(security,'jwks',Keys())
    monkeypatch.setattr(b,'store',Store(str(tmp_path/'b.sqlite')))
    from app import tool_agent
    async def model(owner,messages,tools):
        import json
        request=json.loads(messages[-1]['content'])
        name={'search_flights':'search_inventory','book_flight':'create_booking','cancel_booking':'cancel_reservation'}[request['operation']]
        return {'role':'assistant','content':None,'tool_calls':[{'id':'t','type':'function','function':{'name':name,'arguments':json.dumps(request['args'])}}]}
    monkeypatch.setattr(tool_agent,'completion',model)
    return TestClient(b.app),key

def token(key,**changes):
    claims={'iss':security.ISSUER,'sub':'alice','azp':security.CLIENT,'aud':'airline-agent-b','iat':int(time.time()),'exp':int(time.time())+300,'scope':'flights:search flights:book'}
    claims.update(changes)
    return jwt.encode(claims,key,algorithm='RS256')
def call(client,t,op,args):
    return client.post('/a2a',headers={'Authorization':'Bearer '+t},json={'jsonrpc':'2.0','id':'1','method':'message/send','params':{'message':{'kind':'message','role':'user','messageId':str(uuid.uuid4()),'parts':[{'kind':'data','data':{'operation':op,'args':args}}]}}})
def data(r): return r.json()['result']['artifacts'][0]['parts'][0]['data']
def test_booking_scope_owner_idempotency(env):
    client,key=env; t=token(key)
    args={'flight_id':'AI233','idempotency_key':'one'}
    first=data(call(client,t,'book_flight',args))
    assert data(call(client,t,'book_flight',args))==first
    cancel={'booking_id':first['booking_id'],'idempotency_key':'cancel'}
    assert call(client,t,'cancel_booking',cancel).status_code==403
    other=token(key,sub='bob',scope='flights:cancel')
    assert 'error' in call(client,other,'cancel_booking',cancel).json()
    approved=token(key,scope='flights:cancel')
    assert data(call(client,approved,'cancel_booking',cancel))['status']=='cancelled'
    assert data(call(client,approved,'cancel_booking',cancel))['status']=='cancelled'
@pytest.mark.parametrize('changes',[{'exp':1},{'aud':'wrong'},{'iss':'wrong'},{'azp':'wrong'},{'sub':''}])
def test_bad_claims(env,changes):
    client,key=env
    assert call(client,token(key,**changes),'book_flight',{'flight_id':'AI233','idempotency_key':'x'}).status_code==401

def test_forged_and_missing(env):
    client,key=env
    assert client.post('/a2a',json={}).status_code==401
    other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    assert call(client,token(other),'book_flight',{}).status_code==401

def test_oauth_state_and_a_pause(monkeypatch):
    from app import a
    client=TestClient(a.app); client.get('/')
    assert client.get('/oauth/callback?state=bad').status_code==400
    sid=client.cookies['sid']; s=a.sessions[sid]; s['thread']='test'
    import asyncio
    result=asyncio.run(a.run(sid,{'sid':sid,'intent':{'action':'cancel','key':'x'}}))
    assert result['type']=='consent'
    assert result['scopes']==['flights:cancel']
    assert client.post('/api/confirm',json={'approve':True}).status_code==403
import asyncio

def test_a_booking_and_cancel_pause(monkeypatch):
    from app import a
    sid='graph-test'; a.sessions[sid]={'thread':'booking-test','claims':{'exp':time.time()+300,'scope':'flights:search flights:book'}}
    calls=[]
    async def remote(s,op,args):
        calls.append(op)
        if op=='search_flights': return {'flights':[{'origin':'BOM','destination':'DXB','date':'2026-10-31','id':'AI233','depart':'19:00','seats_left':4,'price_usd':240}]}
        return {'booking_id':'booking-1','status':'confirmed'}
    monkeypatch.setattr(a,'call_b',remote)
    intent={'action':'book','origin':'BOM','destination':'DXB','date':'2026-10-31','time':'19:00','key':'key'}
    result=asyncio.run(a.run(sid,{'sid':sid,'intent':intent}))
    assert result['type']=='confirm'
    assert calls==['search_flights']
    result=asyncio.run(a.run(sid,a.Command(resume=True)))
    assert result['data']['booking_id']=='booking-1'
    a.sessions[sid]['thread']='cancel-test'
    result=asyncio.run(a.run(sid,{'sid':sid,'intent':{'action':'cancel','key':'c'}}))
    assert result['type']=='consent'
    assert calls==['search_flights','book_flight']

def test_dialogue_history_and_no_execution(monkeypatch):
    from app import dialogue
    seen=[]
    async def route(history): return 'book'
    async def generate(role,messages):
        seen.extend(messages)
        return {'intent':{'action':'book','origin':'BOM','destination':'DXB','date':None,'time':None},'message':'What date would you like to fly?'}
    monkeypatch.setattr(dialogue,'classify',route);monkeypatch.setattr(dialogue,'generate',generate)
    history=[{'role':'user','content':'Dubai please'},{'role':'assistant','content':'Where from?'},{'role':'user','content':'Mumbai'}]
    result=asyncio.run(dialogue.graph.ainvoke({'history':history,'draft':{}}))
    assert result['ready'] is False
    assert seen[1:]==history
    assert result['intent']['destination']=='DXB'

def test_policy_question_cannot_cancel(monkeypatch):
    from app import dialogue
    async def route(history): return 'chat'
    async def generate(role,messages): return {'intent':{'action':'cancel'},'message':'Here is how permission works.'}
    monkeypatch.setattr(dialogue,'classify',route);monkeypatch.setattr(dialogue,'generate',generate)
    result=asyncio.run(dialogue.graph.ainvoke({'history':[{'role':'user','content':'How does cancellation work?'}],'draft':{}}))
    assert not result['ready']

def test_log_redaction():
    from app.logs import app
    events=TestClient(app).get('/api/logs').json()
    assert all('subject' not in e and 'token' not in e for e in events)

def test_flexible_time_reaches_consent(monkeypatch):
    from app import dialogue
    async def route(h): return 'book'
    async def generate(role,messages): return {'intent':{'action':'book','origin':'DXB','destination':'COK','date':'2026-11-02','time':'daytime'},'message':'Checking'}
    monkeypatch.setattr(dialogue,'classify',route);monkeypatch.setattr(dialogue,'generate',generate)
    turn=asyncio.run(dialogue.graph.ainvoke({'history':[],'draft':{}}))
    assert turn['ready']

def test_anytime_selects_then_confirms(monkeypatch):
    from app import a
    sid='flexible-test';a.sessions[sid]={'thread':'flexible-thread','claims':{'exp':time.time()+300,'scope':'flights:search flights:book'}}
    calls=[]
    async def remote(s,op,args):
        calls.append(op)
        return {'flights':[{'id':i,'origin':'BOM','destination':'DXB','date':'2026-10-31','depart':t,'seats_left':4,'price_usd':240} for i,t in [('one','07:00'),('two','19:00')]]}
    monkeypatch.setattr(a,'call_b',remote)
    intent={'action':'book','origin':'BOM','destination':'DXB','date':'2026-10-31','time':'any','key':'k'}
    view=asyncio.run(a.run(sid,{'sid':sid,'intent':intent}))
    assert view['type']=='select'
    view=asyncio.run(a.run(sid,a.Command(resume='two')))
    assert view['type']=='confirm' and view['flight']['id']=='two'
    assert 'book_flight' not in calls

def test_no_inventory_reports_actual_result(monkeypatch):
    from app import a
    sid='empty-test';a.sessions[sid]={'thread':'empty-thread','claims':{'exp':time.time()+300,'scope':'flights:search flights:book'}}
    async def remote(s,op,args): return {'flights':[]}
    monkeypatch.setattr(a,'call_b',remote)
    view=asyncio.run(a.run(sid,{'sid':sid,'intent':{'action':'book','origin':'DXB','destination':'COK','date':'2026-11-02','time':'daytime'}}))
    assert view['type']=='error' and 'no available flights' in view['message']

def test_search_only_scope_and_no_booking(monkeypatch):
    from app import a
    sid='search-only';a.sessions[sid]={'thread':'search-only-thread'}
    intent={'action':'search','origin':'BOM','destination':'DXB','date':'2026-10-31','time':'19:00'}
    view=asyncio.run(a.run(sid,{'sid':sid,'intent':intent}))
    assert view['scopes']==['flights:search']
    a.sessions[sid]['claims']={'exp':time.time()+300,'scope':'flights:search'}
    calls=[]
    async def remote(s,op,args):
        calls.append(op)
        return {'flights':[{'id':'AI233','origin':'BOM','destination':'DXB','date':'2026-10-31','depart':'19:00','seats_left':4,'price_usd':240}]}
    monkeypatch.setattr(a,'call_b',remote)
    view=asyncio.run(a.run(sid,a.Command(resume=True)))
    assert view['type']=='result' and len(view['data']['flights'])==1
    assert calls==['search_flights']
    assert 'No booking has been made' in view['message']

def test_search_classifier_cannot_escalate(monkeypatch):
    from app import dialogue
    async def route(h): return 'search'
    async def generate(role,m): return {'intent':{'action':'book','origin':'BOM','destination':'DXB','date':'2026-10-31','time':'19:00'},'message':'Checking'}
    monkeypatch.setattr(dialogue,'classify',route);monkeypatch.setattr(dialogue,'generate',generate)
    turn=asyncio.run(dialogue.graph.ainvoke({'history':[],'draft':{}}))
    assert turn['intent']['action']=='search'

def test_b_rejects_model_expanding_delegation(env):
    client,key=env
    from app import tool_agent
    async def malicious(owner,messages,tools):
        return {'role':'assistant','content':None,'tool_calls':[{'id':'bad','type':'function','function':{'name':'create_booking','arguments':'{"flight_id":"AI233","idempotency_key":"bad"}'}}]}
    from unittest.mock import patch
    with patch.object(tool_agent,'completion',malicious):
        response=call(client,token(key),'search_flights',{'origin':'BOM','destination':'DXB','date':'2026-10-31'})
    assert 'error' in response.json()
    with b.store.db() as c: assert c.execute('SELECT COUNT(*) FROM bookings').fetchone()[0]==0

def test_chat_reset_invalidates_consent():
    from app import a
    client=TestClient(a.app);client.get('/')
    sid=client.cookies['sid'];a.sessions[sid]['history']=[{'role':'user','content':'old'}]
    a.sessions[sid]['booking_id']='existing-booking'
    a.pending['old-state']={'sid':sid}
    assert client.post('/api/reset',headers={'Origin':'http://localhost:8000'}).json()['history']==[]
    assert 'old-state' not in a.pending and 'booking_id' not in a.sessions[sid]

def test_booking_ledger_and_dashboard(env,monkeypatch):
    client,key=env
    from app import bookings
    from pathlib import Path
    monkeypatch.setattr(bookings,'DB',Path(b.store.path))
    args={'flight_id':'AI233','idempotency_key':'ledger'}
    reservation=data(call(client,token(key),'book_flight',args))
    call(client,token(key),'book_flight',args)
    cancel={'booking_id':reservation['booking_id'],'idempotency_key':'c'}
    call(client,token(key,scope='flights:cancel'),'cancel_booking',cancel)
    call(client,token(key,scope='flights:cancel'),'cancel_booking',cancel)
    view=TestClient(bookings.app).get('/api/bookings').json()
    assert view['bookings'][0]['status']=='cancelled'
    assert [e['event'] for e in view['events']]==['cancelled','confirmed']
    assert view['bookings'][0]['user'].startswith('user-')
    assert 'owner' not in view['bookings'][0]

def test_oauth_expired_state_can_restart_without_resuming():
    from app import a
    client=TestClient(a.app);client.get('/')
    sid=client.cookies['sid'];s=a.sessions[sid]
    s.update(thread='expiry',view={'type':'consent','url':'/oauth/start','scopes':['flights:book']})
    a.pending['expiry-test']={'sid':sid,'thread':'expiry','expires':time.time()-1,'verifier':'old'}
    r=client.get('/oauth/callback?state=expiry-test&error=temporarily_unavailable',follow_redirects=False)
    assert r.status_code==307
    assert s['view']['type']=='consent' and 'timed out' in s['view']['message']
    assert 'expiry-test' not in a.pending
    assert client.get('/oauth/start',follow_redirects=False).status_code==307
    assert client.get('/oauth/callback?state=expiry-test').status_code==400

def test_wrong_session_cannot_consume_oauth_state():
    from app import a
    first=TestClient(a.app);first.get('/');sid=first.cookies['sid']
    a.sessions[sid]['thread']='bound'
    a.pending['bound-test']={'sid':sid,'thread':'bound','expires':time.time()+300}
    other=TestClient(a.app);other.get('/')
    assert other.get('/oauth/callback?state=bound-test').status_code==400
    assert 'bound-test' in a.pending

def test_cancel_reference_after_chat_reset(monkeypatch):
    from app import a,travel_agent
    sid='old-booking-chat';a.sessions[sid]={'view':{'type':'ready'},'card':{'url':'test'}}
    view,stop=asyncio.run(travel_agent.handle('cancel_booking',{'booking_id':'previous-chat-id'},{'sid':sid,'label':'cancel'}))
    assert stop and view['scopes']==['flights:cancel']
    a.sessions[sid]['claims']={'exp':time.time()+300,'scope':'flights:cancel'}
    seen=[]
    async def remote(s,op,args):
        seen.append(args['booking_id']);return {'booking_id':args['booking_id'],'status':'cancelled'}
    monkeypatch.setattr(a,'call_b',remote)
    result=asyncio.run(a.run(sid,a.Command(resume=True)))
    assert result['data']['status']=='cancelled' and seen==['previous-chat-id']
    assert 'booking_id' not in a.sessions[sid]

def test_sdk_task_lookup_is_owner_bound(env):
    client,key=env
    booking=call(client,token(key),'book_flight',{'flight_id':'AI233','idempotency_key':'sdk-task'})
    task=booking.json()['result'];tid=task['id']
    def lookup(t): return client.post('/a2a',headers={'Authorization':'Bearer '+t},json={'jsonrpc':'2.0','id':'lookup','method':'tasks/get','params':{'id':tid}}).json()
    assert lookup(token(key))['result']['id']==tid
    assert 'error' in lookup(token(key,sub='bob'))

def test_official_sdk_client_roundtrip(env):
    client,key=env
    from a2a.client.transports.jsonrpc import JsonRpcTransport
    from a2a.types import AgentCard,MessageSendParams,Message,Part,DataPart,Role,Task
    import httpx
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=b.app),base_url='http://test',headers={'Authorization':'Bearer '+token(key)}) as c:
            card=AgentCard.model_validate((await c.get('/.well-known/agent-card.json')).json())
            card.url='http://test/a2a'
            transport=JsonRpcTransport(c,agent_card=card)
            result=await transport.send_message(MessageSendParams(message=Message(role=Role.user,message_id='sdk',parts=[Part(root=DataPart(data={'operation':'book_flight','args':{'flight_id':'AI233','idempotency_key':'sdk-client'}}))])))
            assert isinstance(result,Task) and result.artifacts[0].parts[0].root.data['status']=='confirmed'
    asyncio.run(scenario())

def test_compiled_graph_and_execution_connect_tools(monkeypatch):
    from app import tool_agent
    from app.travel_agent import graph as a_graph
    from app.b import graph as b_graph
    for graph in (a_graph,b_graph):
        edges={(e.source,e.target) for e in graph.get_graph().edges}
        assert ('reason','tools') in edges and ('tools','reason') in edges
    called=[]
    async def model(owner,messages,tools):
        name='discover' if not called else 'execute'
        return {'role':'assistant','content':None,'tool_calls':[{'id':name,'type':'function','function':{'name':name,'arguments':'{}'}}]}
    async def handler(name,args,context):
        called.append(name);return {'result':name},name=='execute'
    monkeypatch.setattr(tool_agent,'completion',model)
    graph=tool_agent.build('B',[tool_agent.tool('discover','discover',{}),tool_agent.tool('execute','execute',{})],handler)
    async def stream():
        return [list(update)[0] async for update in graph.astream({'messages':[{'role':'user','content':'test'}],'context':{}},stream_mode='updates')]
    visited=asyncio.run(stream())
    assert visited==['reason','tools','reason','tools'] and called==['discover','execute']
