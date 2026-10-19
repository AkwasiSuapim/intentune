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

- Local single-listener identity; no production authentication *(B1: the generated listener and its storage exist in the backend; nothing a listener runs reaches them yet)*
- Managed local music library fed by multiple source folders
- SQLite persistence with SQLAlchemy repositories and versioned migrations *(B1: foundation built, holding the listener profile only)*
- Background scanning and analysis, with progressive track readiness
- Structured `ListeningContext` and listening sessions
- Recommendation occurrences, feedback, and playback events
- Continuous recommendation flow with a rolling three-candidate queue
- Controlled exploration and repetition cooldown
- Playlists
- FastAPI HTTP API and local audio playback endpoint
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

In Prototype 1, missing-feature handling, diversity re-ranking, and algorithm versioning arrive with Recommendation Policy v1 (B5). Plural genre and mood labels are stored per track (spec §9). Match classifications and score display are **superseded**: the approved frontend never shows scores or confidence. The remaining items are not scheduled.

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
