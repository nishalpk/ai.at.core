from datetime import datetime
from zoneinfo import ZoneInfo
from typing import TypedDict
import json,re
from langgraph.graph import StateGraph,START,END
from app.models import classify,generate
class Turn(TypedDict,total=False):
    workflow:dict
    history:list
    draft:dict
    label:str
    intent:dict
    message:str
    ready:bool
async def route(s): return {'label':await classify(s['history'][-24:])}
async def converse(s):
    today=datetime.now(ZoneInfo('Asia/Dubai')).date().isoformat()
    prompt=f'''You are a helpful travel assistant. Today is {today}, user timezone Asia/Dubai.
Return JSON with intent (object with action search/book/cancel/chat, origin IATA, destination IATA, date YYYY-MM-DD, time HH:MM or any/daytime/morning/afternoon/evening; unknown fields null), and message (natural conversational reply).
Use the conversation and draft to collect trip details across turns; do not invent missing fields. Normalize city names to airport codes. Ask one concise follow-up for missing details. Respect explicit corrections. General questions should receive helpful answers without executing anything. You CAN search the connected airline demo through the backend after consent; never tell the user to use another booking website. The demo has limited inventory. Never infer a specific airport from a region such as Kerala: ask which airport. Never invent flight availability, prices or bookings. Never claim authorization, confirmation, booking or cancellation happened. Booking is handled separately by deterministic buttons. Search means search only, never book. Preserve search intent across follow-up details unless the user explicitly asks to book. If search has no time preference use any. If trip details are complete, say you will check the airline. If cancellation is explicit say you will check permission. Actual workflow status (authoritative; do not contradict it): {json.dumps(s.get('workflow',{}))}. Current draft: {json.dumps(s.get('draft',{}))}. Classifier hint: {s['label']}.'''
    d=await generate('dialogue',[{'role':'system','content':prompt}]+s['history'][-24:])
    intent=d.get('intent',{}); action=intent.get('action','chat')
    if action not in ('search','book','cancel','chat'): action='chat'
    # Search classification must never escalate to a booking operation.
    if s['label']=='search': action='search'
    intent['action']=action
    ready=action=='cancel' and s['label']=='cancel'
    if action in ('search','book'):
        ready=all(isinstance(intent.get(k),str) and intent[k] for k in ('origin','destination','date','time'))
        if ready:
            try:
                datetime.strptime(intent['date'],'%Y-%m-%d')
                if intent['time'] not in ('any','daytime','morning','afternoon','evening'): datetime.strptime(intent['time'],'%H:%M')
                ready=all(re.fullmatch('[A-Z]{3}',intent[k]) for k in ('origin','destination'))
            except ValueError: ready=False
    if action in ('search','book') and not ready:
        missing=[k for k in ('origin','destination','date','time') if not intent.get(k)]
        if missing: d['message']='To check the airline, I still need your '+', '.join(missing)+'. Any departure time is fine if you have no preference.'
        else: d['message']='Could you clarify the departure time? You can say anytime, daytime, morning, afternoon, evening, or an exact time.'
    return {'intent':intent,'ready':bool(ready),'message':str(d.get('message') or 'Could you tell me a little more about your trip?')[:2000]}
g=StateGraph(Turn);g.add_node('classify_intent',route);g.add_node('converse_and_collect',converse);g.add_edge(START,'classify_intent');g.add_edge('classify_intent','converse_and_collect');g.add_edge('converse_and_collect',END)
graph=g.compile()
