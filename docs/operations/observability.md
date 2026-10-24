# Observability

## Status

**Future Draft.** Reconciled with Prototype 1 in Phase B0 (2026-10-18).

Observability helps the developer understand what the system is doing after other people begin using it.

**Current:** there is no logging setup. The CLI prints to the terminal.

**Planned (Prototype 1):** every API error carries a `request_id` (spec §26). Background jobs persist their status in SQLite, which `GET /api/v1/library/jobs` exposes (B3, B8). Client responses never include raw local paths or stack traces, and logs never include secrets or raw conversational text. Metrics below that mention AI or YouTube are **Future**.

**Current (B11, 2026-10-23):** scoring latency, import and analysis throughput, SQLite latency, API latency, memory, queue response time, and restart behavior are measured offline, by `python -m evaluation.performance` (from `backend/`), on scratch databases with synthetic libraries. The app collects no metrics at runtime and has no metrics endpoint; nothing measured needed one. Results, budgets, and decisions: [Evaluation Report](../quality/evaluation-report.md) and TD-022.

## Logging

Use structured logs containing fields such as:

- Timestamp
- Log level
- Request ID
- Route or operation
- Duration
- Result count
- Catalog source
- Algorithm version
- Error category

Do not log secrets or unnecessary private prompt content.

## Metrics

Potential metrics:

- Recommendation request count
- Successful recommendation count
- Failed recommendation count
- Request duration
- Empty-result count
- Candidates processed
- Recommendations displayed
- Feedback actions by type
- AI parsing failure count
- YouTube provider failure count
- API quota-related errors

## Tracing

Distributed tracing is unnecessary for the initial monolith. A request identifier should still follow the request through logs and error responses.

## Alerts

Alerts should be introduced only for conditions that require action, such as:

- Application unavailable
- Repeated server errors
- Database unavailable
- External quota exhausted
- Unexpected latency increase

## Product Analytics

Product analytics must be separated from operational logs and governed by the privacy policy. Possible product questions include:

- Do users complete the recommendation flow?
- Which result positions receive clicks?
- Do users understand explanations?
- Which recommendation modes are useful?

## Initial Requirement

For the first invited beta, basic structured logs and error tracking are sufficient. Do not introduce an oversized monitoring platform before there is operational need.
