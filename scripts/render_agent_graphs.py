"""Render the actual compiled graph edges into local SVG; no manual arrows."""
from pathlib import Path
from html import escape
from app.travel_agent import graph as a
from app.b import graph as b
positions={'__start__':(270,70),'reason':(270,220),'tools':(650,220),'__end__':(270,400)}
for name,graph in [('a',a),('b',b)]:
    edges=graph.get_graph().edges
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="510" viewBox="0 0 900 510"><defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#75e2ce"/></marker></defs><rect width="900" height="510" fill="#101b2d"/>',f'<text x="40" y="35" fill="white" font-size="22" font-family="sans-serif">Agent {name.upper()} — actual compiled LangGraph edges</text>']
    for edge in edges:
        x,y=positions[edge.source];tx,ty=positions[edge.target]
        if edge.source=='reason' and edge.target=='tools':
            path='M350,200 L570,200';label=(410,181,'tool_calls')
        elif edge.source=='tools' and edge.target=='reason':
            path='M570,245 L350,245';label=(400,275,'continue with result')
        elif edge.source=='tools':
            path='M650,255 Q650,400 350,400';label=(535,395,'terminal tool result')
        else:
            path=f'M{x},{y+35} L{tx},{ty-35}';label=(x+15,(y+ty)/2,'no tool call' if edge.conditional else '')
        parts.append(f'<path d="{path}" fill="none" stroke="#75e2ce" stroke-width="2.5" marker-end="url(#arrow)"/>')
        parts.append(f'<text x="{label[0]}" y="{label[1]}" fill="#9fb6d4" font-size="14" font-family="sans-serif">{label[2]}</text>')
    for node,(x,y) in positions.items():
        parts.append(f'<rect x="{x-80}" y="{y-35}" width="160" height="70" rx="12" fill="#233751" stroke="#75e2ce"/><text x="{x}" y="{y+6}" text-anchor="middle" fill="white" font-size="20" font-family="sans-serif">{escape(node)}</text>')
    parts.append('<text x="40" y="475" fill="#9fb6d4" font-size="14" font-family="sans-serif">Source: graph.get_graph().edges. Conditional edges execute at runtime.</text></svg>')
    Path(f'docs/agent-{name}-graph.svg').write_text(''.join(parts),encoding='utf-8')
    Path(f'docs/agent-{name}-graph.mmd').write_text(graph.get_graph().draw_mermaid(),encoding='utf-8')
    print(name,[(e.source,e.target) for e in edges])
