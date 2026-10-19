# Technical Decisions

## Status

**Living Document**

This file records important architectural and implementation decisions. Each decision should include its context, chosen option, alternatives, consequences, status, and date.

Prototype 1 decisions D01–D39 live in the [Prototype 1 Decision Register](intentune-prototype-decision-register.md) and are adopted by TD-011. Where an entry below conflicts with that register, the register wins; affected entries carry a dated update note rather than being rewritten.

## TD-001: Preserve the Existing Prototype

**Status:** Accepted

**Decision:** Keep the current CodePath recommender as the Version 1 baseline and refactor incrementally.

**Reason:** It already contains working scoring, ranking, explanations, tests, and documentation.

**Alternative:** Delete the project and rebuild from an empty repository.

**Consequence:** Some transitional duplication may exist while the new domain structure is introduced.

## TD-002: Use a Modular Monolith

**Status:** Accepted

**Decision:** Build one application with clearly separated internal modules.

**Reason:** The product is early, the team is small, and domain boundaries are still changing.

**Alternative:** Microservices.

**Consequence:** Deployment remains simple, but internal boundaries must be enforced through code organization and tests.

## TD-003: Develop Deterministic Logic Before AI

**Status:** Accepted

**Decision:** Improve validation, scoring, ranking, diversity, explanations, and feedback logic before adding a chatbot.

**Reason:** AI should translate user language into structured input, not hide weak backend logic.

**Consequence:** The first product increments may feel less advanced, but they will be easier to test and understand.

## TD-004: Add AI as an Adapter

**Status:** Future (deferred beyond Prototype 1). Was: Planned.

**Decision:** AI will implement an intent-parser interface and return validated structured data.

**Alternative:** Let AI control recommendation ranking and application flow directly.

**Consequence:** Intentune can change AI providers or disable AI without rewriting the core recommender.

**Update (2026-10-18, B0):** Prototype 1 uses structured `ListeningContext` plus a limited set of deterministic commands, and defers LLM parsing behind a future `IntentParser` port (D29, D30, D39). The principle stands: an LLM never chooses tracks directly.

## TD-005: Add YouTube as a Catalog Provider

**Status:** Future (deferred beyond Prototype 1). Was: Planned.

**Decision:** YouTube will provide candidates through an adapter using the official API.

**Alternative:** Scrape YouTube pages or make YouTube the recommendation engine.

**Consequence:** Intentune retains control of ranking but must handle missing music features and API quotas.

**Update (2026-10-18, B0):** Prototype 1's catalog is the listener's own music, imported into an Intentune-managed local library (D02, D03). Spotify/YouTube catalogs are deferred (D39). YouTube is no longer the first external catalog.

## TD-006: Use FastAPI for the Backend

**Status:** Accepted (not implemented yet; Phase B8)

**Reason:** The project is Python-based, the user is learning FastAPI, and typed request validation fits the architecture.

**Update (2026-10-18, B0):** confirmed by Prototype 1. `fastapi` and `uvicorn` are listed in `backend/requirements.txt` but no code uses them yet.

## TD-007: Use Streamlit for the First Browser Interface

**Status:** Superseded by TD-010

**Reason:** Fast Python delivery and current dependency availability.

**Alternative:** React or Next.js frontend.

**Revisit When:** The product requires stronger UI customization, multiple clients, or a separate frontend team.

## TD-008: Establish Canonical, Source-Independent Domain Models

**Status:** Accepted

**Decision:** Intentune's domain models must not depend on CSV formats, provider responses, HTTP frameworks, AI providers, or database schemas.

**Detail:** `src/intentune/domain/models.py` introduces typed dataclasses -- `MusicCandidate`, `UserProfile`, `ListeningContext`, `FeatureWeights`, `ScoreComponent`, `ScoreBreakdown`, `Recommendation` -- that any future FastAPI request, AI adapter, CSV loader, database repository, or YouTube adapter can produce or consume. They replace neither the existing dictionary-based functional API nor the existing dataclass-based OOP wrapper in `src/recommender.py`; both remain available with backward-compatible behavior.

**Reason:** The current implementation mixes dictionary profiles (`preferred_energy`, `preferred_danceability`) with a dataclass profile (`target_energy`, no danceability field, an inert `likes_acoustic` field). A single canonical vocabulary must exist before FastAPI, AI, YouTube, or a database can be added, otherwise each new adapter would invent its own shape.

**Alternative:** Keep extending the existing dictionaries and dataclasses ad hoc as new candidate sources are added.

**Consequence:** Three co-existing shapes exist during the transition: the historical dict API, the historical dataclass API, and the new canonical domain models. This is intentional duplication, tracked in docs/decisions/trade-offs.md, and will shrink as scoring and ranking are migrated onto the canonical models in a later phase.

**Also fixed as part of this decision:** the OOP `Recommender` wrapper no longer hard-codes `preferred_danceability` to `0.5` -- the legacy `UserProfile` dataclass gained a real `preferred_danceability` field (default `0.5`, matching the old hard-coded value exactly so existing call sites are unaffected) that the wrapper now actually reads.

## TD-009: Canonical Domain Objects Are the Internal Source of Truth

**Status:** Accepted

**Approval note:** Phase 2 explicitly approved source-independent domain
models, boundary conversion, and preservation of the legacy public
interfaces. The completed implementation also moved scoring and ranking into
canonical modules and added an application service and CSV adapter. The
owner has approved continuing with this canonical modular architecture,
including the module-boundary expansion beyond the earlier
model-only/minimal-structure scope.

**Decision:** Canonical domain objects are the internal source of truth. Storage formats, HTTP schemas, provider responses, and legacy dictionaries must be converted at system boundaries.

**Detail:** `src/intentune/domain/scoring.py` (`score_candidate`) and `src/intentune/domain/ranking.py` (`rank_candidates`) now contain the only implementation of the current four-feature scoring and ranking rules. `src/recommender.py`'s legacy `score_song()` and `recommend_songs()` convert their dict inputs into `MusicCandidate`/`UserProfile` at the top of the function, delegate to the canonical modules, and convert the result back into the historical `{"song", "score", "reasons"}` shape. `src/intentune/adapters/csv_catalog.py` is the only module that knows about CSV column names or file paths; `load_songs()` calls it and converts `MusicCandidate` objects back into the historical dict shape.

**Update (this phase):** a formal `Catalog` port (`src/intentune/ports/catalog.py`, a `Protocol` with `list_candidates()`) now sits between the application layer and any catalog implementation. `CsvCatalog` (`src/intentune/adapters/csv_catalog.py`) implements the port around the existing `load_music_candidates()` loader. `recommend_from_catalog()` (`src/intentune/application/recommendation_service.py`) depends on the `Catalog` port rather than the concrete CSV adapter, so it can be tested with an in-memory fake catalog and is ready to accept a future database or YouTube catalog without a rewrite. `recommend_music()` is unchanged and still accepts a candidate list directly.

**Reason:** TD-008 introduced the canonical models but left scoring and ranking duplicated between the legacy dict/dataclass path and the (until now, unused) canonical models. Keeping two implementations of the same scoring math in sync by hand is exactly the kind of drift the canonical models were meant to prevent.

**Alternative:** Keep the legacy dict-based scoring/ranking as the "real" implementation and let the canonical domain models remain a documentation-only vocabulary until FastAPI arrives.

**Consequence:** `src/recommender.py` no longer contains scoring math -- `_calculate_similarity_points()` and `_validate_numeric_preference()` were removed as dead code. A full-catalog regression test (`tests/test_legacy_compatibility.py`) confirms behaviorally equivalent scores, reasons, and ordering between the legacy and canonical paths for all 20 songs, not only the previously documented top five.

**Temporary limitation:** preserving `load_songs()` and `recommend_songs()`
causes an extra canonical-to-legacy-to-canonical conversion in the CLI path.
The compatibility requirement was explicitly approved; retiring that path is
a future decision.

**Revisit When:** The "Expanded and Configurable Scoring Engine" milestone (see docs/planning/development-phases.md) extends `score_candidate()` to tempo/valence/acousticness and missing-feature normalization; at that point the legacy dict API's four-field shape may need its own documented limitation notice, since it cannot express the wider feature set.

**Update (2026-10-18, B0):** that milestone is superseded by Prototype 1 Phase B5 (Recommendation Policy v1). D38 keeps this decision in force: B5 extends or refactors shared scoring primitives instead of creating a second copy of the scoring math, and must prove complete-input legacy outputs stay identical.

## TD-010: Use React, Vite, and TypeScript for the Frontend

**Status:** Accepted

**Decision:** The browser interface is a separate React application built with Vite and TypeScript in `frontend/`. It communicates with the backend only through the FastAPI HTTP API (TD-006). Streamlit is not used.

**Reason:** A separate frontend gives full control over the interface and keeps the Python backend a plain API with no UI concerns.

**Alternative:** Streamlit for the first browser interface (TD-007).

**Consequence:** The repository is split into `backend/` (Python) and `frontend/` (TypeScript). `streamlit` was removed from `backend/requirements.txt`. The browser interface cannot be built until the API exists, so the backend API phase comes first.

**Update (2026-10-18, B0):** in practice the frontend was built first, on mock data. Frontend phases F0–F8 (2026-10-13 to 2026-10-15) produced the full session UI behind a `SessionService` interface with a mock implementation. Frontend phase F9 (FastAPI integration) waits for the backend API, which corresponds to backend phases B8 and B9. The sentence above about building the API first describes the plan at the time, not what happened.

## TD-011: Adopt Prototype 1 — Local-First, Session-Aware Recommendation

**Status:** Accepted

**Date:** 2026-10-18 (recorded in Phase B0)

**Context:** Earlier planning aimed at a profile-based recommendation API, then an AI chatbot, then YouTube as the first external catalog, followed by hosted deployment. The approved direction is now different: a local-first application that imports the listener's own music, runs continuous listening sessions, and adapts within a session.

**Decision:** Adopt the [Prototype 1 Backend Implementation Specification](../planning/intentune-backend-prototype-implementation-spec.md) and the [Prototype 1 Decision Register](intentune-prototype-decision-register.md) (D01–D39) as the approved backend direction, executed in phases B0–B11 as described in the [backend execution guide](../agents/CLAUDE_BACKEND_EXECUTION_GUIDE.md).

Key consequences for earlier decisions:

| Earlier decision | Effect |
|---|---|
| TD-001 Preserve the existing prototype | Reaffirmed (D38) |
| TD-002 Modular monolith | Reaffirmed; no Redis, Celery, Kafka, or microservices in Prototype 1 |
| TD-003 Deterministic logic before AI | Reaffirmed (D29, D30, D39) |
| TD-004 AI as an adapter | Deferred to Future |
| TD-005 YouTube as a catalog provider | Deferred to Future; replaced for Prototype 1 by a managed local library |
| TD-006 FastAPI | Reaffirmed; built in B8 |
| TD-008, TD-009 Canonical domain | Reaffirmed and protected (D38) |
| TD-010 React frontend | Reaffirmed; integrated in B9 |

New technical choices introduced by the register include SQLite + SQLAlchemy + Alembic (D22), audio outside the database (D23), SHA-256 exact deduplication (D24), and a bounded in-process worker with persisted job state (D28).

**Alternatives Considered:** Continue the earlier roadmap (profile API, then AI, then YouTube); build on an external provider catalog first.

**Consequences:** Prototype 1 works without AI, external providers, accounts, or internet. It adds persistence, background work, and audio handling to a codebase that today has none. Hosted deployment, authentication, PostgreSQL, and provider integrations move to Future.

**Revisit When:** Prototype 1 meets its definition of done (spec §30), or evaluation in B11 shows a decision in the register does not hold.

## TD-012: B1 SQLite Persistence Foundation

**Status:** Accepted, awaiting B1 review

**Date:** 2026-10-19

**Context:** D22 fixes SQLite, synchronous SQLAlchemy, and Alembic, and the execution guide asks for UTC timestamps, enforced foreign keys, WAL only if verified, and one generated local listener. Several implementation details were left open, including one recorded in [risks and open questions](../planning/risks-and-open-questions.md): whether a relative database path resolves from the working directory or from the backend root.

**Decision:**

1. **Database location.** `DATABASE_URL` is read from the process environment. When it is unset, the default is `backend/data/intentune.db`. A relative SQLite path resolves against `backend/`, as the CSV adapter does, not against the working directory. Non-SQLite URLs are rejected. `backend/.env` is not loaded; that waits for a settings loader (B8) and would need a new dependency.
2. **Transactions.** SQLAlchemy emits `BEGIN` (driver `isolation_level = None` plus a `begin` event), so SQLite DDL is transactional and SAVEPOINTs behave on Python 3.11. Python 3.12's `autocommit=False` connect argument is the later alternative.
3. **Foreign keys and WAL.** Foreign keys are on for every connection. They are off during migrations, as SQLite's table-rebuild procedure requires, followed by `PRAGMA foreign_key_check` before commit. File databases use WAL, which tests verify.
4. **Identifiers and time.** UUID strings in canonical form (`String(36)`) rather than SQLAlchemy's `Uuid` type, which stores 32 hex characters without hyphens on SQLite. UTC timestamps through a `UtcDateTime` type that rejects naive datetimes.
5. **Layering.** `ListenerProfile` is a pure domain model. `ListenerProfileRepository` and `UnitOfWork` are ports. SQLAlchemy implementations live in `src/intentune/persistence/`, and ORM records never leave it.
6. **Transaction pattern.** An explicit-commit unit of work. Repositories never commit. Leaving the `with` block rolls back anything uncommitted.
7. **Default listener.** Created by the application use case `ensure_default_listener()`, not by a data migration. The database enforces at most one default with a partial unique index.
8. **Schema discipline.** A constraint naming convention from the first table, Alembic batch mode, migrations that use plain SQLAlchemy types, and a test that migrations and ORM records agree.

**Alternatives Considered:** Resolving the path from the working directory (SQLite's default; it ties correctness to where the process starts). Creating the listener inside the migration (every database would get one, but a deleted row would never come back, and tests that build schemas without migrating would lack it). A commit-on-success context manager (one less call, but a read-only or early-return path could write by accident). SQLAlchemy's `Uuid` type. Leaving the driver's legacy transaction mode (DDL would autocommit, so a failed migration could leave a half-applied schema). Async SQLAlchemy (no measured need).

**Consequences:** The database location does not depend on the working directory. A failed migration rolls back completely. Domain, port, and application code stays free of SQLAlchemy, and a test enforces that. Driver-independent `BEGIN` makes "database is locked" errors more likely under concurrent writers; WAL, short transactions, and the 5-second busy timeout mitigate this until B3 measures real contention. Nothing calls `ensure_default_listener()` or applies migrations at startup until B8.

**Revisit When:** the backend moves to Python 3.12 or later (decision 2); B3's worker shows lock contention (decision 3); B8 introduces settings loading (decision 1); PostgreSQL is adopted (D22).

## New Decision Template

```text
## TD-XXX: Decision Title

Status:
Date:
Owner:

Context:

Decision:

Alternatives Considered:

Consequences:

Revisit When:
```
