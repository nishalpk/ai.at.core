import uuid
from typing import TypedDict
from fastapi import FastAPI,Request,HTTPException
from langgraph.graph import StateGraph,START,END
from app.common import *
from app.security import verify,authorize
from app.store import Store
app=FastAPI(title="Airline Agent B")
store=Store()
class State(TypedDict,total=False):
    operation:str
    args:dict
    claims:dict
    result:dict
def execute(s):
    authorize(s["claims"],SCOPES[s["operation"]])
    owner=s["claims"]["iss"]+"|"+s["claims"]["sub"]
    trace("B","authorized",operation=s["operation"],subject=s["claims"]["sub"])
    return {"result":store.run(s["operation"],s["args"],owner)}
from app.tool_agent import build,tool
import json
fields={k:{'type':'string'} for k in ('origin','destination','date','flight_id','booking_id','idempotency_key')}
tools=[tool('search_inventory','Search airline inventory.',{k:fields[k] for k in ('origin','destination','date')}),tool('create_booking','Create an authorized booking.',{k:fields[k] for k in ('flight_id','idempotency_key')}),tool('cancel_reservation','Cancel an owned booking.',{k:fields[k] for k in ('booking_id','idempotency_key')}),tool('inspect_flight','Inspect a flight before creating the delegated booking.',{'flight_id':fields['flight_id']})]
async def handle(name,args,context):
    state=context['request']
    authorize(state['claims'],SCOPES[state['operation']])
    if name=='inspect_flight':
        if state['operation']!='book_flight' or args!={'flight_id':state['args']['flight_id']}: raise ValueError('Inspection outside delegation')
        with store.db() as c:
            row=c.execute('SELECT data,seats FROM flights WHERE id=?',(args['flight_id'],)).fetchone()
        return ({'flight':json.loads(row[0]),'seats':row[1]} if row else {'error':'Flight not found'}),False
    expected={'search_flights':'search_inventory','book_flight':'create_booking','cancel_booking':'cancel_reservation'}[state['operation']]
    if name!=expected or args!=state['args']: raise ValueError('Tool call outside authorized delegation')
    return execute(state)['result'],True
agent_graph=build('B',tools,handle)
async def run_agent(state):
    # Credentials and user identity remain outside model messages.
    prompt='You are the airline agent. Fulfil this delegated operation using tools. Preserve all arguments exactly. You may inspect a flight before booking. Do not fabricate results or perform another operation.'
    result=await agent_graph.ainvoke({'messages':[{'role':'system','content':prompt},{'role':'user','content':json.dumps({'operation':state['operation'],'args':state['args']})}],'context':{'request':state}})
    if 'output' not in result: raise ValueError('Airline agent did not execute the delegated tool')
    return {'result':result['output']}
graph=agent_graph
# Official A2A SDK owns HTTP dispatch, typed envelopes and task lifecycle.
from contextvars import ContextVar
from fastapi.responses import JSONResponse
from a2a.server.apps import A2AStarletteApplication
from a2a.server.agent_execution import AgentExecutor,RequestContext
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard,Task,TaskStatus,TaskState,Artifact,Part,DataPart,InvalidParamsError,TaskNotCancelableError
from a2a.utils.errors import ServerError
identity=ContextVar('airline_identity')
class OwnedTasks(InMemoryTaskStore):
    def __init__(self): super().__init__(); self.owners={}
    async def save(self,task,context=None):
        claims=identity.get(); owner=(claims['iss'],claims['sub'])
        if task.id in self.owners and self.owners[task.id]!=owner: raise ValueError('Task owner mismatch')
        self.owners[task.id]=owner
        await super().save(task,context)
    async def get(self,task_id,context=None):
        claims=identity.get();owner=(claims['iss'],claims['sub'])
        if task_id in self.owners and self.owners[task_id]!=owner: return None
        return await super().get(task_id,context)
    async def delete(self,task_id,context=None):
        if await self.get(task_id,context):
            await super().delete(task_id,context);self.owners.pop(task_id,None)
class AirlineExecutor(AgentExecutor):
    async def execute(self,context,event_queue):
        try:
            data=next(p.root.data for p in context.message.parts if isinstance(p.root,DataPart))
            result=(await run_agent({'operation':data['operation'],'args':data['args'],'claims':identity.get()}))['result']
            await event_queue.enqueue_event(Task(id=context.task_id,context_id=context.context_id,status=TaskStatus(state=TaskState.completed),artifacts=[Artifact(artifact_id=str(uuid.uuid4()),parts=[Part(root=DataPart(data=result))])]))
        except (ValueError,KeyError,StopIteration) as e:
            raise ServerError(InvalidParamsError(message=str(e))) from e
    async def cancel(self,context,event_queue):
        raise ServerError(TaskNotCancelableError(message='Task cancellation is not booking cancellation'))
@app.middleware('http')
async def authenticate(request,call_next):
    if request.url.path!='/a2a': return await call_next(request)
    try:
        claims=verify(request.headers.get('authorization','').removeprefix('Bearer '))
        body=await request.json()
        if body.get('method') in ('message/send','message/stream'):
            msg=body.get('params',{}).get('message',{})
            data=next((p.get('data') for p in msg.get('parts',[]) if p.get('kind')=='data'),{})
            op=data.get('operation');args=data.get('args',{})
            if op not in SCOPES: return JSONResponse({'jsonrpc':'2.0','id':body.get('id'),'error':{'code':-32602,'message':'Unknown operation'}})
            authorize(claims,SCOPES[op])
            needed={'search_flights':['origin','destination','date'],'book_flight':['flight_id','idempotency_key'],'cancel_booking':['booking_id','idempotency_key']}[op]
            if not isinstance(args,dict) or any(not isinstance(args.get(k),str) or not args[k] for k in needed): return JSONResponse({'jsonrpc':'2.0','id':body.get('id'),'error':{'code':-32602,'message':'Invalid operation fields'}})
        binding=identity.set(claims)
        try: return await call_next(request)
        finally: identity.reset(binding)
    except HTTPException as e: return JSONResponse({'detail':e.detail},status_code=e.status_code,headers=e.headers)
    except ValueError: return JSONResponse({'detail':'Invalid JSON'},status_code=400)
agent_card=AgentCard.model_validate({"name":"Airline Agent","description":"Search and manage airline bookings","url":B_URL+"/a2a","version":"1.0.0","protocolVersion":"0.3.0","preferredTransport":"JSONRPC","capabilities":{"streaming":False,"pushNotifications":False},"defaultInputModes":["application/json"],"defaultOutputModes":["application/json"],"skills":[{"id":op,"name":op,"description":scope,"tags":["flights"]} for op,scope in SCOPES.items()],"securitySchemes":{"oauth":{"type":"oauth2","flows":{"authorizationCode":{"authorizationUrl":ISSUER+"/protocol/openid-connect/auth","tokenUrl":ISSUER+"/protocol/openid-connect/token","scopes":{s:s for s in SCOPES.values()}}}}},"security":[{"oauth":["flights:search"]}]})
sdk=A2AStarletteApplication(agent_card=agent_card,http_handler=DefaultRequestHandler(agent_executor=AirlineExecutor(),task_store=OwnedTasks()))
sdk.add_routes_to_app(app,rpc_url='/a2a')
