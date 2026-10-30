# Simplified architecture: A + B + OAuth

OAuth consent permits an action class; it does not itself create a ticket. The user approves the specific itinerary/price in A; B then independently authorizes and commits the booking. A's model cannot approve a purchase. This second approval is a deliberate demo safeguard, not an OAuth or A2A requirement.

```mermaid
flowchart TB
    U[User / browser]
    K[Keycloak: airline login and consent]
    subgraph A[Agent A - travel assistant :8000]
        C[Chat history + Jev intent guard]
        R[LLM reason and tool-calling loop]
        T[Tools: discover / search / book / cancel]
        G[Code checks required scopes]
        O[OAuth callback and server-side token store]
        P[Pause for user purchase approval]
        AC[Official A2A SDK client]
        C --> R
        R -->|tool call| T
        T -->|discovery result| R
        T --> G
        G -->|authorized search or cancellation| AC
        G -->|booking: search first| AC
        AC -->|itinerary for booking| P
        P -->|user approved: send booking| AC
        O -->|resume pending workflow| G
    end
    subgraph B[Agent B - airline :8001]
        CARD[Public Agent Card]
        V[Verify JWT and required scope]
        BR[LLM reason and tool-calling loop]
        BT[Inventory and reservation tools]
        CHECK[Exact delegation / scope / ownership checks]
        DB[(Airline SQLite: flights / bookings / events)]
        OUT[Official SDK task and result artifact]
        V --> BR
        BR -->|tool call| BT
        BT -->|inspection result| BR
        BT --> CHECK
        CHECK --> DB
        DB --> OUT
    end
    U -->|messages| C
    G -->|permission missing: redirect browser| K
    U -->|login and grant scopes| K
    K -->|authorization code via browser| O
    O -->|code exchange with PKCE and client authentication| K
    K -->|signed scoped access token| O
    U -->|Approve purchase button| P
    AC -->|A2A discovery| CARD
    AC -->|A2A JSON-RPC over HTTP + bearer token| V
    K -. public signing keys / JWKS .-> V
    OUT -->|A2A response| AC
    AC -->|display actual airline result| U
```

A uses its stored token on A2A calls. B validates it against Keycloak's keys and expected issuer/audience/client, then checks the operation scope. An insufficient grant pauses in A for fresh OAuth consent before the operation is sent. B owns all airline writes and confirmed/cancelled outcomes. Search-only never enters the purchase approval step. Cancellation needs flights:cancel and verified booking ownership, including for references from previous chats.

Both loops use Haiku with Gemini fallback. Jev classifies A's intent. Credentials are kept out of model prompts. Task dispatch and envelopes use SDK 0.3.26 / protocol 0.3.0. A and B are independent processes; observers on ports 8002/8003 are read-only and omitted from this simplified operational diagram.
