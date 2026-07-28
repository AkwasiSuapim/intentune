# Testing Strategy

## Status

**Planned**

## Goals

- Protect existing behavior during refactoring
- Verify business rules independently of frameworks
- Avoid live external calls during normal tests
- Test errors and edge cases, not only successful paths
- Make releases repeatable

## Current Test Coverage

The uploaded project already tests areas including:

- CSV loading
- Type conversion
- Perfect and partial matches
- Numerical validation
- Ranking
- Top-k behavior
- Empty input
- Negative `k`
- Deterministic tie-breaking
- Mutation protection
- CLI integration

The existing suite becomes the regression baseline.

## Test Layers

### Unit Tests

Cover pure logic:

- Preference validation
- Similarity functions
- Candidate scoring
- Weight normalization
- Ranking
- Tie-breaking
- Diversity re-ranking
- Match classification
- Profile update rules

### Integration Tests

Cover module cooperation:

- CSV adapter with recommendation service
- Database repositories with test database
- AI adapter with mocked provider response
- YouTube adapter with mocked HTTP response

### API Tests

Cover:

- Request validation
- Response schema
- Status codes
- Error format
- Dependency failure handling
- Request limits

### End-to-End Tests

Cover one complete user journey in a deployed or test environment.

### Manual User Testing

Ask invited users to complete tasks and report:

- Whether input controls are understandable
- Whether results feel relevant
- Whether explanations make sense
- Whether errors are understandable
- Whether the product is responsive enough

## External Service Rule

Ordinary pytest runs must not consume real AI tokens or YouTube quota. Use fixtures and mocked clients.

## Test Data

Keep stable fixtures for:

- Internal songs
- User profiles
- YouTube search responses
- AI structured outputs
- Provider errors
- Missing metadata

## Continuous Integration

A later GitHub Actions workflow should:

1. Check out code.
2. Install the supported Python version.
3. Install dependencies.
4. Run formatting or lint checks.
5. Run pytest.
6. Fail the workflow when required checks fail.

## Definition of Done for a Feature

A feature is complete only when:

- Behavior is documented
- Tests cover the main path
- Tests cover important failure paths
- Existing tests still pass
- Manual behavior is verified when applicable
- Relevant documentation is updated
