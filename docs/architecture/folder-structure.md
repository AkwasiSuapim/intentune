# Folder Structure

## Status

**Current, Planned, and Superseded.** Reconciled with Prototype 1 in Phase B0 (2026-10-18).

## Current Repository Structure

**Current (verified in B0; backend updated through B5, 2026-10-20).** Generated and ignored content (`.venv/`, `__pycache__/`, `node_modules/`, `dist/`, `.env`, `backend/data/intentune.db*`) is omitted.

```text
intentune/
├── .gitignore
├── README.md
├── model_card.md
├── ai_interactions.md
├── docs/
│   ├── README.md
│   ├── DOCUMENTATION-MANIFEST.txt
│   ├── changelog.md
│   ├── agents/          backend execution guide
│   ├── architecture/
│   ├── decisions/       incl. the Prototype 1 decision register
│   ├── design/
│   ├── frontend/        frontend architecture, phases, approved design
│   ├── operations/
│   ├── planning/        incl. the Prototype 1 specification
│   ├── product/
│   ├── quality/
│   └── templates/
├── backend/
│   ├── .env.example
│   ├── requirements.txt
│   ├── alembic.ini                    (B1)
│   ├── alembic/                       (B1)
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       ├── 20261019_6ef3a3452ab7_create_listener_profiles.py
│   │       ├── 20261019_2540be2956b8_create_managed_library.py  (B2)
│   │       ├── 20261020_7a42f0b9c8bf_create_background_analysis.py  (B3)
│   │       ├── 20261020_dd7360f46b8b_create_listening_sessions.py  (B4)
│   │       ├── 20261020_de244c476f3a_record_surfaced_position_and_exploration.py  (B5)
│   │       └── 20261021_ce0b59df2cd1_create_playlists.py  (B7)
│   ├── data/
│   │   └── songs.csv                  (intentune.db and media/ appear here when used; gitignored)
│   ├── src/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── recommender.py
│   │   └── intentune/
│   │       ├── __init__.py
│   │       ├── domain/
│   │       │   ├── __init__.py
│   │       │   ├── models.py
│   │       │   ├── scoring.py
│   │       │   ├── ranking.py
│   │       │   ├── listener.py        (B1)
│   │       │   ├── library.py         (B2)
│   │       │   ├── validation.py      (B2: shared validators)
│   │       │   ├── analysis.py        (B3: jobs, features, analyzer identity)
│   │       │   ├── session.py         (B4: sessions, turns, occurrences, feedback events)
│   │       │   ├── policy.py          (B5: Recommendation Policy v1 and its constants; B6: Feedback Policy v1)
│   │       │   └── playlist.py        (B7: playlists and their ordered items)
│   │       ├── application/
│   │       │   ├── __init__.py
│   │       │   ├── recommendation_service.py
│   │       │   ├── local_listener.py  (B1)
│   │       │   ├── library.py         (B2: LibraryService)
│   │       │   ├── analysis.py        (B3: AnalysisService)
│   │       │   ├── analysis_worker.py (B3: AnalysisWorker thread)
│   │       │   ├── sessions.py        (B4: SessionService)
│   │       │   ├── recommendations.py (B5: RecommendationService, queue refresh)
│   │       │   ├── feedback.py        (B6: FeedbackService)
│   │       │   ├── playlists.py       (B7: PlaylistService)
│   │       │   ├── listening.py       (B8: ListeningService, start/steer then re-rank)
│   │       │   ├── library_scans.py   (B8: LibraryScanCoordinator, one scan at a time)
│   │       │   └── messages.py        (B9: MessageService, typed words -> the controls' use cases)
│   │       ├── ports/
│   │       │   ├── __init__.py
│   │       │   ├── catalog.py
│   │       │   ├── listener_profiles.py  (B1)
│   │       │   ├── unit_of_work.py    (B1)
│   │       │   ├── library.py         (B2: library repositories)
│   │       │   ├── library_files.py   (B2: folders, inspector, media)
│   │       │   ├── analysis.py        (B3: analyzer, job and feature repositories)
│   │       │   ├── sessions.py        (B4: session, turn, occurrence, feedback repositories)
│   │       │   └── playlists.py       (B7: playlist repository)
│   │       ├── adapters/
│   │       │   ├── __init__.py
│   │       │   ├── csv_catalog.py
│   │       │   ├── local_folders.py   (B2)
│   │       │   ├── managed_media.py   (B2)
│   │       │   ├── mutagen_audio.py   (B2)
│   │       │   ├── signal_levels.py   (B3: SignalLevelAnalyzer)
│   │       │   └── deterministic_intent.py  (B9: DeterministicIntentInterpreter)
│   │       ├── api/                   (B8: the HTTP API)
│   │       │   ├── __init__.py
│   │       │   ├── __main__.py        (python -m src.intentune.api)
│   │       │   ├── app.py             (create_app(), lifespan)
│   │       │   ├── container.py       (composition root: adapters once, services per request)
│   │       │   ├── settings.py        (process environment)
│   │       │   ├── errors.py          (error envelope, request IDs)
│   │       │   ├── schemas.py         (Pydantic request and response bodies)
│   │       │   ├── views.py           (domain objects -> response bodies)
│   │       │   ├── dependencies.py
│   │       │   └── routes/
│   │       │       ├── __init__.py
│   │       │       ├── health.py
│   │       │       ├── library.py
│   │       │       ├── tracks.py      (audio by track id)
│   │       │       ├── sessions.py
│   │       │       └── playlists.py
│   │       └── persistence/           (B1)
│   │           ├── __init__.py
│   │           ├── db.py
│   │           ├── models.py
│   │           ├── repositories.py
│   │           ├── unit_of_work.py
│   │           └── migrations.py
│   └── tests/
│       ├── conftest.py                (B1: database fixtures; B2: generated audio files, library fixture; B8: API app and client)
│       ├── test_recommender.py
│       ├── test_domain_models.py
│       ├── test_csv_catalog.py
│       ├── test_canonical_scoring.py
│       ├── test_canonical_ranking.py
│       ├── test_recommendation_service.py
│       ├── test_legacy_compatibility.py
│       ├── test_catalog_port.py
│       ├── test_listener_profile.py   (B1)
│       ├── test_local_listener_service.py  (B1)
│       ├── test_persistence_db.py     (B1)
│       ├── test_migrations.py         (B1)
│       ├── test_listener_repository.py  (B1)
│       ├── test_architecture_boundaries.py  (B1)
│       ├── test_library_domain.py     (B2)
│       ├── test_mutagen_audio.py      (B2)
│       ├── test_managed_media.py      (B2)
│       ├── test_local_folders.py      (B2)
│       ├── test_library_repositories.py  (B2)
│       ├── test_library_service.py    (B2)
│       ├── test_analysis_domain.py    (B3)
│       ├── test_signal_levels.py      (B3)
│       ├── test_analysis_repositories.py  (B3)
│       ├── test_analysis_service.py   (B3)
│       ├── test_analysis_worker.py    (B3)
│       ├── test_session_domain.py     (B4)
│       ├── test_session_repositories.py  (B4)
│       ├── test_session_service.py    (B4)
│       ├── test_policy.py             (B5)
│       ├── test_queue_refresh.py      (B5)
│       ├── test_feedback_policy.py    (B6)
│       ├── test_feedback_service.py   (B6)
│       ├── test_playlist_domain.py    (B7)
│       ├── test_playlist_repositories.py  (B7)
│       ├── test_playlist_service.py   (B7)
│       ├── test_listening_service.py  (B8)
│       ├── test_library_scans.py      (B8)
│       ├── test_api_errors.py         (B8)
│       ├── test_api_library.py        (B8)
│       ├── test_api_audio.py          (B8)
│       ├── test_api_sessions.py       (B8)
│       ├── test_api_playlists.py      (B8)
│       ├── test_api_startup.py        (B8)
│       ├── test_intent_interpreter.py (B9)
│       ├── test_message_service.py    (B9)
│       └── test_api_messages.py       (B9)
└── frontend/
    ├── package.json, vite.config.ts, tsconfig*.json, .oxlintrc.json, index.html
    ├── browser-checks/  headless-Chrome checks (npm run check:browser)
    └── src/
        ├── app/         AppShell, MobileHeader, WorkspaceStatus, shell hooks
        ├── components/  presentational component vocabulary (CSS Modules)
        ├── features/
        │   └── session/ types, reducers, commands, composition, service interface
        ├── services/
        │   └── http/    (B9) the HTTP SessionService: client, mappings, service
        ├── mocks/       mock SessionService, mock songs/sessions/artwork, quick actions
        ├── demo/        component gallery and fixed design scenes
        ├── styles/      tokens and base CSS
        └── test/        DOM test helpers
```

`domain/scoring.py` and `domain/ranking.py` implement the current four-feature scoring rule and ranking/tie-breaking as the single source of truth; `ports/catalog.py` defines the `Catalog` protocol (`list_candidates() -> Sequence[MusicCandidate]`); `application/recommendation_service.py` is a use-case orchestrator offering both `recommend_music(candidates, profile, limit)` (candidates passed directly) and `recommend_from_catalog(catalog, profile, limit)` (candidates requested from a `Catalog` port); `adapters/csv_catalog.py` is the first adapter, converting raw CSV rows into `MusicCandidate` objects via `load_music_candidates()` and exposing `CsvCatalog`, which implements the `Catalog` port around that loader. `src/recommender.py`'s legacy dict/dataclass functions call into these rather than containing their own copy of the logic.

B1 added the SQLite persistence foundation. `domain/listener.py` is the pure `ListenerProfile` model. `ports/listener_profiles.py` and `ports/unit_of_work.py` are the storage ports. `application/local_listener.py` holds the `ensure_default_listener()` use case. `persistence/` is the SQLAlchemy adapter package (engine configuration, ORM records, repository, unit of work, programmatic migrations). `backend/alembic/` holds the migrations. Persistence sits in its own package beside `adapters/`, as the execution guide suggested, because later phases add many tables and repositories to it.

B2 added the managed library:
- **Domain:** `domain/library.py` holds the pure library rules; `domain/validation.py` holds validators shared by the listener and library models.
- **Ports:** `ports/library.py` (repositories) and `ports/library_files.py` (source folders, audio inspector, managed media).
- **Application:** `application/library.py` holds `LibraryService`.
- **File adapters:** `adapters/local_folders.py`, `adapters/managed_media.py`, and `adapters/mutagen_audio.py`.
- **Persistence:** the library repositories and records joined `persistence/`, with a second migration.

B3 added background analysis:
- **Domain:** `domain/analysis.py` holds jobs, features, analyzer identity, and their rules.
- **Ports:** `ports/analysis.py` holds the `AudioAnalyzer` port and the job and feature repositories.
- **Application:** `application/analysis.py` holds `AnalysisService`, and `application/analysis_worker.py` holds the single worker thread.
- **Adapter:** `adapters/signal_levels.py` holds the soundfile and numpy analyzer.
- **Persistence:** analysis repositories and records joined `persistence/`, with a third migration.

The worker lives in `application/`: it only coordinates `AnalysisService` with a thread and two events, and does no I/O itself.

B4 added the session domain:
- **Domain:** `domain/session.py`.
- **Ports:** `ports/sessions.py`.
- **Application:** `application/sessions.py` (`SessionService`).
- **Persistence:** session records, repositories, and the context JSON codec joined `persistence/`, with a fourth migration.

No new adapter or dependency.

B5 added Recommendation Policy v1:
- **Domain:** `domain/policy.py` holds every stage and every constant (one versioned `RecommendationPolicy`). `domain/scoring.py` now exposes the shared feature primitives it reuses.
- **Application:** `application/recommendations.py` (`RecommendationService`). It is not `recommendation_service.py`, which keeps the legacy catalog use cases.
- **Persistence:** two columns on occurrence records (surfaced position and exploration mark), with a fifth migration.

No new port, adapter, or dependency.

B6 added feedback:
- **Domain:** Feedback Policy v1 joined `domain/policy.py`; listener replays joined `domain/session.py`.
- **Application:** `application/feedback.py` (`FeedbackService`), with the recording itself in `SessionService.record_feedback()`.

No new port, adapter, table, migration, or dependency.

B7 added playlists:
- **Domain:** `domain/playlist.py`.
- **Ports:** `ports/playlists.py`.
- **Application:** `application/playlists.py` (`PlaylistService`).
- **Persistence:** playlist records and their repository joined `persistence/`, with a sixth migration.

No new adapter or dependency.

B9 added frontend integration:
- **Domain:** `domain/intent.py` (vocabulary, energy scale, message meanings).
- **Port:** `ports/intent.py` (`IntentInterpreter`).
- **Adapter:** `adapters/deterministic_intent.py`.
- **Application:** `application/messages.py`.
- **API:** `api/routes/listening.py`.
- **Migration:** `4b1e9c7d2a6f` (UNLIKE).
- **Frontend:** `src/services/http/` and `features/session/useAudioPlayback.ts`.

No new dependency.

B8 added the HTTP API:
- **API:** `api/`, with its routes in `api/routes/`. Only `container.py` and `settings.py` import persistence or adapters.
- **Application:** `application/listening.py` and `application/library_scans.py`.

No new port, adapter, table, migration, or dependency.

Backend tests import `src.…`, so the suite runs from `backend/`. The frontend's own structure is described in [the frontend architecture](../frontend/ARCHITECTURE.md) §24.

## Planned Prototype 1 Additions

**Planned.** The backend stays under `backend/`, and the existing packages stay where they are. Directories are created only when the phase that needs them is implemented (see the Migration Rule).

Fixed by the specification:

```text
backend/data/
    songs.csv            (existing; CSV compatibility)
    intentune.db         SQLite database          — must be gitignored
    media/
        <track_uuid>.<extension>                   — must be gitignored
```

The [backend execution guide](../agents/CLAUDE_BACKEND_EXECUTION_GUIDE.md) suggested `persistence/` with `db.py`, `models.py`, and `repositories.py`, plus `backend/alembic/` and `backend/alembic.ini`, for B1. **Implemented in B1** as shown in the current tree above, with `unit_of_work.py` and `migrations.py` added.

Later phases are expected to add, under `backend/src/intentune/`:

- new ports beside `ports/catalog.py` and `ports/listener_profiles.py`: `SessionRepository`, `TrackRepository`, `PlaylistRepository`, `FeedbackRepository` (spec §4), each exposed through the existing `UnitOfWork`, with SQLAlchemy implementations and migrations in `persistence/` and `backend/alembic/versions/`
- session-domain models and Recommendation Policy v1 modules under `domain/`, with all policy constants in one versioned module (B4, B5) *(done: `domain/session.py`, `domain/policy.py`)*
- library and analysis adapters (B2, B3)
- a thin FastAPI package with Pydantic schemas separate from ORM and domain models (B8) *(done: `api/`)*

The exact module names are decided in the phase that creates them and recorded here at that time.

## Superseded: Proposed Incremental Structure

**Superseded.** This earlier proposal moved code to a repository-root `src/intentune/`, `data/`, and `tests/unit|integration|api/`, and named YouTube and AI adapters. The `backend/`/`frontend/` split (TD-010) replaced the root layout, Prototype 1 places data under `backend/data/`, and YouTube and AI adapters are deferred (D39). Kept for history.

```text
intentune/
├── README.md
├── model_card.md
├── pyproject.toml or requirements.txt
├── .env.example
├── .gitignore
│
├── docs/
│   └── project documentation
│
├── data/
│   └── songs.csv
│
├── src/
│   └── intentune/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       ├── exceptions.py
│       │
│       ├── domain/
│       │   ├── models.py
│       │   ├── scoring.py
│       │   ├── ranking.py
│       │   └── feedback.py
│       │
│       ├── application/
│       │   └── recommendation_service.py
│       │
│       ├── api/
│       │   ├── routes.py
│       │   ├── schemas.py
│       │   └── dependencies.py
│       │
│       ├── ports/
│       │   ├── catalog.py
│       │   ├── feedback_store.py
│       │   └── intent_parser.py
│       │
│       └── adapters/
│           ├── csv_catalog.py
│           ├── database_catalog.py
│           ├── youtube_catalog.py
│           ├── ai_intent_parser.py
│           └── repositories.py
│
└── tests/
    ├── unit/
    ├── integration/
    ├── api/
    └── fixtures/
```

## Directory Responsibilities

### `backend/src/intentune/domain/`

Pure business rules and models. No FastAPI, SQLAlchemy, SQLite, filesystem, AI, or provider imports.

### `backend/src/intentune/application/`

Coordinates complete use cases through ports.

### `backend/src/intentune/ports/`

Interfaces that describe what the application needs from storage and external capabilities.

### `backend/src/intentune/adapters/` and `backend/src/intentune/persistence/`

Concrete implementations.
- **`adapters/`** holds the CSV catalog; since B2, the source-folder walker, managed media, and the mutagen audio inspector; and since B3, the signal-level analyzer.
- **`persistence/`** (B1) holds the SQLite/SQLAlchemy engine setup, ORM records, repositories, and unit of work.

Outside the tests, only `persistence/` and `backend/alembic/` import SQLAlchemy or Alembic. Only `adapters/` imports mutagen, soundfile, or numpy, or does file I/O.

### `backend/alembic/`

Alembic environment and versioned migrations (B1). Run `alembic upgrade head` from `backend/`.

### `backend/src/intentune/api/`

The HTTP API (B8): FastAPI routes, HTTP schemas, error translation, request IDs, and dependencies. Thin. `container.py` and `settings.py` are the composition root, the only API modules that import persistence or adapters; routes, schemas, views, and error handling reach storage and files only through the application layer. No inner layer imports the API. An architecture test enforces both rules.

### `backend/data/`

The CSV catalog, and the default locations of the SQLite database (`intentune.db`, from B1, created by `alembic upgrade head`) and managed media (`media/`, from B2, created on first import). Both are gitignored.

### `backend/tests/`

All backend tests, run from `backend/` with `python -m pytest -q`.

### `frontend/`

Browser interface, built with React, Vite, and TypeScript. It lives outside the Python package, talks to the backend only through the API once integrated, and must not own recommendation rules.

## Migration Rule

Do not move all files at once. Introduce new structure gradually, only when working code needs it, while keeping the current test suite passing. Existing modules stay in place unless an approved requirement forces a move (D38).
