# External Services

## Status

**Future Draft**

The current recommender does not require external APIs.

## AI Provider

### Purpose

Convert natural-language requests into validated recommendation intent and possibly help generate grounded explanations.

### Required Interface

```text
parse_intent(message) -> structured intent
```

### Design Requirements

- Provider-specific code stays in an adapter.
- Request timeout is required.
- Output must use a strict schema.
- Output must be validated.
- Manual input remains available when AI fails.
- Tests use mocked provider responses.

### Open Decision

Which AI provider and model will be used for the first implementation.

## YouTube Data API

### Purpose

Search for real videos using generated queries and return official metadata.

### Intended Data

- Video ID
- Title
- Channel title
- Thumbnail
- Description or snippet
- Link or embed reference

### Design Requirements

- Use the official API.
- Do not scrape pages.
- Do not download music or videos.
- Restrict and protect the API key.
- Set timeouts.
- Handle quota errors.
- Deduplicate results.
- Do not claim audio properties that are unavailable.
- Use mocked API responses in tests.

## Future Spotify Integration

Spotify is intentionally postponed until YouTube integration and the core workflow are stable.

## Service Availability Strategy

External services should be treated as unreliable dependencies. The application should return controlled errors and, where appropriate, fall back to the internal catalog.

## Provider Evaluation Template

Before adding a service, document:

- Business purpose
- Required data
- Authentication method
- Cost
- Quota
- Latency
- Privacy impact
- Failure modes
- Test strategy
- Exit or replacement strategy
