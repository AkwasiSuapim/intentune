# Folder Structure

## Status

**Current, Planned, and Superseded.** Reconciled with Prototype 1 in Phase B0 (2026-10-18).

## Current Repository Structure

**Current (verified in B0).** Generated and ignored content (`.venv/`, `__pycache__/`, `node_modules/`, `dist/`, `.env`) is omitted.

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
│   ├── data/
│   │   └── songs.csv
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
│   │       │   └── ranking.py
│   │       ├── application/
│   │       │   ├── __init__.py
│   │       │   └── recommendation_service.py
│   │       ├── ports/
│   │       │   ├── __init__.py
│   │       │   └── catalog.py
│   │       └── adapters/
│   │           ├── __init__.py
│   │           └── csv_catalog.py
│   └── tests/
│       ├── test_recommender.py
│       ├── test_domain_models.py
│       ├── test_csv_catalog.py
│       ├── test_canonical_scoring.py
│       ├── test_canonical_ranking.py
│       ├── test_recommendation_service.py
│       ├── test_legacy_compatibility.py
│       └── test_catalog_port.py
└── frontend/
    ├── package.json, vite.config.ts, tsconfig*.json, .oxlintrc.json, index.html
    ├── browser-checks/  headless-Chrome checks (npm run check:browser)
    └── src/
        ├── app/         AppShell, MobileHeader, WorkspaceStatus, shell hooks
        ├── components/  presentational component vocabulary (CSS Modules)
        ├── features/
        │   └── session/ types, reducers, commands, composition, service interface
        ├── mocks/       mock SessionService, mock songs/sessions/artwork
        ├── demo/        component gallery and fixed design scenes
        ├── styles/      tokens and base CSS
        └── test/        DOM test helpers
```

`domain/scoring.py` and `domain/ranking.py` implement the current four-feature scoring rule and ranking/tie-breaking as the single source of truth; `ports/catalog.py` defines the `Catalog` protocol (`list_candidates() -> Sequence[MusicCandidate]`); `application/recommendation_service.py` is a use-case orchestrator offering both `recommend_music(candidates, profile, limit)` (candidates passed directly) and `recommend_from_catalog(catalog, profile, limit)` (candidates requested from a `Catalog` port); `adapters/csv_catalog.py` is the first adapter, converting raw CSV rows into `MusicCandidate` objects via `load_music_candidates()` and exposing `CsvCatalog`, which implements the `Catalog` port around that loader. `src/recommender.py`'s legacy dict/dataclass functions call into these rather than containing their own copy of the logic.

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

Suggested by the [backend execution guide](../agents/CLAUDE_BACKEND_EXECUTION_GUIDE.md) for B1. These are suggestions, not final names:

```text
backend/src/intentune/persistence/
    db.py
    models.py
    repositories.py

backend/alembic/
backend/alembic.ini
```

Later phases are expected to add, under `backend/src/intentune/`:

- new ports beside `ports/catalog.py`: `SessionRepository`, `TrackRepository`, `PlaylistRepository`, `FeedbackRepository` (spec §4)
- session-domain models and Recommendation Policy v1 modules under `domain/`, with all policy constants in one versioned module (B4, B5)
- library and analysis adapters (B2, B3)
- a thin FastAPI package with Pydantic schemas separate from ORM and domain models (B8)

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

### `backend/src/intentune/adapters/` (and the planned persistence package)

Concrete implementations: CSV, SQLite/SQLAlchemy repositories, managed media, metadata and audio analyzers.

### API package (planned, B8)

FastAPI routes, HTTP schemas, error translation, request IDs, and dependencies. Thin.

### `backend/data/`

The CSV catalog today. In Prototype 1 also the SQLite database and managed media, both gitignored.

### `backend/tests/`

All backend tests, run from `backend/` with `python -m pytest -q`.

### `frontend/`

Browser interface, built with React, Vite, and TypeScript. It lives outside the Python package, talks to the backend only through the API once integrated, and must not own recommendation rules.

## Migration Rule

Do not move all files at once. Introduce new structure gradually, only when working code needs it, while keeping the current test suite passing. Existing modules stay in place unless an approved requirement forces a move (D38).
