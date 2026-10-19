# Database Design

## Status

**Planned (Prototype 1 concepts), Superseded (earlier draft).** Reconciled with Prototype 1 in Phase B0 (2026-10-18).

**Current:** the project uses no database. The only data store is `backend/data/songs.csv`. `sqlalchemy==2.1.5` and `alembic==1.20.0` are pinned in `backend/requirements.txt` and installed in the backend virtual environment (2026-10-18), but nothing imports them yet.

Persistence is built from Phase **B1** onward. This document records the approved concepts and the facts the [Prototype 1 specification](../planning/intentune-backend-prototype-implementation-spec.md) §5–§10 fixes. Exact tables, columns, types, and indexes are designed in the phase that creates them and recorded here at that time.

## Technology

**Planned (D22, D23).**

- **SQLite** for Prototype 1 (local, single listener). PostgreSQL is Future.
- **SQLAlchemy**, synchronous. No async SQLAlchemy without a measured need.
- **Alembic** for versioned migrations. Never edit tables by hand.
- UTC timestamps. SQLite foreign keys enabled. WAL mode only if verified.
- UUID identifiers. Never trust source filenames as internal storage names.
- Audio files stay **outside** SQLite, in managed media.

Location (spec §5): `backend/data/intentune.db`, with managed media in `backend/data/media/<track_uuid>.<extension>`. Both must be gitignored.

**Current (2026-10-18):** `backend/.env.example` sets `DATABASE_URL=sqlite:///./data/intentune.db`; SQLite resolves it from the working directory, so the backend must run from `backend/` (or B1 must resolve the path explicitly). `.gitignore` ignores `backend/data/intentune.db*` and `backend/data/media/`. *Found in B0 and since fixed:* the template pointed at `backend/intentune.db`, and neither path was ignored.

## Prototype 1 Concepts

**Planned.** Concept names from spec §9:

```text
listener_profiles
library_sources
tracks
track_features
track_labels
analysis_jobs

listening_sessions
session_turns
recommendation_occurrences
feedback_events

playlists
playlist_items
```

### Listener profile (B1)

No authentication in Prototype 1. One generated default local listener profile is created, instead of a hard-coded id such as `"user1"` (D01).

### Library sources and incremental scanning (B2)

Several source folders may be registered; together they form one logical library, and adding a source never replaces earlier ones (D03). For incremental scanning the spec requires persisting: source path, file size, modification time, SHA-256, import status, and analysis version (spec §5). SHA-256 identifies exact duplicates (D24).

### Tracks, features, and labels (B2, B3)

Desired track data (spec §6):

- **Identity/display:** title, artist/creator, album, duration, year, artwork, format, managed media path
- **Recommendation/audio:** genre/primary genre, mood/primary mood, BPM, energy, danceability, valence, acousticness, loudness, key, mode, vocal/instrumental estimate
- **System:** SHA-256, source, analysis status/version, provenance/confidence, timestamps

Unavailable features are stored as `NULL`. Spotify-like `energy`, `danceability`, `valence`, and `acousticness` are never fabricated; inferred values carry source, analyzer version, and confidence (D19–D21).

`track_labels` allows several genre and mood labels per track (spec §9):

```text
track_id
kind        # genre | mood
value
source
confidence
is_primary
```

The canonical `MusicCandidate` may keep projecting a single primary genre and mood for compatibility until a plural-label domain change is justified.

Readiness states (spec §7): `DISCOVERED`, `IMPORTED`, `ANALYZING`, `READY`, and the failure states `UNSUPPORTED`, `FAILED`, `MISSING_MANAGED_FILE`.

The managed media path is internal. It is never returned to the frontend.

### Analysis jobs (B3)

Job state is persisted so interrupted work resumes after restart (D28). Suggested job kinds: `IMPORT_TRACK`, `EXTRACT_TAGS`, `ANALYZE_AUDIO`, `REANALYZE_TRACK`, `RESCAN_SOURCE`. Jobs are idempotent and transactions stay short.

### Listening sessions (B4)

A `ListeningSession` is a listening experience, not a chat thread. Minimal conceptual model (spec §10):

```text
ListeningSession
    session_id
    listener_profile_id
    status
    current_context
    current_track_occurrence_id
    rolling_queue
    started_at
    ended_at
```

The session holds where we are now. `session_turns`, `recommendation_occurrences`, and `feedback_events` hold how we got here (D31).

Not stored:

- UI-only state: drawers, animations, scroll position, composer draft, explanation expansion (D32)
- raw conversational text, by default; structured intent is stored instead (D33)

Historical sessions persist, but the active queue is **not** restored after restart. A fresh active session starts when listening begins again (D35).

### Recommendation occurrences (B4)

`Recommendation` is an algorithm result. `RecommendationOccurrence` records that a recommendation was surfaced or queued in a specific session at a specific moment. The two stay distinct.

### Feedback events (B6)

Persist the raw fact, not only the interpreted label (spec §9):

```text
event_type
played_seconds
duration_seconds
played_fraction
recommendation_occurrence_id
session_id
timestamp
```

Storing raw facts lets Feedback Policy v1 thresholds change later without losing evidence.

### Playlists (B7)

Create, rename, delete, add, remove, and reorder, persisted in `playlists` and `playlist_items`. One occurrence of a track per playlist by default. Recommendations are never auto-saved.

### Long-term adaptation records (B10)

Every profile adjustment persists its evidence IDs, algorithm version, before and after values, and reason, so it is traceable and reversible or recomputable (D06).

## Data Retention

Resolved for Prototype 1:

- Raw natural-language prompts: not stored by default (D33).
- Accounts: none; one local listener (D01).
- Imported music: managed copies stay on the device and are never shared externally (spec §27).

Still open:

- Whether the listener can delete history, feedback, or the whole library from inside the app, and what deletion removes.
- Whether session history should keep any user-visible wording, given D33. See [risks and open questions](../planning/risks-and-open-questions.md).

## Migration Strategy

Use version-controlled Alembic migrations from the first table. A clean migration from an empty database must work and is tested in B1.

## Open Trade-offs

- Normalized tables versus JSON columns for structured context and the rolling queue (B1/B4)
- How long raw playback events are kept as the history grows (B11)

Resolved: SQLite for Prototype 1, PostgreSQL later (D22). Normalized `track_labels` for plural genres and moods (spec §9). Recommendation occurrences are stored (spec §9).

## Superseded: Pre-Prototype 1 Draft

**Superseded by the Prototype 1 concepts above.** Kept for history. This draft assumed accounts or anonymous users, a provider-oriented `catalog_items` table, stateless recommendation requests with an optional `raw_prompt`, and a feedback `action` without playback facts.

Initial recommendation (historical):

- Continue using the CSV catalog while refactoring the recommendation domain.
- Introduce SQLite when feedback, recommendation history, or persistent profiles are needed locally.
- Consider PostgreSQL for deployed multi-user persistence.

Proposed entities (historical):

- `users`: `id`, `email` or external identity reference, `display_name`, `created_at`, `updated_at`, `status`
- `user_profiles`: `id`, `user_id`, `preferred_energy`, `preferred_danceability`, `profile_version`, `created_at`, `updated_at`
- `profile_genres`: `profile_id`, `genre`, `preference_strength`
- `profile_moods`: `profile_id`, `mood`, `preference_strength`
- `catalog_items`: `id`, `source`, `external_id`, `title`, `creator`, `genre`, `mood`, `energy`, `danceability`, `tempo_bpm`, `valence`, `acousticness`, `url`, `thumbnail_url`, `metadata_json`, `created_at`, `updated_at`
- `recommendation_requests`: `id`, `user_id` (nullable), `input_type`, `raw_prompt` (nullable), `profile_snapshot_json`, `catalog_source`, `algorithm_version`, `created_at`
- `recommendation_results`: `id`, `request_id`, `catalog_item_id` or external candidate reference, `rank`, `score`, `match_level`, `reason_json`, `created_at`
- `feedback_events`: `id`, `request_id`, `user_id` (nullable), `candidate_reference`, `action`, `created_at`

Relationship sketch (historical):

```text
users 1 ---- 1..n user_profiles
users 1 ---- 0..n recommendation_requests
recommendation_requests 1 ---- n recommendation_results
recommendation_requests 1 ---- 0..n feedback_events
catalog_items 1 ---- 0..n recommendation_results
```
