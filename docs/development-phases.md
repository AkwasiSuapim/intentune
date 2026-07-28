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
