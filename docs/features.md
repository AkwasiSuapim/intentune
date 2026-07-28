# Features

## Status

**Current, Planned, and Future**

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
- Pytest coverage
- Model card and README

## Planned Core-Logic Features

- Unified typed domain models
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

## Planned Backend Features

- FastAPI application
- Versioned recommendation endpoint
- Health endpoint
- Structured validation errors
- Catalog repository abstraction
- Configuration through environment variables
- Structured logging
- Automated API tests

## Planned Persistence Features

- Anonymous session identifiers
- Feedback events
- Recommendation history
- Persistent user profiles
- Database migrations
- Optional user accounts later

## Planned User Interface Features

- Browser-based preference form
- Result cards
- Scores and explanations
- Feedback controls
- Loading states
- Empty states
- Error messages

## Future AI Features

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
- Saved recommendation collections
- Adaptive user profiles
- Diversity controls based on feedback
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
