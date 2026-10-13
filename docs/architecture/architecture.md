# Architecture

## Status

**Current and Planned**

## Architectural Style

Intentune will begin as a **modular monolith**.

This means:

- One repository
- One backend application
- One primary deployment unit
- Clear internal modules and interfaces
- No microservices until real operational needs justify them

## Why a Modular Monolith

The product requirements and domain rules are still evolving. A modular monolith gives us simple local development and deployment while allowing strong separation of responsibilities.

Microservices would add network calls, service discovery, distributed logging, authentication between services, deployment coordination, and more failure modes. Those costs are not justified for the current team and expected early usage.

## High-Level Components

The diagram below is the planned modular-monolith direction. The current
implementation has a domain layer, a minimal application service, and a CSV
adapter, but it does not yet define a catalog port or an API/UI boundary.

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

Contains business rules that should not depend on HTTP, databases, Streamlit, AI providers, or YouTube.

**Current:** `src/intentune/domain/models.py` defines the typed, source-independent models (`MusicCandidate`, `UserProfile`, `ListeningContext`, `FeatureWeights`, `ScoreComponent`, `ScoreBreakdown`, `Recommendation`). `src/intentune/domain/scoring.py` and `src/intentune/domain/ranking.py` now implement the current four-feature scoring rule and tie-breaking ranking rule as the single source of truth -- `src/recommender.py`'s legacy `score_song()`/`recommend_songs()` delegate to them rather than containing a second copy of the scoring math. None of these three modules import CSV, HTTP, database, or provider-specific code. `ListeningContext` and `FeatureWeights` are modeled but not yet used by scoring -- see docs/planning/development-phases.md, Phase 3.

Responsibilities:

- User preference models
- Candidate models
- Scoring
- Ranking
- Tie-breaking
- Diversity adjustment
- Match classification
- Recommendation reasons
- Feedback interpretation rules later

### Application Layer

Coordinates complete use cases.

Example:

```text
recommend_music(request)
  -> validate request
  -> get candidates
  -> score candidates
  -> rank candidates
  -> diversify results
  -> build response
```

**Current:** `src/intentune/application/recommendation_service.py` implements a first, minimal `recommend_music(candidates, profile, limit)` that validates its inputs and delegates to canonical ranking. It has no request/response concept yet (no diversification, no HTTP request object) -- those arrive with Phase 4's FastAPI layer.

**Dependency direction (Current):** the application layer may import the
domain, and adapters may construct domain models. The domain does not import
the application layer, adapters, legacy compatibility code, or external
frameworks.

### API Layer

Handles HTTP concerns:

- Routes
- Request and response schemas
- Status codes
- Error translation
- Dependency injection
- Authentication later

### Repository and Port Layer

Defines interfaces for data access and external capabilities.

Examples:

- Catalog provider
- User repository
- Feedback repository
- Intent parser
- External video provider

### Adapter Layer

Implements ports using specific technology:

- CSV catalog adapter
- SQLite repository
- PostgreSQL repository
- AI provider client
- YouTube Data API client

**Current:** `src/intentune/adapters/csv_catalog.py` is the first implemented adapter. It is the only module that knows about CSV column names, file paths, and string-to-number conversion for the song catalog; it converts raw rows into `MusicCandidate` objects and never prints. The legacy `load_songs()` in `src/recommender.py` calls it and converts the result back into the historical dictionary shape for compatibility. SQLite/PostgreSQL repositories, an AI provider client, and a YouTube client remain future adapters.

**Temporary limitation:** there is no formal catalog port or protocol yet.
The legacy compatibility layer calls the CSV adapter directly. Introducing a
catalog abstraction remains pending work; no placeholder port module has been
created.

### UI Layer

Provides a browser experience. It should call application or API interfaces rather than contain scoring rules.

## Core Architectural Rule

The recommendation domain must not import FastAPI, Streamlit, database drivers, OpenAI SDKs, or YouTube clients.

## Initial Deployment Model

One backend application and one browser-accessible interface. They may be packaged together initially.

## Conditions for Considering Microservices

Microservices should only be considered when there is evidence of one or more of these needs:

- Independent teams own separate capabilities
- One module requires independent scaling
- Deployment frequency differs significantly by module
- Security boundaries require separate services
- A clear domain boundary has remained stable over time
- The modular monolith has measurable operational limitations

Until then, the modular monolith remains the preferred architecture.
