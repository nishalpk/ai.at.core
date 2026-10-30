# Verification status

- Nine automated tests pass locally (Python 3.14 / Windows).
- A and B were started as separate processes and respond on ports 8000 and 8001.
- Eight-slide PPTX passed package/layout/import validation and visual review.
- Real Keycloak integration passed through HTTP form login and consent: PKCE exchange, signed token, A2A search/book, 403 on cancellation, fresh cancellation grant and successful cancellation. This does not claim a manual browser walkthrough or a live A/model run.
- Live OpenRouter extraction and the full A -> Keycloak -> B booking/confirmation/cancellation flow passed after the key was supplied. HTTP form automation exercised both initial consent and scope escalation; manual browser visual walkthrough remains separate.
- The message trace is explicitly illustrative. Capture the redacted runtime events after the real demo.

Conversational update: 12 tests pass; a live three-turn missing-details conversation reached consent, Jev classification and Claude Haiku responses were verified, and the full OAuth booking/cancellation smoke passed. The combined structured-event viewer responds on port 8002.

Flexible-time regression: 15 tests pass, including daytime readiness, selection before confirmation, and truthful empty inventory results. Live DXB-to-COK next-Monday daytime input now reaches OAuth consent rather than stopping in chat.

Search-only regression: 17 tests pass. Live exact input “search from BOM to Dubai tomorrow at 7pm” produced Jev label search and OAuth scope flights:search only. Tests verify search returns results without book_flight and classifier search cannot escalate to booking.

Native tool-agent update: 19 tests pass. Live full smoke passed with A and B making OpenRouter native tool_calls. B rejects model attempts to expand a search delegation into booking. Chat reset invalidates pending consent state without cancelling stored bookings. Browser chat now has New chat; observer has Refresh/Clear view.

Airline dashboard update: 20 tests pass. The live booking/cancellation smoke passed and port 8003 showed confirmed/cancelled events from that run. Purchase approval wording now distinguishes A user approval from B authoritative confirmation. Ledger retries are tested for duplicate prevention.

23 tests pass after cross-chat cancellation update; regression confirms explicit prior booking reference survives consent without a session booking. Existing B tests reject cancellation by another user.

Official SDK migration: a2a-sdk[http-server]==0.3.26 now provides A2A v0.3.0 transport, typed client and server lifecycle. 25 tests pass, including SDK client/server roundtrip and task ownership. Real OAuth/model booking/cancellation smoke passed after restarting the separate backends. Final benchmark ran 48 requests across classification and tool-selection comparisons; the diagnostic first run is preserved separately. Updated PPTX passed structural, layout and import checks; all eight slides were visually reviewed.

Graph connectivity audit: current A and B compiled edges contain reason -> tools, tools -> reason and terminal edges. A controlled async graph stream executed reason, tools, reason, tools and invoked both handlers. The graph connectivity/execution regression is included in the 26-test suite. Direct SVG renders are derived from compiled edges rather than hand-drawn connections.
