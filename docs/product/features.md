# Features

## Status

**Current, Planned, Superseded, and Future.** Reconciled with Prototype 1 in Phase B0 (2026-10-18).

## Current Features

- CSV-based song catalog
- Content-based recommendation scoring
- Exact genre matching
- Exact mood matching
- Energy similarity scoring
- Danceability similarity scoring
- Deterministic ranking
- Top-k recommendations
- Human-readable reasons
- CLI output
- Unified typed domain models (`MusicCandidate`, `UserProfile`, `ListeningContext`, `FeatureWeights`, `ScoreComponent`, `ScoreBreakdown`, `Recommendation`)
- Formal `Catalog` port with a `CsvCatalog` implementation, and catalog-backed application orchestration (`recommend_from_catalog()`)
- Pytest coverage
- Model card and README
- Mock-driven React frontend: mobile-first listening sessions, intent strip, hero and compact recommendations, Why this fits, Like / Not for me / Save, quick actions and Tune, playlist picker, session drawer, responsive tablet/desktop layouts. Nothing is persisted and there is no audio.

## Planned Prototype 1 Features

**Planned (approved).** From the [Prototype 1 specification](../planning/intentune-backend-prototype-implementation-spec.md) §3:

- Local single-listener identity; no production authentication *(B1: the generated listener and its storage exist in the backend. B8: created at API startup, and owner of every session and playlist.)*
- Managed local music library fed by multiple source folders *(B2: built and tested in the backend, with import, dedupe, tags, and incremental rescans. B8: reachable over HTTP, with a startup scan at every start.)*
- SQLite persistence with SQLAlchemy repositories and versioned migrations *(B1: foundation built, holding the listener profile only)*
- Background scanning and analysis, with progressive track readiness *(B3: background analysis built and tested, with persisted jobs, one worker, recovery, and exact level and duration measurements. B8: the API starts the worker and wakes it after scans; the startup scan runs in the background, and manual Import and Rescan run within their request.)*
- Structured `ListeningContext` and listening sessions *(B4: session state machine, turns, and the restart rule built and tested in the backend. B8: reachable over HTTP; startup applies the restart rule.)*
- Recommendation occurrences, feedback, and playback events *(B4: occurrences, plus the raw-feedback table; recording feedback is B6. B5: each occurrence keeps its surfaced position and exploration mark.)* *(B6: Like, Save, Replay, Skip, Complete, and Not for me are recorded as raw facts, read through Feedback Policy v1, and re-rank the queue at once. A skip, completion, or Not for me moves on; Replay plays a past track again. Built and tested in the backend. B8: playback-events and reactions routes.)*
- Continuous recommendation flow with a rolling three-candidate queue *(B5: Recommendation Policy v1 fills and re-ranks the queue from the session's intent, turns, and plays, with #2 able to play first; built and tested in the backend. B8: every session command over HTTP re-ranks it.)*
- Controlled exploration and repetition cooldown *(B5: about 90/10 exploration moved by the listener's controls and recent outcomes, a cooldown that shrinks for small libraries, and repeated-artist and near-duplicate penalties. Without a control, exploration stays in a requested genre. Listener controls act on the next refresh, deterministically: Surprise me adds a novel track, leaving the genre only when it offers no novelty. Try something different makes a track outside the genre the next to play. More familiar holds exploration back.)*
- Playlists *(B7: create, rename, delete, add, remove, and reorder, with one entry per track and names unique per listener. Adding a recommendation from a session is strong positive feedback that re-ranks the queue; nothing is ever saved automatically. Built and tested in the backend. B8: reachable over HTTP.)*
- FastAPI HTTP API and local audio playback endpoint *(B8: every spec route, with strict validation, one error envelope with request IDs, and audio served by track id with range requests for seeking. B9: the approved frontend runs on it, with real audio playback; typed words are interpreted by a small deterministic backend vocabulary; Like can be taken back (Unlike).)*
- Long-term evidence collection and conservative long-term adaptation

The sections below predate Prototype 1. Items that Prototype 1 replaces are marked.

## Planned Core-Logic Features

- Multiple preferred genres
- Multiple preferred moods
- Preference strength
- User-specific feature weights
- Partial genre similarity
- Partial mood similarity
- Missing-feature handling
- Score normalization
- Match classifications
- Diversity re-ranking
- Better explanation objects
- Algorithm versioning

Each feature must be introduced only after its behavior and tests are defined.

In Prototype 1, missing-feature handling, diversity re-ranking, and algorithm versioning arrive with Recommendation Policy v1 (B5). *(Current since B5, 2026-10-20: each occurrence records the policy version, `policy-v1`.)* Plural genre and mood labels are stored per track (spec §9). Match classifications and score display are **superseded**: the approved frontend never shows scores or confidence. The remaining items are not scheduled.

## Planned Backend Features

- FastAPI application
- Versioned recommendation endpoint *(superseded: Prototype 1 uses session, library, and playlist endpoints)*
- Health endpoint
- Structured validation errors
- Configuration through environment variables
- Structured logging
- Automated API tests

## Planned Persistence Features

- Anonymous session identifiers *(Prototype 1: one generated local listener, UUID sessions)*
- Feedback events
- Recommendation history
- Persistent user profiles
- Database migrations
- Optional user accounts later *(Future)*

## Planned User Interface Features

**Superseded in part.** The frontend was built as a conversational listening session instead of a preference form (frontend phases F0–F8). Scores are never displayed.

- Browser-based preference form *(superseded)*
- Result cards
- Scores and explanations *(scores superseded; explanations kept as Why this fits)*
- Feedback controls
- Loading states
- Empty states
- Error messages

## Future AI Features

Deferred beyond Prototype 1 (D39). Prototype 1 supports only a limited set of deterministic commands such as "more energetic", "calmer", and "surprise me" (D30).

- Conversational input
- Current mood extraction
- Desired mood extraction
- Listening-goal extraction
- Genre suggestion
- Search-keyword generation
- Clarifying questions for ambiguous requests
- Grounded explanation support

AI output must be validated before entering the core system.

## Future YouTube Features

Deferred beyond Prototype 1 (D39).

- Official YouTube Data API integration
- Video title
- Channel or artist name
- Thumbnail
- YouTube link
- Embeddable player where allowed
- Deduplication
- Provider error handling
- Quota-aware search

## Later Possibilities

- Spotify integration
- Saved recommendation collections *(Prototype 1: playlists, D34)*
- Adaptive user profiles *(Prototype 1: conservative long-term adaptation, D06)*
- Diversity controls based on feedback *(Prototype 1: exploration controls such as Surprise me and More familiar, D36)*
- Collaborative recommendations
- Mobile client
- More advanced ranking models

## Explicitly Deferred

- Microservices
- Complex event streaming
- Payments
- Large-scale custom model training
- Automatic playlist publishing
- Social network features
- Prototype 1 deferrals (spec §3): production auth/OAuth/JWT, multi-user cloud system, Spotify/YouTube catalog, unrestricted LLM intent parser, vector database, Redis/Celery/Kafka, AI DJ, real-time filesystem watchers, cross-user collaborative filtering
