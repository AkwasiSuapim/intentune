# External Services

## Status

**Future Draft.** Reconciled with Prototype 1 in Phase B0 (2026-10-18).

The current recommender does not require external APIs, and **Prototype 1 uses none**. It must work with AI disabled, external providers disabled, and no internet connection. AI, Spotify/YouTube catalogs, vector retrieval, and an AI DJ are deferred (D39). Ordinary tests make no provider network calls.

Everything below describes Future integrations. It is kept as design guidance for when they are approved.

## Local Libraries Used by Prototype 1 (not external services)

**Planned.** Prototype 1 analyzes the listener's own files on the device, adding each dependency only in the phase that needs it:

- `mutagen` for tags, artwork, and basic metadata (B2)
- `librosa` for deterministic signal analysis, only if needed (B3)
- pretrained audio models only in a later analysis subphase, after environment compatibility is verified, and only where validated (D19)

These run locally and send no data off the device.

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

Spotify is intentionally postponed until the core workflow is stable. Before Prototype 1, the plan was to add YouTube first; Prototype 1 defers both (D39), and their order is not decided.

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
