# API Design

## Status

**Planned (route list approved), Draft (schemas), Superseded (earlier contract).** Reconciled with Prototype 1 in Phase B0 (2026-10-18).

No HTTP API exists in the repository. `fastapi` and `uvicorn` are listed in `backend/requirements.txt` but nothing imports them. The API is built in Phase **B8**.

The Prototype 1 route list below comes from the [Prototype 1 specification](../planning/intentune-backend-prototype-implementation-spec.md) §24–§26, which calls them "suggested routes". **Request and response bodies are not defined yet.** They are designed in B8 and reconciled with the frontend service boundary in B9. Do not build a client against bodies that this document does not define.

## API Principles

- Version public routes from the beginning (`/api/v1`).
- Use nouns for resources.
- Validate all request bodies.
- Return a consistent error envelope with a request ID.
- Keep routes thin: no scoring, ranking, or persistence logic in route functions.
- Use Pydantic schemas that are separate from ORM and domain models.
- Never expose stack traces, secrets, or local filesystem paths.
- The frontend asks for audio by track ID, never by path.
- No authentication in Prototype 1 (D01).

## Base Path

```text
/api/v1
```

`GET /health` sits outside the versioned prefix.

## Prototype 1 Routes

**Planned (B8).**

```text
GET    /health

GET    /api/v1/library/tracks
POST   /api/v1/library/import
POST   /api/v1/library/sources
GET    /api/v1/library/sources
POST   /api/v1/library/rescan
GET    /api/v1/library/jobs
GET    /api/v1/tracks/{track_id}/audio

POST   /api/v1/sessions
GET    /api/v1/sessions
GET    /api/v1/sessions/{session_id}
POST   /api/v1/sessions/{session_id}/turns
POST   /api/v1/sessions/{session_id}/playback-events
POST   /api/v1/sessions/{session_id}/recommendations/{occurrence_id}/reactions

GET    /api/v1/playlists
POST   /api/v1/playlists
GET    /api/v1/playlists/{playlist_id}
PATCH  /api/v1/playlists/{playlist_id}
DELETE /api/v1/playlists/{playlist_id}
POST   /api/v1/playlists/{playlist_id}/items
DELETE /api/v1/playlists/{playlist_id}/items/{track_id}
PATCH  /api/v1/playlists/{playlist_id}/items/order
```

### Session turn variants

`POST /api/v1/sessions/{session_id}/turns` accepts these turn variants:

`initial_intent`, `refine`, `next`, `not_for_me`, `more_like_this`, `surprise_me`, `more_familiar`, `try_something_different`.

Structured `ListeningContext` is the source of truth for intent (D29). Prototype 1 may map a small, fixed set of deterministic phrases to structured changes (D30). Unrestricted natural-language parsing is deferred behind a future `IntentParser` port. Raw conversational text is not persisted by default (D33).

### Feedback events

Events recorded through playback events and reactions (B6): `LIKE`, `SAVE`, `REPLAY`, `SKIP`, `COMPLETE`, `NOT_FOR_ME`. The backend persists the raw facts (`event_type`, `played_seconds`, `duration_seconds`, `played_fraction`, `recommendation_occurrence_id`, `session_id`, timestamp) and records meaningful events, not per-second ticks. Which events travel on which route is decided in B8.

**Use cases current since B6** (`FeedbackService`, no route yet):
- **`react(session, occurrence, LIKE | SAVE | REPLAY | NOT_FOR_ME)`** matches the reactions route.
- **`report_playback(session, occurrence, SKIP | COMPLETE, played_seconds, duration_seconds)`** matches the playback-events route.
- **Each call:** it stores the raw event, applies its playback effect, and re-ranks the queue. It returns the event, its own weight, the track's interpretation, and the new session state.
- **Errors** map onto the codes below:
  - `SESSION_NOT_FOUND`;
  - `RECOMMENDATION_NOT_FOUND` for an occurrence of another session;
  - `INVALID_SESSION_TRANSITION` for an ended session, or a skip, completion, or replay of a track that never played;
  - `VALIDATION_ERROR` for missing or negative seconds, or a zero duration.

Left for B8:
- whether the frontend's Next sends a `next` turn, a SKIP playback event, or both (both are safe: a late SKIP about a finished track moves nothing);
- whether Not for me travels as a turn or a reaction (both are read together, and both move on);
- how a replay from history is sent.

### Playlists

**Use cases current since B7** (`PlaylistService`, no route yet), one per planned route:

| Route | Use case |
|---|---|
| `GET /api/v1/playlists` | `list_playlists(listener)`: oldest first, with track counts |
| `POST /api/v1/playlists` | `create_playlist(listener, name)` |
| `GET /api/v1/playlists/{playlist_id}` | `get_playlist(playlist)`: the tracks in order |
| `PATCH /api/v1/playlists/{playlist_id}` | `rename_playlist(playlist, name)` |
| `DELETE /api/v1/playlists/{playlist_id}` | `delete_playlist(playlist)` |
| `POST /api/v1/playlists/{playlist_id}/items` | `add_track(playlist, track, session_id?, occurrence_id?)`. With a session and occurrence, the add is also PLAYLIST_ADD feedback and the session's queue is re-ranked. |
| `DELETE /api/v1/playlists/{playlist_id}/items/{track_id}` | `remove_track(playlist, track)` |
| `PATCH /api/v1/playlists/{playlist_id}/items/order` | `reorder_tracks(playlist, track_ids)`: the full new order |

Errors map onto the codes below:
- `PLAYLIST_NOT_FOUND`;
- `TRACK_NOT_FOUND`;
- `CONFLICT` for a name already used by the listener or a track already in the playlist;
- `VALIDATION_ERROR` for a name that is empty or over 100 characters, an order that does not list exactly the playlist's tracks, or a session given without its occurrence;
- the session codes for an add from a recommendation.

The frontend's playlist tone is presentation and is not stored (D32). Whether the frontend's Save maps to playlist adds is B9's to settle.

### Audio serving

`GET /api/v1/tracks/{track_id}/audio`:

- verifies the track exists and its managed file is available
- resolves a safe path inside managed media only (no arbitrary file serving, no path traversal)
- sets the media type
- supports browser seeking through range requests. The installed Starlette/FastAPI behavior must be verified; if it is not enough, a tested safe range response is implemented.

## Error Format

**Planned (spec §26).**

```json
{
  "error": {
    "code": "TRACK_NOT_FOUND",
    "message": "The requested track does not exist.",
    "details": {},
    "request_id": "..."
  }
}
```

Potential codes: `VALIDATION_ERROR`, `TRACK_NOT_FOUND`, `TRACK_UNAVAILABLE`, `UNSUPPORTED_AUDIO`, `IMPORT_FAILED`, `ANALYSIS_FAILED`, `SESSION_NOT_FOUND`, `RECOMMENDATION_NOT_FOUND`, `PLAYLIST_NOT_FOUND`, `INVALID_SESSION_TRANSITION`, `CONFLICT`, `RECOMMENDATION_UNAVAILABLE`, `INTERNAL_ERROR`.

## Status Codes

**Draft (from the earlier contract).** The mapping from the Prototype 1 error codes above to HTTP status codes, including codes the earlier draft did not cover (such as `CONFLICT` and audio range errors), is decided in B8.

- `200 OK`: successful read or recommendation
- `201 Created`: resource or event stored
- `400 Bad Request`: malformed request
- `404 Not Found`: referenced resource missing
- `422 Unprocessable Entity`: schema validation failure
- `500 Internal Server Error`: unexpected server failure
- `503 Service Unavailable`: required dependency unavailable

`429 Too Many Requests` (rate limit) and `502 Bad Gateway` (external provider failure) from the earlier draft relate to public deployment and external providers. They are **Future**.

## Frontend Contract Alignment

**Open, to be resolved in B8/B9.** The frontend's current `SessionService` (see [frontend architecture](../frontend/ARCHITECTURE.md) §23 and `frontend/src/features/session/sessionService.ts`) and the Prototype 1 routes differ:

- The frontend sends starters, quick actions, and typed text as one `message` kind with free text. The spec uses named turn variants. Something must map one to the other without the React UI parsing language.
- Frontend intent is categorical (mood, genre, and a five-level energy scale). `ListeningContext` uses numeric targets (for example `target_energy` from 0.0 to 1.0) plus temporary genre and mood lists.
- Like, Save, Replay, and playlist creation are local-only in the frontend, and its service interface has no methods for reactions, playback events, or playlist CRUD.
- The frontend has no real playback, so it cannot yet report played seconds.
- The frontend shows one hero and at most one Up Next peek. The backend keeps three candidates.
- The frontend needs artwork URLs. The route list has no artwork route.
- The frontend never shows scores, ranks, or confidence. Current backend reasons include points (for example `genre match (+3.0)`).

## Superseded: Pre-Prototype 1 Draft Contract

**Superseded by the Prototype 1 routes above.** Kept for history. The profile-based recommendation request and the like/dislike/skip/save/open feedback set are replaced by sessions, turns, playback events, and reactions. The example response also exposed numeric scores and match levels, which the approved frontend does not show.

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

### `POST /api/v1/feedback`

Planned request:

```json
{
  "recommendation_request_id": "generated-id",
  "candidate_id": "9",
  "action": "like"
}
```

Allowed initial actions: `like`, `dislike`, `skip`, `save`, `open`.

### `GET /api/v1/catalog/candidates`

This route may be included for development or administrative use. It should not automatically expose every internal field in production.

### `POST /api/v1/intents/parse`

**Future.** Purpose: Convert a user message into a validated structured intent. Deferred with LLM intent parsing (D30, D39).

## Open Decisions

- Request and response schemas for every Prototype 1 route (B8)
- Which feedback events travel as playback events and which as reactions (B8)
- How the frontend's message, quick-action, and refine requests map to turn variants (B8/B9)
- Whether and how artwork is served (B2/B8)
- Maximum list sizes and pagination for tracks, sessions, and jobs (B8)

Resolved by Prototype 1:

- Session identity: one generated local listener, no accounts (D01).
- Authentication for Prototype 1: none (D01). Authentication for a public release remains Future.
- Recommendations: computed per session and recorded as recommendation occurrences (spec §9).
