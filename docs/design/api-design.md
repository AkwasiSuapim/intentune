# API Design

## Status

**Draft**

No HTTP API exists in the current repository. The following contract is proposed for the first backend version.

## API Principles

- Version public routes from the beginning.
- Use nouns for resources.
- Validate all request bodies.
- Return consistent error objects.
- Keep scoring internals out of route functions.
- Do not expose secret or provider-specific data.

## Base Path

```text
/api/v1
```

## Health Endpoint

### `GET /health`

Purpose: Verify that the application process is running.

Example response:

```json
{
  "status": "ok",
  "service": "intentune",
  "version": "0.1.0"
}
```

A later readiness endpoint may check database or required provider connectivity.

## Create Recommendations

### `POST /api/v1/recommendations`

Example request:

```json
{
  "profile": {
    "preferred_genres": ["lofi", "jazz"],
    "preferred_moods": ["focused", "calm"],
    "preferred_energy": 0.4,
    "preferred_danceability": 0.3,
    "feature_weights": {
      "genre": 0.35,
      "mood": 0.35,
      "energy": 0.2,
      "danceability": 0.1
    }
  },
  "limit": 5,
  "catalog_source": "internal"
}
```

Example response:

```json
{
  "request_id": "generated-id",
  "catalog_source": "internal",
  "recommendations": [
    {
      "candidate_id": "9",
      "title": "Focus Flow",
      "creator": "LoRoom",
      "source": "internal",
      "score": 0.91,
      "match_level": "strong",
      "reasons": [
        "Preferred genre match",
        "Preferred mood match",
        "Energy is close to the requested value"
      ],
      "url": null,
      "thumbnail_url": null
    }
  ]
}
```

## Record Feedback

### `POST /api/v1/feedback`

Planned request:

```json
{
  "recommendation_request_id": "generated-id",
  "candidate_id": "9",
  "action": "like"
}
```

Allowed initial actions:

- `like`
- `dislike`
- `skip`
- `save`
- `open`

## Catalog Endpoint

### `GET /api/v1/catalog/candidates`

This route may be included for development or administrative use. It should not automatically expose every internal field in production.

## Natural-Language Intent Endpoint

### `POST /api/v1/intents/parse`

**Future**

Purpose: Convert a user message into a validated structured intent.

## Error Format

Proposed standard response:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "preferred_energy must be between 0.0 and 1.0",
    "details": {
      "field": "profile.preferred_energy"
    },
    "request_id": "generated-id"
  }
}
```

## Proposed Status Codes

- `200 OK`: successful read or recommendation
- `201 Created`: feedback event stored
- `400 Bad Request`: malformed request
- `404 Not Found`: referenced resource missing
- `422 Unprocessable Entity`: schema validation failure
- `429 Too Many Requests`: rate limit reached
- `500 Internal Server Error`: unexpected server failure
- `502 Bad Gateway`: external provider failure
- `503 Service Unavailable`: required dependency unavailable

## Open Decisions

- Whether recommendations are represented as created resources or calculated responses
- Whether session identifiers are anonymous or attached to accounts
- Maximum allowed recommendation limit
- Authentication requirements for the first public beta
