# Trade-offs

## Status

**Living Document**

A trade-off records what the project gains and what it accepts in return.

Every Prototype 1 decision has its main trade-off listed in the [Prototype 1 Decision Register](intentune-prototype-decision-register.md). The [Prototype 1 Trade-offs](#prototype-1-trade-offs) section below expands the ones with the largest consequences. Older entries were reconciled in Phase B0 (2026-10-18).

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

**Status:** Current for the recommendation catalog; its revisit condition is met. Prototype 1 stores a library, sessions, feedback, and playlists, so SQLite arrived in B1 (2026-10-19, D22), so far holding only the local listener profile. Library tracks move into it in B2. The CSV adapter stays as a compatibility source.

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

**Prototype 1 note:** ranking stays deterministic and staged (D07). No model is trained before an evaluation dataset exists. Validated pretrained audio analyzers may supply features where justified (D19), but they do not rank.

## Separate React Frontend Instead of Streamlit

### Gain

- Full control over the interface and interaction
- Backend stays a plain HTTP API that any client can use
- Frontend and backend can be developed and deployed independently

### Cost

- Slower first browser MVP than a Python-only Streamlit page
- Two languages and two toolchains (Python and TypeScript)
- The API must exist before the interface can be built

**Update (2026-10-18, B0):** the last cost did not hold. The frontend was built first against a mock service (F0–F8). The real cost is reconciliation: the mock service boundary and the Prototype 1 API were designed separately and must be aligned in B8/B9 (see [API Design](../design/api-design.md#frontend-contract-alignment)).

### Revisit When

Maintaining a separate frontend is slowing delivery of the core recommendation features.

## External AI Provider

**Status:** Future. Deferred beyond Prototype 1 (D39).

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

**Status:** Superseded. Prototype 1 uses the listener's own music in a managed local library (D02, D03), and external catalogs are deferred (D39). Kept for history.

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

**Update (2026-10-18, B0):** that milestone is superseded by Prototype 1 Phase B5. The revisit point is now B5.

## Prototype 1 Trade-offs

**Accepted (2026-10-18).** The trade-offs below carry the largest consequences. Every decision's main trade-off is in the [decision register](intentune-prototype-decision-register.md).

### Managed copies of imported music (D02, D23)

- **Gain:** the library keeps working when the original files move or are deleted; storage names are generated, so filenames never become identifiers.
- **Cost:** uses extra disk space, roughly one more copy of every imported track. Since B2, content that changes at the source adds a new copy and keeps the old one, until a removal feature exists (TD-013).
- **Status:** Current since B2 (2026-10-19).
- **Revisit when:** disk use becomes a problem for real libraries (B11).

### SQLite + SQLAlchemy + Alembic (D22)

- **Gain:** no server to run; fits one listener on one device; versioned migrations from the start.
- **Cost:** limited write concurrency, which matters because a background worker writes while the app reads; a later move to PostgreSQL needs a migration path. B1's correct transaction handling (SQLAlchemy emits `BEGIN`, so DDL is transactional) makes "database is locked" errors somewhat more likely than the driver's legacy mode would (TD-012).
- **Mitigation:** short transactions, one worker initially, the driver's 5-second busy timeout, and WAL mode, enabled for file databases in B1 and verified by tests. Real contention is measured when B3 adds the worker.

### In-process bounded worker instead of a task queue (D28)

- **Gain:** no Redis or Celery; simple to run and debug.
- **Cost:** shutting the process down interrupts active work.
- **Mitigation:** job state persisted in SQLite; idempotent jobs that resume after restart.

### SHA-256 exact deduplication (D24)

- **Gain:** simple, exact, and testable.
- **Cost:** the same song in two encodings (for example, an MP3 and a FLAC) counts as two tracks. So does the same audio with different embedded tags, since tags are part of the file's bytes.
- **Status:** Current since B2 (2026-10-19).
- **Revisit when:** duplicate transcodes become common; perceptual fingerprinting is deferred.

### Missing features stay missing (D21)

- **Gain:** scores never rest on invented values.
- **Cost:** fewer active features for partly analyzed tracks, so lower coverage and less discriminating scores until analysis finishes.

### Staged ranking with fixed heuristic weights (D07–D09)

- **Gain:** each stage can be explained, tested, and debugged separately.
- **Cost:** the weights (0.55/0.30/0.15), feedback values, and thresholds are versioned heuristics, not proven values.
- **Mitigation:** one versioned policy module; deterministic evaluation scenarios; no claim of improvement without comparison evidence.

### Conservative long-term learning (D06)

- **Gain:** one session or one skip never rewrites long-term taste.
- **Cost:** the profile adapts slowly. The 4-signal, 2-session threshold itself must later be evaluated.

### No raw conversational text by default (D33)

- **Gain:** data minimization.
- **Cost:** past sessions cannot show exactly what the listener typed, and future intent-parser work has no stored examples to learn from.

### Fresh session after restart (D35)

- **Gain:** no stale queue or playback state is restored.
- **Cost:** the listener cannot pick up a queue exactly where it stopped.

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
