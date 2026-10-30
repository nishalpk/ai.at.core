# Model comparison — 30 October 2026

One pass over eight fixed synthetic fixtures per model/task. Randomized order (seed 42), concurrency two, temperature zero. Chat output capped at 400 tokens. Latency is wall-clock HTTP/provider latency, excluding semaphore queue wait. No retries or fallback. Tools are never executed.

| Task | Model | Correct | Median seconds | Observed inference cost, USD | Cost coverage |
|---|---|---:|---:|---:|---:|
| classification | anthropic/claude-haiku-4.5 | 8/8 | 1.796 | 0.00196000 | 8/8 |
| classification | google/gemini-2.5-flash-lite | 7/8 | 1.950 | 0.00013290 | 7/8 |
| classification | typesafe/jev-1.13 | 8/8 | 1.582 | 0.00013314 | 8/8 |
| tools | anthropic/claude-haiku-4.5 | 8/8 | 2.240 | 0.00970500 | 8/8 |
| tools | google/gemini-2.5-flash-lite | 7/8 | 1.493 | 0.00033360 | 8/8 |
| tools | qwen/qwen3-30b-a3b-instruct-2507 | 6/8 | 4.349 | 0.00043569 | 8/8 |

Costs sum provider-reported upstream inference cost where available, otherwise platform cost. Haiku uses BYOK: platform charge is zero but the upstream provider cost above is nonzero. Gemini classification has one HTTP error with no usage; its cost is a partial total, not a complete bill. No estimates are substituted. These costs exclude diagnostic runs, full integration tests and future chat turns.

## Quality definition and observed failures

Classification requires the exact expected label. Tool quality requires the correct function, exact normalized arguments, one call, and no call for policy/missing-detail cases. Fixtures cover search, booking, previous-chat cancellation, policy-only questions, missing origin/date, multi-turn details, corrections, and explicit search-only boundaries. This tests a simplified single decision, not an entire agent trajectory or fluent response quality.

Gemini classification: 7 correct and one HTTP failure; no observed misclassification among the seven returned responses. Gemini tools: used unsupported time value anytime instead of any. Qwen tools: returned city names instead of IATA codes on the follow-up case and selected search for an explicit booking request. Haiku passed all eight tool cases; Jev and Haiku passed all eight classification cases.

## Selection

Keep Jev for classification: 8/8, faster median and lower observed inference cost than Haiku on these fixtures. Keep Haiku for A and B native tool reasoning: strongest observed argument/tool correctness, at a substantial premium over Gemini. Retain Gemini for availability fallback, behind the same deterministic validators; its malformed time argument illustrates why validation is necessary. Qwen is not selected: cheaper than Haiku but slower and less accurate here. B uses the same model because it needs exact tool arguments, though B-specific multi-step planning has not been benchmarked separately.

## Reproducibility and limits

Run `.venv/Scripts/python -m scripts.benchmark` with the configured key. Raw final fixtures, messages, tool proposals, usage, model IDs and timing are in model-comparison.json; aggregate data is model-summary.json. The initial diagnostic run is preserved in model-comparison-initial.json: it exposed classification prompt/schema ambiguity and BYOK accounting. The final run uses a clarified classification contract; initial and final measurements are not pooled. Prompt adjustment after diagnostics means this is not a blind holdout study. Eight cases, one repetition, provider routing, cache/BYOK differences and concurrency limit generalization. No statistical significance or production SLA is claimed.

Sources: [Official SDK](https://github.com/a2aproject/a2a-python), [A2A v0.3.0](https://a2a-protocol.org/v0.3.0/specification/), [Jev API](https://openrouter.ai/docs/guides/community/jev-tutorial).