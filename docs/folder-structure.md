# Folder Structure

## Status

**Current and Planned**

## Current Repository Structure

```text
intentune/
├── README.md
├── model_card.md
├── ai_interactions.md
├── requirements.txt
├── data/
│   └── songs.csv
├── src/
│   ├── __init__.py
│   ├── main.py
│   └── recommender.py
└── tests/
    └── test_recommender.py
```

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
│       ├── adapters/
│       │   ├── csv_catalog.py
│       │   ├── database_catalog.py
│       │   ├── youtube_catalog.py
│       │   ├── ai_intent_parser.py
│       │   └── repositories.py
│       │
│       └── ui/
│           └── streamlit_app.py
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

### `ui/`

Browser interface. It must not own recommendation rules.

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
