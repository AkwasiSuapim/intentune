# Trade-offs

## Status

**Living Document**

A trade-off records what the project gains and what it accepts in return.

## Modular Monolith Instead of Microservices

### Gain

- Simpler development
- Easier local debugging
- One deployment
- Fewer distributed-system failures

### Cost

- Strong module boundaries depend on discipline
- Independent scaling is limited

### Revisit When

Clear modules need separate ownership, scaling, or deployment.

## CSV Catalog Before a Database

### Gain

- Simple baseline
- Easy inspection
- No migration or database setup

### Cost

- Limited querying and concurrent updates
- Not suitable for persistent users and feedback

### Revisit When

The product stores profiles, feedback, or recommendation history.

## Deterministic Scoring Before Machine Learning

### Gain

- Explainability
- Easier testing
- Lower cost
- Easier debugging

### Cost

- Limited ability to learn complex preference patterns
- Manual feature and weight design

### Revisit When

Enough quality feedback data exists to evaluate a learned model responsibly.

## Separate React Frontend Instead of Streamlit

### Gain

- Full control over the interface and interaction
- Backend stays a plain HTTP API that any client can use
- Frontend and backend can be developed and deployed independently

### Cost

- Slower first browser MVP than a Python-only Streamlit page
- Two languages and two toolchains (Python and TypeScript)
- The API must exist before the interface can be built

### Revisit When

Maintaining a separate frontend is slowing delivery of the core recommendation features.

## External AI Provider

### Gain

- Strong natural-language interpretation without training a model

### Cost

- API cost
- Latency
- Provider availability
- Privacy considerations
- Output variability

### Mitigation

Structured output, validation, timeouts, fallback behavior, and provider abstraction.

## YouTube as the First External Catalog

### Gain

- Broad visible catalog
- Thumbnails, links, channels, and embeddable videos

### Cost

- API quota
- Search metadata may not include precise audio features
- Availability and regional restrictions

### Mitigation

Use official APIs, normalize metadata, avoid unsupported claims, and keep the internal catalog available.

## Canonical Domain Internals with Legacy Boundary Compatibility

**Status:** Implemented and accepted (TD-009)

**Approval note:** Preserving the existing dictionary, dataclass, scoring,
ranking, and CLI behavior was explicitly approved. Moving scoring/ranking
into canonical modules and adding application/port/adapter modules went
beyond the earlier model-only/minimal-structure boundary; the owner has since
approved continuing with this canonical modular architecture.

### Gain

- A single typed, source-independent vocabulary (`MusicCandidate`, `UserProfile`, `ListeningContext`, `FeatureWeights`, `ScoreComponent`, `ScoreBreakdown`, `Recommendation`) exists for future FastAPI, AI, YouTube, and database work to target.
- Existing scoring, ranking, CLI output, and all original tests are provably unchanged.
- **Update (this phase):** scoring and ranking have since been rewired onto the canonical models (`src/intentune/domain/scoring.py`, `src/intentune/domain/ranking.py`) as the single source of truth, resolving the "not yet unified" cost below for scoring/ranking specifically.
- **Update (this phase):** a formal `Catalog` port (`src/intentune/ports/catalog.py`) and application-level catalog dependency injection (`recommend_from_catalog()`) now exist, so the application layer depends on an abstraction rather than the concrete CSV adapter.

### Cost

- Two dict/dataclass *shapes* still coexist at the legacy boundary (the historical dictionary API and the historical dataclass API in `src/recommender.py`) alongside the canonical domain models -- but they are now thin conversions at the boundary, not separate implementations of the scoring/ranking math.
- The legacy `UserProfile` dataclass still carries a deprecated, inert `likes_acoustic` field for backward compatibility.
- `load_songs()`'s legacy dict shape assumes every candidate field is present (`int(candidate.tempo_bpm)` would fail on a `None` value); this remains true for the current CSV catalog but would need to change before a source with genuinely missing fields could flow through the legacy dict path.
- The CLI path performs an extra `MusicCandidate -> legacy dict -> MusicCandidate`
  conversion so the historical `load_songs()` and `recommend_songs()` shapes
  remain unchanged.

### Revisit When

The "Expanded and Configurable Scoring Engine" milestone (see docs/planning/development-phases.md, Phase 3) extends scoring to tempo/valence/acousticness and missing-feature normalization -- at that point the legacy dict API's fixed four-field shape will need a documented limitation notice or a wider replacement, since it cannot express per-feature weights or partial data.

## Trade-off Entry Template

```text
## Trade-off Title

Date:
Related Decision:

Gain:

Cost:

Mitigation:

Revisit When:
```
