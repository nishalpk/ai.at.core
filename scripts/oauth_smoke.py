"""Real-provider HTTP smoke test. Uses only locally generated demo credentials."""
import base64,hashlib,secrets,json,time
from html.parser import HTMLParser
from urllib.parse import urlparse,parse_qs,urljoin
import httpx
from dotenv import load_dotenv
import os
load_dotenv()
class Form(HTMLParser):
    def __init__(self): super().__init__(); self.action=None; self.fields={}
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='form': self.action=a.get('action')
        if tag=='input' and a.get('name') and a.get('type')=='hidden': self.fields[a['name']]=a.get('value','')
def grant(scopes):
    c=httpx.Client(follow_redirects=False,timeout=30)
    issuer='http://localhost:8080/realms/airline-demo'; verifier=secrets.token_urlsafe(48)
    state=secrets.token_urlsafe(32)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    r=c.get(issuer+'/protocol/openid-connect/auth',params={'client_id':'travel-agent-a','redirect_uri':'http://localhost:8000/oauth/callback','response_type':'code','scope':'openid '+scopes,'state':state,'code_challenge':challenge,'code_challenge_method':'S256','prompt':'consent'})
    form=Form(); form.feed(r.text)
    assert form.action,'Login form missing'
    fields=form.fields|{'username':'alice','password':json.load(open('runtime/demo-users.json'))['alice']}
    # Browsers treat localhost as trustworthy for Secure cookies; httpx does not.
    # This exception is confined to the local development-provider test.
    for cookie in c.cookies.jar: cookie.secure=False
    r=c.post(urljoin(issuer,form.action),data=fields)
    for _ in range(8):
        for cookie in c.cookies.jar: cookie.secure=False
        location=r.headers.get('location','')
        if location.startswith('http://localhost:8000/oauth/callback'):
            params=parse_qs(urlparse(location).query); assert params['state']==[state]
            assert 'code' in params,'Authorization denied'
            result=c.post(issuer+'/protocol/openid-connect/token',data={'grant_type':'authorization_code','client_id':'travel-agent-a','client_secret':os.environ['OAUTH_CLIENT_SECRET'],'redirect_uri':'http://localhost:8000/oauth/callback','code':params['code'][0],'code_verifier':verifier})
            result.raise_for_status(); return result.json()['access_token']
        if location: r=c.get(urljoin(issuer,location)); continue
        form=Form(); form.feed(r.text)
        
        if not form.action:
            import re
            visible=re.sub(r'<[^>]+>',' ',r.text)
            raise AssertionError('Consent page: '+re.sub(r'\s+',' ',visible)[-1800:])
        r=c.post(urljoin(issuer,form.action),data=form.fields|{'accept':'Yes'})
    raise RuntimeError('Authorization did not finish')
def rpc(token,op,args):
    return httpx.post('http://localhost:8001/a2a',headers={'Authorization':'Bearer '+token},json={'jsonrpc':'2.0','id':'smoke','method':'message/send','params':{'message':{'kind':'message','role':'user','messageId':secrets.token_hex(8),'parts':[{'kind':'data','data':{'operation':op,'args':args}}]}}},timeout=30)
def result(r):
    r.raise_for_status(); d=r.json(); assert 'error' not in d,d
    return d['result']['artifacts'][0]['parts'][0]['data']
if __name__=='__main__':
    from datetime import datetime,timedelta
    from zoneinfo import ZoneInfo
    t=grant('flights:search flights:book')
    date=(datetime.now(ZoneInfo('Asia/Dubai'))+timedelta(days=1)).date().isoformat()
    flights=result(rpc(t,'search_flights',{'origin':'BOM','destination':'DXB','date':date}))
    assert any(f['id']=='AI233' for f in flights['flights'])
    booking=result(rpc(t,'book_flight',{'flight_id':'AI233','idempotency_key':secrets.token_hex(16)}))
    args={'booking_id':booking['booking_id'],'idempotency_key':secrets.token_hex(16)}
    assert rpc(t,'cancel_booking',args).status_code==403
    upgraded=grant('flights:cancel')
    assert result(rpc(upgraded,'cancel_booking',args))['status']=='cancelled'
    print('PASS: real Keycloak login, consent, PKCE, signed token, A2A search/book, scope rejection, fresh cancel consent.')

