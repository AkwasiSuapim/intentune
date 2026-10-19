# Claude Backend Execution Guide — Intentune Prototype 1

Use this together with `intentune-backend-prototype-implementation-spec.md`.

**Authoritative repository:** `AkwasiSuapim/intentune`

Your job is to implement the approved design, not redesign the product.

## 1. Non-negotiable rules

- Inspect the actual working tree before claims.
- Documentation is not proof of implementation.
- Preserve working functionality.
- Do not rewrite canonical scoring/ranking from scratch.
- Stay a modular monolith.
- Domain has no FastAPI/SQLAlchemy/filesystem/provider dependencies.
- Application coordinates use cases through ports.
- Adapters implement storage/filesystem/analyzer concerns.
- API routes remain thin.
- No auth, Redis, Celery, microservices, vector DB, LLM provider, Spotify/YouTube, or AI DJ in Prototype 1.
- Never expose raw local paths to the frontend.
- Never store audio binaries in SQLite.
- Never invent missing features.
- Work **one phase at a time**.
- At the end of each phase: tests, docs, report, then STOP unless explicitly told to continue.
- Do not commit or push unless explicitly instructed.

## 2. Mandatory B0 audit

Before feature code, inspect:

```text
backend/src/intentune/domain/models.py
backend/src/intentune/domain/scoring.py
backend/src/intentune/domain/ranking.py
backend/src/intentune/application/recommendation_service.py
backend/src/intentune/ports/catalog.py
backend/src/intentune/adapters/csv_catalog.py
backend/src/recommender.py
backend/src/main.py
backend/requirements.txt
backend/tests/

docs/architecture/architecture.md
docs/architecture/folder-structure.md
docs/architecture/system-workflow.md
docs/architecture/current-system-audit.md
docs/design/api-design.md
docs/design/database-design.md
docs/decisions/technical-decisions.md
docs/decisions/trade-offs.md
docs/planning/development-phases.md
docs/quality/testing-strategy.md
docs/quality/security-and-privacy.md
```

If present locally, also inspect the frontend session boundary:

```text
frontend/src/features/session/sessionService.ts
frontend/src/features/session/types.ts
frontend/src/features/session/commands.ts
frontend/src/features/session/sessionReducer.ts
frontend/src/features/session/workspaceReducer.ts
frontend/src/mocks/mockSessionService.ts
```

GitHub default branch may not contain the latest local F0-F8 frontend. Report any discrepancy instead of inventing contracts.

Run:

```text
python -m pytest -q
```

The docs currently report 131 backend tests. The local working tree is authoritative.

**B0 makes no feature-code changes. STOP after audit.**

## 3. Protected existing code

Treat these as architectural assets:

```text
MusicCandidate
UserProfile
ListeningContext
FeatureWeights
ScoreComponent
ScoreBreakdown
Recommendation

score_candidate()
rank_candidates()

Catalog
CsvCatalog
recommend_music()
recommend_from_catalog()
```

Legacy compatibility is protected by regression tests.

Prefer additive extension. Refactor shared internals only when needed to avoid duplicated business logic.

## 4. Phase B1 — Persistence foundation

Implement synchronous SQLAlchemy + SQLite + Alembic.

Suggested structure may include:

```text
backend/src/intentune/persistence/
    db.py
    models.py
    repositories.py

backend/alembic/
backend/alembic.ini
```

Use UTC timestamps and SQLite foreign keys. WAL mode may be used if verified.

Do not introduce async SQLAlchemy without measured need.

Create one generated default local listener profile.

Acceptance:
- clean migration works
- repository smoke tests work
- existing suite remains green

Update docs and STOP.

## 5. Phase B2 — Managed local library

Implement application capabilities:

```text
register source
list sources
scan source
import track
list tracks
get track
mark unavailable
```

Managed media:

```text
backend/data/media/
```

Use generated UUID-based storage names and SHA-256 exact dedupe.

Import pipeline:

```text
validate
-> hash
-> dedupe
-> copy to managed media
-> persist track
-> extract basic tags
-> queue deeper analysis
```

Add `mutagen` only when implementing this phase.

Tests must prove:
- multiple sources coexist
- exact duplicate is not duplicated
- managed copy survives original deletion
- unsupported formats fail safely
- rescan is incremental

Update docs and STOP.

## 6. Phase B3 — Background analysis

Use persisted jobs + bounded in-process worker. No Celery/Redis.

Add `librosa` only if needed for approved deterministic signal analysis.

Safe initial features:
- duration
- tempo estimate
- loudness/audio-level descriptors
- chroma/key estimate
- beat/onset descriptors

High-level semantic features such as valence, mood, acousticness, genre, vocal probability, and danceability must come from a validated analyzer/model or remain `NULL`. Do not fake provider-equivalent values.

Store analyzer source/version/confidence.

Tests:
- ready tracks usable during analysis
- failed track does not kill worker
- interrupted jobs recover
- reanalysis works after analyzer version changes

Update docs and STOP.

## 7. Phase B4 — Session domain

Introduce:

```text
ListeningSession
SessionTurn
RecommendationOccurrence
FeedbackEvent
```

Keep algorithm `Recommendation` separate from surfaced `RecommendationOccurrence`.

Session owns current state; history is separate.

Do not persist raw natural-language prompt by default.

App restart rule:
- retain history
- do not auto-resume active queue
- new listening action creates fresh session

Write pure application tests before HTTP.

Update docs and STOP.

## 8. Phase B5 — Recommendation Policy v1

Implement in this order:

```text
eligibility
-> intent fit
-> session fit
-> long-term fit
-> combine
-> diversity/cooldown
-> exploration
-> top 3
```

### Component weights

```text
intent      .55
session     .30
long-term   .15
```

Renormalize if a component is unavailable.

### Missing values

Never invent defaults. Omit unavailable feature contributions and renormalize active feature weights.

### Preserve legacy scorer

Do not duplicate the current scoring math. Refactor shared scoring primitives if necessary, while proving old complete-input outputs remain identical.

### Feedback/session score

Use one reusable candidate similarity function.

```text
net = sum(event_weight * similarity * recency)
      / sum(abs(event_weight) * recency)

session_fit = (clamp(net,-1,1)+1)/2
```

No evidence -> `.5`.

Initial recency: `.85 ** age`.

### Diversity

At minimum test:
- recent-track cooldown
- repeated artist
- excessive near-duplicate similarity

### Exploration

Default target behavior ~90/10 exploit/explore.

### Top 3

Maintain three candidates.

If:

```text
top1_score - top2_score <= .08
```

and #2 provides useful novelty, #2 may play first. Otherwise #1.

If #2 safely plays first and nothing meaningful changes:

```text
#2 -> #1 -> #3
```

Meaningful feedback/refinement re-ranks remaining candidates.

All heuristic constants live in one versioned policy module/config.

Acceptance includes deterministic tests for no feedback, positive feedback, early skip, Not-for-me, conflicting current/history intent, missing features, finite library, exploration success/failure, and #2 safety threshold.

Update docs and STOP.

## 9. Phase B6 — Feedback/playback

Persist meaningful events only, not per-second ticks.

Required events:

```text
LIKE
SAVE
REPLAY
SKIP
COMPLETE
NOT_FOR_ME
```

Persist playback seconds, duration, and fraction when relevant.

Policy v1:

```text
0-8 sec           0.00
<15%             -0.50
15-39%           -0.20
40-74%           +0.10
75-89%           +0.50
90-100%          +0.80
LIKE              +1.00
SAVE              +1.00
REPLAY            +1.00
NOT_FOR_ME        -1.00
```

Explicit actions take precedence over passive duration.

After meaningful feedback:

```text
persist raw event
-> interpret
-> update session evidence
-> re-rank queue
```

Not-for-me excludes the exact track for that session but does not permanently mutate long-term taste.

Boundary tests are mandatory.

Update docs and STOP.

## 10. Phase B7 — Playlists

Implement playlist CRUD + add/remove/reorder.

Default: one occurrence of a track per playlist unless the product later approves duplicates.

Playlist add is strong positive feedback, but never auto-save.

Update docs and STOP.

## 11. Phase B8 — FastAPI

Create thin HTTP boundary with Pydantic schemas separate from ORM/domain models.

Implement routes from the implementation spec.

Use consistent error envelope and request IDs.

### Audio

Serve by track ID, never path.

Verify installed Starlette/FastAPI Range request behavior for browser seeking. If not sufficient, implement a tested safe range response.

Update docs and STOP.

## 12. Phase B9 — Frontend integration

Inspect the actual local F8 service boundary first.

Do not mirror React internal state into Python.

Backend owns:
- session identity
- structured context
- recommendation occurrences/history
- reactions
- playlist state

Frontend owns:
- modal/drawer state
- composer draft
- animation
- scrolling/focus
- visual expansion state

Implement the HTTP adapter needed to satisfy the existing frontend use-case interface. Do not rewrite frontend architecture.

Update docs and STOP.

## 13. Phase B10 — Long-term adaptation

Do not begin until session behavior is stable.

Gate:

```text
>= 4 consistent strong signals
across >= 2 sessions
```

Then allow only a small bounded change.

Persist evidence IDs, algorithm version, before/after value, and reason. Make adjustments reversible/recomputable.

Update docs and STOP.

## 14. Phase B11 — Evaluation/hardening

Measure before adding new infrastructure.

Evaluate:
- full-catalog scoring latency
- import throughput
- analysis throughput
- SQLite latency
- API latency
- memory
- queue response time
- restart behavior

Do not add vector search for hundreds or a few thousand tracks without evidence.

## 15. Security requirements

- path traversal protection
- allowlisted audio formats
- generated managed filenames
- media/DB excluded from Git
- no raw path leakage in API
- no raw prompt persistence by default
- no provider network calls in normal tests
- no stack traces in client errors

## 16. Documentation discipline

Whenever reality changes, update the relevant existing docs:

```text
docs/architecture/current-system-audit.md
docs/architecture/architecture.md
docs/architecture/folder-structure.md
docs/architecture/system-workflow.md
docs/design/api-design.md
docs/design/database-design.md
docs/decisions/technical-decisions.md
docs/decisions/trade-offs.md
docs/planning/development-phases.md
docs/quality/testing-strategy.md
docs/quality/security-and-privacy.md
docs/changelog.md
```

Never label planned behavior as implemented.

## 17. Required phase report

After each phase report:

```text
1. Phase completed
2. What existed before
3. What changed
4. Files created
5. Files modified
6. Architecture/decision notes
7. Tests added
8. Full test results
9. Manual verification
10. Known limitations
11. Documentation updated
12. Recommended next phase
```

Then STOP.

## 18. Forbidden shortcuts

Do not:
- delete legacy compatibility to simplify work
- weaken tests
- increase timeouts to hide failures
- fabricate audio features
- trust browser-reconstructed session history
- store UI state in backend domain/session tables
- use raw paths as public identifiers
- create one giant route or god service
- make one skip permanently rewrite taste
- train ML before an evaluation dataset exists
- add embeddings because they sound modern
- let an LLM directly choose tracks
- add future provider/AI-DJ code during Prototype 1

## 19. Target experience

```text
open Intentune
-> local library ready; new analysis continues in background
-> start fresh session
-> choose mood/genre/energy/goal
-> press Play
-> maintain 3 candidates
-> safe #2 exploration may occur
-> listen/skip/like/replay/save
-> queue adapts immediately
-> music keeps flowing
-> repetition stays controlled
-> playlists persist
-> history persists
-> reopening starts a fresh active session
-> repeated cross-session evidence may later make small explainable profile changes
```

Prototype 1 must work with AI disabled, external providers disabled, and no internet.
