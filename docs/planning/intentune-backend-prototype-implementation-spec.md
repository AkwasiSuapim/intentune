# Intentune Backend Prototype Implementation Specification

**Status:** Approved implementation direction  
**Scope:** Prototype 1  
**Architecture:** Modular monolith  
**Repository:** `AkwasiSuapim/intentune`  
**Product principle:** **Conversation steers. Music leads.**

## 1. Purpose

Intentune is evolving from a deterministic profile-based recommender into a **local-first, session-aware, continuously adapting music recommendation application**.

Prototype 1 must preserve the existing recommendation core unless a change is necessary, import and manage music from the user's own device, analyze and persist useful song metadata/features locally, run continuous listening sessions, adapt immediately from in-session feedback, keep a small rolling candidate queue, support playlists, and expose a clean backend contract to the React frontend.

It must remain usable without AI, external music providers, accounts, or cloud infrastructure.

## 2. Existing code is not disposable

The current repository already contains:

```text
backend/src/intentune/domain/
    models.py
    scoring.py
    ranking.py

backend/src/intentune/application/
    recommendation_service.py

backend/src/intentune/ports/
    catalog.py

backend/src/intentune/adapters/
    csv_catalog.py

backend/src/recommender.py
backend/src/main.py
backend/tests/
```

Existing architecture already provides canonical source-independent models, deterministic scoring/ranking, a formal `Catalog` port, CSV adapter, application orchestration, FastAPI direction, React/Vite/TypeScript direction, and modular-monolith boundaries.

The documentation currently reports **131 passing backend tests**. Verify the actual local baseline before implementation.

### Preservation rule

Do not rewrite working modules merely because another design looks cleaner. Rewrite only when an approved requirement is blocked, duplicate business logic would otherwise be created, a correctness/security problem exists, or a migration can preserve behavior with tests.

## 3. Prototype 1 scope

### Included

- local single-listener identity; no production authentication
- managed local music library
- multiple import/source folders
- SQLite persistence
- SQLAlchemy repositories
- versioned database migrations
- background scanning/analysis
- progressive track readiness
- structured `ListeningContext`
- listening sessions
- recommendation occurrences
- feedback/playback events
- continuous recommendation flow
- rolling three-candidate queue
- controlled exploration
- repetition cooldown
- playlists
- FastAPI HTTP API
- local audio playback endpoint
- long-term evidence collection
- conservative long-term adaptation

### Deferred

- production auth/OAuth/JWT
- multi-user cloud system
- Spotify/YouTube catalog
- unrestricted LLM intent parser
- vector database
- microservices
- Redis/Celery/Kafka
- AI DJ
- real-time filesystem watchers
- cross-user collaborative filtering

## 4. Target architecture

```text
React / TypeScript
        |
        | HTTP / JSON
        v
FastAPI
        |
        v
Application use cases
        |
        +----------------------+
        |                      |
        v                      v
Listening-session domain   Recommendation domain
        |                      |
        |                      +--> scoring
        |                      +--> ranking
        |                      +--> diversity/exploration
        |
        v
Ports
  - Catalog
  - SessionRepository
  - TrackRepository
  - PlaylistRepository
  - FeedbackRepository
        |
        v
Adapters
  - SQLite / SQLAlchemy
  - managed local media
  - CSV compatibility
  - metadata/audio analyzers
```

The domain must not import FastAPI, SQLAlchemy, SQLite, React, filesystem-specific code, AI SDKs, or provider SDKs.

## 5. Managed local music library

Prototype 1 uses an **Intentune-managed copy** of imported audio.

```text
source file/folder
    -> scan
    -> validate
    -> identify/deduplicate
    -> copy into managed media
    -> extract basic metadata
    -> playable
    -> background feature analysis
```

Recommended local layout:

```text
backend/data/
    intentune.db
    media/
        <track_uuid>.<extension>
```

Both database and media must be gitignored.

The user may register multiple source folders. All imported tracks form one logical library. Adding a new source must not replace old sources.

### Incremental scan

Persist source path, file size, modification time, SHA-256, import status, and analysis version.

Rules:

```text
unchanged -> no work
new -> import + analyze
changed -> re-hash; re-import/re-analyze if content changed
missing source -> source marked missing; managed copy remains usable
exact duplicate -> do not create a second logical track
```

Use **SHA-256** for exact duplicate detection in Prototype 1. Perceptual fingerprinting is deferred.

Run a lightweight incremental scan at startup and provide a manual **Rescan Library** action. No real-time watcher yet.

## 6. Metadata and audio analysis

Use a hybrid pipeline.

```text
embedded tags
    -> title, artist, album, artwork, year, declared genre

deterministic signal analysis
    -> duration, BPM estimate, loudness, key/mode estimate,
       raw audio descriptors

validated pretrained ML where justified
    -> mood, missing genre, vocal/instrumental,
       other semantic attributes
```

Do not use ML when reliable file metadata already exists. Do not pretend inferred values are facts.

Persist source/analyzer version/confidence when relevant.

### Desired feature set

Identity/display:
- title
- artist/creator
- album
- duration
- year
- artwork
- format
- managed media path

Recommendation/audio:
- genre / primary genre
- mood / primary mood
- BPM
- energy
- danceability
- valence
- acousticness
- loudness
- key
- mode
- vocal/instrumental estimate

System:
- SHA-256
- source
- analysis status/version
- provenance/confidence
- timestamps

### Scientific constraint

Do not fabricate Spotify-like `energy`, `danceability`, `valence`, or `acousticness`. If a feature is unavailable, persist `NULL`. Any Intentune-specific heuristic must be clearly named, versioned, tested, and evaluated.

Suggested dependencies, only when needed:
- `mutagen` for tags/artwork/basic metadata
- `librosa` for signal analysis
- `alembic` for migrations
- pretrained audio models only in a later analysis subphase after environment compatibility is verified

## 7. Progressive readiness

Recommended states:

```text
DISCOVERED
  -> IMPORTED       (basic metadata; playable)
  -> ANALYZING      (features arriving)
  -> READY
```

Failure states:
`UNSUPPORTED`, `FAILED`, `MISSING_MANAGED_FILE`.

Rules:
- playable as soon as basic metadata is ready
- richer recommendation ability arrives progressively
- ranking uses only available features
- missing features never receive invented defaults
- one analyzer failure never crashes the library

## 8. Background work

Use a **bounded in-process worker**, not Redis/Celery.

Persist job state in SQLite so interrupted jobs can resume.

Suggested jobs:
- `IMPORT_TRACK`
- `EXTRACT_TAGS`
- `ANALYZE_AUDIO`
- `REANALYZE_TRACK`
- `RESCAN_SOURCE`

Start conservatively with one worker. Keep DB transactions short and jobs idempotent.

## 9. Persistence

Use **SQLite + SQLAlchemy + Alembic**.

Recommended concepts:

```text
listener_profiles
library_sources
tracks
track_features
track_labels
analysis_jobs

listening_sessions
session_turns
recommendation_occurrences
feedback_events

playlists
playlist_items
```

### Local listener

No auth in Prototype 1. Create one generated default local listener profile instead of hard-coding `"user1"`.

### Tracks

Use UUIDs. Never trust source filenames as internal storage names. Audio stays outside SQLite.

### Track labels

Allow multiple genre/mood labels in persistence:

```text
track_id
kind        # genre | mood
value
source
confidence
is_primary
```

The current canonical `MusicCandidate` may continue to project a primary label for compatibility until a plural-label domain change is justified.

### Sessions

A `ListeningSession` is a listening experience, not a chat thread.

Persist historical sessions, but **do not restore the active queue after app restart**. Start a fresh active session when listening begins again.

### Recommendation occurrence

Keep this distinct from `Recommendation`.

`Recommendation` = algorithm result.  
`RecommendationOccurrence` = this recommendation was surfaced/queued in this specific session at this moment.

### Feedback

Persist the raw fact:

```text
event_type
played_seconds
duration_seconds
played_fraction
recommendation_occurrence_id
session_id
timestamp
```

Do not persist only the interpreted label.

### Playlists

Prototype 1 supports create, rename, delete, add, remove, and reorder. Do not auto-save recommendations.

## 10. Listening session state

Minimal conceptual model:

```text
ListeningSession
    session_id
    listener_profile_id
    status
    current_context
    current_track_occurrence_id
    rolling_queue
    started_at
    ended_at
```

The session tells us **where we are now**.

Separate history tells us **how we got here**:
`SessionTurn`, `RecommendationOccurrence`, `FeedbackEvent`.

Do not store UI-only state such as drawers, animations, scroll, composer draft, or explanation expansion.

Do not permanently store raw conversational text by default; persist structured intent.

## 11. Intent input

Prototype 1 uses structured `ListeningContext` as source of truth.

Limited deterministic commands may map into structured context:

```text
"more energetic" -> increase target energy
"calmer" -> decrease target energy
"more afrobeats" -> temporary genre preference
"something happier" -> positive mood/valence direction
"surprise me" -> increase exploration
"more familiar" -> reduce exploration
"more like this" -> increase affinity to current track
"try something different" -> increase exploration
```

LLM intent parsing is deferred behind a future `IntentParser` port.

## 12. Recommendation pipeline

```text
ALL ELIGIBLE LOCAL TRACKS
        |
        v
1. eligibility filter
        |
        v
2. current-intent score
        |
        v
3. current-session score
        |
        v
4. long-term score
        |
        v
5. combined rank
        |
        v
6. diversity/repetition re-rank
        |
        v
7. controlled exploration
        |
        v
ROLLING TOP 3
```

Do not collapse everything into one opaque score.

## 13. Eligibility

Ineligible when:
- managed file unavailable
- corrupt/unsupported
- `NOT_FOR_ME` in this session
- repetition cooldown forbids it
- no meaningful score can be computed from available data

Manual replay overrides cooldown. One session rejection does not permanently ban a track.

## 14. Current-intent scoring

Current explicit intent wins over conflicting historical preference.

Build effective targets from:

```text
system/default policy
+ long-term profile
+ current ListeningContext
```

For a feature:
- current explicit value wins
- otherwise long-term value
- otherwise unknown

Missing-feature rule:

```text
target exists + candidate value exists -> score
target absent -> feature inactive
candidate value absent -> omit feature
fewer active features -> renormalize active weights
```

Do not invent a midpoint.

Preserve current legacy scoring behavior when legacy inputs are complete. Extend/refactor shared primitives rather than creating a second copy of the old scoring math.

## 15. Session-fit scoring

Session feedback changes ranking immediately.

Initial feedback weights:

```text
LIKE                +1.00
SAVE/PLAYLIST_ADD   +1.00
REPLAY              +1.00
90-100% completion  +0.80
75-89% completion   +0.50
40-74% completion   +0.10
15-39% completion   -0.20
<15% after grace    -0.50
NOT_FOR_ME          -1.00
0-8 seconds         0.00
```

These are **Policy v1 heuristics**, not scientific facts.

Implement a reusable `candidate_similarity()` using only common available features.

For candidate `c` and prior meaningful feedback events:

```text
e_i = signed event weight
s_i = similarity(c, feedback_track)
r_i = recency weight
```

Initial formula:

```text
net = sum(e_i * s_i * r_i) / sum(abs(e_i) * r_i)
session_fit = (clamp(net, -1, 1) + 1) / 2
```

No meaningful evidence => `session_fit = 0.5`.

Prototype recency:
`r_i = 0.85 ** age`, latest event has age 0.

All constants belong in one versioned policy module/config object.

## 16. Combined rank

Initial Algorithm Policy v1:

```text
intent      0.55
session     0.30
long-term   0.15
```

```text
combined =
    0.55 * intent_fit
  + 0.30 * session_fit
  + 0.15 * long_term_fit
```

If a component is unavailable, renormalize active weights.

Current intent and recent session behavior must outweigh stale history when signals conflict.

## 17. Skip vs Not-for-me

They are distinct.

**Skip/Next:** stop the track now; meaning depends on how far playback progressed.

**Not for me:** explicit strong rejection.

Effects of Not-for-me:
- exact track excluded for current session
- similar tracks strongly down-ranked during current session
- no automatic permanent profile mutation

Interpret passive playback:

```text
0-8 sec          ignore as preference evidence
<15%             medium negative
15-39%           weak negative
40-74%           weak positive / near-neutral
75-89%           medium positive
90-100%          strong positive
```

Explicit actions override passive interpretation.

## 18. Immediate adaptation

Positive feedback -> more similar tracks become attractive.  
Negative feedback -> similar tracks become less attractive.  
Repeated failed exploration -> temporarily reduce exploration.  
Successful exploration -> cautiously explore that direction further.

One skip never permanently shuts down exploration.

## 19. Diversity and repetition

Diversity is a separate re-ranking stage.

Consider penalties for:
- same track recently played
- same artist streak
- near-identical feature vectors
- unnecessary genre/mood monotony

Do not force diversity so strongly that it violates explicit intent.

Finite local libraries may repeat songs after a cooldown. `NOT_FOR_ME` stays excluded for the session. Manual Replay is allowed immediately.

## 20. Controlled exploration

Initial behavior target: approximately **90% high-confidence / 10% controlled exploration**.

This is an experimental heuristic.

User controls may shift exploration:
- More familiar
- Surprise me
- Try something different
- More like this
- Play something from recently liked music

Exploration must remain plausible, not random.

## 21. Rolling three-candidate queue

Maintain three upcoming candidates.

Raw ranking:
`#1`, `#2`, `#3`.

The user-approved behavior allows #2 to play before #1 when #2 is close enough and offers useful novelty.

Initial safety gate:

```text
if score(#1) - score(#2) <= 0.08
and #2 provides useful novelty:
    select #2 first
else:
    select #1 first
```

If #2 safely plays first and nothing meaningful changes, default continuation may be:

```text
#2 -> #1 -> #3
```

The candidates are provisional. Like, Save, Replay, Skip, Not-for-me, refinement, More like this, Surprise me, More familiar, or Try something different can trigger immediate re-ranking.

## 22. Continuous playback

User presses Play/Tune In once. Then:

```text
current track
    -> next candidate already prepared
    -> track ends
    -> next begins
    -> queue refilled/re-ranked
```

The frontend owns real playback position/timers. The backend records meaningful events, not per-second ticks.

## 23. Long-term adaptation

Permanent profile change requires:

```text
>= 4 consistent strong signals
across >= 2 separate sessions
```

Then only a **small bounded** adjustment is allowed.

Every adjustment must be:
- traceable to evidence
- algorithm-versioned
- bounded
- reversible/recomputable

Examples:
- repeated strong positive evidence for a genre -> slight increase
- repeated strong negative evidence around very high energy -> slight downward energy adjustment

Do not implement opaque irreversible learning.

## 24. API direction

The old request-only API draft is superseded for this prototype.

Suggested routes:

```text
GET    /health

GET    /api/v1/library/tracks
POST   /api/v1/library/import
POST   /api/v1/library/sources
GET    /api/v1/library/sources
POST   /api/v1/library/rescan
GET    /api/v1/library/jobs
GET    /api/v1/tracks/{track_id}/audio

POST   /api/v1/sessions
GET    /api/v1/sessions
GET    /api/v1/sessions/{session_id}
POST   /api/v1/sessions/{session_id}/turns
POST   /api/v1/sessions/{session_id}/playback-events
POST   /api/v1/sessions/{session_id}/recommendations/{occurrence_id}/reactions

GET    /api/v1/playlists
POST   /api/v1/playlists
GET    /api/v1/playlists/{playlist_id}
PATCH  /api/v1/playlists/{playlist_id}
DELETE /api/v1/playlists/{playlist_id}
POST   /api/v1/playlists/{playlist_id}/items
DELETE /api/v1/playlists/{playlist_id}/items/{track_id}
PATCH  /api/v1/playlists/{playlist_id}/items/order
```

Turn variants:
`initial_intent`, `refine`, `next`, `not_for_me`, `more_like_this`, `surprise_me`, `more_familiar`, `try_something_different`.

Routes stay thin.

## 25. Audio serving

Frontend requests by track ID, never local path.

`GET /api/v1/tracks/{track_id}/audio`

Backend verifies track + file, resolves safe managed path, sets media type, and supports browser seeking/range requests using the actual installed framework behavior.

## 26. Error shape

```json
{
  "error": {
    "code": "TRACK_NOT_FOUND",
    "message": "The requested track does not exist.",
    "details": {},
    "request_id": "..."
  }
}
```

Potential codes:
`VALIDATION_ERROR`, `TRACK_NOT_FOUND`, `TRACK_UNAVAILABLE`, `UNSUPPORTED_AUDIO`, `IMPORT_FAILED`, `ANALYSIS_FAILED`, `SESSION_NOT_FOUND`, `RECOMMENDATION_NOT_FOUND`, `PLAYLIST_NOT_FOUND`, `INVALID_SESSION_TRANSITION`, `CONFLICT`, `RECOMMENDATION_UNAVAILABLE`, `INTERNAL_ERROR`.

Never expose stack traces or filesystem paths.

## 27. Security/privacy

Required even locally:
- no secrets committed
- no arbitrary file serving
- path traversal prevention
- allowlisted audio formats
- file-size limits
- generated managed filenames
- text-length validation
- DB/media gitignored
- no raw prompt retention by default
- no external sharing of imported music
- no real provider network calls in ordinary tests

Prototype 1 is personal/local; public licensing/distribution is future work.

## 28. Testing

Run the existing full suite after every phase. Prefer:

```text
python -m pytest -q
```

Required new coverage includes:
- context resolution
- missing-feature scoring
- feedback thresholds
- candidate similarity
- session-fit
- combined weights
- diversity/cooldown
- exploration gate
- three-candidate selection
- long-term evidence threshold
- migrations/repositories
- multi-folder import
- duplicate import
- source deletion after managed import
- progressive readiness
- job recovery
- API validation/errors
- playlist ordering
- playback-event behavior

Create deterministic evaluation scenarios:
`study/calm`, `workout/high energy`, `party/dance`, `relax`, `discovery`.

Do not claim algorithm improvement without comparison evidence.

## 29. Implementation phases

### B0 — Reconcile/freeze baseline
Inspect real repo/frontend, run tests, record baseline. No feature code.

### B1 — SQLite persistence foundation
SQLAlchemy, SQLite, Alembic, local listener, repositories, migration tests.

### B2 — Local library + managed media
Sources, safe copy, SHA-256 dedupe, tags, progressive status, scanning.

### B3 — Background analysis
Persisted jobs, in-process worker, audio analysis, recovery, provenance/versioning.

### B4 — Session domain
ListeningSession, SessionTurn, RecommendationOccurrence, FeedbackEvent, repositories.

### B5 — Recommendation Policy v1
Intent/session/long-term scores, missing features, similarity, diversity, exploration, rolling top 3, legacy preservation.

### B6 — Feedback/playback events
Like, Save, Replay, Skip, Complete, Not-for-me; raw event persistence; immediate re-ranking.

### B7 — Playlists
CRUD, add/remove/reorder, persistence.

### B8 — FastAPI
Library/session/feedback/playlist/audio routes, errors, request IDs, API tests.

### B9 — Frontend integration
Inspect actual F8 service boundary; add HTTP adapter without rewriting frontend state architecture.

### B10 — Conservative long-term adaptation
4 strong signals / 2 sessions gate, bounded changes, audit trail, reversibility.

### B11 — Evaluation/hardening
Performance, hundreds/thousands of tracks, restart behavior, migrations, algorithm evaluation.

## 30. Definition of done

Prototype 1 is successful when the user can:

1. run Intentune locally
2. register/import multiple folders
3. retain managed copies
4. use the app while analysis runs
5. start a fresh session
6. define structured listening intent
7. press Play once and get continuous music
8. have three candidates managed dynamically
9. skip, like, replay, save, or say Not for me
10. see future recommendations adapt immediately
11. receive diversity and controlled discovery
12. create/manage playlists
13. restart without losing library, playlists, metadata, feedback, or history
14. start a fresh active session after restart
15. run the full automated suite successfully

## 31. Core rule

**Do not optimize for impressive architecture. Optimize for behavior we can explain, test, measure, and improve.**

Working code is preserved until an approved requirement proves it must change.
