# API Design

## Status

**Current (B8, 2026-10-21)** for the Prototype 1 routes, bodies, status codes, and error envelope below. **Superseded** for the earlier contract at the end. Reconciled with Prototype 1 in Phase B0 (2026-10-18).

The HTTP API is `backend/src/intentune/api/`, a thin FastAPI boundary over the application layer. Run it from `backend/` with:

```bash
python -m src.intentune.api        # or: uvicorn --factory src.intentune.api.app:create_app
```

It listens on `API_HOST:API_PORT` (default `127.0.0.1:8000`). FastAPI also serves its generated OpenAPI document at `/openapi.json` and interactive docs at `/docs`.

The frontend does not call it yet. Reconciling the frontend's service boundary with these routes is B9 ([Frontend Contract Alignment](#frontend-contract-alignment)).

## API Principles

- Public routes are versioned (`/api/v1`); `GET /health` sits outside the prefix.
- Resources are nouns.
- Every request body is validated: unknown fields are rejected, numbers must be finite JSON numbers (not strings or booleans), and text has a length limit ([Validation](#validation)).
- Every error uses one envelope, with a request ID ([Errors](#errors)).
- Routes are thin. Each parses its request, calls one application use case, and maps the result. Scoring, ranking, and persistence stay in the application and domain layers. An architecture test checks that routes, schemas, views, and error handling import no persistence, adapter, or SQLAlchemy code; only the composition root (`api/container.py`, `api/settings.py`) does.
- Pydantic schemas (`api/schemas.py`) are separate from ORM and domain models. `api/views.py` maps domain objects onto them and computes nothing the domain did not decide.
- No response or error carries a stack trace, a secret, or a filesystem path. The frontend asks for audio by track ID.
- No authentication in Prototype 1 (D01). Sessions and playlists belong to the one local listener, created at startup.

## Wire Conventions

- Enumerations travel in lowercase snake_case: `not_for_me`, `queued`, `missing_managed_file`, `app_restarted`. Turn kinds and feedback events use the spec's names.
- Times are ISO 8601 in UTC (`2026-10-21T16:21:54.735291Z`).
- Ids are the domain's canonical UUID strings. An id that names nothing is a not-found error, whatever its shape.
- Lists that can grow are paged with `limit` (1 to 500, default 100) and `offset` (0 or more), and answer `{items, total, limit, offset}`. In Prototype 1 the page is cut from the full list after it is loaded, which is fine for a personal library and is revisited in B11.
- A track's audio is addressed by its `audio_url`, `/api/v1/tracks/{track_id}/audio`.

## Routes

```text
GET    /health

GET    /api/v1/library/tracks
POST   /api/v1/library/import
POST   /api/v1/library/sources
GET    /api/v1/library/sources
POST   /api/v1/library/rescan
GET    /api/v1/library/jobs
GET    /api/v1/tracks/{track_id}/audio          (and HEAD)

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

These are exactly the spec's §24 routes, plus `HEAD` on audio. Nothing else is exposed (no artwork, no session end, no queue refresh).

| Route | Use case | Success |
|---|---|---|
| `GET /health` | none: the process is serving | 200 `{"status": "ok"}` |
| `GET /library/tracks` | `LibraryService.list_tracks()`, oldest first | 200 page of tracks |
| `POST /library/sources` `{path}` | `register_source(path)`; does not scan | 201 source; **200** if the folder was already registered |
| `GET /library/sources` | `list_sources()` | 200 `{items, scanning}` |
| `POST /library/import` `{source_id}` | `LibraryScanCoordinator.scan_source()` | 200 scan report |
| `POST /library/rescan` | `rescan_library()`: every source | 200 `{reports: [...]}` |
| `GET /library/jobs?status=` | `AnalysisService.list_jobs(status)`, oldest first | 200 page of jobs |
| `GET`/`HEAD /tracks/{id}/audio` | `LibraryService.track_audio()` | 200, or 206 for a range |
| `POST /sessions` `{context}` | `ListeningService.start()`: start, then surface the first queue | 201 session state |
| `GET /sessions` | `list_sessions(listener)`, newest first | 200 page of sessions |
| `GET /sessions/{id}` | `get_session()` and `history()` | 200 session detail |
| `POST /sessions/{id}/turns` | `ListeningService.steer()`: the turn, then re-rank | 200 `{turn, state}` |
| `POST /sessions/{id}/playback-events` | `FeedbackService.report_playback()` | 201 feedback outcome |
| `POST /sessions/{id}/recommendations/{occ}/reactions` | `FeedbackService.react()` | 201 feedback outcome |
| `GET /playlists` | `list_playlists(listener)`, oldest first | 200 `{items}` with track counts |
| `POST /playlists` `{name}` | `create_playlist()` | 201 playlist |
| `GET /playlists/{id}` | `get_playlist()` | 200 playlist with its tracks |
| `PATCH /playlists/{id}` `{name}` | `rename_playlist()` | 200 playlist |
| `DELETE /playlists/{id}` | `delete_playlist()`; tracks and feedback stay | 204, no body |
| `POST /playlists/{id}/items` `{track_id, session_id?, occurrence_id?}` | `add_track()` | 201 `{playlist, feedback}` |
| `DELETE /playlists/{id}/items/{track_id}` | `remove_track()` | 200 playlist |
| `PATCH /playlists/{id}/items/order` `{track_ids}` | `reorder_tracks()`: the full new order | 200 playlist |

## Library

**Registering** a folder answers its `source_id`, `name`, `status` (`active` or `missing`), `created_at`, and `last_scanned_at`. `name` is the folder's own name (`Music`); the full path is never returned. A path that is not an existing folder Intentune may scan answers `422 VALIDATION_ERROR` with a fixed message that does not repeat the path. That includes a missing path, a file, and the managed media folder.

**Import** scans one source; **Rescan** scans all of them. Each answers its scan report: `imported` (new tracks), `duplicates`, `unchanged`, `repaired`, `unsupported`, `failed`, `missing`, `ignored`, `tag_failures`, and `source_missing`. Both run the scan inside the request, on FastAPI's thread pool. The server keeps answering other requests meanwhile, because a scan holds no long transaction. Scans never overlap: one asked for while another runs answers `409 CONFLICT`. That includes the startup scan; `GET /library/sources` reports `scanning: true` while it runs. After each scan the analysis worker is woken, so new tracks are analyzed without waiting for its idle period.

A **track** answers:

```json
{
  "track_id": "73a3ca0b-b343-43a0-a6e8-542f8f2677b5",
  "title": "Drift",
  "file_name": "01 Drift.flac",
  "artist": "Artist 1",
  "album": "B8 Check",
  "year": 2026,
  "duration_seconds": 20.0,
  "format": "flac",
  "status": "ready",
  "playable": true,
  "genres": ["Ambient"],
  "moods": [],
  "audio_url": "/api/v1/tracks/73a3ca0b-b343-43a0-a6e8-542f8f2677b5/audio"
}
```

`file_name` is the source file's name, never a folder. Absent tags stay `null` and absent labels `[]`; nothing is filled in (D21). `status` is `imported`, `analyzing`, `ready`, or `missing_managed_file`; only the last is not `playable`. Measured features (B3 signal levels) are not part of the track body.

An **analysis job** answers `job_id`, `track_id`, `kind` (`analyze_audio`), `analyzer`, `status` (`pending`, `running`, `succeeded`, `failed`, `skipped`), `attempts`, its times, `failure_reason`, and `error_message`. Job messages never contain paths (B3). `?status=` filters by one status.

## Audio Serving

`GET /api/v1/tracks/{track_id}/audio` (and `HEAD`):

- Only the track ID comes from the client. `LibraryService.track_audio()` checks the track exists and is not `missing_managed_file`, then checks that its managed copy exists. The file name is built from the validated UUID and the allowlisted format (`adapters/managed_media.py`), so no client input reaches a path. Ids that try to traverse (`..%2F..`) name no track.
- A managed copy found missing answers `409 TRACK_UNAVAILABLE`, and the track is marked `missing_managed_file`, as analysis does. A rescan that finds the same content restores it.
- The media type follows the format: `mp3` audio/mpeg, `m4a` audio/mp4, `flac` audio/flac, `wav` audio/wav, `ogg` and `opus` audio/ogg.
- **Range requests (verified on the installed Starlette 1.8.0, FastAPI 0.143.0).** Starlette's `FileResponse` already does what browser seeking needs, so no custom range code was written. Every response carries `Accept-Ranges: bytes`. A single range (`bytes=a-b`, `bytes=a-`, or a suffix `bytes=-n`) answers `206 Partial Content` with `Content-Range`, and an end past the file is clamped. Several ranges answer `multipart/byteranges`. A range starting past the end answers `416` with `Content-Range: bytes */size`, and a malformed one answers `400`. These were checked through the test client and through a real server, with real FLAC files and `curl`. `tests/test_api_audio.py` pins each behavior, so an upgrade that changes one fails there.
- The 400 and 416 replies to a bad Range header are Starlette's plain-text responses, outside the JSON envelope; media elements handle them on their own. They still carry `X-Request-ID`.
- No `Content-Disposition` is sent; the original file name is not exposed this way.

## Sessions

A **session state** answers what the session is now:

```json
{
  "session": {
    "session_id": "...", "status": "active",
    "context": {"current_mood": null, "desired_mood": "calm", "listening_goal": null, "activity": null,
                "temporary_genres": ["Ambient"], "temporary_moods": [],
                "target_energy": null, "target_danceability": null, "target_valence": null,
                "target_acousticness": null, "target_tempo_bpm": null},
    "started_at": "...", "updated_at": "...", "ended_at": null, "end_reason": null
  },
  "playing": null,
  "queue": [
    {"occurrence_id": "...", "track": {"...": "a track body"}, "status": "queued", "rank": 1, "score": 0.82,
     "algorithm": "policy-v1", "is_exploration": false, "surfaced_position": 0, "queue_position": 0,
     "surfaced_at": "...", "started_at": null, "finished_at": null}
  ]
}
```

Every occurrence carries its track. `score` is the normalized score Policy v1 stored, or `null` for a pick admitted by the explicit fallback rule or a listener replay. `surfaced_position` never changes; `queue_position` is set only while queued.

`GET /sessions/{id}` adds how the session got here, oldest first: `turns` (`sequence`, `kind`, the `context` in force after it, `occurrence_id`), every `occurrence`, and every raw `feedback_event` (`event_type`, `played_seconds`, `duration_seconds`, `played_fraction`, `occurred_at`).

**Starting** (`POST /sessions` with `{"context": {...}}`) ends the listener's previous active session (`replaced_by_new_session`), records the initial intent, and surfaces the first queue. Nothing plays yet. An empty library starts with an empty queue; that is not an error.

### Turns

`POST /sessions/{id}/turns` takes `{"kind": ..., "context"?: {...}, "occurrence_id"?: ...}` with the spec's variants:

| Kind | Body | Effect |
|---|---|---|
| `refine` | `context` (required) | replaces the context |
| `next` | `occurrence_id` optional, must be the playing one | finishes the playing track and starts the next queued one. **While nothing plays, it starts the first queued track: this is Play.** |
| `not_for_me` | `occurrence_id` optional (the playing one by default) | excludes the track for the session (D18); about the playing track, it moves on |
| `more_like_this` | `occurrence_id` optional (the playing one by default) | positive evidence |
| `surprise_me`, `more_familiar`, `try_something_different` | neither | a one-refresh steering control (B5) |
| `initial_intent` | none | refused with `409 INVALID_SESSION_TRANSITION`: the intent is set when the session starts |

After every turn the queue is re-ranked (spec §21), and the answer is `{turn, state}`. Recording the turn and re-ranking are two transactions. If the re-rank fails, the turn stays recorded and the next command re-ranks again.

Turns carry no free text. A body with any field beyond these is refused, so no raw prompt can be stored (D33). Mapping the frontend's typed messages onto turns is B9's ([alignment](#frontend-contract-alignment)).

### Feedback

Which events travel where (decided in B8):

- **`POST /sessions/{id}/playback-events`**: how a track's playback ended. Body `{occurrence_id, event_type: "skip" | "complete", played_seconds, duration_seconds}`; seconds are non-negative and the duration positive. A skip or completion of the playing track moves on. One about a track that never played answers `409`. No progress ticks are accepted (spec §22).
- **`POST /sessions/{id}/recommendations/{occurrence_id}/reactions`**: body `{reaction: "like" | "save" | "replay" | "not_for_me"}`. Not for me about the playing track moves on. Replay of a track that has played starts it again now, as a fresh occurrence with the `listener-replay` algorithm and no score.
- **Playlist adds** are recorded by `POST /playlists/{id}/items` with the recommendation's `session_id` and `occurrence_id` (below), never as a reaction.
- **Not for me and Next** may each be sent as a turn or as feedback. Both forms are read together and both move on. A late skip about a finished track moves nothing, so sending a `next` turn and a SKIP event for the same track is safe.

Each answers `201` with the stored raw event, its `event_weight` under Feedback Policy v1, the track's `interpretation` in this session (`weight`, `basis`: `explicit`, `passive`, `grace`, or `none`, `excluded`, `at`, `occurrence_id`), and the session `state` after re-ranking.

## Playlists

A **playlist** answers `playlist_id`, `name`, `created_at`, `updated_at`, and `items`, in order: each `{position, added_at, track}`, with positions from 0. The list route answers summaries with `track_count` instead of items.

Names are trimmed, 1 to 100 characters, and unique per listener (`409 CONFLICT`). A track appears at most once (`409 CONFLICT`). Removing a track moves the rest up. A new order must list exactly the playlist's tracks, each once (`422`).

Adding with `session_id` and `occurrence_id` (always together, `422` otherwise) says the track is that session's recommendation. The add is then also PLAYLIST_ADD feedback (+1.00) and re-ranks the session, and `feedback` in the answer carries the outcome (`null` for a plain add). The occurrence must be of the same track; otherwise `422`, and neither an item nor an event is stored. Nothing is ever added automatically.

## Validation

| Input | Rule |
|---|---|
| Context labels (`current_mood`, `desired_mood`, `listening_goal`, `activity`, each genre and mood) | text, trimmed, 1 to 100 characters |
| `temporary_genres`, `temporary_moods` | at most 20 each |
| `target_energy`, `target_danceability`, `target_valence`, `target_acousticness` | numbers from 0.0 to 1.0 |
| `target_tempo_bpm` | a positive number |
| `played_seconds` / `duration_seconds` | non-negative / positive numbers |
| Playlist names | trimmed, 1 to `MAX_PLAYLIST_NAME_LENGTH` (100) characters |
| Ids in bodies | at most 64 characters |
| A folder path to register | 1 to 4096 characters |
| A playlist order | at most 10,000 track ids |
| `limit` / `offset` | 1 to 500 / 0 or more |

Numbers must be JSON numbers: `"0.5"` and `true` are refused, as are NaN and infinities. Unknown fields are refused everywhere. The domain checks every value again when it builds its own objects. A domain refusal (for example a `refine` turn without a context) answers `422 VALIDATION_ERROR` with the domain's message.

## Errors

Every error answers one envelope (spec §26):

```json
{
  "error": {
    "code": "TRACK_NOT_FOUND",
    "message": "The track does not exist.",
    "details": {},
    "request_id": "40449d158eb042c28018a6345651a0ee"
  }
}
```

**Request IDs.** Every response, success or error, carries `X-Request-ID`, and an error's envelope repeats it. (CORS preflight answers, which the CORS layer gives before the request reaches the API, do not.) A client may send its own `X-Request-ID` (1 to 64 letters, digits, `.`, `_`, `-`) to correlate; anything else is replaced by a generated id. Unexpected errors are logged with the id.

**Messages** are written for the listener. Errors that name a resource use fixed messages, so they never echo ids or paths. The messages passed through (session transitions, domain validation) are the application's own and name no paths. Validation `details.errors` lists each problem's `location`, `message`, and `type`, but not the rejected value.

### Status Codes

| Status | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | the body is not valid JSON |
| 404 | `SESSION_NOT_FOUND` | no such session |
| 404 | `RECOMMENDATION_NOT_FOUND` | no such occurrence in this session (including one of another session) |
| 404 | `TRACK_NOT_FOUND` | no such track; also a track not in the playlist, with "The track is not in this playlist." |
| 404 | `PLAYLIST_NOT_FOUND` | no such playlist |
| 404 | `SOURCE_NOT_FOUND` | no such library source (a code B8 added; the spec's list is "potential") |
| 404 | `NOT_FOUND` | no such route |
| 405 | `METHOD_NOT_ALLOWED` | the route exists but not with this method; `Allow` lists the methods |
| 409 | `INVALID_SESSION_TRANSITION` | the command does not fit the session's state: it has ended, the turn has nothing to apply to, the track never played, or `initial_intent` was sent as a turn |
| 409 | `TRACK_UNAVAILABLE` | the track's managed copy is missing |
| 409 | `CONFLICT` | a playlist name already used, a track already in the playlist, or a scan already running |
| 422 | `VALIDATION_ERROR` | the request breaks a schema rule, or the domain refuses a value |
| 500 | `INTERNAL_ERROR` | anything unexpected; the details stay in the server log |

`UNSUPPORTED_AUDIO`, `IMPORT_FAILED`, and `ANALYSIS_FAILED` are not used: per-file import and analysis failures are recorded and counted in scan reports and job listings, not raised to the client (spec §7). `RECOMMENDATION_UNAVAILABLE` is not used either: an empty queue is a normal state (nothing eligible), answered as such. `503` is not used: nothing in Prototype 1 depends on an external service.

`429` (rate limit) and `502` (external provider failure) relate to public deployment and external providers. They are **Future**.

## CORS

Browser origins come from `CORS_ORIGINS` (default `http://localhost:5173`, the Vite dev server). They may use `GET`, `HEAD`, `POST`, `PATCH`, and `DELETE`, and send `Content-Type`, `Range`, and `X-Request-ID`. Responses expose `X-Request-ID`, `Content-Range`, `Accept-Ranges`, and `Content-Length` to scripts. Error responses, including the 500 envelope, carry the CORS headers, so the frontend can read them. Other origins get no CORS headers.

## Configuration and Startup

Settings come from the process environment only (`api/settings.py`): `DATABASE_URL`, `MEDIA_ROOT` (default `backend/data/media`), `CORS_ORIGINS`, `API_HOST`, and `API_PORT`. Relative paths resolve against `backend/`. **`backend/.env` is not loaded.** A tool that loads it (for example `uvicorn --env-file`) applies whatever it holds.

At startup, before any request is served:
1. the database is migrated to the latest revision;
2. the local listener is created on first run and found again after;
3. sessions a previous run left active end (`app_restarted`, D35);
4. the analysis worker starts (D28);
5. the incremental startup scan starts in the background (D25, D26).

At shutdown, the worker stops after its current job, a running scan is waited for (up to 30 seconds each), and database connections close. A startup that fails stops whatever it had started.

## Frontend Contract Alignment

**Open, to be resolved in B9.** The backend side is now fixed by the routes above. The frontend's current `SessionService` (see [frontend architecture](../frontend/ARCHITECTURE.md) §23 and `frontend/src/features/session/sessionService.ts`) differs:

- The frontend sends starters, quick actions, and typed text as one `message` kind with free text. The API takes only structured turns and contexts and stores no text (D33). B9 must map one to the other without the React UI parsing language; a small, fixed phrase mapping (D30) would sit behind a backend port, not in React.
- Frontend intent is categorical (mood, genre, and a five-level energy scale). `ListeningContext` uses numeric targets (for example `target_energy` from 0.0 to 1.0) plus temporary genre and mood lists.
- Like, Save, Replay, and playlist creation are local-only in the frontend, and its service interface has no methods for reactions, playback events, or playlist CRUD. The routes for them now exist.
- The frontend has no real playback, so it cannot yet report played seconds. Audio is now served with range support.
- The frontend shows one hero and at most one Up Next peek. The backend keeps three candidates.
- The frontend needs artwork URLs. The API serves no artwork (B2 does not extract it).
- The frontend never shows scores, ranks, or confidence. The API carries `rank` and `score` on occurrences, but no explanation text. Policy v1's reasons are not stored, so nothing is invented to fill `why`.

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

- How the frontend's message, quick-action, and refine requests map to turn variants and contexts (B9)
- Whether the frontend's Save sends playlist adds only, leaving the SAVE reaction unused (B9)
- Whether and how artwork is served (no route; B2 extracts none)
- Whether manual Import and Rescan should answer at once and scan in the background, with progress, instead of within the request ([trade-off](../decisions/trade-offs.md))
- Whether the API should expose explanation text for a recommendation; Policy v1's reasons are not stored today

Resolved in B8 (2026-10-21):

- Request and response schemas for every route: above.
- Which feedback events travel where: playback endings as playback events, reactions as reactions, playlist adds through playlist items; Next and Not for me work either way.
- Status codes for every error code, including `CONFLICT` and audio range errors: above.
- List sizes and pagination: `limit` 1 to 500 (default 100) and `offset`, for tracks, sessions, and jobs.
- Range support for audio: the installed Starlette `FileResponse`, verified and pinned by tests.

Resolved by Prototype 1:

- Session identity: one generated local listener, no accounts (D01).
- Authentication for Prototype 1: none (D01). Authentication for a public release remains Future.
- Recommendations: computed per session and recorded as recommendation occurrences (spec §9).
