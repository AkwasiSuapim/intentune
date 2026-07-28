# Architecture

## Status

**Planned with Draft Details**

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
