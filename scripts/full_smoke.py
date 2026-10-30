"""Live A → OAuth → B smoke test; books then cancels a synthetic flight."""
import json
from urllib.parse import urljoin
import httpx
from oauth_smoke import Form
c=httpx.Client(timeout=60,follow_redirects=False)
BASE='http://localhost:8000'
ORIGIN={'Origin':BASE}
def consent():
    r=c.get(BASE+'/oauth/start')
    r=c.get(r.headers['location'])
    for _ in range(10):
        for cookie in c.cookies.jar: cookie.secure=False
        location=r.headers.get('location')
        if location:
            r=c.get(urljoin('http://localhost:8080',location))
            if r.status_code>=400: raise RuntimeError('OAuth callback failed: '+str(r.status_code))
            if str(r.url).startswith(BASE+'/oauth/callback'):
                return c.get(BASE+'/api/status').json()
            continue
        form=Form();form.feed(r.text)
        if not form.action: raise RuntimeError('Expected consent form')
        fields=form.fields|({'username':'alice','password':json.load(open('runtime/demo-users.json'))['alice']} if 'name="username"' in r.text else {'accept':'Yes'})
        r=c.post(urljoin('http://localhost:8080',form.action),data=fields)
    raise RuntimeError('OAuth did not finish')
if __name__=='__main__':
    c.get(BASE+'/')
    r=c.post(BASE+'/api/chat',headers=ORIGIN,json={'message':'Book from BOM to Dubai tomorrow at 7pm'});r.raise_for_status()
    assert r.json()['type']=='consent'
    view=consent();assert view['type']=='confirm',view
    assert view['flight']['id']=='AI233'
    r=c.post(BASE+'/api/confirm',headers=ORIGIN,json={'approve':True});r.raise_for_status()
    assert r.json()['data']['status']=='confirmed',r.json()
    r=c.post(BASE+'/api/chat',headers=ORIGIN,json={'message':'Cancel it'});r.raise_for_status()
    assert r.json()['type']=='consent' and r.json()['scopes']==['flights:cancel'],r.json()
    view=consent();assert view['data']['status']=='cancelled',view
    print('PASS: live model, A consent, B search, confirmation, booking, fresh cancel consent, cancellation.')
