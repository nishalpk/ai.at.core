# Two Agents, One Task

Two separate FastAPI processes use LangGraph and a small A2A v0.3.0 JSON-RPC implementation. Keycloak supplies OAuth authorization; B independently checks signed tokens and permissions.

## Run (Windows / Python 3.12+ / Docker Desktop)

From this directory:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python scripts/setup.py
```

Setup generates random local secrets and two users. Add your OpenRouter key to `.env`. Read the generated passwords in `runtime/demo-users.json`; these are local demo credentials, not submission assets. Never rerun setup against an initialized realm. Start Docker Desktop, then:

```powershell
docker compose up -d keycloak
```

Wait for http://localhost:8080/realms/airline-demo/.well-known/openid-configuration to respond. In separate terminals:

```powershell
.venv/Scripts/python -m uvicorn app.b:app --host 127.0.0.1 --port 8001
.venv/Scripts/python -m uvicorn app.a:app --host 127.0.0.1 --port 8000
```

Alternatively `powershell -ExecutionPolicy Bypass -File scripts/start.ps1` starts both in the background and prints process IDs. Stop those IDs with `Stop-Process -Id <id>`; stop Keycloak with `docker compose down`.

Open **http://localhost:8000** (use localhost, not 127.0.0.1, in the browser).

1. Say “Book from BOM to Dubai tomorrow at 7pm”.
2. Click Authorize with airline; log in as alice using the generated password. Approve search and book.
3. Inspect AI233, departure 19:00, price USD 240; confirm the booking.
4. Say “Cancel it”. A pauses for additional consent. No cancellation is sent yet.
5. Authorize cancellation using the same airline account. The booking becomes cancelled.
6. Repeat and deny the cancellation grant to show that the booking remains active.

The input must include origin; the assistant asks for missing details. Flight times are departure-local (BOM Asia/Kolkata, DXB Asia/Dubai); relative dates use Asia/Dubai. Fixtures marked tomorrow are resolved on B's first database initialization. After a date change, stop B and remove only its disposable `runtime/b.sqlite` before restarting.

## Trust boundaries and OAuth

A is the confidential OAuth client, Keycloak the airline's authorization server, and B the resource server. A initiates consent; the user approves at Keycloak. Authorization Code + PKCE S256 uses exact callback registration, single-use state bound to the browser and pending graph, a short code exchange, and five-minute signed access tokens. No refresh tokens are requested.

A keeps tokens server-side. B verifies RS256 signature from JWKS, issuer, audience, expiry, subject and authorized client. It checks the required operation scope before invoking its graph, and again in execution. Booking owner is the verified issuer + subject, never an A-supplied user ID. A refuses an account switch during scope escalation. Keycloak optional client scopes keep cancellation out of the initial grant.

OAuth consent permits classes of actions; A's itinerary confirmation approves a specific purchase. These are distinct steps. Local HTTP and development-mode Keycloak are local-demo exceptions; production needs HTTPS, hardened Keycloak, persistent encrypted token storage, session expiry/cleanup, durable graph checkpoints, rate limits and monitoring.

## Protocol and agents

B publishes `/.well-known/agent-card.json` with its skills and OAuth flow. A discovers at a configured trusted base URL. The `/a2a` JSON-RPC endpoint implements `message/send`, `tasks/get` and terminal-task cancellation errors. `DataPart` carries application operations `search_flights`, `book_flight`, `cancel_booking`; artifacts carry results. The operation schema is our convention, not a standard airline A2A API. Tokens travel only in the HTTP Authorization header.

This is a hand-written, synchronous A2A subset using the v0.3.0 wire shapes, rather than the originally proposed SDK. It keeps the interview implementation small; full SDK conformance/interoperability is not claimed. Task cancellation is not booking cancellation. All returned tasks are terminal, and ownership protects task reads.

A's graph: consent → search → itinerary confirmation → execute. LangGraph interrupts resume the same checkpoint after browser consent/confirmation. B's graph is a small deterministic executor. Neither model decides permissions or owns the database. A and B share code definitions but no runtime database. A contacts B only over HTTP.

A uses `google/gemini-2.5-flash-lite` through OpenRouter for narrow structured intent extraction. B has no unnecessary model call. Set OPENROUTER_MODEL to compare alternatives. The default is a cost/speed hypothesis, not a measured benchmark; review A's model_usage events for usage and evaluate accuracy/latency with the actual key before presenting claims. Model/API failures fail closed.

## Verification and trace

```powershell
.venv/Scripts/python -m pytest -q --basetemp=runtime/test-tmp
```

Tests generate RSA keys, exercise B over HTTP with signed tokens, and validate A's consent pause. They do not replace a real browser/Keycloak walkthrough. Redacted runtime events appear in `runtime/A.jsonl` and `runtime/B.jsonl`. No bearer tokens or client secrets are logged. `docs/message-trace.md` describes message ownership and identifies illustrative events.

Limitations: A sessions/checkpoints and B task records are in memory; restart loses pending work. Bookings/inventory persist in B's SQLite. Run one worker per service. No payments, passenger management, refresh/revocation, arbitrary airline discovery or production deployment. Database writes use transactions; booking retries use a per-intent idempotency key. Cancellation is naturally idempotent. A requires a real model key; no silent parser fallback disguises API failure.

## Submission

Run `python scripts/package.py --id YOUR_ID` to create `YOUR_ID_challenge-4.zip`. It includes an explicit allowlist of source, docs, fixtures and the PPTX, excluding `.env`, runtime state and credentials. Review the zip before emailing it to the brief's address. The script does not send email.

References: https://a2a-protocol.org/v0.3.0/specification/ ; https://www.ietf.org/rfc/rfc9700.pdf ; https://docs.langchain.com/oss/python/langgraph/interrupts ; https://www.keycloak.org/docs/latest/server_admin/index.html

For a real Keycloak / B integration smoke test (requires the services running): `.venv/Scripts/python scripts/oauth_smoke.py`. It signs in as the generated demo user, books a seat, verifies cancellation rejection and then obtains fresh cancellation consent to clean up. It bypasses A and OpenRouter deliberately so provider/token enforcement can be tested independently.

Local verification: nine automated tests passed, and the real-provider smoke test passed. The full browser chat still needs your OpenRouter key. After adding it, stop/restart A so it reloads `.env`. See docs/verification.md.
