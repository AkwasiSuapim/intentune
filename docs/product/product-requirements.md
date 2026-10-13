# Product Requirements

## Status

**Draft**

This document defines the intended product behavior. Requirements will be refined after the repository audit and early user testing.

## Product Goal

Allow a user to provide music preferences and receive a small, ranked, explainable set of recommendations through a browser-accessible application.

## Primary User Story

> As a listener, I want to describe what I like or what I need music for, so I can receive recommendations that fit my current situation and understand why they were selected.

## MVP Functional Requirements

### Recommendation Input

The system must initially allow a user to provide:

- One or more preferred genres
- One or more preferred moods
- Preferred energy from 0.0 to 1.0
- Preferred danceability from 0.0 to 1.0
- Number of requested recommendations within a safe limit

### Recommendation Processing

The backend must:

- Validate all input
- Load recommendation candidates through a catalog abstraction
- Score each candidate
- Rank candidates deterministically
- Apply tie-breaking rules
- Return a limited result set
- Explain the main contribution of each scoring feature
- Handle empty catalogs and invalid data safely

### Recommendation Output

Each recommendation should include:

- Candidate identifier
- Title
- Artist or creator
- Source
- Final score
- Match classification
- Explanation reasons
- Optional URL and thumbnail when the source supports them

### Feedback

A later MVP increment should allow users to record:

- Like
- Dislike
- Skip
- Save
- Open result

Initially, feedback may be stored without automatically changing the profile.

### User Interface

A browser interface should provide:

- Preference controls
- A Recommend action
- Loading and error states
- Ranked result cards
- Recommendation explanations
- Basic feedback controls

## Nonfunctional Requirements

### Reliability

- Invalid input must return a clear error rather than crash the application.
- External service failure must not expose internal exceptions to users.
- The recommendation engine must continue to work in tests without live AI or YouTube calls.

### Performance

- Local recommendations should return quickly for the small internal catalog.
- External API calls must use timeouts.
- Results should be limited to avoid unnecessary processing and API cost.

### Security

- Secrets must come from environment variables or a deployment secret manager.
- `.env` files must not be committed.
- Inputs must be validated at API boundaries.
- Logs must not include secret values.

### Maintainability

- UI, API, domain logic, persistence, and external integrations must have separate responsibilities.
- New catalog providers should not require rewriting the recommendation domain.
- Core logic must be covered by unit tests.

**Current:** `src/intentune/domain/models.py` provides the canonical, source-independent models (`MusicCandidate`, `UserProfile`, `ListeningContext`, `FeatureWeights`, `ScoreComponent`, `ScoreBreakdown`, `Recommendation`) that a future FastAPI request schema, database repository, or YouTube adapter can target directly instead of inventing its own shape. See docs/decisions/technical-decisions.md, TD-008.

### Explainability

- Every result must include clear reasons.
- Explanations must not claim unsupported facts.

## Success Criteria for Early Testing

The early version is successful when:

- A nontechnical user can request recommendations without assistance.
- Different profiles produce meaningfully different rankings.
- The system does not crash during ordinary use.
- Users can understand why a result appeared.
- Test users provide actionable feedback about relevance and usability.

## Out of Scope for the Initial MVP

- Microservices
- Native mobile applications
- Spotify integration
- Payments
- Social feeds
- Collaborative playlists
- Large-scale machine-learning training
- Full authentication and account recovery
- Automatic long-term storage of every user prompt
