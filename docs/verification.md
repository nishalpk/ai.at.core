# Verification status

- Nine automated tests pass locally (Python 3.14 / Windows).
- A and B were started as separate processes and respond on ports 8000 and 8001.
- Eight-slide PPTX passed package/layout/import validation and visual review.
- Real Keycloak integration passed through HTTP form login and consent: PKCE exchange, signed token, A2A search/book, 403 on cancellation, fresh cancellation grant and successful cancellation. This does not claim a manual browser walkthrough or a live A/model run.
- Live OpenRouter extraction is not yet verified: no key was supplied. Add it to .env.
- The message trace is explicitly illustrative. Capture the redacted runtime events after the real demo.
