import jwt
from fastapi import HTTPException
from app.common import ISSUER,CLIENT
jwks=jwt.PyJWKClient(ISSUER+"/protocol/openid-connect/certs")
def verify(token):
    try:
        claims=jwt.decode(token,jwks.get_signing_key_from_jwt(token).key,algorithms=["RS256"],audience="airline-agent-b",issuer=ISSUER,options={"require":["exp","iat","sub","iss","aud"]})
        if not claims["sub"] or claims.get("azp")!=CLIENT: raise ValueError("Wrong client")
        return claims
    except Exception:
        raise HTTPException(401,"Invalid access token",headers={"WWW-Authenticate":"Bearer"})
def authorize(claims,scope):
    if scope not in claims.get("scope","").split():
        raise HTTPException(403,"Missing scope: "+scope,headers={"WWW-Authenticate":f'Bearer error="insufficient_scope", scope="{scope}"'})
