# Two Agents, One Task

Two independent FastAPI processes run bounded LangGraph tool-calling agents. A owns conversation and delegation; B owns authorization, inventory and booking outcomes. Keycloak owns login, consent and signed token issuance. A and B communicate only over A2A HTTP; only B accesses the booking database. Local observer pages are separate from that communication channel.

## Run

Requires Python 3.12+ and Docker Desktop. From this directory:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python scripts/setup.py
docker compose up -d keycloak
```

Run setup only once. It generates `.env`, the Keycloak realm and local users. Add OPENROUTER_API_KEY to `.env`; read demo passwords in `runtime/demo-users.json`. Neither file belongs in the submission. Wait for http://localhost:8080/realms/airline-demo/.well-known/openid-configuration to respond, then start all four local services:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

Or run these separately:

```powershell
.venv/Scripts/python -m uvicorn app.a:app --host 127.0.0.1 --port 8000
.venv/Scripts/python -m uvicorn app.b:app --host 127.0.0.1 --port 8001
.venv/Scripts/python -m uvicorn app.logs:app --host 127.0.0.1 --port 8002
.venv/Scripts/python -m uvicorn app.bookings:app --host 127.0.0.1 --port 8003
```

Use localhost in the browser. Chat: http://localhost:8000; events: http://localhost:8002; bookings: http://localhost:8003. Observers are unauthenticated, read-only local demo views: bind to loopback, never expose publicly. Booking users are pseudonymized. They do not send commands to either agent. Stop printed process IDs using Stop-Process; stop Keycloak with docker compose down. Restart A/B after changing model/key settings.

## Demo

1. Ask “Book from BOM to Dubai tomorrow at 7pm”. A discovers B and requests search/book consent at Keycloak. Sign in as alice using the generated password.
2. Review AI233, 19:00, USD 240. **Approve purchase** in A; B verifies the token, creates the user-owned booking and returns confirmed.
3. Say “Cancel it”. A requests fresh flights:cancel consent before contacting B to cancel.
4. Search-only requests require only flights:search and never create a booking.
5. After New chat, cancel by explicit booking reference. B still checks the verified user's ownership; the reference alone grants nothing.

A accepts exact HH:MM or any/daytime/morning/afternoon/evening. Multiple flight matches require selection then purchase approval. Empty results report B's actual inventory response; there are no Kochi flights in the supplied fixture. Tomorrow resolves when B first seeds SQLite. After a date change, stop B and remove only disposable runtime/b.sqlite to reseed. User-relative dates use Asia/Dubai; flight departure times are airport-local. New chat clears A state/token/pending callbacks without cancelling bookings or revoking Keycloak grants. Old callback links cannot be reused; expired current callbacks offer fresh authorization.

## Why A2A, and exactly what is implemented

**Protocol: A2A v0.3.0, JSON-RPC 2.0 over HTTP. Official Python package: a2a-sdk[http-server]==0.3.26.** We deliberately retain the 0.3 wire version to avoid an unrelated protocol migration while replacing custom transport code. This is not the latest SDK major release.

A2A fits cross-company task delegation: capability discovery, typed messages, task IDs and result artifacts without exposing B's internal tools or database. Plain custom REST could implement this small demo, but A2A gives those interactions a standard shape; MCP would focus on exposing tools rather than this agent-to-agent task boundary. OAuth remains a separate delegated-permission mechanism.

A uses the official A2ACardResolver and JsonRpcTransport with SDK Message/Part/DataPart models. B uses A2AStarletteApplication, DefaultRequestHandler, a custom AgentExecutor, and an ownership-aware InMemoryTaskStore. SDK code handles JSON-RPC envelopes, typed parsing and task lifecycle. B's application middleware authenticates tokens and checks scopes before SDK execution; its tools repeat authorization and enforce exact delegation arguments. Booking owner is the verified issuer + subject. Task lookup checks that same identity.

Only the synchronous feature set is used: discovery, message/send, completed Task/artifact results and tasks/get. Terminal tasks cannot be cancelled; airline booking cancellation is an application operation inside message/send. search_flights/book_flight/cancel_booking are our business schemas, not standard A2A method names. Streaming/push are advertised off. Official SDK use and SDK roundtrip tests are not a claim of independent certification or interoperability with every external agent.

[Official SDK](https://github.com/a2aproject/a2a-python) · [Pinned protocol](https://a2a-protocol.org/v0.3.0/specification/)

## OAuth and safety boundaries

Authorization Code + PKCE S256 uses single-use state bound to browser session and pending operation, exact redirect registration, and confidential client authentication. Keycloak issues short-lived tokens. A keeps them server-side. B verifies RS256 signature via JWKS, issuer, audience airline-agent-b, expiry, subject and authorized client travel-agent-a. The requested operation determines required scope. A pauses for additional consent before sending out-of-scope business requests; B rejects unauthorized direct requests independently. A's purchase button is user approval; B's transaction is authoritative confirmation.

Token claims/credentials stay outside model prompts and log files. Models propose native tools; code enforces scope, identity, ownership and transactional inventory updates. B rejects any model call whose operation/arguments differ from the delegation. Booking retries use idempotency keys; cancellations are idempotent. The event ledger records confirmations/cancellations atomically and does not duplicate retries. Historical timestamps are not invented.

## Agents and measured model choices

A uses Jev classification then a Haiku reason/tools loop: discover_airline, search_flights, book_flight, cancel_booking. Tool handlers enter a deterministic LangGraph workflow that pauses for OAuth, flight selection and purchase approval. B uses its own Haiku loop with inspect_flight, search_inventory, create_booking and cancel_reservation. Each loop allows five model steps and one tool per step. Both fail closed if primary and fallback models fail. Gemini is the fallback, with the same tool validation. The legacy app/dialogue.py extraction graph is not used by the live chat route.

Configuration: CLASSIFIER_MODEL=typesafe/jev-1.13; DIALOGUE_MODEL=anthropic/claude-haiku-4.5; AGENT_B_MODEL=anthropic/claude-haiku-4.5; FALLBACK_MODEL=google/gemini-2.5-flash-lite. The old OPENROUTER_MODEL setting is unused.

| Task | Model | Correct | Median seconds | Observed inference cost, USD | Cost coverage |
|---|---|---:|---:|---:|---:|
| classification | anthropic/claude-haiku-4.5 | 8/8 | 1.796 | 0.00196000 | 8/8 |
| classification | google/gemini-2.5-flash-lite | 7/8 | 1.950 | 0.00013290 | 7/8 |
| classification | typesafe/jev-1.13 | 8/8 | 1.582 | 0.00013314 | 8/8 |
| tools | anthropic/claude-haiku-4.5 | 8/8 | 2.240 | 0.00970500 | 8/8 |
| tools | google/gemini-2.5-flash-lite | 7/8 | 1.493 | 0.00033360 | 8/8 |
| tools | qwen/qwen3-30b-a3b-instruct-2507 | 6/8 | 4.349 | 0.00043569 | 8/8 |

The table reports one pass over eight synthetic fixtures per task, not production accuracy. Haiku was strongest on exact tool selection/arguments (8/8); Gemini was faster and much cheaper but failed the follow-up time enum (7/8). Qwen scored 6/8. Jev matched Haiku classification at lower observed latency/cost. Gemini classification had one HTTP failure, not an observed semantic misclassification. Haiku's account uses BYOK: upstream cost is reported rather than falsely treating its zero OpenRouter platform charge as free. The partial Gemini classification cost covers 7/8 calls.

See [full methodology, failures and limits](docs/model-comparison.md), [raw final measurements](docs/model-comparison.json), and [aggregate results](docs/model-summary.json). The diagnostic first run is preserved separately; it is not pooled with the final run. This small test does not measure full-agent latency or B-specific multi-step planning, and does not statistically prove model superiority.

## Checks and hand-in

```powershell
.venv/Scripts/python -m pytest -q --basetemp=runtime/test-tmp
.venv/Scripts/python scripts/full_smoke.py
.venv/Scripts/python scripts/oauth_smoke.py
.venv/Scripts/python -m scripts.benchmark
.venv/Scripts/python -m scripts.diagrams
.venv/Scripts/python scripts/package.py --id YOUR_ID
```

Tests use generated RSA keys and stub model proposals; they exercise SDK roundtrips, token rejection, task/user ownership, scopes, idempotency, delegation guards, OAuth expiry and cross-chat cancellation. Live smoke uses real models/Keycloak, books then cancels a synthetic seat. Benchmark never executes tools. It incurs small API charges and overwrites final results if rerun.

See docs/architecture.md for generated LangGraph exports and the full architecture; docs/message-trace.md for message ownership; docs/approach.pptx for the eight-slide hand-in. Packaging uses an explicit allowlist, excludes runtime credentials/.env and creates YOUR_ID_challenge-4.zip. Replace YOUR_ID with the actual submission ID. No email is sent automatically.

Limits: one worker per agent; A sessions/checkpoints and B task store are in memory. Bookings/inventory persist in SQLite. Restart loses pending conversations. Local HTTP/development Keycloak, synthetic flights, no payments, no refresh/revocation or production deployment. Production needs HTTPS, hardened identity infrastructure, durable encrypted session/token storage and operational controls.

## Simplified presentation diagram

See [A + B + OAuth in one diagram](docs/simplified-architecture.md). OAuth consent grants scoped permission; it does not purchase a specific itinerary. The user clicks Approve purchase in A after reviewing the actual flight/price. B then independently verifies authorization and commits the booking transaction. A's model cannot give this approval. This extra itinerary approval is our application safeguard, not an OAuth/A2A requirement.
