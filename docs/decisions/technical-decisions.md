# Technical Decisions

## Status

**Living Document**

This file records important architectural and implementation decisions. Each decision should include its context, chosen option, alternatives, consequences, status, and date.

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

**Status:** Planned

**Decision:** AI will implement an intent-parser interface and return validated structured data.

**Alternative:** Let AI control recommendation ranking and application flow directly.

**Consequence:** Intentune can change AI providers or disable AI without rewriting the core recommender.

## TD-005: Add YouTube as a Catalog Provider

**Status:** Planned

**Decision:** YouTube will provide candidates through an adapter using the official API.

**Alternative:** Scrape YouTube pages or make YouTube the recommendation engine.

**Consequence:** Intentune retains control of ranking but must handle missing music features and API quotas.

## TD-006: Use FastAPI for the Backend

**Status:** Accepted

**Reason:** The project is Python-based, the user is learning FastAPI, and typed request validation fits the architecture.

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

**Status:** Pending owner approval

**Approval note:** Phase 2 explicitly approved source-independent domain
models, boundary conversion, and preservation of the legacy public
interfaces. The completed implementation also moved scoring and ranking into
canonical modules and added an application service and CSV adapter. That
expanded module-boundary decision is implemented and tested, but it exceeded
the earlier model-only/minimal-structure boundary and requires owner review
before this decision is marked accepted.

**Decision:** Canonical domain objects are the internal source of truth. Storage formats, HTTP schemas, provider responses, and legacy dictionaries must be converted at system boundaries.

**Detail:** `src/intentune/domain/scoring.py` (`score_candidate`) and `src/intentune/domain/ranking.py` (`rank_candidates`) now contain the only implementation of the current four-feature scoring and ranking rules. `src/recommender.py`'s legacy `score_song()` and `recommend_songs()` convert their dict inputs into `MusicCandidate`/`UserProfile` at the top of the function, delegate to the canonical modules, and convert the result back into the historical `{"song", "score", "reasons"}` shape. `src/intentune/adapters/csv_catalog.py` is the only module that knows about CSV column names or file paths; `load_songs()` calls it and converts `MusicCandidate` objects back into the historical dict shape.

**Reason:** TD-008 introduced the canonical models but left scoring and ranking duplicated between the legacy dict/dataclass path and the (until now, unused) canonical models. Keeping two implementations of the same scoring math in sync by hand is exactly the kind of drift the canonical models were meant to prevent.

**Alternative:** Keep the legacy dict-based scoring/ranking as the "real" implementation and let the canonical domain models remain a documentation-only vocabulary until FastAPI arrives.

**Consequence:** `src/recommender.py` no longer contains scoring math -- `_calculate_similarity_points()` and `_validate_numeric_preference()` were removed as dead code. A full-catalog regression test (`tests/test_legacy_compatibility.py`) confirms behaviorally equivalent scores, reasons, and ordering between the legacy and canonical paths for all 20 songs, not only the previously documented top five.

**Temporary limitation:** preserving `load_songs()` and `recommend_songs()`
causes an extra canonical-to-legacy-to-canonical conversion in the CLI path.
The compatibility requirement was explicitly approved; retiring that path is
a future decision.

**Revisit When:** The "Expanded and Configurable Scoring Engine" milestone (see docs/planning/development-phases.md) extends `score_candidate()` to tempo/valence/acousticness and missing-feature normalization; at that point the legacy dict API's four-field shape may need its own documented limitation notice, since it cannot express the wider feature set.

## TD-010: Use React, Vite, and TypeScript for the Frontend

**Status:** Accepted

**Decision:** The browser interface is a separate React application built with Vite and TypeScript in `frontend/`. It communicates with the backend only through the FastAPI HTTP API (TD-006). Streamlit is not used.

**Reason:** A separate frontend gives full control over the interface and keeps the Python backend a plain API with no UI concerns.

**Alternative:** Streamlit for the first browser interface (TD-007).

**Consequence:** The repository is split into `backend/` (Python) and `frontend/` (TypeScript). `streamlit` was removed from `backend/requirements.txt`. The browser interface cannot be built until the API exists, so the backend API phase comes first.

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
