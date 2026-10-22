# Security and Privacy

## Status

**Draft, with Prototype 1 requirements Planned.** Reconciled with Prototype 1 in Phase B0 (2026-10-18); the feedback section was updated in B6 (2026-10-20) and B7 (2026-10-21), and the requirements, logging, and library sections in B8 (2026-10-21).

## Prototype 1 Requirements

**Planned (spec §27, execution guide §15).** Required even though Prototype 1 is local and personal:

| Requirement | Status at B0 |
|---|---|
| No secrets committed | **Current:** `.env` is gitignored; only `backend/.env.example` is committed, with no secret values |
| Database and managed media gitignored | **Current (2026-10-18):** `.gitignore` covers `backend/data/intentune.db*` (including SQLite journal, WAL, and SHM files) and `backend/data/media/`. Since B1 (2026-10-19) the database defaults to that ignored path, and tests use temporary files only. An older local `backend/.env` may still point at `backend/intentune.db`, which is not ignored. B1 does not load `.env`, but that line should be updated before anything does. *(B8: the API still does not load `.env`; a tool that does, such as `uvicorn --env-file`, would use that line.)* **Fixed (2026-10-21, after B8):** the local `.env` now points at the canonical `backend/data/intentune.db`, and `.gitignore` also covers `backend/intentune.db*`, so a database created at the old location cannot be committed. |
| No arbitrary file serving; path traversal prevention | **Partly current (B2):** managed paths are built only from a validated UUID and an allowlisted format. Source-relative paths are validated so they cannot escape their folder, and are re-checked against the real location. The scanner follows no links and enters no folder outside the source (including Windows junctions). **Current (B8):** audio is served by track ID only. The track must exist and be playable, and its managed copy is located from the validated id and format, so no client input reaches a path. Path-like ids (`..%2F..`, `C:%5C...`) name no track, and tests show they reach no file. |
| Allowlisted audio formats; file-size limits | **Current (B2):** MP3, M4A, FLAC, Ogg, Opus, and WAV, confirmed by content, not extension; 1 GiB per file by default |
| Generated managed filenames (UUID-based) | **Current (B2):** `<track_uuid>.<extension>`; source file names are never used for storage |
| No raw local paths in API responses or errors | **Current (B8):** sources are shown by folder name, tracks by file name, and no body or error carries a path. Errors that name resources use fixed messages, and a refused folder is not echoed. Tests search responses for the test folders' paths. |
| No stack traces in client errors | **Current (B8):** unexpected errors are logged on the server with the request ID and answered with a generic `500 INTERNAL_ERROR`; tests check that the exception text and traceback stay out of the response. |
| Text-length validation | **Current (B8):** context labels 1–100 characters (at most 20 genres and 20 moods), playlist names 1–100, ids at most 64, a folder path at most 4096, a playlist order at most 10,000 ids, page sizes at most 500. Unknown fields are refused, and numbers must be finite JSON numbers. *(B9: a typed message is 1–500 characters.)* |
| No raw prompt retention by default (D33) | **Current (B4):** session turns store a kind and a structured `ListeningContext` only. No session table has a text column for a prompt, and a test pins their exact columns. No use case accepts raw text. *(B8: no request body has a text field for a prompt, and unknown fields, such as a `text` on a turn, are refused.)* **B9:** typed words now reach the backend, as a `message` turn, so it can interpret them. They are interpreted and then dropped. Only the structured turn or event they lead to is stored, the words are never logged, and a refusal (`MESSAGE_NOT_UNDERSTOOD`) does not echo them. A test scans every table for a typed phrase and finds none. |
| No external sharing of imported music | Planned; Prototype 1 has no network integrations |
| No real provider network calls in ordinary tests | **Current:** no test makes a network call |

There is no authentication in Prototype 1 (D01). The API listens on `127.0.0.1` by default (`API_HOST`), so only the local machine can reach it. Browsers may call it only from the `CORS_ORIGINS` origins (default `http://localhost:5173`). Any local process can still call it, including to register a folder; that is accepted for a personal prototype. Prototype 1 is for personal, local use; licensing and distribution policy for a public release is Future work (D37).

## Security Principles

- Never commit secrets.
- Validate data at system boundaries.
- Give components only the access they need.
- Avoid collecting data without a product reason.
- Log operational information without exposing sensitive content.

## Secrets

Store these outside source control:

- AI provider API keys
- YouTube API keys
- Database credentials
- Session or authentication secrets

Local development may use a `.env` file. Commit only `.env.example` with empty placeholder names.

## Input Validation

Validate:

- Numerical ranges
- Requested result limits
- Allowed feedback actions
- Identifier formats
- Text length
- Optional URL fields
- AI structured output

## Logging

Do not log:

- API keys
- Passwords
- Authentication tokens
- Full database connection strings
- Raw private user prompts by default

Logs may include:

- Request identifier
- Route
- Status
- Duration
- Candidate count
- Provider error category

**Current (B8):** Uvicorn's access log records method, route, and status. Unexpected errors are logged with their request ID and traceback, on the server only. A traceback can include a local path; it never reaches a client. Request bodies are not logged.

## Local Music and Library Privacy

**Current (B2) for the first two points; Planned for the rest.**

- Imported audio is copied into `backend/data/media/` under generated names and stays on the device. Copies are verified by SHA-256 and never shared. Embedded tags are read locally; nothing is looked up online. *(B3)* Audio analysis reads only Intentune's managed copies, locally, with libsndfile; no audio or fingerprint leaves the device. Analysis job error messages are built from exception types and OS error text, never from file paths, so they are safe to show; the job listing (B8) shows them.
- Source folder paths are stored in the local database for rescanning (`library_sources.path`, plus source-relative paths in `source_files`). Tracks keep only the original file *name* for display, never a path. Raw local paths are never exposed to the frontend or written into client-facing errors (execution guide §1). *(B8:)* the source listing identifies a folder by its id and its own name (for example `Music`), never the full path. Registering a folder still sends its path from the client to the backend, which is how the listener names it.
- Listening history, feedback, and playlists stay in the local SQLite database.

## User Prompt Privacy

The first version should process prompts without automatically retaining them permanently. **Prototype 1 confirms this (D33):** raw conversational text is not persisted by default; structured intent is stored instead. If prompts are stored later, document:

- Why they are stored
- Retention duration
- Who can access them
- Deletion process
- Whether they are used for analytics or model improvement

## Feedback Privacy

Anonymous feedback should use random session identifiers. Avoid collecting names or email addresses unless accounts become necessary. In Prototype 1, feedback belongs to one generated local listener profile (D01), and sessions use UUIDs.

**Current (B1, 2026-10-19):** the local listener profile stores only a random UUID4, a default flag, and a UTC creation time. It holds no name, email, device identifier, or other personal data.

**Current (B6, 2026-10-20):** a feedback event stores only:
- an event type from a fixed set of six;
- the seconds played and the track's duration (a capped fraction is derived from them);
- the occurrence and session UUIDs;
- a time.

It has no text field, and no progress ticks are collected, only how a track ended.

**Current (B7, 2026-10-21):** a playlist stores a name the listener chose, trimmed and limited to 100 characters (in the domain and by a CHECK), plus its tracks' ids, positions, and when each was added. Presentation such as the frontend's colour tone is not stored (D32). Playlists stay in the local database, like the rest of the listener's data. Feedback is validated before storage: a known event type, non-negative seconds, a positive duration, and an occurrence of the same session. Feedback changes only the current session's ranking, and a Not for me is not carried into later sessions (D18).

## External Providers

*Future: Prototype 1 uses no external providers (D39).* Before enabling AI or YouTube in production, review:

- Data sent to the provider
- Provider retention rules
- API terms
- Quota limits
- Regional restrictions
- Key restrictions

## Authentication

Authentication is not required for the first private prototype. It may be required when profiles or saved history become persistent and accessible remotely. Prototype 1 has no authentication (D01); production auth, OAuth, and JWT are deferred (spec §3).

## Abuse Prevention

*Future.* A public deployment may need:

- Rate limiting
- Request-size limits
- Provider quota protection
- Input moderation for chatbot prompts
- Automated secret scanning

## Incident Response Placeholder

When the application is deployed, document:

- How to rotate a leaked key
- How to disable an external integration
- How to inspect logs
- How to notify affected users if stored data is involved
