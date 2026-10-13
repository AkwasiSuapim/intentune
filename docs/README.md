# Intentune Documentation

This directory contains the living technical and product documentation for **Intentune**, a personalized and explainable music recommendation system.

Intentune began as a CodePath Music Recommender Simulation and is being developed into a larger personalized music recommendation platform. The current prototype loads a small CSV catalog, compares each song with a user profile, scores the songs, ranks them, and explains each recommendation. The long-term goal is to turn that working prototype into a reliable backend-driven product that friends, family, and other users can access through a browser.

## Documentation Status

The documents use these labels:

- **Current**: describes functionality that already exists in the uploaded repository.
- **Planned**: a decision we have discussed and intend to build.
- **Draft**: a proposed design that must be reviewed before implementation.
- **Future**: an idea intentionally postponed until the core product is stable.

## Documentation Index

The documents are grouped into folders by purpose.

### `product/` — what Intentune is and what it must do

- [Project Description](product/project-description.md)
- [Product Requirements](product/product-requirements.md)
- [Features](product/features.md)

### `architecture/` — how the system is structured today and where it is heading

- [Architecture](architecture/architecture.md)
- [System Workflow](architecture/system-workflow.md)
- [Folder Structure](architecture/folder-structure.md)
- [Current System Audit](architecture/current-system-audit.md)

### `design/` — interface, data, and integration designs

- [API Design](design/api-design.md)
- [Database Design](design/database-design.md)
- [External Services](design/external-services.md)

### `planning/` — roadmap and unresolved questions

- [Development Phases](planning/development-phases.md)
- [Risks and Open Questions](planning/risks-and-open-questions.md)

### `decisions/` — why the system is built the way it is

- [Technical Decisions](decisions/technical-decisions.md)
- [Trade-offs](decisions/trade-offs.md)

### `quality/` — testing and security

- [Testing Strategy](quality/testing-strategy.md)
- [Security and Privacy](quality/security-and-privacy.md)

### `operations/` — running the system

- [Deployment](operations/deployment.md)
- [Observability](operations/observability.md)

### `templates/` — reusable document templates

- [Decision Log Template](templates/decision-log-template.md)
- [Phase Review Template](templates/phase-review-template.md)

### Project history

- [Changelog](changelog.md)

## Documentation Rules

- Update the relevant document whenever the implementation changes.
- Do not present a proposal as completed functionality.
- Record important architectural choices and rejected alternatives.
- Record technical challenges, consequences, and trade-offs.
- Keep the root project `README.md` concise and link to these deeper documents.
- Prefer simple language that a new engineer can understand quickly.
