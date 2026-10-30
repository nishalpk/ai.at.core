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
        if op=='search_flights': return {'flights':[{'id':'AI233','depart':'19:00','seats_left':4,'price_usd':240}]}
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
