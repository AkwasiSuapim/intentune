# Observability

## Status

**Future Draft**

Observability helps the developer understand what the system is doing after other people begin using it.

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
