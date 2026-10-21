# Database Design

## Status

**Current (B1 persistence foundation and B2 managed library, 2026-10-19; B3 background analysis, B4 session domain, B5 occurrence columns, and B6 feedback recording, 2026-10-20; B7 playlists, 2026-10-21; B8 `BEGIN IMMEDIATE`, 2026-10-21, with no schema change), Planned (the remaining Prototype 1 concepts), Superseded (earlier draft).** Reconciled with Prototype 1 in Phase B0 (2026-10-18).

**Current:**
- **B1** built the SQLite persistence foundation: engine and connection configuration, ORM records, a repository and unit-of-work pattern, Alembic migrations, and `listener_profiles` (see [Current Schema (B1)](#current-schema-b1)).
- **B2** added the managed library: `library_sources`, `source_files`, `tracks`, and `track_labels` (see [Current Schema (B2)](#current-schema-b2)).
- **B3** added background analysis: `analysis_jobs` and `track_features`, and the `ANALYZING` and `READY` track states (see [Current Schema (B3)](#current-schema-b3)).
- **B4** added the session domain: `listening_sessions`, `session_turns`, `recommendation_occurrences`, and `feedback_events` (see [Current Schema (B4)](#current-schema-b4)).
- **B5** added two columns to `recommendation_occurrences` (see [Current Schema (B5)](#current-schema-b5)): `surfaced_position`, which never changes, and `is_exploration`, which marks Recommendation Policy v1's exploration picks. Policy v1 ranks library tracks; it adds no other table, and its constants live in code, not in the database.
- **B6** records feedback into the B4 `feedback_events` table, with no schema change (see [Feedback events (B6)](#feedback-events-b6)).
- **B7** added `playlists` and `playlist_items`, and `feedback_events` accepts `PLAYLIST_ADD` (see [Current Schema (B7)](#current-schema-b7)).
- The recommendation catalog used by the CLI is still `backend/data/songs.csv`.
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
- **`BEGIN IMMEDIATE`** *(since B8, 2026-10-21, TD-019).* Every transaction takes SQLite's write lock when it begins, so concurrent transactions wait on the 5-second busy timeout instead of failing. With a deferred `BEGIN`, a transaction that read and then wrote failed at once with "database is locked" if another connection had committed in between (its snapshot was stale, so the busy timeout could not help). The API's request threads, the worker, and the startup scan made that routine. Reads queue too, so WAL's concurrent readers are given up; transactions stay short.
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

The table holds no name, email, or other personal data. Taste preferences (`UserProfile`) are not stored yet; attaching long-term preferences to the listener is later work (B10). *(B5: Policy v1 accepts a long-term profile, but none is stored, so its long-term stage is unavailable until B10.)*

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

## Current Schema (B3)

**Current.** Created by migration `7a42f0b9c8bf` (`backend/alembic/versions/20261020_7a42f0b9c8bf_create_background_analysis.py`), which revises `2540be2956b8`.

### `tracks` (changed)

`status` may now also be `ANALYZING` (first analysis running) or `READY` (analyzed). `analysis_version` holds the analyzer key `name@version` once analyzed. SQLite cannot alter a CHECK constraint, so the migration rebuilds `tracks` in batch mode. The test suite checks that the rebuild keeps every other constraint and every row. Downgrading returns `ANALYZING` and `READY` tracks to `IMPORTED` and clears `analysis_version`.

### `analysis_jobs`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `VARCHAR(36)` | not null | Primary key. |
| `track_id` | `VARCHAR(36)` | not null | Foreign key to `tracks`. |
| `kind` | `VARCHAR(16)` | not null | `ANALYZE_AUDIO` (the only kind in B3). |
| `analyzer` | `VARCHAR(128)` | not null | Analyzer key, `name@version`. |
| `status` | `VARCHAR(16)` | not null | `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, or `SKIPPED`. |
| `attempts` | `INTEGER` | not null | `>= 0`; counted when the job is claimed. |
| `failure_reason` | `VARCHAR(32)` | null | Required for `FAILED` and `SKIPPED`; forbidden for `SUCCEEDED`; kept on a `PENDING` job to show why it is being retried. |
| `error_message` | `TEXT` | null | Short, built from exception types and OS error text only; never contains a file path. |
| `created_at`, `updated_at` | `DATETIME` | not null | |
| `started_at`, `finished_at` | `DATETIME` | null | Last claim and last finish. |

- **Uniqueness:** `(track_id, kind, analyzer)`. One job per track and analyzer version makes queuing idempotent at the database level.
- **Index:** `ix_analysis_jobs_status_created_at` serves "oldest pending job first".
- **Reasons:**
  - `SKIPPED` jobs: `FORMAT_NOT_SUPPORTED` or `SUPERSEDED`;
  - `FAILED` jobs: `DECODE_ERROR`, `IO_ERROR`, `MISSING_MANAGED_FILE`, `INTERRUPTED`, or `ANALYZER_ERROR`.

### `track_features`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `VARCHAR(36)` | not null | Primary key. |
| `track_id` | `VARCHAR(36)` | not null | Foreign key to `tracks`. Unique with `name`: one current value per feature. |
| `name` | `VARCHAR(64)` | not null | `decoded_duration_seconds`, `sample_peak`, or `rms_level`. No other name is accepted; `energy`, `danceability`, and `tempo_bpm` are refused by the CHECK. |
| `value` | `FLOAT` | not null | Finite and non-negative (validated by the domain). Levels are linear fractions of digital full scale. |
| `analyzer_name`, `analyzer_version` | `VARCHAR(64)` | not null | Provenance (D20). |
| `confidence` | `FLOAT` | null | 0–1 for estimates; null for exact measurements, which is every B3 feature. |
| `computed_at` | `DATETIME` | not null | |

Reanalysis replaces one analyzer's features for a track in the same transaction that marks the job `SUCCEEDED`. A failed reanalysis leaves the earlier features in place.

## Current Schema (B4)

**Current.** Created by migration `dd7360f46b8b` (`backend/alembic/versions/20261020_dd7360f46b8b_create_listening_sessions.py`), which revises `7a42f0b9c8bf`.

The session row is the current state; turns, occurrences, and feedback events are the history (D31). The current track and the queue are not stored on the session. They are the session's one `PLAYING` occurrence and its `QUEUED` occurrences in `queue_position` order, so the database constrains them like any other rows.

### `listening_sessions`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `VARCHAR(36)` | not null | Primary key. |
| `listener_profile_id` | `VARCHAR(36)` | not null | Foreign key to `listener_profiles`. |
| `status` | `VARCHAR(16)` | not null | `ACTIVE` or `ENDED`. |
| `end_reason` | `VARCHAR(32)` | null | `ENDED_BY_LISTENER`, `REPLACED_BY_NEW_SESSION`, or `APP_RESTARTED`; set exactly when `ENDED` (CHECK). |
| `context_json` | `TEXT` | not null | The `ListeningContext` in force, as JSON (see below). |
| `started_at`, `updated_at` | `DATETIME` | not null | |
| `ended_at` | `DATETIME` | null | Set exactly when `ENDED`. |

Partial unique index `uq_listening_sessions_one_active` on `listener_profile_id WHERE status = 'ACTIVE'`: a listener has at most one active session.

### `recommendation_occurrences`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `VARCHAR(36)` | not null | Primary key; unique together with `session_id` (target of composite foreign keys). |
| `session_id` | `VARCHAR(36)` | not null | Foreign key to `listening_sessions`. |
| `track_id` | `VARCHAR(36)` | not null | Foreign key to `tracks`; indexed. |
| `rank` | `INTEGER` | not null | `>= 1`: the algorithm's rank. |
| `score` | `FLOAT` | null | 0–1: the algorithm's normalized score. |
| `algorithm` | `VARCHAR(64)` | not null | Which algorithm and version produced it. |
| `status` | `VARCHAR(16)` | not null | `QUEUED`, `PLAYING`, `PLAYED`, `REPLACED`, or `DISCARDED`. |
| `queue_position` | `INTEGER` | null | Set exactly while `QUEUED` (CHECK). |
| `surfaced_at`, `updated_at` | `DATETIME` | not null | |
| `started_at` | `DATETIME` | null | Set exactly when `PLAYING` or `PLAYED`. |
| `finished_at` | `DATETIME` | null | Set exactly when `PLAYED`, `REPLACED`, or `DISCARDED`. |

Partial unique indexes: `uq_recommendation_occurrences_one_playing` (one `PLAYING` per session) and `uq_recommendation_occurrences_queue_position` (`session_id`, `queue_position`). Queue order is the order given to `queue_recommendations()`, which may differ from rank order. Positions are not renumbered when a queued occurrence is played early; order is what counts. *(B5: `queue_position` is cleared when an occurrence leaves the queue, so B5 adds `surfaced_position`, which keeps the surfaced order for good.)*

### `session_turns`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `VARCHAR(36)` | not null | Primary key. |
| `session_id` | `VARCHAR(36)` | not null | Foreign key to `listening_sessions`. Unique with `sequence`. |
| `sequence` | `INTEGER` | not null | From 1; the first turn, and only the first, is `INITIAL_INTENT` (CHECK). |
| `kind` | `VARCHAR(32)` | not null | `INITIAL_INTENT`, `REFINE`, `NEXT`, `NOT_FOR_ME`, `MORE_LIKE_THIS`, `SURPRISE_ME`, `MORE_FAMILIAR`, or `TRY_SOMETHING_DIFFERENT`. |
| `context_json` | `TEXT` | not null | The context in force after the turn. |
| `occurrence_id` | `VARCHAR(36)` | null | The occurrence the turn is about; required for `NOT_FOR_ME` and `MORE_LIKE_THIS` (CHECK). Composite foreign key (`occurrence_id`, `session_id`), so it must belong to the same session. |
| `created_at` | `DATETIME` | not null | |

There is no column for text: raw conversational text cannot be stored (D33).

### `feedback_events`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `VARCHAR(36)` | not null | Primary key. |
| `session_id` | `VARCHAR(36)` | not null | Foreign key to `listening_sessions`. |
| `occurrence_id` | `VARCHAR(36)` | not null | Composite foreign key (`occurrence_id`, `session_id`): an occurrence of the same session. |
| `event_type` | `VARCHAR(16)` | not null | `LIKE`, `SAVE`, `REPLAY`, `SKIP`, `COMPLETE`, or `NOT_FOR_ME`. |
| `played_seconds` | `FLOAT` | null | `>= 0`; required for `SKIP` and `COMPLETE`; recorded together with `duration_seconds`. |
| `duration_seconds` | `FLOAT` | null | `> 0`. |
| `played_fraction` | `FLOAT` | null | 0–1: `played_seconds / duration_seconds`, capped at 1.0; present exactly when the seconds are. |
| `occurred_at` | `DATETIME` | not null | |

Raw facts only; no interpreted weight is stored. B4 creates the table and repository. Recording events and interpreting them is B6. *(Current since B6; see [Feedback events (B6)](#feedback-events-b6).)*

### Context storage

`context_json` holds `{"format": 1, "context": {...every ListeningContext field...}}`, compact and key-sorted. Loading refuses an unknown format or an unknown field rather than ignoring it, and re-validates through `ListeningContext`. A missing field takes its default, so a field added to the model later reads as unset on older rows.

## Current Schema (B5)

**Current.** Migration `de244c476f3a` (`backend/alembic/versions/20261020_de244c476f3a_record_surfaced_position_and_exploration.py`), which revises `dd7360f46b8b`. The committed B4 migration is unchanged.

### `recommendation_occurrences` (changed)

| Column | Type | Null | Notes |
|---|---|---|---|
| `surfaced_position` | `INTEGER` | not null | CHECK `>= 0`. Where in its queue the occurrence was surfaced, from 0. Written once and never changed (see below). |
| `is_exploration` | `BOOLEAN` | not null | Default `0`; CHECK `IN (0, 1)`. Whether Policy v1 surfaced the occurrence as its exploration pick. |

`queue_position` keeps its B4 meaning, the current queue state: set while `QUEUED`, cleared when the occurrence leaves the queue. `surfaced_position` is the record of where it was surfaced. So an exploratory order, such as rank 2 surfaced ahead of rank 1, can be reconstructed after both have been played or replaced.

What was surfaced (track, rank, score, algorithm, surfaced time, surfaced position, exploration mark) is written once by the repository's `add()`; `save()` changes only the lifecycle columns. History (`list_for_session()` without a status) reads in surfaced order, by `surfaced_at` then `surfaced_position`. In B4 it read in rank order within a queue.

The migration:
- **Adds `surfaced_position`** with a plain `ADD COLUMN` and backfills it before rebuilding the table. B4 inserted each queue's occurrences one at a time, in queue order, all with the same `surfaced_at`. So within a session and `surfaced_at`, rowid order is the surfaced order. It is read while the rowids are still the original ones.
- **Rebuilds the table** (batch mode) to make the column not null and to add both CHECK constraints. `session_turns` and `feedback_events` reference this table; the rebuild keeps every row, and the migration's foreign-key check passes before commit.
- **Leaves older rows unmarked:** occurrences from before B5 read `is_exploration = 0`.
- **Downgrade** drops both columns and their constraints the same way.

Policy v1 writes occurrences through `queue_recommendations()` as before: `algorithm` is the policy version (`policy-v1`), `rank` is the policy's rank, and `score` is the combined score (0–1). A pick with no meaningful score has `score` `NULL`; no value is invented for it.

Within a session, `SessionService` gives every change a strictly later time (TD-016 item 13). Each surfaced queue therefore has its own `surfaced_at`, and a queue is always later than the turn before it.

## Current Schema (B7)

**Current.** Migration `ce0b59df2cd1` (`backend/alembic/versions/20261021_ce0b59df2cd1_create_playlists.py`), which revises `de244c476f3a`.

### `playlists`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `VARCHAR(36)` | not null | Primary key. |
| `listener_profile_id` | `VARCHAR(36)` | not null | Foreign key to `listener_profiles`. |
| `name` | `VARCHAR(100)` | not null | Trimmed, 1–100 characters (CHECK on the length). Unique per listener: `uq_playlists_listener_name` on (`listener_profile_id`, `name`). |
| `created_at`, `updated_at` | `DATETIME` | not null | |

### `playlist_items`

| Column | Type | Null | Notes |
|---|---|---|---|
| `playlist_id` | `VARCHAR(36)` | not null | Foreign key to `playlists`; part of the primary key. |
| `track_id` | `VARCHAR(36)` | not null | Foreign key to `tracks`; part of the primary key, so a track appears once per playlist; indexed. |
| `position` | `INTEGER` | not null | `>= 0` (CHECK); unique per playlist (`uq_playlist_items_playlist_position`). The domain keeps them 0, 1, 2… with no gaps. |
| `added_at` | `DATETIME` | not null | Kept through reorders. |

How the tables are used:
- **Writes:** the repository writes a playlist's items as a whole (delete, then insert in order) inside one transaction, so a swap never breaks the unique positions.
- **Deleting a playlist** removes its items; tracks and feedback events stay.
- **Not stored:** presentation, such as the frontend's colour tone (D32).

### `feedback_events` (changed)

`event_type` also accepts `PLAYLIST_ADD`, a recommendation added to a playlist (+1.00). The CHECK change rebuilt the table in batch mode, keeping its rows, index, and composite foreign key. The downgrade deletes PLAYLIST_ADD events before restoring the earlier constraint, since their playlists are dropped too.

## Prototype 1 Concepts

**Planned**, except these, which exist:
- `listener_profiles` (B1);
- `library_sources`, `tracks`, and `track_labels` (B2);
- `analysis_jobs` and `track_features` (B3);
- `listening_sessions`, `session_turns`, `recommendation_occurrences`, and `feedback_events` (B4);
- `playlists` and `playlist_items` (B7).

B2 also added `source_files`, which is not in this list. Concept names from spec §9:

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
- analysis version, in `tracks.analysis_version`, set by B3's analysis once a track is analyzed (null before).

SHA-256 identifies exact duplicates (D24). The scan rules are in [System Workflow](../architecture/system-workflow.md#library-import-and-scanning-b2).

### Tracks, features, and labels (B2, B3)

**Current (B2):** `tracks` and `track_labels`, with title, artist, album, year, declared genre, duration, format, and provenance-tagged genre labels.

**Current (B3):** `track_features` holds three exact signal measurements: decoded duration, sample peak, and RMS level.

**Not yet produced:** BPM, key, mode, loudness in LUFS, and every semantic feature in the desired list above. They stay absent (D21); see [TD-014](../decisions/technical-decisions.md#td-014-b3-background-analysis). Artwork is not extracted yet (an [open question](../planning/risks-and-open-questions.md#open-backend-questions)).

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
- **Not written yet:** `DISCOVERED`, since B2 records a file only once it has been processed.
- **Since B3:** tracks also take `ANALYZING` and `READY`.
  - `IMPORTED → ANALYZING` when its first analysis is claimed, then `READY` on success, or back to `IMPORTED` on failure or skip.
  - A `READY` track stays `READY` during reanalysis.
  - Every track state except `MISSING_MANAGED_FILE` is playable.

The managed media path is internal. It is never returned to the frontend.

### Analysis jobs (B3)

**Current.** Job state is persisted, so interrupted work resumes after restart (D28). The spec suggests these job kinds: `IMPORT_TRACK`, `EXTRACT_TAGS`, `ANALYZE_AUDIO`, `REANALYZE_TRACK`, `RESCAN_SOURCE`.
- **Implemented in B3:** only `ANALYZE_AUDIO`. Reanalysis is an `ANALYZE_AUDIO` job for a new analyzer version, so `REANALYZE_TRACK` is not needed.
- **Not implemented:** import, tag extraction, and rescans stay synchronous `LibraryService` calls, because B3 is analysis only.
- **Idempotency:** jobs are unique per track and analyzer version.
- **Short transactions:** analysis runs between two of them, claim and finish.

Lifecycle, retries, and recovery: [System Workflow](../architecture/system-workflow.md#background-analysis-b3).

### Listening sessions (B4)

**Current (B4)**; see [Current Schema (B4)](#current-schema-b4). The spec's `current_track_occurrence_id` and `rolling_queue` are represented by occurrence status and queue position, not by session columns.

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

**Current (B4).** `SessionService.queue_recommendations()` takes domain `Recommendation` objects, which stay in memory, and records `RecommendationOccurrence` rows. Each row copies the candidate's track id, rank, normalized score, and the algorithm label.

**Current (B5).** Recommendation Policy v1 produces those `Recommendation`s (`RecommendationService.refresh_queue()`). An occurrence also records whether it was an exploration pick, and its surfaced position. Later evidence about exploration picks moves the exploration rate (spec §18, §20). The surfaced position keeps the order a queue was surfaced in, after the queue has moved on.

### Feedback events (B6)

**Table current since B4; recording current since B6** (`SessionService.record_feedback()`, through `FeedbackService`). B6 needed no schema change: every event is one row of raw facts, and nothing interpreted is stored. Feedback Policy v1 reads the rows at each refresh, per track in the session (TD-017).

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

Since B6:
- **Replay:** it adds a row to `recommendation_occurrences` as well, a fresh occurrence of the replayed track with status `PLAYING`, `algorithm = 'listener-replay'`, rank 1, and `score` `NULL`. The listener chose it; no algorithm surfaced it.
- **Not for me:** it writes nothing outside the session; long-term records are B10.

### Playlists (B7)

Create, rename, delete, add, remove, and reorder, persisted in `playlists` and `playlist_items`. One occurrence of a track per playlist by default. Recommendations are never auto-saved.

**Current (B7)**; see [Current Schema (B7)](#current-schema-b7).

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

**Current (B1; library repositories added in B2; analysis repositories in B3; session repositories in B4).**

- **Ports** (`backend/src/intentune/ports/`):
  - `ListenerProfileRepository` (`get`, `get_default`, `add`);
  - *(B2, `ports/library.py`)* `LibrarySourceRepository` (`get`, `get_by_path`, `list_all`, `add`, `save`), `SourceFileRepository` (`list_for_source`, `add`, `save`), and `TrackRepository` (`get`, `get_by_sha256`, `list_all`, `ids_with_status`, `add`, `save`; a track's labels are saved with it);
  - *(B3, `ports/analysis.py`)* `AnalysisJobRepository` (`get`, `list_all`, `list_for_analyzer`, `add`, `save`, `claim_next`) and `TrackFeatureRepository` (`list_for_track`, `replace_for_analyzer`).
  - *(B4, `ports/sessions.py`)* `ListeningSessionRepository` (`get`, `get_active_for_listener`, `list_for_listener`, `list_active`, `add`, `save`), `SessionTurnRepository` (`list_for_session`, `add`), `RecommendationOccurrenceRepository` (`get`, `list_for_session`, `add`, `save`), and `FeedbackEventRepository` (`list_for_session`, `add`). Turns and feedback events are history: added, never changed.
  - *(B7, `ports/playlists.py`)* `PlaylistRepository` (`get`, `get_by_name`, `list_for_listener`, `track_counts`, `add`, `save`, `delete`, `items`, `replace_items`).

    The occurrence repository flushes every write at once, so writes reach the database in the caller's order. That keeps the one-`PLAYING` and queue-position indexes satisfied after every statement.

    `claim_next` is a single `UPDATE … WHERE id = (oldest pending) AND status = 'PENDING' RETURNING id`, so two workers can never claim the same job. It needs SQLite 3.35 or later; this machine runs 3.45.1.
  - `UnitOfWork`, which exposes all of these plus `commit()` and `rollback()`.

  Application use cases depend only on these ports.
- **Adapters** (`backend/src/intentune/persistence/`): `SqlAlchemyListenerProfileRepository`, `SqlAlchemyLibrarySourceRepository`, `SqlAlchemySourceFileRepository`, `SqlAlchemyTrackRepository`, `SqlAlchemyAnalysisJobRepository`, `SqlAlchemyTrackFeatureRepository`, the four session repositories (B4), `SqlAlchemyPlaylistRepository` (B7), and `SqlAlchemyUnitOfWork`. A unit of work is not thread-safe; the analysis worker uses its own.
- A repository works inside the session it is given, never commits, and accepts and returns domain models only.
- A unit of work is used as `with unit_of_work:`. Each block is one fresh session and transaction. `commit()` makes staged changes durable. Leaving the block always rolls back anything uncommitted, whether by an early return or an exception, then closes the session. A unit of work is not re-entrant, and it refuses use outside a `with` block. It can be reused for consecutive transactions.
- Later phases add their repositories to the same unit of work, so one use case can change several tables atomically.

## Migration Strategy

**Current (B1).** Version-controlled Alembic migrations from the first table. History: `6ef3a3452ab7` creates `listener_profiles` (B1); `2540be2956b8` creates the managed-library tables (B2); `7a42f0b9c8bf` creates the analysis tables and rebuilds `tracks` for the new states (B3); `dd7360f46b8b` creates the session tables (B4); `de244c476f3a` adds and backfills `surfaced_position`, then rebuilds `recommendation_occurrences` with it and `is_exploration` (B5); `ce0b59df2cd1` creates the playlist tables and rebuilds `feedback_events` to accept `PLAYLIST_ADD` (B7). The B3 rebuild found that Alembic's batch mode re-creates a table's constraints in a varying order (it copies them from an unordered set). The schema snapshot tests therefore compare each table's clauses as a set.

- From `backend/`: `alembic upgrade head` (or `alembic -c backend/alembic.ini upgrade head` from the repository root). The target is the database resolved from `DATABASE_URL`, as above.
- From Python: `upgrade_database(url)` in `backend/src/intentune/persistence/migrations.py`, used by tests and later by application startup. It passes the URL through Alembic's `Config.attributes`, so paths containing `%` are not affected by `configparser` interpolation, and it leaves the caller's logging alone.
- `backend/alembic/env.py` uses the application's engine factory, so migrations get the same connection setup. The whole upgrade runs in one transaction (`transactional_ddl=True`), with batch mode (`render_as_batch=True`) for future SQLite `ALTER` operations.
- Migration files are named `<YYYYMMDD>_<revision>_<slug>.py` and use plain SQLAlchemy types (`sa.DateTime`), not application types, so they never import application code.
- Tested (`backend/tests/test_migrations.py`):
  - a clean upgrade from an empty database, the resulting schema, and a single head;
  - a no-op re-upgrade, downgrade to base, and a full round trip;
  - a path with spaces and `%`;
  - migrations matching the ORM records exactly (Alembic `compare_metadata`; `alembic check` reports the same from the command line);
  - a deliberately failing migration rolling back schema and data completely;
  - *(B3, B5)* the table rebuilds keeping their rows, in both directions: tracks for B3, and for B5 occurrences together with the turns that reference them;
  - *(B5)* surfaced positions recovered for pre-B5 occurrences, across two sessions and two queues, including out-of-rank order.

  These tests are written against whatever tables the ORM declares, so they cover each new migration without edits. The B2 library tables' constraints are tested in `backend/tests/test_library_repositories.py`.

## Open Trade-offs

- How long raw playback events are kept as the history grows (B11)

Resolved:
- SQLite for Prototype 1, PostgreSQL later (D22).
- Normalized `track_labels` for plural genres and moods (spec §9).
- Recommendation occurrences are stored (spec §9).
- *(B4, TD-015)* Structured context is a versioned JSON column: always read and written whole, never queried by field. The rolling queue is normalized as occurrence rows with status and position, so the database enforces it.

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
