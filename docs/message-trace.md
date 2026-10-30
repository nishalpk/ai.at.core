# Message ownership trace

Illustrative successful sequence (not a claim of a completed live OAuth run):

| Sender → receiver | Message | Owner / reason |
|---|---|---|
| Browser → A | Book BOM → DXB tomorrow 19:00 | A interprets the request |
| A → B | GET Agent Card | B advertises skills and authorization metadata |
| A → Browser → Keycloak | Authorization request: search + book, state, PKCE challenge | Keycloak owns authentication and consent |
| Keycloak → A | Authorization code + state | A checks session binding |
| A → Keycloak | Code exchange with verifier and client authentication | Keycloak issues scoped access token |
| A → B | message/send: search_flights, Authorization: Bearer [redacted] | B verifies token and search scope |
| B → A | Completed task with flight artifact | B owns inventory |
| A → Browser | Confirm AI233 / USD 240 | User confirms concrete itinerary |
| A → B | message/send: book_flight + idempotency key | B checks book scope, stores verified owner |
| Browser → A | Cancel it | A detects missing cancel scope |
| A → Browser → Keycloak | Fresh cancellation consent | No cancellation request sent before approval |
| A → B | message/send: cancel_booking with new token | B checks cancel scope and booking ownership |

Actual redacted events are written independently to runtime/A.jsonl and runtime/B.jsonl during runs. OAuth headers, tokens, authorization codes and passwords are intentionally absent. B authorized events identify operation and verified subject.

## Recorded real-provider smoke test

The HTTP smoke test obtains tokens from Keycloak and calls the running B process. It bypasses A/model extraction. The original token received HTTP 403 for cancellation; a second authorization completed cancellation. Actual B authorization events (subject redacted):

```json
[
  {
    "time": 1793342359.1830926,
    "owner": "B",
    "event": "authorized",
    "operation": "search_flights",
    "subject": "[verified airline user]"
  },
  {
    "time": 1793342361.6089404,
    "owner": "B",
    "event": "authorized",
    "operation": "book_flight",
    "subject": "[verified airline user]"
  },
  {
    "time": 1793342370.2165606,
    "owner": "B",
    "event": "authorized",
    "operation": "cancel_booking",
    "subject": "[verified airline user]"
  }
]
```

## Full A integration verified

After configuring OpenRouter, the live HTTP form test completed model parsing, A consent, B search, itinerary confirmation, booking, a new cancellation consent, and cancellation. No scope escalation was delegated to the model. Synthetic bookings from intermediate test runs were cancelled during cleanup.

## Native agent tools

The latest live run includes A agent_model -> tool_call(discover_airline) -> tool_result -> agent_model -> tool_call(book_flight) -> OAuth pause. After consent, B agent_model proposes search_inventory; B validates the delegation, then returns a canonical result. After itinerary confirmation B agent_model proposes create_booking (optionally preceded by inspect_flight). Cancellation follows a new A cancel_booking tool proposal and consent, then B cancel_reservation. Model credentials and access tokens are excluded from prompts and log events.

## Official SDK transport update

Current execution uses A2ACardResolver/JsonRpcTransport on A and A2AStarletteApplication/DefaultRequestHandler/AirlineExecutor on B, pinned SDK 0.3.26 / protocol 0.3.0. The live smoke passed after this migration. Earlier trace descriptions remain application-level explanations; JSON-RPC envelope parsing, task/event aggregation and typed serialization are now SDK-owned.
