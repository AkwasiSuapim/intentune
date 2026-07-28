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

**Status:** Proposed

**Reason:** The project is Python-based, the user is learning FastAPI, and typed request validation fits the architecture.

**Must Be Confirmed Before Implementation:** Yes.

## TD-007: Use Streamlit for the First Browser Interface

**Status:** Proposed

**Reason:** Fast Python delivery and current dependency availability.

**Alternative:** React or Next.js frontend.

**Revisit When:** The product requires stronger UI customization, multiple clients, or a separate frontend team.

## TD-008: Establish Canonical, Source-Independent Domain Models

**Status:** Accepted

**Decision:** Intentune's domain models must not depend on CSV formats, provider responses, HTTP frameworks, AI providers, or database schemas.

**Detail:** `src/intentune/domain/models.py` introduces typed dataclasses -- `MusicCandidate`, `UserProfile`, `ListeningContext`, `FeatureWeights`, `ScoreComponent`, `ScoreBreakdown`, `Recommendation` -- that any future FastAPI request, AI adapter, CSV loader, database repository, or YouTube adapter can produce or consume. They replace neither the existing dictionary-based functional API nor the existing dataclass-based OOP wrapper in `src/recommender.py`; both keep working unchanged.

**Reason:** The current implementation mixes dictionary profiles (`preferred_energy`, `preferred_danceability`) with a dataclass profile (`target_energy`, no danceability field, an inert `likes_acoustic` field). A single canonical vocabulary must exist before FastAPI, AI, YouTube, or a database can be added, otherwise each new adapter would invent its own shape.

**Alternative:** Keep extending the existing dictionaries and dataclasses ad hoc as new candidate sources are added.

**Consequence:** Three co-existing shapes exist during the transition: the historical dict API, the historical dataclass API, and the new canonical domain models. This is intentional duplication, tracked in docs/trade-offs.md, and will shrink as scoring and ranking are migrated onto the canonical models in a later phase.

**Also fixed as part of this decision:** the OOP `Recommender` wrapper no longer hard-codes `preferred_danceability` to `0.5` -- the legacy `UserProfile` dataclass gained a real `preferred_danceability` field (default `0.5`, matching the old hard-coded value exactly so existing call sites are unaffected) that the wrapper now actually reads.

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
