# Folder Structure

## Status

**Current and Planned**

## Current Repository Structure

```text
intentune/
├── .gitignore
├── README.md
├── model_card.md
├── ai_interactions.md
├── docs/
│   └── project documentation
├── backend/
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
    └── Vite + React + TypeScript scaffold
```

`domain/scoring.py` and `domain/ranking.py` implement the current four-feature scoring rule and ranking/tie-breaking as the single source of truth; `ports/catalog.py` defines the `Catalog` protocol (`list_candidates() -> Sequence[MusicCandidate]`); `application/recommendation_service.py` is a use-case orchestrator offering both `recommend_music(candidates, profile, limit)` (candidates passed directly) and `recommend_from_catalog(catalog, profile, limit)` (candidates requested from a `Catalog` port); `adapters/csv_catalog.py` is the first adapter, converting raw CSV rows into `MusicCandidate` objects via `load_music_candidates()` and exposing `CsvCatalog`, which implements the `Catalog` port around that loader. `src/recommender.py`'s legacy dict/dataclass functions now call into these rather than containing their own copy of the logic. Placeholder folders (`api/`, `database_catalog.py`, `youtube_catalog.py`, `ai_intent_parser.py`) are still intentionally not created until working code needs them, per the Migration Rule below.

## Proposed Incremental Structure

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

### `domain/`

Pure business rules and models. No framework or provider imports.

### `application/`

Coordinates complete use cases.

### `api/`

FastAPI routes, HTTP schemas, and API dependencies.

### `ports/`

Interfaces that describe what the domain or application needs from external systems.

### `adapters/`

Concrete integrations for CSV, databases, AI providers, and YouTube.

### `frontend/`

Browser interface, built with React, Vite, and TypeScript. It lives outside the Python package, talks to the backend through the API, and must not own recommendation rules.

### `tests/unit/`

Fast tests for individual functions and classes.

### `tests/integration/`

Tests communication between modules, repositories, or mocked external services.

### `tests/api/`

Tests routes, validation, status codes, and error responses.

### `tests/fixtures/`

Stable sample data such as mocked YouTube responses.

## Migration Rule

Do not move all files at once. Introduce the target structure gradually while keeping the current test suite passing.
