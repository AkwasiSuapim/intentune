# Database Design

## Status

**Current (B1 persistence foundation and B2 managed library, 2026-10-19), Planned (the remaining Prototype 1 concepts), Superseded (earlier draft).** Reconciled with Prototype 1 in Phase B0 (2026-10-18).

**Current:**
- **B1** built the SQLite persistence foundation: engine and connection configuration, ORM records, a repository and unit-of-work pattern, Alembic migrations, and `listener_profiles` (see [Current Schema (B1)](#current-schema-b1)).
- **B2** added the managed library: `library_sources`, `source_files`, `tracks`, and `track_labels` (see [Current Schema (B2)](#current-schema-b2)).
- The recommendation catalog used by the CLI is still `backend/data/songs.csv`. Recommending from library tracks is B5.
- Nothing in the running CLI opens the database yet. The FastAPI startup (B8) will apply migrations, create the default listener, and run the startup scan.

This document records the approved concepts and the facts the [Prototype 1 specification](../planning/intentune-backend-prototype-implementation-spec.md) §5–§10 fixes. Exact tables, columns, types, and indexes are designed in the phase that creates them and recorded here at that time.

## Technology

**Current (B1, D22, D23)** unless marked otherwise:

- **SQLite** for Prototype 1 (local, single listener). Only SQLite URLs are accepted. PostgreSQL is Future.
- **SQLAlchemy 2.1**, synchronous. No async SQLAlchemy without a measured need.
- **Alembic** for versioned migrations. Never edit tables by hand.
- UTC timestamps. SQLite foreign keys enforced on every connection. WAL mode on, verified by tests.
- UUID identifiers. Never trust source filenames as internal storage names.
- Audio files stay **outside** SQLite, in managed media *(Current since B2)*. Tracks store no file path; a managed copy's location comes from its track id and format.

Location (spec §5): `backend/data/intentune.db`, with managed media in `backend/data/media/<track_uuid>.<extension>`. `.gitignore` covers both, including the database's `-wal` and `-shm` files.

### Configuration and connections

**Current (B1).** All of this lives in `backend/src/intentune/persistence/db.py`.

- **Which database:** `DATABASE_URL` from the process environment. When it is unset or blank, the default is `backend/data/intentune.db`. A relative SQLite path is resolved against `backend/`, as the CSV adapter resolves `data/songs.csv`, so the location does not depend on the working directory. The value in `backend/.env.example`, `sqlite:///./data/intentune.db`, therefore means `backend/data/intentune.db` and equals the default. Nothing loads `backend/.env` yet.
- **Transactions:** SQLAlchemy, not the `sqlite3` driver, emits `BEGIN`. On Python 3.11 the driver's legacy mode skips `BEGIN` before `SELECT` and DDL, so schema changes would autocommit and a rolled-back `CREATE TABLE` would survive. Taking over `BEGIN` is the approach SQLAlchemy documents for all Python versions. It makes DDL transactional, and a test proves the rollback.
- **Foreign keys:** `PRAGMA foreign_keys = ON` on every connection (SQLite's default is off). Migrations turn them off, as SQLite's table-rebuild procedure requires, and run `PRAGMA foreign_key_check` before committing. Any violation fails the migration and rolls it back.
- **Journal mode:** WAL for file databases, so readers do not block the single writer. This matters from B3, when the background worker writes while the app reads. SQLAlchemy notes that driver-independent `BEGIN` makes "database is locked" errors more likely; WAL, short transactions, and the driver's 5-second busy timeout are the mitigation.
- **Sessions:** `create_session_factory(engine)` returns a `sessionmaker`; a unit of work opens one session per transaction.

### Conventions for every table

**Current (B1).** Defined in `backend/src/intentune/persistence/models.py`.

- Primary keys are UUID strings in canonical lowercase hyphenated form, `String(36)`. The domain validates the form.
- Timestamps use `UtcDateTime`. It stores the UTC wall-clock value (SQLite has no time-zone type), returns timezone-aware UTC datetimes, and rejects naive ones.
- Constraint and index names come from one naming convention (`pk_<table>`, `fk_<table>_<column>_<referred table>`, `uq_<table>_<column>`, `ix_<column label>`, `ck_<table>_<name>`). Alembic's SQLite batch mode needs named constraints to alter or drop them later.
- ORM classes carry a `Record` suffix (`ListenerProfileRecord`) and never leave the persistence package. Repositories convert them to and from domain models.
- *(Since B2)* Every enumerated column (statuses, formats, label kinds, failure reasons) has a named CHECK constraint. The ORM records generate its value list from the domain enum; migrations spell the list out literally. A test inserts every domain value and rejects undefined ones. Boolean columns added in B2 also check `IN (0, 1)`.
- *(Since B2)* The records declare no ORM relationships. A repository therefore flushes a parent row (a source, a track) as soon as it is added, so child rows staged in the same transaction never reach the database before the row they reference.

## Current Schema (B1)

**Current.** Created by migration `6ef3a3452ab7` (`backend/alembic/versions/20261019_6ef3a3452ab7_create_listener_profiles.py`).

### `listener_profiles`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `VARCHAR(36)` | not null | Primary key (`pk_listener_profiles`). A generated UUID4. |
| `is_default` | `BOOLEAN` | not null | Marks the default local listener. |
| `created_at` | `DATETIME` | not null | UTC. |

Index `uq_listener_profiles_is_default`: `UNIQUE (is_default) WHERE is_default = 1`. Any number of non-default rows may exist, but the database refuses a second default.

The table holds no name, email, or other personal data. Taste preferences (`UserProfile`) are not stored yet; attaching long-term preferences to the listener is later work (B5/B10).

Alembic also keeps its `alembic_version` table.

## Current Schema (B2)

**Current.** Created by migration `2540be2956b8` (`backend/alembic/versions/20261019_2540be2956b8_create_managed_library.py`), which revises `6ef3a3452ab7`. Every timestamp column is a UTC `DATETIME`.

### `library_sources`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `VARCHAR(36)` | not null | Primary key. Generated UUID4. |
| `path` | `TEXT` | not null | Absolute, normalized folder path. Unique (`uq_library_sources_path`): a folder is registered once. Internal; never shown to the frontend. |
| `status` | `VARCHAR(16)` | not null | `ACTIVE` or `MISSING` (the folder was not found at the last scan). |
| `created_at` | `DATETIME` | not null | |
| `last_scanned_at` | `DATETIME` | null | Null until the first scan. |

### `tracks`

One row per distinct content in managed media. The managed file is `<id>.<audio_format>`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `VARCHAR(36)` | not null | Primary key. Generated UUID4; also the managed file's name. |
| `sha256` | `VARCHAR(64)` | not null | Unique (`uq_tracks_sha256`): the exact-duplicate key (D24). |
| `size_bytes` | `INTEGER` | not null | `>= 0`. |
| `audio_format` | `VARCHAR(8)` | not null | `mp3`, `m4a`, `flac`, `ogg`, `opus`, or `wav`. |
| `status` | `VARCHAR(32)` | not null | `IMPORTED` or `MISSING_MANAGED_FILE`. |
| `original_filename` | `TEXT` | not null | File name (not path) of the first source file imported. For display fallback only. |
| `title`, `artist`, `album` | `TEXT` | null | From embedded tags; null when absent. |
| `year` | `INTEGER` | null | 1–9999, from a date tag. |
| `duration_seconds` | `FLOAT` | null | `>= 0`, from the container header. |
| `analysis_version` | `VARCHAR(64)` | null | Null until analyzed (B3). |
| `created_at`, `updated_at` | `DATETIME` | not null | |

### `source_files`

What the last scan recorded about each file in a source, so the next scan can skip unchanged files (spec §5). This table is not in the spec's concept list; it holds the incremental-scan state the spec requires.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `VARCHAR(36)` | not null | Primary key. |
| `source_id` | `VARCHAR(36)` | not null | Foreign key to `library_sources`. Unique with `relative_path`. |
| `relative_path` | `TEXT` | not null | POSIX path under the source folder; validated so it cannot escape it. |
| `size_bytes`, `modified_ns` | `INTEGER` | not null | The file's size and modification time at the last scan. |
| `sha256` | `VARCHAR(64)` | null | Set once hashed. |
| `status` | `VARCHAR(16)` | not null | `IMPORTED`, `UNSUPPORTED`, `FAILED`, or `MISSING`. |
| `failure_reason` | `VARCHAR(32)` | null | `FILE_TOO_LARGE` or `UNSUPPORTED_FORMAT` (UNSUPPORTED); `IO_ERROR` or `CHANGED_DURING_IMPORT` (FAILED). |
| `track_id` | `VARCHAR(36)` | null | Foreign key to `tracks`; indexed. Several files may point to one track. |
| `created_at`, `updated_at` | `DATETIME` | not null | |

CHECK constraints tie the status to the other columns. An `IMPORTED` row has a `track_id`, a `sha256`, and no `failure_reason`. An `UNSUPPORTED` or `FAILED` row has a `failure_reason`. A `MISSING` row keeps its last `track_id`.

### `track_labels`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `VARCHAR(36)` | not null | Primary key. |
| `track_id` | `VARCHAR(36)` | not null | Foreign key to `tracks`; indexed. |
| `kind` | `VARCHAR(8)` | not null | `genre` or `mood`. |
| `value` | `TEXT` | not null | |
| `source` | `VARCHAR(64)` | not null | Provenance; B2 writes `embedded_tags`. |
| `confidence` | `FLOAT` | null | 0–1. Null for declared (tag) values. |
| `is_primary` | `BOOLEAN` | not null | |

Unique `(track_id, kind, value, source)`. Partial unique index `uq_track_labels_primary` on `(track_id, kind) WHERE is_primary = 1`: at most one primary genre and one primary mood per track.

## Prototype 1 Concepts

**Planned**, except `listener_profiles` (B1) and `library_sources`, `tracks`, and `track_labels` (B2), which exist. B2 also added `source_files`, which is not in this list. Concept names from spec §9:

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

**Current.** No authentication in Prototype 1. One generated default local listener profile is created, instead of a hard-coded id such as `"user1"` (D01).

The application use case `ensure_default_listener()` (`backend/src/intentune/application/local_listener.py`) creates it, not a migration. On first run it generates a random UUID4 with the current UTC time and commits it. Later runs, including after a restart, return the same profile without writing. The partial unique index is the backstop. If two processes ever created the default at the same moment, the second would fail on the index instead of adding a duplicate, and a retry would return the first. Prototype 1 runs one backend process, so this is not expected.

No entry point calls `ensure_default_listener()` yet. The B8 FastAPI startup will call it after applying migrations.

### Library sources and incremental scanning (B2)

**Current.** Several source folders may be registered; together they form one logical library, and adding a source never replaces earlier ones (D03). The spec requires persisting these for incremental scanning (spec §5):
- source path, in `library_sources.path`;
- file size and modification time, in `source_files`;
- SHA-256, in `source_files.sha256` and `tracks.sha256`;
- import status, in `source_files.status`;
- analysis version, in `tracks.analysis_version`, which is null until B3.

SHA-256 identifies exact duplicates (D24). The scan rules are in [System Workflow](../architecture/system-workflow.md#library-import-and-scanning-b2).

### Tracks, features, and labels (B2, B3)

**Current (B2):** `tracks` and `track_labels`, with title, artist, album, year, declared genre, duration, format, and provenance-tagged genre labels. **Planned (B3):** `track_features` and analyzed values. Artwork is not extracted yet (an [open question](../planning/risks-and-open-questions.md#open-backend-questions)).

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

**Current (B2):** the states are split between files and tracks, because a file that fails validation never becomes a track.
- **Source files:** `UNSUPPORTED` and `FAILED` (plus `IMPORTED` and `MISSING`).
- **Tracks:** `IMPORTED` and `MISSING_MANAGED_FILE`.
- **Not written yet:** `DISCOVERED`, since B2 records a file only once it has been processed, and `ANALYZING` and `READY`, which arrive with B3. B3 extends the CHECK constraints in a migration.

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

## Repository and Transaction Pattern

**Current (B1; library repositories added in B2).**

- **Ports** (`backend/src/intentune/ports/`):
  - `ListenerProfileRepository` (`get`, `get_default`, `add`);
  - *(B2, `ports/library.py`)* `LibrarySourceRepository` (`get`, `get_by_path`, `list_all`, `add`, `save`), `SourceFileRepository` (`list_for_source`, `add`, `save`), and `TrackRepository` (`get`, `get_by_sha256`, `list_all`, `ids_with_status`, `add`, `save`; a track's labels are saved with it);
  - `UnitOfWork`, which exposes all of these plus `commit()` and `rollback()`.

  Application use cases depend only on these ports.
- **Adapters** (`backend/src/intentune/persistence/`): `SqlAlchemyListenerProfileRepository`, `SqlAlchemyLibrarySourceRepository`, `SqlAlchemySourceFileRepository`, `SqlAlchemyTrackRepository`, and `SqlAlchemyUnitOfWork`.
- A repository works inside the session it is given, never commits, and accepts and returns domain models only.
- A unit of work is used as `with unit_of_work:`. Each block is one fresh session and transaction. `commit()` makes staged changes durable. Leaving the block always rolls back anything uncommitted, whether by an early return or an exception, then closes the session. A unit of work is not re-entrant, and it refuses use outside a `with` block. It can be reused for consecutive transactions.
- Later phases add their repositories to the same unit of work, so one use case can change several tables atomically.

## Migration Strategy

**Current (B1).** Version-controlled Alembic migrations from the first table. History: `6ef3a3452ab7` creates `listener_profiles` (B1); `2540be2956b8` creates the managed-library tables (B2).

- From `backend/`: `alembic upgrade head` (or `alembic -c backend/alembic.ini upgrade head` from the repository root). The target is the database resolved from `DATABASE_URL`, as above.
- From Python: `upgrade_database(url)` in `backend/src/intentune/persistence/migrations.py`, used by tests and later by application startup. It passes the URL through Alembic's `Config.attributes`, so paths containing `%` are not affected by `configparser` interpolation, and it leaves the caller's logging alone.
- `backend/alembic/env.py` uses the application's engine factory, so migrations get the same connection setup. The whole upgrade runs in one transaction (`transactional_ddl=True`), with batch mode (`render_as_batch=True`) for future SQLite `ALTER` operations.
- Migration files are named `<YYYYMMDD>_<revision>_<slug>.py` and use plain SQLAlchemy types (`sa.DateTime`), not application types, so they never import application code.
- Tested (`backend/tests/test_migrations.py`):
  - a clean upgrade from an empty database, the resulting schema, and a single head;
  - a no-op re-upgrade, downgrade to base, and a full round trip;
  - a path with spaces and `%`;
  - migrations matching the ORM records exactly (Alembic `compare_metadata`; `alembic check` reports the same from the command line);
  - a deliberately failing migration rolling back schema and data completely.

  These tests are written against whatever tables the ORM declares, so they cover each new migration without edits. The B2 library tables' constraints are tested in `backend/tests/test_library_repositories.py`.

## Open Trade-offs

- Normalized tables versus JSON columns for structured context and the rolling queue (B4)
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
