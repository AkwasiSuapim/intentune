# Architecture

## Status

**Current and Planned.** Reconciled with Prototype 1 in Phase B0 (2026-10-18). The approved target is defined in the [Prototype 1 specification](../planning/intentune-backend-prototype-implementation-spec.md) §4. This file explains it and records what exists today.

## Architectural Style

Intentune is a **modular monolith**, and Prototype 1 stays one.

This means:

- One repository
- One backend application
- One primary deployment unit
- Clear internal modules and interfaces
- No microservices until real operational needs justify them

## Why a Modular Monolith

The product requirements and domain rules are still evolving. A modular monolith gives us simple local development and deployment while allowing strong separation of responsibilities.

Microservices would add network calls, service discovery, distributed logging, authentication between services, deployment coordination, and more failure modes. Those costs are not justified for the current team and expected early usage. Prototype 1 runs on one device for one listener, which strengthens this choice.

## Current Components

**Current:** the backend has a domain layer, application use cases, and ports. Its adapters are the CSV catalog and, since B2 (2026-10-19), local folders, managed media, and a mutagen audio inspector, plus, since B3 (2026-10-20), a signal-level audio analyzer. It also has, since B1, a SQLite persistence package. Since B3 it has a background analysis worker, a single in-process thread, and since B4 a listening-session service. It has no API boundary. The CLI flow below does not touch the database, the library, the worker, or sessions; those paths are used by tests only until the B8 startup wires them in. The frontend is a separate React application running on a mock service; it does not call the backend.

```text
CLI (src/main.py)
      |
      v
Legacy compatibility layer (src/recommender.py)
      |
      v
Application service (recommend_music, recommend_from_catalog)
      |
      +------------------------+
      |                        |
      v                        v
Recommendation domain      Catalog port
(models, scoring, ranking)     |
                               v
                           CsvCatalog adapter
                               |
                               v
                           backend/data/songs.csv


ensure_default_listener() (B1)      LibraryService (B2): register/list sources,
      |                             scan, rescan, import file, list/get track,
      |                             mark unavailable          (no caller yet)
      |                                   |
      v                                   v
UnitOfWork and repository ports     + SourceFolders, AudioInspector, ManagedMedia ports
      |                                   |
      v                                   v
SqlAlchemy repositories             LocalSourceFolders   MutagenAudioInspector   LocalManagedMedia
(persistence)                       (source folders)     (mutagen)               (backend/data/media/)
      |                                                                                 ^
      v                                                                                 | reads managed copies
SQLite: backend/data/intentune.db (schema managed by Alembic)                           |
      ^                                                                                 |
      | jobs, features, track status                                                    |
AnalysisWorker (B3, one thread) -> AnalysisService -> AudioAnalyzer port -> SignalLevelAnalyzer (soundfile, numpy)
                                   (no caller starts the worker yet)

SessionService (B4): start / turn / queue / play / advance / end / restart cleanup / history   (no caller yet)
      |   takes in-memory Recommendations, records persisted RecommendationOccurrences
      v
UnitOfWork: listening_sessions, session_turns, recommendation_occurrences, feedback_events (+ listener_profiles, tracks)


React frontend (frontend/) --> SessionService interface --> mock implementation
                               (no connection to the backend yet)
```

## Prototype 1 Target Architecture

**Planned (approved).** From spec §4:

```text
React / TypeScript
        |
        | HTTP / JSON
        v
FastAPI
        |
        v
Application use cases
        |
        +----------------------+
        |                      |
        v                      v
Listening-session domain   Recommendation domain
        |                      |
        |                      +--> scoring
        |                      +--> ranking
        |                      +--> diversity/exploration
        |
        v
Ports
  - Catalog
  - SessionRepository
  - TrackRepository
  - PlaylistRepository
  - FeedbackRepository
        |
        v
Adapters
  - SQLite / SQLAlchemy
  - managed local media
  - CSV compatibility
  - metadata/audio analyzers
```

Everything runs locally. There are no accounts, cloud services, or external music providers. A bounded in-process worker handles scanning and analysis (D28), and its job state is persisted in SQLite.

### Superseded target diagram

**Superseded by the Prototype 1 target above.** The earlier planned direction had a feedback domain beside the recommendation domain, "CSV / Database / YouTube" catalog adapters, "Memory / SQLite / PostgreSQL" feedback adapters, and an AI chatbot feeding an intent-parser port. Prototype 1 replaces the YouTube catalog with a managed local library, chooses SQLite only (PostgreSQL later, D22), and defers the AI intent parser behind a future `IntentParser` port (D30, D39).

```text
Client or browser
      |
      v
API / UI boundary
      |
      v
Application service
      |
      +-----------------------+
      |                       |
      v                       v
Recommendation domain     Feedback domain
      |                       |
      v                       v
Catalog port             Feedback repository port
      |                       |
      v                       v
CSV / Database /         Memory / SQLite /
YouTube adapters          PostgreSQL adapters

Future AI chatbot
      |
      v
Intent parser port
      |
      v
Validated recommendation request
```

## Layer Responsibilities

### Domain Layer

Contains business rules that do not depend on HTTP, databases, the filesystem, AI providers, or music providers.

**Current:** `src/intentune/domain/models.py` defines the typed, source-independent models (`MusicCandidate`, `UserProfile`, `ListeningContext`, `FeatureWeights`, `ScoreComponent`, `ScoreBreakdown`, `Recommendation`). `src/intentune/domain/scoring.py` and `src/intentune/domain/ranking.py` implement the current four-feature scoring rule and tie-breaking ranking rule as the single source of truth -- `src/recommender.py`'s legacy `score_song()`/`recommend_songs()` delegate to them rather than containing a second copy of the scoring math. None of these three modules import CSV, HTTP, database, or provider-specific code. `ListeningContext` and `FeatureWeights` are not used by `score_candidate()`; since B5, Recommendation Policy v1 uses both (below). `src/intentune/domain/listener.py` (B1) defines `ListenerProfile`, the local listener identity (a canonical UUID, a default flag, and a UTC creation time; no personal data), and `new_default_listener_profile()`, which generates it. `src/intentune/domain/library.py` (B2) holds the managed-library rules. It defines the entities `LibrarySource`, `SourceFile`, `Track`, and `TrackLabel`, and the values `DiscoveredFile`, `EmbeddedTags`, `AudioProbe`, and `ScanReport`. It sets the allowlisted `AudioFormat`s and the readiness states, a relative-path rule that cannot escape a source folder, and how tag values become year and genre labels. `src/intentune/domain/validation.py` (B2) holds validators shared by the listener and library models. `src/intentune/domain/analysis.py` (B3) holds:
- the job model and its transitions (`AnalysisJob`): succeeded, skipped, failed, retry later, after interruption, requeued;
- `AnalyzerIdentity` (`name@version`), `AnalysisResult`, and `TrackFeature`, which carries provenance;
- the `needs_analysis` rule.

`Track` gained the `ANALYZING` and `READY` states, `available_status`, and `with_analysis()`.

`src/intentune/domain/session.py` (B4) holds:
- `ListeningSession`: the current state, with status, end reason, and the `ListeningContext` in force;
- `SessionTurn`: steering history with the context after each turn, and no text field;
- `RecommendationOccurrence`: a surfaced recommendation's lifecycle, QUEUED → PLAYING → PLAYED, or REPLACED or DISCARDED;
- `FeedbackEvent`: a raw listening fact with a derived `played_fraction`;
- the read models `SessionState` and `SessionHistory`.

Each enforces its invariants and transitions. *(B5: an occurrence also records `is_exploration`, and `surfaced_position`: where it was surfaced in its queue, never changed, unlike the current-queue `queue_position`.)*

`src/intentune/domain/policy.py` (B5) is Recommendation Policy v1, pure and deterministic apart from an injected random generator:
- `RecommendationPolicy`: every constant, validated and versioned as a whole (`POLICY_V1`, `policy-v1`);
- inputs: `PolicyCandidate` (a library track as the policy sees it, from `candidate_from_track()`), `SessionEvidence`, and `SessionSignals`, built from a session's turns and plays by `signals_from_session()`;
- the stages: `Targets.effective()` (current intent first), `feature_fit()`, `candidate_similarity()`, `session_fit()`, `score()` (renormalized stage weights), and `decide()` (eligibility, diversity, exploration, top three, #2 first), returning a `PolicyDecision` that converts to canonical `Recommendation`s.

A pending listener control in the signals is a one-refresh directive, part of current intent (TD-016 item 11):
- it decides exploration deterministically, without the random draw;
- it decides whether the pick may set an explicitly requested genre aside (`score(..., set_aside_genre=True)`);
- it decides where the pick goes.

A track that nothing can score is never given one. It can only be a control's pick under an explicit fallback rule, and it is surfaced without a score.

Feature comparison reuses `scoring.category_match()` and `scoring.closeness()`, extracted from `score_candidate()` without changing its output, so there is one copy of the scoring math.

`backend/tests/test_architecture_boundaries.py` checks every domain, port, and application module, including subpackages, with relative imports resolved. It fails if any of them imports SQLAlchemy, Alembic, `sqlite3`, FastAPI, Starlette, Pydantic, mutagen, soundfile, numpy, a filesystem module (`os`, `shutil`, `pathlib`, ...), or the persistence or adapter packages.

**Planned (Prototype 1):**

- A listening-session domain: `ListeningSession`, `SessionTurn`, `RecommendationOccurrence`, `FeedbackEvent` (B4). The session owns current state; turns, occurrences, and feedback own history (D31). *(Current since B4; see above.)*
- Recommendation Policy v1 (B5): eligibility, intent fit, session fit, long-term fit, combined rank, diversity/repetition re-rank, controlled exploration, and the rolling top three. Each stage is computed separately (D07, D08). All constants live in one versioned policy module. *(Current since B5; see above.)*
- Feedback interpretation (B6) and conservative long-term adaptation (B10).
- Existing `score_candidate()`/`rank_candidates()` are preserved. New scoring extends or refactors shared primitives so the scoring math is never duplicated, and complete-input legacy outputs stay identical (D38).

`Recommendation` (an algorithm result) stays distinct from `RecommendationOccurrence` (that result surfaced in a specific session at a specific moment).

### Application Layer

Coordinates complete use cases through ports.

**Current:** `src/intentune/application/recommendation_service.py` implements `recommend_music(candidates, profile, limit)`, which validates its inputs and delegates to canonical ranking, and `recommend_from_catalog(catalog, profile, limit)`, which requests candidates from a `Catalog` port (see below) and delegates to `recommend_music()`. Neither has a request/response concept, diversification, or session awareness. `src/intentune/application/local_listener.py` (B1) implements `ensure_default_listener(unit_of_work)`. It returns the default local listener, generating and committing it on first run, and depends only on the `UnitOfWork` port. `src/intentune/application/library.py` (B2) implements `LibraryService` with the guide's B2 capabilities: register and list sources, scan a source and rescan all, import one discovered file, list and get tracks, and mark a track unavailable. It runs the validate → hash → dedupe → copy → persist → tag pipeline and the incremental-scan rules through ports only (see [System Workflow](system-workflow.md#library-import-and-scanning-b2)).

`src/intentune/application/analysis.py` (B3) implements `AnalysisService`:
- `enqueue_pending()`: idempotent queuing of every track the current analyzer has not analyzed;
- `recover_interrupted()`;
- `process_next()` and `run_until_idle()`;
- `list_jobs()` and `features_for()`.

It owns retries, skips, and recording outcomes; the analyzer port only measures. `src/intentune/application/analysis_worker.py` (B3) implements `AnalysisWorker`:
- one daemon thread with `start()`, `wake()`, and `stop()`;
- it recovers interrupted jobs on start, then processes one job at a time;
- it queues new work when idle and survives errors (D28).

See [System Workflow](system-workflow.md#background-analysis-b3).

`src/intentune/application/sessions.py` (B4) implements `SessionService`, through the `UnitOfWork` port only:
- `start_session()` ends the listener's previous active session first;
- `apply_turn()`, `queue_recommendations()`, `play()`, `advance()`, and `end_session()`;
- `end_sessions_from_previous_run()` for D35;
- reads: `get_session()`, `list_sessions()`, and `history()`.

Each command is one transaction and works only on an active session. It does not rank (B5) or record and interpret feedback (B6). See [System Workflow](system-workflow.md#listening-session-b4-b5). *(B5: every change to a session gets a strictly later time than the one before, even when the clock has not moved, so turns and surfaced queues are totally ordered within a session; TD-016 item 13.)*

`src/intentune/application/recommendations.py` (B5) implements `RecommendationService`, through the `UnitOfWork` port only:
- `refresh_queue(session_id)`: reads the session, its turns and occurrences, and the library in one transaction, asks Policy v1 for the next three tracks, and surfaces them with `SessionService.queue_recommendations()`, marking the exploration pick;
- `decide(session_id)`: the same decision without writing.

The random generator and clock are injected, so tests are deterministic.

**Planned (Prototype 1):** library use cases (register/list sources, scan, import, list/get tracks, mark unavailable), session use cases (start session, apply turn, record playback event or reaction, refill/re-rank the queue), and playlist use cases. Pure application tests come before HTTP.

**Dependency direction (Current):** the application layer may import the
domain, and adapters may construct domain models. The domain does not import
the application layer, adapters, legacy compatibility code, or external
frameworks.

### API Layer

**Planned (B8).** A thin FastAPI boundary:

- Routes (listed in [API Design](../design/api-design.md))
- Pydantic request and response schemas, separate from ORM and domain models
- Status codes and a consistent error envelope with request IDs
- Dependency injection
- Audio serving by track ID with range support

Authentication is **not** part of Prototype 1 (D01). Routes stay thin: no scoring, ranking, or persistence logic inside route functions.

### Repository and Port Layer

Defines interfaces for data access and external capabilities.

**Current:** `src/intentune/ports/catalog.py` defines `Catalog`, a `Protocol` with one method, `list_candidates() -> Sequence[MusicCandidate]`. It names no CSV, database, or provider concept -- any adapter that returns `MusicCandidate` objects satisfies it. `src/intentune/application/recommendation_service.py`'s `recommend_from_catalog()` depends on this port, not on `CsvCatalog` or any other concrete adapter.

**Current (B1):** `src/intentune/ports/listener_profiles.py` defines `ListenerProfileRepository` (`get`, `get_default`, `add`). `src/intentune/ports/unit_of_work.py` defines `UnitOfWork`, the transaction boundary: it exposes the repositories, `commit()`, and `rollback()`, and anything left uncommitted is discarded when its `with` block ends. Repositories stage changes and never commit. See [Database Design](../design/database-design.md#repository-and-transaction-pattern).

**Current (B2):** `src/intentune/ports/library.py` defines `LibrarySourceRepository`, `SourceFileRepository`, and `TrackRepository`, all exposed by the same `UnitOfWork`. `src/intentune/ports/library_files.py` defines the file ports: `SourceFolders` (resolve, list, hash, and locate files in a source folder), `AudioInspector` (confirm a format by content and read tags), and `ManagedMedia` (store a verified copy, locate, check, and discard it). The library use cases touch files only through these.

**Current (B3):** `src/intentune/ports/analysis.py` defines `AudioAnalyzer`. It exposes `identity`, `supports(format)`, and `analyze(path, format)`, and measures only. It is kept separate from the job system. The same module defines `AnalysisJobRepository`, including the atomic `claim_next()`, and `TrackFeatureRepository`; both are exposed by `UnitOfWork`. A unit of work is not thread-safe; each thread uses its own.

**Current (B4):** `src/intentune/ports/sessions.py` defines the spec's `SessionRepository` and `FeedbackRepository` as four ports: `ListeningSessionRepository`, `SessionTurnRepository`, `RecommendationOccurrenceRepository`, and `FeedbackEventRepository`. All are exposed by `UnitOfWork`.

**Planned (Prototype 1):** `PlaylistRepository` (spec §4), added to the same unit of work.

**Future:** an `IntentParser` port for LLM intent parsing (D30), and an external provider port (D39).

### Adapter Layer

Implements ports using specific technology.

**Current:** `src/intentune/adapters/csv_catalog.py` is the first implemented adapter. It is the only module that knows about CSV column names, file paths, and string-to-number conversion for the song catalog; it converts raw rows into `MusicCandidate` objects and never prints. It exposes both the functional `load_music_candidates()` loader and `CsvCatalog`, a small class implementing the `Catalog` port around that loader. The legacy `load_songs()` in `src/recommender.py` calls `load_music_candidates()` directly and converts the result back into the historical dictionary shape for compatibility -- the legacy path predates the port and was not rewired onto it, since that would change nothing observable and adds risk for no behavioral benefit.

**Current (B1):** `src/intentune/persistence/` is the SQLite adapter package. `db.py` resolves the database URL and creates engines (foreign keys on, WAL, SQLAlchemy-emitted `BEGIN`). `models.py` holds the ORM records and the `UtcDateTime` type. `repositories.py` holds `SqlAlchemyListenerProfileRepository`, `unit_of_work.py` holds `SqlAlchemyUnitOfWork`, and `migrations.py` runs Alembic from Python. Migrations live in `backend/alembic/`. Records never leave this package; repositories return domain models. Details: [Database Design](../design/database-design.md).

**Current (B2):**

- `persistence/` gained `SqlAlchemyLibrarySourceRepository`, `SqlAlchemySourceFileRepository`, and `SqlAlchemyTrackRepository`, with migration `2540be2956b8`.
- `adapters/local_folders.py` (`LocalSourceFolders`) walks source folders safely. It skips links, stays inside the source even through Windows junctions, protects against loops, and excludes managed media.
- `adapters/managed_media.py` (`LocalManagedMedia`) writes atomic, hash-verified copies into `backend/data/media/<track_uuid>.<extension>`.
- `adapters/mutagen_audio.py` (`MutagenAudioInspector`) validates files by content and maps ID3, Vorbis-comment, and MP4 tags. It is the only module that imports mutagen.

**Current (B3):**

- `adapters/signal_levels.py` (`SignalLevelAnalyzer`) decodes WAV, FLAC, Ogg Vorbis, Opus, and MP3 through soundfile (libsndfile 1.2.2) in fixed-size blocks.
- It measures decoded duration, sample peak, and RMS level with numpy. It is the only module that imports soundfile or numpy.
- Its version, `1+libsndfile-1.2.2`, includes the decoder version, so a decoder upgrade triggers reanalysis.
- `persistence/` gained `SqlAlchemyAnalysisJobRepository` and `SqlAlchemyTrackFeatureRepository`, with migration `7a42f0b9c8bf`.
- `librosa` was evaluated and not added; see [TD-014](../decisions/technical-decisions.md#td-014-b3-background-analysis).

**Current (B4):** `persistence/` gained the four session repositories and migration `dd7360f46b8b`.
- The `ListeningContext` is stored as strict, versioned JSON (`context_to_json` / `context_from_json`).
- Partial unique indexes and composite same-session foreign keys enforce one active session per listener, one playing occurrence per session, unique queue positions, and turns and events that reference only their own session's occurrences.

**Planned (Prototype 1):**

- Further SQLAlchemy repositories and migrations for playlists (B7) and long-term adaptation records (B10)
- Estimated features (tempo, key, loudness in LUFS): a later analyzer version, once an evaluation set exists to measure their accuracy (TD-014)
- CSV compatibility (the existing adapter, kept)

**Future:** PostgreSQL repositories, an AI provider client, a YouTube Data API client, Spotify (D22, D39).

### UI Layer

**Current:** a React + TypeScript + Vite application in `frontend/`, governed by [the frontend architecture](../frontend/ARCHITECTURE.md). It calls a `SessionService` interface and never contains scoring or ranking rules.

**Planned (B9 / frontend F9):** an HTTP implementation of the service boundary. The backend owns session identity, structured context, recommendation occurrences and history, reactions, and playlist state. The frontend owns modal and drawer state, the composer draft, animation, scrolling and focus, and visual expansion state (D32).

## Core Architectural Rule

The domain must not import FastAPI, SQLAlchemy, SQLite, React, filesystem-specific code, AI SDKs, or provider SDKs (spec §4). Never expose raw local file paths to the frontend, and never store audio binaries in SQLite (D23).

## Deployment Model

**Planned (Prototype 1):** one backend process and one browser client on the listener's own device (D37). Database and media live under `backend/data/`.

**Future:** hosted deployment for other users, PostgreSQL, authentication, and multi-user operation.

## Conditions for Considering Microservices

Microservices should only be considered when there is evidence of one or more of these needs:

- Independent teams own separate capabilities
- One module requires independent scaling
- Deployment frequency differs significantly by module
- Security boundaries require separate services
- A clear domain boundary has remained stable over time
- The modular monolith has measurable operational limitations

Until then, the modular monolith remains the preferred architecture. Redis, Celery, Kafka, and microservices are explicitly out of scope for Prototype 1 (spec §3).
