import json,secrets
from pathlib import Path
if Path('.env').exists(): raise SystemExit('Existing .env preserved; setup already initialized.')
secret=secrets.token_urlsafe(32)
scopes=[]
for name,desc in [('flights:search','Search flights'),('flights:book','Book flights'),('flights:cancel','Cancel bookings')]:
    scopes.append({'name':name,'protocol':'openid-connect','attributes':{'include.in.token.scope':'true','display.on.consent.screen':'true','consent.screen.text':desc},'protocolMappers':[]})
client={'clientId':'travel-agent-a','secret':secret,'publicClient':False,'standardFlowEnabled':True,'directAccessGrantsEnabled':False,'serviceAccountsEnabled':False,'consentRequired':True,'redirectUris':['http://localhost:8000/oauth/callback'],'defaultClientScopes':[],'optionalClientScopes':[s['name'] for s in scopes],'attributes':{'pkce.code.challenge.method':'S256'},'protocolMappers':[{'name':'airline-audience','protocol':'openid-connect','protocolMapper':'oidc-audience-mapper','config':{'included.custom.audience':'airline-agent-b','access.token.claim':'true','id.token.claim':'false'}}]}
client['protocolMappers'].append({'name': 'verified-user-subject', 'protocol': 'openid-connect', 'protocolMapper': 'oidc-usermodel-property-mapper', 'config': {'user.attribute': 'id', 'claim.name': 'sub', 'jsonType.label': 'String', 'access.token.claim': 'true', 'id.token.claim': 'true'}})
users=[]
credentials={}
for name in ('alice','bob'):
    password=secrets.token_urlsafe(16); credentials[name]=password
    users.append({'username':name,'enabled':True,'emailVerified':True,'firstName':name.title(),'lastName':'Demo','email':name+'@example.test','credentials':[{'type':'password','value':password,'temporary':False}]})
Path('runtime/keycloak').mkdir(parents=True,exist_ok=True)
realm={'realm':'airline-demo','enabled':True,'registrationAllowed':False,'accessTokenLifespan':300,'clients':[client],'clientScopes':scopes,'users':users}
Path('runtime/keycloak/realm.json').write_text(json.dumps(realm,indent=2))
Path('runtime/demo-users.json').write_text(json.dumps(credentials,indent=2))
if not Path('.env').exists(): Path('.env').write_text('OAUTH_CLIENT_SECRET='+secret+'\nOPENROUTER_API_KEY=\nOPENROUTER_MODEL=google/gemini-2.5-flash-lite\n')
else: raise SystemExit('Existing .env preserved. Do not rerun setup on an initialized realm.')
print('Generated local configuration. Demo credentials: runtime/demo-users.json. Add your model key to .env.')
