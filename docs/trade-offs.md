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

## Streamlit Before a Separate Frontend

### Gain

- Faster browser MVP
- Python-only development
- Easy result visualization

### Cost

- Less UI flexibility
- Tighter coupling to Python application execution

### Revisit When

The application needs polished custom interaction, a mobile client, or a separately deployed frontend.

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

## Canonical Domain Models Before Rewiring Scoring and Adapters

### Gain

- A single typed, source-independent vocabulary (`MusicCandidate`, `UserProfile`, `ListeningContext`, `FeatureWeights`, `ScoreComponent`, `ScoreBreakdown`, `Recommendation`) exists for future FastAPI, AI, YouTube, and database work to target.
- Existing scoring, ranking, CLI output, and all 21 original tests are provably unchanged.

### Cost

- Three shapes now coexist during the transition: the historical dictionary API, the historical dataclass API (`Song`, `UserProfile` in `src/recommender.py`), and the new canonical domain models in `src/intentune/domain/models.py`. They are not yet unified.
- The legacy `UserProfile` dataclass still carries a deprecated, inert `likes_acoustic` field for backward compatibility.

### Revisit When

Scoring and ranking are rewritten to consume `MusicCandidate`/`UserProfile`/`ScoreBreakdown` directly (see docs/development-phases.md, Phase 3's Expanded and Configurable Scoring Engine milestone), at which point the historical dict and dataclass shapes can be retired or reduced to thin compatibility wrappers.

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
