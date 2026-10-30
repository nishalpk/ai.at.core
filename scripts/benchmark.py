"""Small reproducible live benchmark: no tools execute and no bookings are changed."""
import asyncio,json,time,statistics,random,csv
from pathlib import Path
import httpx
from app.common import *
from app.tool_agent import tool
MODELS=['anthropic/claude-haiku-4.5','google/gemini-2.5-flash-lite','qwen/qwen3-30b-a3b-instruct-2507']
CASES=[('search','Search BOM to DXB on 2026-10-31 at 19:00','search'),('book','Book BOM to DXB on 2026-10-31 at 19:00','book'),('cancel','Cancel booking old-reference-123 from my previous chat','cancel'),('policy','How do cancellations work? Do not cancel anything.','chat'),('missing','I want to book a flight to Dubai.','chat'),('followup','User: Search Dubai tomorrow. Assistant: Where from? User: Mumbai. Assistant: What time? User: Anytime. Today is 2026-10-30.','search'),('correction','User: Book BOM to DXB 2026-10-31 at 07:00. User: Actually make that 19:00.','book'),('search_only','Search BOM to DXB 2026-10-31 19:00. Do not book anything.','search')]
criteria={'search':'Search flights without booking; follow-up details for search','book':'Explicit booking request with complete route/date/time','cancel':'Explicit cancellation request, including previous chat reference','chat':'General question or incomplete request requiring clarification'}
props={k:{'type':'string'} for k in ('origin','destination','date','time')}
tools=[tool('search','Search only, no booking',props),tool('book','Request a booking with complete trip details',props),tool('cancel','Cancel by reference',{'booking_id':{'type':'string'}})]
rows=[];gate=asyncio.Semaphore(2)
async def trial(kind,model,case):
 async with gate:
  name,text,expected=case;start=time.perf_counter();row={'kind':kind,'model':model,'case':name,'expected':expected,'correct':False,'error':None,'cost_usd':None}
  try:
   headers={'Authorization':'Bearer '+os.environ['OPENROUTER_API_KEY']}
   if kind=='classification' and model.startswith('typesafe/'):
    url='https://openrouter.ai/api/alpha/decisions';payload={'model':model,'state':{'text':text},'questions':{'intent':{'type':'choice','instructions':'Classify intent. Incomplete booking requests need chat clarification.','criteria':criteria}}}
   else:
    url='https://openrouter.ai/api/v1/chat/completions'
    system='Today is 2026-10-30. Normalize Mumbai=BOM, Dubai=DXB. Resolve tomorrow to 2026-10-31. Never invent missing details.'
    payload={'model':model,'temperature':0,'max_tokens':400,'messages':[{'role':'system','content':system},{'role':'user','content':text}]}
    if kind=='classification': payload['messages'][0]['content']+=' Classification task. Definitions: '+json.dumps(criteria)+'. Incomplete booking requests are chat. Respond with exactly one JSON object containing only the key label and one value from search, book, cancel, chat. Example: {"label":"search"}.';payload['response_format']={'type':'json_object'}
    else: payload['messages'][0]['content']+=' Use exactly one appropriate tool when details are complete, else ask a question without tools. Times must be HH:MM or any. Never book on a search-only request.';payload['tools']=tools;payload['parallel_tool_calls']=False
   async with httpx.AsyncClient(timeout=60) as c:
    r=await c.post(url,headers=headers,json=payload);r.raise_for_status();d=r.json()
   row['served_model']=d.get('model',model);row['usage']=d.get('usage',{});row['platform_cost_usd']=d.get('usage',{}).get('cost');row['byok']=d.get('usage',{}).get('is_byok',False);row['cost_usd']=d.get('usage',{}).get('cost_details',{}).get('upstream_inference_cost',row['platform_cost_usd']);row['response']=d.get('answers') or d.get('choices',[{}])[0].get('message')
   if kind=='classification':
    if model.startswith('typesafe/'): actual=d['answers']['intent']['choice']
    else:
     content=d['choices'][0]['message']['content'].strip()
     if content.startswith('```'): content=content.split('\n',1)[1].rsplit('```',1)[0]
     actual=json.loads(content)['label']
    row['actual']=actual;row['correct']=actual==expected
   else:
    m=d['choices'][0]['message'];calls=m.get('tool_calls',[]);row['actual']=calls[0]['function']['name'] if calls else 'chat'
    row['correct']=row['actual']==expected and len(calls)<=1
    if calls:
     args=json.loads(calls[0]['function']['arguments']);row['arguments']=args
     target={'booking_id':'old-reference-123'} if expected=='cancel' else {'origin':'BOM','destination':'DXB','date':'2026-10-31','time':'any' if name=='followup' else '19:00'}
     row['correct']=row['correct'] and args==target
  except Exception as e: row['error']=type(e).__name__
  row['latency_s']=round(time.perf_counter()-start,3);rows.append(row)
  print(kind,model,name,'PASS' if row['correct'] else 'FAIL',flush=True)
async def main():
 jobs=[('tools',m,c) for m in MODELS for c in CASES]+[('classification',m,c) for m in ['typesafe/jev-1.13',MODELS[0],MODELS[1]] for c in CASES]
 random.Random(42).shuffle(jobs)
 await asyncio.gather(*(trial(*j) for j in jobs))
 Path('docs/model-comparison.json').write_text(json.dumps({'date':'2026-10-30','method':'One pass per model/case; randomized order seed42, concurrency2, temperature0, max_tokens400 for chat. Provider-reported upstream inference cost when available (including BYOK), otherwise platform cost; no estimates; latency includes HTTP and provider routing. Tool schemas are simplified equivalents; tools never execute.','rows':rows},indent=2),encoding='utf-8')
 summary=[]
 for kind in ['classification','tools']:
  for model in sorted({r['model'] for r in rows if r['kind']==kind}):
   rs=[r for r in rows if r['kind']==kind and r['model']==model];costs=[r['cost_usd'] for r in rs if r['cost_usd'] is not None]
   summary.append({'kind':kind,'model':model,'correct':sum(r['correct'] for r in rs),'total':len(rs),'median_s':round(statistics.median(r['latency_s'] for r in rs),3),'mean_s':round(statistics.mean(r['latency_s'] for r in rs),3),'reported_cost_usd':round(sum(costs),8) if costs else None,'cost_coverage':len(costs),'errors':sum(r['error'] is not None for r in rs)})
 Path('docs/model-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
 print(json.dumps(summary,indent=2))
if __name__=='__main__': asyncio.run(main())
