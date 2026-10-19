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

The suite must run from `backend/`, because tests import `src.…` and there is no pytest configuration file. `tests/conftest.py` (B1) provides database fixtures only. At B0, running from the repository root failed collection with 8 import errors. Outside the venv, the system Python on the B0 machine has no pytest.

Persistence tests create their own SQLite files under pytest's `tmp_path` and upgrade them with the real migrations. They never open `backend/data/intentune.db` or depend on `DATABASE_URL`.

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

## After B1 (2026-10-19)

| Suite | Result |
|---|---|
| Backend `python -m pytest -q` | **228 passed**: the 131 baseline tests, unchanged, plus 97 from B1 |

B1 tests per file: `test_persistence_db.py` 26, `test_listener_profile.py` 19, `test_listener_repository.py` 19, `test_architecture_boundaries.py` 15, `test_migrations.py` 14, `test_local_listener_service.py` 4. These counts include the test-only [B1 hardening pass](../planning/development-phases.md#b1-hardening-pass-2026-10-19). The frontend was not changed or re-run.

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

Added in B1 (persistence foundation):

- `tests/test_listener_profile.py`: `ListenerProfile` validation (canonical UUID, bool flag, timezone-aware UTC time, immutability) and default-listener generation.
- `tests/test_local_listener_service.py`: pure application tests of `ensure_default_listener()` against an in-memory fake unit of work, with no SQLite.
- `tests/test_persistence_db.py`: `DATABASE_URL` resolution (default, relative to `backend/` regardless of working directory, `.env.example` agreement, absolute and in-memory URLs, non-SQLite rejection); connection setup (foreign keys enforced and actually rejecting an orphan row, WAL, transactional DDL proven by a rolled-back `CREATE TABLE`); `UtcDateTime` round trips, offset conversion, and naive rejection.
- `tests/test_migrations.py`:
  - **Upgrades:** a clean upgrade from an empty database; a single head; a path with spaces and `%`.
  - **Schema:** the `listener_profiles` columns, non-null constraints, primary key, and the unique index on the default flag, checked through stable reflected fields (names, columns, the unique flag) rather than whole reflected dictionaries or raw DDL text.
  - **Snapshots:** a no-op re-upgrade and an upgrade–downgrade–upgrade round trip, each compared against a before/after schema snapshot; downgrade to base removing every table the ORM declares.
  - **Code agreement:** migrations matching the ORM records (`compare_metadata`).
  - **One default listener, by behavior:** a second default is refused on both INSERT and UPDATE, and several non-default rows are allowed.
  - **Atomic failure:** a deliberately failing migration changes the schema, confirms the change, then raises. The schema and existing data are left unchanged. A failing upgrade from an empty database leaves no partial schema, not even `alembic_version`. Both tests fail when B1's transaction handling is removed.
- `tests/test_listener_repository.py`: repository reads and writes against a migrated database; unit-of-work commit, rollback on exit, exception, or explicit rollback, isolation between transactions, reuse, non-re-entrancy, and refusal outside `with`; the default listener end to end, including idempotence and survival across an engine restart.
- `tests/test_architecture_boundaries.py`: covers every Python file under `domain/`, `ports/`, and `application/`, including nested subpackages. None may import a storage or delivery framework, or the persistence or adapter packages. The domain may import nothing from `src` outside itself. Relative imports are resolved to absolute module names before checking. Self-tests cover the resolver and plant violations in a synthetic nested package to prove they are caught.

### Frontend

Described in [the frontend architecture](../frontend/ARCHITECTURE.md) §26: pure tests (composition policy, reducers, commands, mock service, service boundary), static-render tests (every block type and the unknown-block fallback), DOM tests (interaction, focus, overlays, loading/waiting/failure states), and browser checks (layout matrix, motion, contrast, axe-core audit, keyboard probe, design comparison). The frontend has not been tested on physical phones or with real screen readers.

## Prototype 1 Required Coverage

**Planned.** From spec §28 and the execution guide. Each item lands with the phase that implements it.

| Area | Phase |
|---|---|
| Clean migration, repository smoke tests | B1 — **Current** (2026-10-19) |
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
