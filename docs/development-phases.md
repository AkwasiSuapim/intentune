# Development Phases

## Status

**Planned Roadmap**

## Phase 0: Preserve and Audit the Baseline

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

**Status:** Future -- not implemented in Phase 2.

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

**Status:** Future -- not implemented in Phase 2.

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
