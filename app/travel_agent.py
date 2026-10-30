import json,uuid
from datetime import datetime
from zoneinfo import ZoneInfo
import httpx
from app.common import B_URL
from app.models import classify
from app.tool_agent import build,tool
fields={'origin':{'type':'string','description':'Three-letter uppercase IATA code'},'destination':{'type':'string','description':'Three-letter uppercase IATA code'},'date':{'type':'string','description':'Absolute date YYYY-MM-DD, resolve relative to today'},'time':{'type':'string','description':'24-hour HH:MM, or any/daytime/morning/afternoon/evening'}}
tools=[tool('discover_airline','Discover the trusted airline capabilities.',{}),tool('search_flights','Search only. No booking. Date YYYY-MM-DD, time HH:MM or any/daytime/morning/afternoon/evening.',fields),tool('book_flight','Request booking: requires OAuth and explicit UI confirmation. Collect full route/date/time first.',fields),tool('cancel_booking','Cancel an airline booking by reference, including previous chats. B verifies signed-in user ownership and scope.',{'booking_id':{'type':'string','description':'Booking reference explicitly provided by the user or the current conversation booking reference; never invent it.'}})]
async def handle(name,args,context):
    from app import a
    sid=context['sid'];s=a.sessions[sid]
    if name=='discover_airline':
        from a2a.client import A2ACardResolver
        async with httpx.AsyncClient(timeout=15) as c:
            card=(await A2ACardResolver(c,B_URL).get_agent_card()).model_dump(mode='json',by_alias=True,exclude_none=True)
        if card.get('url')!=B_URL+'/a2a' or card.get('protocolVersion')!='0.3.0': raise ValueError('Untrusted card')
        s['card']=card
        return card,False
    if not s.get('card'): return {'error':'Discover the airline first.'},False
    if name=='book_flight' and context['label']!='book': return {'error':'User has not requested booking. Search only or ask a question.'},False
    if name=='cancel_booking':
        if context['label']!='cancel': return {'error':'No explicit cancellation request.'},False
        bid=args.get('booking_id') or s.get('booking_id')
        if not isinstance(bid,str) or not bid.strip(): return {'error':'Ask the user for their booking reference.'},False
        args={'booking_id':bid.strip()}
    action={'search_flights':'search','book_flight':'book','cancel_booking':'cancel'}[name]
    if action!='cancel':
        import re
        if set(args)!=set(fields): return {'error':'Collect route, date and time preference before calling.'},False
        if not all(re.fullmatch('[A-Z]{3}',args[k]) for k in ('origin','destination')): raise ValueError('Invalid airport')
        try:
            datetime.strptime(args['date'],'%Y-%m-%d')
            if args['time'] not in ('any','daytime','morning','afternoon','evening'): datetime.strptime(args['time'],'%H:%M')
        except ValueError:
            return {'error':'Retry with date YYYY-MM-DD and time 24-hour HH:MM, e.g. 19:00 for 7pm.'},False
    s['thread']=str(uuid.uuid4())
    view=await a.run(sid,{'sid':sid,'intent':{'action':action,**args,'key':str(uuid.uuid4())}})
    return view,True

graph=build('A',tools,handle)
async def respond(sid):
    from app import a
    s=a.sessions[sid];label=await classify(s['history'][-24:])
    prompt=f'''You are Voyage, a travel agent. Today is {datetime.now(ZoneInfo('Asia/Dubai')).date()}. Converse naturally, remember previous trip details, ask for missing details. Use discover_airline then the appropriate tool to actually search/book/cancel. For an explicit BOOK request with complete details, call book_flight directly after discovery: its deterministic handler already searches and pauses for itinerary confirmation. Do not downgrade a booking request to search_flights. Never claim a tool ran unless it did. Search requests are search only; do not book unless explicitly requested. Policy questions are not cancellation requests. Normalize city names; clarify regions like Kerala. Flexible time is any/daytime/morning/afternoon/evening. Do not infer unknown route/date. OAuth and confirmation use UI buttons, never chat approval. Classifier: {label}. Actual workflow: {json.dumps(s['view'])}. Current booking reference: {s.get('booking_id')}. A booking from a previous chat can be cancelled by its reference after airline authorization. B checks ownership; do not refer the user elsewhere just because the booking is from another chat. Ask for the reference if it is unknown.'''
    result=await graph.ainvoke({'messages':[{'role':'system','content':prompt}]+s['history'][-24:],'context':{'sid':sid,'label':label}})
    if result.get('output',{}).get('type'): return result['output']
    return a.record(s,{'type':'chat','message':result['messages'][-1].get('content') or 'What would you like to do next?'})
