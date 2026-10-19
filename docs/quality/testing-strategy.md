# Testing Strategy

## Status

**Current and Planned.** Reconciled with Prototype 1 in Phase B0 (2026-10-18).

## Goals

- Protect existing behavior during refactoring
- Verify business rules independently of frameworks
- Avoid live external calls during normal tests
- Test errors and edge cases, not only successful paths
- Make results repeatable and deterministic
- Never claim an algorithm improvement without comparison evidence

## How to Run

### Backend

From `backend/`, with the backend virtual environment active:

```text
python -m pytest -q
```

The suite must run from `backend/`, because tests import `src.…` and there is no pytest configuration file. Run from the repository root, collection fails with 8 import errors. Outside the venv, the system Python on the B0 machine has no pytest.

Run the full suite after every phase (spec §28).

### Frontend

From `frontend/`:

```text
npm test                # Vitest: unit, static-render and DOM tests
npm run build           # typecheck and production build
npm run lint            # oxlint
npm run check:browser   # headless-Chrome browser checks (not part of npm test)
```

## Baseline (B0, 2026-10-18)

| Suite | Result |
|---|---|
| Backend `python -m pytest -q` | **131 passed** (Python 3.11.9, pytest 9.1.1) |
| Frontend `npm test` | **214 passed** in 9 files (Vitest 5.0.4) |
| Frontend `npm run build` | Passes |
| Frontend `npm run lint` | Clean |
| Frontend `npm run check:browser` | Not run in B0 |

Backend tests per file: `test_domain_models.py` 44, `test_recommender.py` 21, `test_canonical_scoring.py` 17, `test_csv_catalog.py` 13, `test_legacy_compatibility.py` 12, `test_recommendation_service.py` 11, `test_canonical_ranking.py` 10, `test_catalog_port.py` 3.

No backend or frontend test makes a network call.

## Current Test Coverage

### Backend

The original project tests areas including:

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

The existing suite is the regression baseline.

Added during the canonical domain refactor:

- `tests/test_canonical_scoring.py` and `tests/test_canonical_ranking.py` exercise typed domain objects without CSV or legacy dictionary inputs.
- `tests/test_csv_catalog.py` verifies CSV-row dictionaries, numeric conversion, optional metadata, catalog loading, `CsvCatalog`'s conformance to the `Catalog` port, and the adapter's lack of printing side effects.
- `tests/test_catalog_port.py` verifies the `Catalog` protocol's structural typing: an object with `list_candidates()` satisfies it, one without does not.
- `tests/test_recommendation_service.py` verifies application-level orchestration and type boundaries, including `recommend_from_catalog()` against an in-memory fake catalog (ranking determinism, result limits, empty catalog, non-`Catalog` rejection).
- `tests/test_legacy_compatibility.py` covers legacy-to-canonical conversion, the documented top-five baseline, and behavioral equivalence between legacy and canonical results across all 20 songs.

### Frontend

Described in [the frontend architecture](../frontend/ARCHITECTURE.md) §26: pure tests (composition policy, reducers, commands, mock service, service boundary), static-render tests (every block type and the unknown-block fallback), DOM tests (interaction, focus, overlays, loading/waiting/failure states), and browser checks (layout matrix, motion, contrast, axe-core audit, keyboard probe, design comparison). The frontend has not been tested on physical phones or with real screen readers.

## Prototype 1 Required Coverage

**Planned.** From spec §28 and the execution guide. Each item lands with the phase that implements it.

| Area | Phase |
|---|---|
| Clean migration, repository smoke tests | B1 |
| Multi-folder import; exact duplicate not duplicated; managed copy survives source deletion; unsupported formats fail safely; incremental rescan | B2 |
| Tracks usable during analysis; a failed track does not stop the worker; interrupted jobs recover; reanalysis after an analyzer version change | B3 |
| Session domain transitions, written as pure application tests before HTTP | B4 |
| Context resolution; missing-feature scoring; candidate similarity; session fit; combined weights; diversity/cooldown (recent track, repeated artist, near-duplicates); exploration gate; three-candidate selection; #2 safety threshold; conflicting current vs historical intent; finite library; exploration success and failure; **complete-input legacy outputs unchanged** | B5 |
| Feedback thresholds, including boundary values (8 s, 15%, 40%, 75%, 90%); explicit actions overriding passive playback; playback-event behavior; Not for me excluding the track for the session only | B6 |
| Playlist CRUD and ordering; one occurrence per playlist | B7 |
| API validation and error envelope; request IDs; no paths or stack traces in errors; audio range requests | B8 |
| Frontend service boundary against the HTTP adapter | B9 |
| Long-term evidence threshold; bounded, reversible adjustments | B10 |
| Restart behavior; migrations on existing data; performance with hundreds to thousands of tracks | B11 |

### Deterministic evaluation scenarios

Create fixed scenarios to compare policy versions: `study/calm`, `workout/high energy`, `party/dance`, `relax`, `discovery`. Algorithm changes are reported against these scenarios, not asserted as improvements.

## Test Layers

### Unit Tests

Cover pure logic:

- Preference and context validation
- Similarity functions
- Candidate scoring and missing-feature renormalization
- Ranking and tie-breaking
- Diversity re-ranking and cooldown
- Exploration and queue selection
- Feedback interpretation
- Profile update rules

### Integration Tests

Cover module cooperation:

- CSV adapter with recommendation service
- Repositories against a test SQLite database
- Library import against temporary source and media folders
- Background worker and job recovery
- AI adapter with mocked provider response *(Future)*
- YouTube adapter with mocked HTTP response *(Future)*

### API Tests

Cover:

- Request validation
- Response schema
- Status codes
- Error format
- Dependency failure handling
- Request limits

### End-to-End Tests

Cover one complete local journey: import, start a session, play, give feedback, see the queue adapt, restart, and find the library and history intact (spec §30).

### Manual User Testing

Ask test users to complete tasks and report:

- Whether input controls are understandable
- Whether results feel relevant
- Whether explanations make sense
- Whether errors are understandable
- Whether the product is responsive enough

## External Service Rule

Ordinary pytest runs make no real provider network calls (spec §27). Prototype 1 has no providers; when Future AI or YouTube work begins, it uses fixtures and mocked clients.

## Test Data

Keep stable fixtures for:

- Internal songs (`backend/data/songs.csv`)
- User profiles and listening contexts
- Missing metadata
- Small generated audio files for import and analysis tests (B2, B3)
- YouTube search responses *(Future)*
- AI structured outputs *(Future)*
- Provider errors *(Future)*

Tests never read from or write to the real `backend/data/intentune.db` or `backend/data/media/`.

## Continuous Integration

**Future.** No CI workflow exists (`.github/` is absent). A later GitHub Actions workflow should:

1. Check out code.
2. Install the supported Python version.
3. Install dependencies.
4. Run formatting or lint checks.
5. Run pytest from `backend/`.
6. Run the frontend tests, build, and lint.
7. Fail the workflow when required checks fail.

## Definition of Done for a Feature

A feature is complete only when:

- Behavior is documented
- Tests cover the main path
- Tests cover important failure paths
- Existing tests still pass, without weakened assertions or raised timeouts
- Manual behavior is verified when applicable
- Relevant documentation is updated
