import os,json,time,re
import httpx
from app.common import trace
FALLBACK=os.getenv('FALLBACK_MODEL','google/gemini-2.5-flash-lite')
async def generate(role,messages):
    primary=FALLBACK if role=='classification fallback' else os.getenv('DIALOGUE_MODEL','anthropic/claude-haiku-4.5')
    for model in dict.fromkeys([primary,FALLBACK]):
        started=time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=35) as c:
                r=await c.post('https://openrouter.ai/api/v1/chat/completions',headers={'Authorization':'Bearer '+os.environ['OPENROUTER_API_KEY']},json={'model':model,'temperature':0.3,'response_format':{'type':'json_object'},'messages':messages})
                r.raise_for_status(); d=r.json(); content=d['choices'][0]['message']['content'].strip()
                if content.startswith('```'): content=re.sub(r'^```(?:json)?\s*|\s*```$','',content)
                answer=json.loads(content)
                if not isinstance(answer,dict): raise ValueError('Expected JSON object')
                trace('A','model_usage',role=role,model=model,latency_ms=round((time.monotonic()-started)*1000),usage=d.get('usage',{}))
                return answer
        except Exception as e:
            trace('A','model_fallback',role=role,model=model,error=type(e).__name__)
    raise ValueError('The language service is unavailable. Please try again shortly.')
async def classify(history):
    model=os.getenv('CLASSIFIER_MODEL','typesafe/jev-1.13')
    criteria={'search':'Searching or browsing flights without purchase authorization, including follow-up search details','book':'Explicit request to book or purchase a flight, or supplying details for an existing booking request','cancel':'Explicitly requesting cancellation of the current booking','chat':'Greeting, explanation or general conversation without asking to execute an operation'}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r=await c.post('https://openrouter.ai/api/alpha/decisions',headers={'Authorization':'Bearer '+os.environ['OPENROUTER_API_KEY']},json={'model':model,'state':{'conversation':history},'questions':{'intent':{'type':'choice','instructions':'Classify the latest user turn in context. Questions about cancellation policy are chat, not requests to cancel.','criteria':criteria}}})
            r.raise_for_status(); d=r.json(); a=d['answers']['intent']
            if a['choice'] not in criteria or a.get('confidence',0)<0.55: raise ValueError('Uncertain classification')
            trace('A','classification',model=model,label=a['choice'],confidence=a['confidence'],usage=d.get('usage',{}))
            return a['choice']
    except Exception as e:
        trace('A','model_fallback',role='classification',model=model,error=type(e).__name__)
        d=await generate('classification fallback',[{'role':'system','content':'Return JSON {"label":"search|book|cancel|chat"}. Classify latest user turn in context. Never treat a policy question as a cancellation request.'},{'role':'user','content':json.dumps(history)}])
        return d.get('label','chat')
