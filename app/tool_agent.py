"""Shared bounded LangGraph model/tool loop. Handlers remain authorization boundaries."""
import os,json,time
from typing import TypedDict
import httpx
from langgraph.graph import StateGraph,START,END
from app.common import trace
async def completion(owner,messages,tools):
    primary=os.getenv('AGENT_B_MODEL' if owner=='B' else 'DIALOGUE_MODEL','anthropic/claude-haiku-4.5')
    for model in dict.fromkeys([primary,os.getenv('FALLBACK_MODEL','google/gemini-2.5-flash-lite')]):
        try:
            async with httpx.AsyncClient(timeout=40) as c:
                r=await c.post('https://openrouter.ai/api/v1/chat/completions',headers={'Authorization':'Bearer '+os.environ['OPENROUTER_API_KEY']},json={'model':model,'messages':messages,'tools':tools,'temperature':0,'parallel_tool_calls':False})
                r.raise_for_status();d=r.json();m=d['choices'][0]['message']
                trace(owner,'agent_model',model=model,usage=d.get('usage',{}))
                return {k:v for k,v in m.items() if k in ('role','content','tool_calls')}
        except Exception as e: trace(owner,'model_fallback',model=model,error=type(e).__name__)
    raise ValueError('Agent model unavailable; no further action performed.')
def tool(name,description,properties,required=None):
    return {'type':'function','function':{'name':name,'description':description,'parameters':{'type':'object','properties':properties,'required':required or list(properties),'additionalProperties':False}}}
def build(owner,tools,handler):
    class State(TypedDict,total=False):
        messages:list
        context:dict
        count:int
        stop:bool
        output:dict
    async def reason(s):
        if s.get('count',0)>=5: raise ValueError('Agent tool budget reached')
        m=await completion(owner,s['messages'],tools)
        return {'messages':s['messages']+[m],'count':s.get('count',0)+1}
    async def act(s):
        calls=s['messages'][-1].get('tool_calls',[])
        if len(calls)!=1: raise ValueError('Exactly one tool call per step is required')
        call=calls[0];name=call['function']['name'];args=json.loads(call['function']['arguments'])
        if name not in [t['function']['name'] for t in tools]: raise ValueError('Unknown tool')
        trace(owner,'tool_call',operation=name)
        output,stop=await handler(name,args,s['context'])
        trace(owner,'tool_result',operation=name,success=True)
        return {'messages':s['messages']+[{'role':'tool','tool_call_id':call['id'],'content':json.dumps(output)}],'output':output,'stop':stop}
    g=StateGraph(State);g.add_node('reason',reason);g.add_node('tools',act);g.add_edge(START,'reason')
    g.add_conditional_edges('reason',lambda s:'tools' if s['messages'][-1].get('tool_calls') else END,{'tools':'tools',END:END})
    g.add_conditional_edges('tools',lambda s:END if s.get('stop') else 'reason',{'reason':'reason',END:END})
    return g.compile()
