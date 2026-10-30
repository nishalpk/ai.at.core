from pathlib import Path
from app.a import graph as workflow
from app.travel_agent import graph as dialogue
from app.b import graph as airline
out=Path('docs/architecture.md')
text='# Architecture\n\nActual LangGraph Mermaid exports; the conversation graph precedes the execution graph.\n'
for title,g in [('Agent A tool-calling loop',dialogue),('Agent A authorized execution',workflow),('Agent B execution',airline)]:
    text+='\n## '+title+'\n\n```mermaid\n'+g.get_graph().draw_mermaid()+'\n```\n'
text+='''
## Tool connections (dispatcher detail)

```mermaid
flowchart TD
 subgraph A[Agent A]
  AR[LLM reason] -->|native tool_calls| AD[tools dispatcher]
  AD --> AC[discover_airline]
  AD --> AS[search_flights]
  AD --> AB[book_flight]
  AD --> AX[cancel_booking]
  AC -->|Agent Card result| AR
  AS --> AW[OAuth / selection / confirmation workflow]
  AB --> AW
  AX --> AW
 end
 AW -->|A2A HTTP| BA[B verifies token and scope]
 subgraph B[Agent B]
  BA --> BR[LLM reason]
  BR -->|native tool_calls| BD[tools dispatcher]
  BD --> BI[inspect_flight]
  BD --> BS[search_inventory]
  BD --> BC[create_booking]
  BD --> BX[cancel_reservation]
  BI -->|tool result| BR
  BS --> BG[Scope / exact delegation / ownership guard]
  BC --> BG
  BX --> BG
  BG --> DB[Airline SQLite]
 end
 DB -->|canonical result| RESULT[A2A artifact to A]
```

The generated graph's single tools node dispatches individual registered functions. Their names are not separate LangGraph nodes. Conditional dotted edges reason -> tools and tools -> reason are executable routing edges. Terminal tool results leave the loop; discovery and inspection results return to the model. A's deterministic subworkflow is called by its tool handlers; it is not an unconnected replacement for the agent.
'''
text+='''
## Complete system

```mermaid
flowchart TD
 U[Browser chat and New chat button] --> A[Agent A FastAPI :8000]
 A --> J[Jev intent guard]
 J --> AR[A LangGraph reason/tools loop]
 AR --> AM[Haiku native tool calls / Gemini fallback]
 AM --> AR
 AR --> AT[Discover / search / book / cancel handlers]
 AT --> WF[Deterministic OAuth and confirmation subworkflow]
 WF --> K[Keycloak :8080 consent and PKCE]
 K --> WF
 WF --> CONF[Explicit itinerary confirmation]
 WF --> RPC[A2A JSON-RPC bearer token]
 RPC --> B[Agent B FastAPI :8001]
 B --> AUTH[Verify token and requested scope before model]
 AUTH --> BR[B LangGraph reason/tools loop]
 BR --> BM[Haiku native tool calls / Gemini fallback]
 BM --> BR
 BR --> BT[Inspect / search inventory / create / cancel tools]
 BT --> CHECK[Exact delegation match + scope + owner checks]
 CHECK --> DB[B SQLite]
 DB --> DASH[Read-only airline booking dashboard :8003]
 DB --> RESULT[Canonical tool result / A2A artifact]
 RESULT --> A
 A --> LA[A events]
 B --> LB[B events]
 LA --> LOG[Log viewer :8002 refresh and clear view]
 LB --> LOG
```

Models propose tool calls; handlers enforce capabilities and delegation. A workflow pauses for OAuth and purchase approval. B receives verified claims only in private execution context; they are excluded from model prompts. The observer reads structured events, never token stores. Both agent loops allow five model steps and one tool call per step; failures stop without widening permission.
'''
out.write_text(text,encoding='utf-8')
