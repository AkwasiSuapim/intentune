# Intentune Documentation

This directory contains the living technical and product documentation for **Intentune**, a personalized and explainable music recommendation system.

Intentune began as a CodePath Music Recommender Simulation. The current backend loads a small CSV catalog, compares each song with a user profile, scores the songs, ranks them, and explains each recommendation. A separate React frontend runs an interactive listening-session experience on mock data.

The approved next step is **Prototype 1**: a local-first, session-aware, continuously adapting music application that imports the listener's own music, persists it locally, and adapts recommendations within a listening session. It must work without AI, external music providers, accounts, or cloud infrastructure. Product principle: **Conversation steers. Music leads.**

## Sources of Truth

When documents disagree, use this order:

1. **The local repository** — what is actually implemented. Documentation is not proof of implementation.
2. **[Prototype 1 Backend Implementation Specification](planning/intentune-backend-prototype-implementation-spec.md)** and **[Prototype 1 Decision Register](decisions/intentune-prototype-decision-register.md)** (decisions D01–D39) — the approved backend direction.
3. **[Claude Backend Execution Guide](agents/CLAUDE_BACKEND_EXECUTION_GUIDE.md)** — how backend phases B0–B11 are executed.
4. **[Frontend documents](frontend/)** — frontend architecture, phases, and the approved design. They govern the browser client.
5. **The other documents in this directory** — reconciled with Prototype 1 in Phase B0 (2026-10-18). Earlier plans they contain are kept and marked **Superseded**.

## Documentation Status Labels

- **Current**: exists in the repository today and has been verified.
- **Planned**: approved to build (for the backend, in Prototype 1) but not implemented yet.
- **Draft**: a proposed design that must be reviewed before implementation, such as request/response schemas not yet defined.
- **Superseded**: an earlier plan replaced by a later approved decision. Kept for history; do not build from it.
- **Future**: intentionally postponed beyond Prototype 1.

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

- [Prototype 1 Backend Implementation Specification](planning/intentune-backend-prototype-implementation-spec.md)
- [Development Phases](planning/development-phases.md)
- [Risks and Open Questions](planning/risks-and-open-questions.md)

### `decisions/` — why the system is built the way it is

- [Prototype 1 Decision Register](decisions/intentune-prototype-decision-register.md)
- [Technical Decisions](decisions/technical-decisions.md)
- [Trade-offs](decisions/trade-offs.md)

### `agents/` — execution instructions for coding agents

- [Claude Backend Execution Guide](agents/CLAUDE_BACKEND_EXECUTION_GUIDE.md)

### `frontend/` — the browser client

- [Agent Instructions](frontend/AGENT_INSTRUCTIONS.md)
- [Architecture](frontend/ARCHITECTURE.md)
- [Implementation Phases](frontend/IMPLEMENTATION_PHASES.md)
- [Approved design reference](frontend/design/approved/README.md)

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
- Mark replaced plans as **Superseded** instead of deleting them.
- Record important architectural choices and rejected alternatives.
- Record technical challenges, consequences, and trade-offs.
- Keep the root project `README.md` concise and link to these deeper documents.
- Prefer simple language that a new engineer can understand quickly.
