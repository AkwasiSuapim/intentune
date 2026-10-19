# Security and Privacy

## Status

**Draft, with Prototype 1 requirements Planned.** Reconciled with Prototype 1 in Phase B0 (2026-10-18).

## Prototype 1 Requirements

**Planned (spec §27, execution guide §15).** Required even though Prototype 1 is local and personal:

| Requirement | Status at B0 |
|---|---|
| No secrets committed | **Current:** `.env` is gitignored; only `backend/.env.example` is committed, with no secret values |
| Database and managed media gitignored | **Current (2026-10-18):** `.gitignore` covers `backend/data/intentune.db*` (including SQLite journal, WAL, and SHM files) and `backend/data/media/`. Since B1 (2026-10-19) the database defaults to that ignored path, and tests use temporary files only. An older local `backend/.env` may still point at `backend/intentune.db`, which is not ignored. B1 does not load `.env`, but that line should be updated before anything does. |
| No arbitrary file serving; path traversal prevention | Planned (B8): audio is served by track ID from managed media only |
| Allowlisted audio formats; file-size limits | Planned (B2) |
| Generated managed filenames (UUID-based) | Planned (B2) |
| No raw local paths in API responses or errors | Planned (B8) |
| No stack traces in client errors | Planned (B8) |
| Text-length validation | Planned (B8) |
| No raw prompt retention by default (D33) | Planned (B4) |
| No external sharing of imported music | Planned; Prototype 1 has no network integrations |
| No real provider network calls in ordinary tests | **Current:** no test makes a network call |

There is no authentication in Prototype 1 (D01). `backend/.env.example` binds the future API to `127.0.0.1`, so it listens only on the local machine. Prototype 1 is for personal, local use; licensing and distribution policy for a public release is Future work (D37).

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

## Local Music and Library Privacy

**Planned (Prototype 1).**

- Imported audio is copied into `backend/data/media/` under generated names and stays on the device.
- Source folder paths are stored in the local database for rescanning. Raw local paths are never exposed to the frontend or written into client-facing errors (execution guide §1). How the source listing identifies folders without paths is an [open question](../planning/risks-and-open-questions.md#open-backend-questions).
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
