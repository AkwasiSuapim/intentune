# Development Phases

## Status

**Planned roadmap.** Reconciled with Prototype 1 in Phase B0 (2026-10-18).

The backend roadmap is now the Prototype 1 phase plan **B0–B11** from the [Prototype 1 specification](../planning/intentune-backend-prototype-implementation-spec.md) §29, executed one phase at a time under the [backend execution guide](../agents/CLAUDE_BACKEND_EXECUTION_GUIDE.md). The frontend has its own phase plan, **F0–F9**, in [frontend implementation phases](../frontend/IMPLEMENTATION_PHASES.md).

The original roadmap (Phases 0–10) is kept below as history. Phases 0–2 are complete. The rest are superseded by B-phases or deferred to Future, as marked.

## Prototype 1 Backend Phases

Each phase ends with the full test suite, documentation updates, a report, and a stop for review. No phase starts without explicit authorization.

| Phase | Scope | Status |
|---|---|---|
| **B0** Reconcile/freeze baseline | Inspect the repository and frontend, run tests, record the baseline, reconcile documentation. No feature code. | **Complete, awaiting review** (2026-10-18). Baseline: 131 backend tests pass. |
| **B1** SQLite persistence foundation | SQLAlchemy, SQLite, Alembic, local listener, repositories, migration tests | Prerequisites done (2026-10-18); implementation not started |
| **B2** Local library + managed media | Sources, safe copy, SHA-256 dedupe, tags, progressive status, scanning | Not started |
| **B3** Background analysis | Persisted jobs, in-process worker, audio analysis, recovery, provenance/versioning | Not started |
| **B4** Session domain | `ListeningSession`, `SessionTurn`, `RecommendationOccurrence`, `FeedbackEvent`, repositories | Not started |
| **B5** Recommendation Policy v1 | Intent/session/long-term scores, missing features, similarity, diversity, exploration, rolling top 3, legacy preservation | Not started |
| **B6** Feedback/playback events | Like, Save, Replay, Skip, Complete, Not-for-me; raw event persistence; immediate re-ranking | Not started |
| **B7** Playlists | CRUD, add/remove/reorder, persistence | Not started |
| **B8** FastAPI | Library/session/feedback/playlist/audio routes, errors, request IDs, API tests | Not started |
| **B9** Frontend integration | Inspect the actual F8 service boundary; add an HTTP adapter without rewriting frontend state architecture | Not started. Corresponds to frontend phase F9. |
| **B10** Conservative long-term adaptation | 4 strong signals / 2 sessions gate, bounded changes, audit trail, reversibility | Not started |
| **B11** Evaluation/hardening | Performance with hundreds to thousands of tracks, restart behavior, migrations, algorithm evaluation | Not started |

Acceptance criteria for each phase are in the execution guide §4–§14. Prototype 1 is done when every item in spec §30 holds.

### B0 record (2026-10-18)

- Backend: 131 tests pass (`python -m pytest -q` from `backend/` with the venv active). CLI output matches the documented baseline.
- Frontend: F0–F8 implemented; 214 Vitest tests pass; build and lint clean.
- No feature code was changed. Documentation was reconciled to distinguish Current, Planned, Superseded, and Future behavior.
- Findings carried into B1: `.gitignore` did not cover the database or managed media; `.env.example`'s `DATABASE_URL` pointed to `backend/intentune.db` rather than `backend/data/intentune.db`; `sqlalchemy` was listed in `requirements.txt` but not installed, `alembic` was not listed, and all entries were unpinned.

Details: [current system audit](../architecture/current-system-audit.md).

### B1 prerequisites (2026-10-18)

Done before any B1 feature code:

- The three Prototype 1 documents were committed (`d493392`).
- `.gitignore` now ignores `backend/data/intentune.db*` and `backend/data/media/`.
- `backend/.env.example` now sets `DATABASE_URL=sqlite:///./data/intentune.db`.
- SQLAlchemy 2.1.5, Alembic 1.20.0, and httpx 0.28.1 were installed, and every direct dependency in `backend/requirements.txt` is pinned to its verified version. `pip check` is clean, and the backend suite still passes (131).

No persistence code, migration, or database file exists yet.

## Frontend Phases

| Phase | Status |
|---|---|
| F0–F8 (readiness through API-ready service boundary) | Complete (2026-10-13 to 2026-10-15) |
| F9 FastAPI integration | Waiting for an approved, implemented backend contract; carried out with B9 |

---

## Original Roadmap (historical)

The phases below were planned before Prototype 1. Their status notes record what happened to each.

## Phase 0: Preserve and Audit the Baseline

**Status:** Complete.

### Goal

Understand the uploaded CodePath implementation and preserve its behavior.

### Deliverables

- Repository audit
- Current workflow documentation
- Passing baseline tests
- Baseline CLI output
- Clean Git branch for new work

### Completion Criteria

- Current tests pass
- Current behavior is recorded
- No important working code is deleted

## Phase 1: Documentation and Product Definition

**Status:** Complete. Reconciled with Prototype 1 in B0.

### Goal

Create a shared understanding of the product, architecture, boundaries, and roadmap.

### Deliverables

- Documentation directory
- Product description
- Requirements
- Architecture
- Workflow
- API draft
- Database draft
- Testing, privacy, deployment, and trade-off documents

### Completion Criteria

- Documentation distinguishes current, planned, draft, and future work
- Another engineer can explain the product after reading the docs

## Phase 2: Core Domain Refactor

**Status:** Complete. The current four-feature baseline milestone, the formal
catalog port, and catalog-backed application orchestration are all
implemented and verified.

### Goal

Separate pure recommendation logic from CLI and storage concerns.

### Deliverables

- Unified typed models
- Pure scoring module
- Pure ranking module
- Catalog interface
- Existing CSV adapter
- Regression tests proving current behavior remains available

### Completion Criteria

- Domain layer does not depend on FastAPI, Streamlit, AI, YouTube, or databases
- Current tests and new domain tests pass

### Progress So Far (Current)

- Unified typed models introduced in `src/intentune/domain/models.py` (`MusicCandidate`, `UserProfile`, `ListeningContext`, `FeatureWeights`, `ScoreComponent`, `ScoreBreakdown`, `Recommendation`).
- Hard-coded `preferred_danceability` bug fixed in the legacy `Recommender` wrapper.
- Pure scoring module (`src/intentune/domain/scoring.py`) and pure ranking module (`src/intentune/domain/ranking.py`) added, implementing the current four-feature rule and tie-breaking as the single source of truth.
- CSV adapter added (`src/intentune/adapters/csv_catalog.py`), converting raw CSV rows into `MusicCandidate`; `load_songs()` now delegates to it instead of parsing CSV itself.
- A first application-service orchestrator added (`src/intentune/application/recommendation_service.py`, `recommend_music()`).
- `src/recommender.py`'s legacy `score_song()`/`recommend_songs()` now convert to canonical models and delegate to the canonical scorer/ranker, rather than containing a second copy of the scoring math; the now-dead `_calculate_similarity_points()`/`_validate_numeric_preference()` helpers were removed.
- Regression tests confirmed: 119 tests passed before this phase's catalog-port work; 131 tests pass now. CLI output matches the documented baseline; legacy and canonical outputs are behaviorally equivalent across the full 20-song catalog, not only the top five.
- Completion criteria for the current four-feature scoring path are met: the domain layer is independent of FastAPI/Streamlit/AI/YouTube/databases, and current and new tests pass. `score_candidate()` already matches a candidate's genre/mood against *any* of a profile's `preferred_genres`/`preferred_moods` (still an exact, case-insensitive match, not partial similarity) -- the legacy dict converter simply never supplies more than one of each, since the legacy dict profile only ever carries a single favorite genre and mood.
- A formal catalog port is implemented: `src/intentune/ports/catalog.py` defines `Catalog`, a `Protocol` with a single `list_candidates() -> Sequence[MusicCandidate]` method. `src/intentune/adapters/csv_catalog.py` adds `CsvCatalog`, a thin class binding a CSV path to `list_candidates()` around the existing `load_music_candidates()` loader. `src/intentune/application/recommendation_service.py` adds `recommend_from_catalog(catalog, profile, limit)`, which depends on the `Catalog` port rather than the concrete CSV adapter and is tested with an in-memory fake catalog. `recommend_music(candidates, profile, limit)` is unchanged.
- Deferred to Phase 3: configurable weights, partial similarity, missing-feature handling, and diversity re-ranking.

## Phase 3: Recommendation Logic Improvements

**Status:** Superseded by B5 (Recommendation Policy v1). Missing-feature handling, diversity re-ranking, and context-aware targets move into B5 with the rules fixed by the specification. The other increments (partial genre/mood similarity, match levels, configurable per-feature weights, context presets) are not part of Prototype 1 unless a B-phase needs them.

### Goal

Improve deterministic recommendation quality before introducing AI.

### Candidate Increments

- Multiple genres and moods
- Configurable weights
- Partial similarity
- Missing-value policy
- Diversity re-ranking
- Match levels
- Better explanations

### Completion Criteria

Each increment has documented behavior, tests, and an evaluation example.

### Future Milestone: Expanded and Configurable Scoring Engine

**Status:** Superseded by B5. The draft weighting below was never implemented or tuned. B5's missing-feature rule (spec §14) keeps the same principle: no invented target, omit a missing feature, renormalize the active weights.

The current scoring algorithm (genre 3 pts, mood 3 pts, energy up to 2 pts, danceability up to 2 pts, 10-point maximum, sharp similarity cutoff at a 0.5 difference) is preserved unchanged through this phase. A later milestone must extend it to also weigh tempo, valence, and acousticness. A draft default weighting has been proposed for evaluation (not yet implemented or tuned):

```text
Genre             3.0
Mood              3.0
Energy            1.5
Danceability      1.0
Tempo             0.5
Valence           0.5
Acousticness      0.5
Maximum          10.0
```

These numbers require evaluation using real recommendation profiles, comparison experiments, and user feedback before adoption. This milestone should also implement: configurable feature weights (using `FeatureWeights`), partial genre/mood matching, energy/danceability/tempo/valence/acousticness similarity, missing-feature handling (see below), score normalization, confidence calculation, ranking evaluation, and comparison across multiple user profiles.

**Missing-feature handling principle (for this future milestone):**

```text
User explicitly specifies a preference -> include the feature when candidate data is available
User does not specify a preference -> do not invent a target value
Candidate does not contain the feature -> exclude the feature from the active score
Fewer useful features are available -> normalize by the total active weight and lower confidence
```

For example, if only genre (3.0), mood (3.0), and energy (1.5) are active, the total active weight is 7.5, and a normalized score may be `earned active points / total active weight`. `FeatureWeights.total_active_weight` already supports this calculation; the normalization itself is not implemented yet.

### Future Milestone: Context-Aware and User-Configurable Weighting

**Status:** Partly absorbed by B5, the rest Future. B5 builds effective *targets* from system policy, the long-term profile, and the current `ListeningContext`, with current explicit intent winning (spec §14). Context presets and user-editable per-feature weights are not in Prototype 1. The five evaluation scenarios in spec §28 (study/calm, workout/high energy, party/dance, relax, discovery) are test scenarios, not presets.

Feature importance must eventually vary by both long-term user taste (`UserProfile`) and moment-specific need (`ListeningContext`), producing session-specific `FeatureWeights`:

```text
default system weights
+ long-term user preferences
+ current listening context
+ explicit user overrides
= session-specific feature weights
```

Examples of how weighting should shift by context: workouts favor tempo and energy; study favors mood, moderate energy, acousticness, and low danceability; parties favor danceability, tempo, and energy; sleep favors low energy, low tempo, and acousticness; discovery may intentionally reduce genre weight to increase variety. Future context presets (study, workout, relax, party, sleep, commute, focus, mood improvement, discovery) must provide editable defaults, not rigid rules, and users must be able to override any feature weight. None of this is implemented yet -- `FeatureWeights`, `UserProfile`, and `ListeningContext` are modeled so it can be added later without a domain redesign.

## Phase 4: Backend API

**Status:** Superseded by B8. The API is session-based, not a profile-only recommendation route (see [API Design](../design/api-design.md)).

### Goal

Expose the recommendation engine through a reliable HTTP interface.

### Deliverables

- FastAPI application
- Health route
- Recommendation route
- Request and response schemas
- Error handling
- API tests

### Completion Criteria

A client can submit preferences and receive ranked recommendations as JSON.

## Phase 5: Browser Interface

**Status:** Superseded by frontend phases F0–F9. A conversational listening-session UI was built instead of a preference form (F0–F8 complete; F9 integration pending, with B9).

### Goal

Allow friends and family to use the product.

### Deliverables

- Preference form
- Recommendation result cards
- Explanations
- Error and loading states
- Basic feedback controls

### Completion Criteria

A nontechnical test user can complete the main flow without developer assistance.

## Phase 6: Feedback Persistence

**Status:** Superseded by B1 (persistence), B4 (session history), and B6 (feedback events). SQLite is chosen (D22).

### Goal

Record user reactions without yet making uncontrolled profile changes.

### Deliverables

- Feedback endpoint
- SQLite or PostgreSQL storage
- Database migrations
- Feedback tests

### Completion Criteria

Feedback events are stored reliably and can be reviewed.

## Phase 7: Adaptive Profile Logic

**Status:** Superseded by B10, which fixes the gate at 4 consistent strong signals across 2 sessions (D06). Session-level adaptation happens earlier, in B5/B6.

### Goal

Use feedback to update preferences gradually and transparently.

### Deliverables

- Profile update policy
- Bounds and safeguards
- Algorithm versioning
- Explanation of profile changes

### Completion Criteria

Profile changes are deterministic, tested, reversible, and explainable.

## Phase 8: AI Chatbot

**Status:** Future. Deferred beyond Prototype 1 (D30, D39). Prototype 1 has limited deterministic commands only.

### Goal

Convert natural language into the same validated recommendation request used by the manual interface.

### Deliverables

- Intent parser port
- AI adapter
- Structured output validation
- Clarification and fallback behavior
- Mocked AI tests

### Completion Criteria

AI can be disabled without breaking the manual recommendation flow.

## Phase 9: YouTube Integration

**Status:** Future. Deferred beyond Prototype 1 (D39).

### Goal

Use the official YouTube API as an external candidate provider.

### Deliverables

- Query builder
- YouTube client
- Candidate normalization
- Deduplication
- Provider timeouts and errors
- Mocked integration tests

### Completion Criteria

The system returns real YouTube results without scraping or downloading content.

## Phase 10: Deployment and Product Hardening

**Status:** Future for hosted deployment (Prototype 1 is local and personal, D37). Local performance and restart hardening are part of B11.

### Goal

Operate Intentune safely for invited users.

### Deliverables

- Hosted deployment
- Secure secrets
- CI checks
- Logging and monitoring
- Rate limiting
- User feedback review process
- Rollback procedure

### Completion Criteria

Selected users can access the application remotely and failures can be diagnosed.
