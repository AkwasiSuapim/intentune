# Changelog

All meaningful product, architecture, and behavior changes should be recorded here.

## Unreleased

### Added

- Canonical, source-independent domain models in `src/intentune/domain/models.py`: `MusicCandidate`, `UserProfile`, `ListeningContext`, `FeatureWeights`, `ScoreComponent`, `ScoreBreakdown`, `Recommendation`, each with explicit validation and no CSV/HTTP/database/provider dependencies.
- `tests/test_domain_models.py` covering the new models plus compatibility checks (danceability fix, legacy result shapes, CLI output, top-five ranking).
- Canonical scoring (`src/intentune/domain/scoring.py`, `score_candidate()`) implementing the current four-feature rule (genre, mood, energy, danceability) as the single source of truth, producing typed `ScoreBreakdown`/`ScoreComponent` output.
- Canonical ranking (`src/intentune/domain/ranking.py`, `rank_candidates()`) implementing the current score/title/creator tie-breaking rule and rank assignment, returning typed `Recommendation` objects.
- CSV catalog adapter (`src/intentune/adapters/csv_catalog.py`, `load_music_candidates()`/`music_candidate_from_csv_row()`) converting raw CSV rows into `MusicCandidate`; `id`/`title`/`artist` are required, genre/mood/audio features are optional (missing or blank becomes `None`).
- A first application-service orchestrator (`src/intentune/application/recommendation_service.py`, `recommend_music()`) coordinating canonical scoring and ranking for one use case.
- Legacy boundary converters in `src/recommender.py`: `legacy_profile_to_user_profile()` and `song_dict_to_music_candidate()`.
- `tests/test_csv_catalog.py`, `tests/test_canonical_scoring.py`, `tests/test_canonical_ranking.py`, `tests/test_recommendation_service.py`, `tests/test_legacy_compatibility.py`.
- A formal catalog port, `Catalog` (`src/intentune/ports/catalog.py`), a `Protocol` with one method, `list_candidates() -> Sequence[MusicCandidate]`. Contains no CSV/database/YouTube-specific language.
- `CsvCatalog` (`src/intentune/adapters/csv_catalog.py`), a small class implementing the `Catalog` port around the existing `load_music_candidates()` loader.
- `recommend_from_catalog(catalog, profile, limit)` (`src/intentune/application/recommendation_service.py`), an application-level orchestrator that depends on the `Catalog` port rather than a concrete adapter, so a fake in-memory catalog can be injected for tests.
- `tests/test_catalog_port.py`, plus new tests in `tests/test_csv_catalog.py` and `tests/test_recommendation_service.py` covering `CsvCatalog` and `recommend_from_catalog()`.

### Added — Phase B1: SQLite persistence foundation (2026-10-19)

- `src/intentune/persistence/db.py`: `DATABASE_URL` resolution, defaulting to `backend/data/intentune.db`, with relative paths resolved against `backend/` and non-SQLite URLs rejected. Also a synchronous engine factory: foreign keys enforced, WAL for file databases, and SQLAlchemy-emitted `BEGIN` so DDL is transactional. Plus a session factory.
- `src/intentune/persistence/models.py`: declarative `Base` with a constraint naming convention, the `UtcDateTime` column type (aware UTC in and out, naive rejected), and `ListenerProfileRecord`.
- `src/intentune/domain/listener.py`: `ListenerProfile` (canonical UUID, default flag, UTC creation time; no personal data) and `new_default_listener_profile()`.
- Ports `ListenerProfileRepository` (`src/intentune/ports/listener_profiles.py`) and `UnitOfWork` (`src/intentune/ports/unit_of_work.py`), implemented by `SqlAlchemyListenerProfileRepository` and `SqlAlchemyUnitOfWork` (explicit commit; rollback on leaving the block).
- `ensure_default_listener()` (`src/intentune/application/local_listener.py`): generates one default local listener on first run and returns the same one afterwards (D01).
- Alembic: `backend/alembic.ini`, `backend/alembic/env.py` (uses the application engine factory, one transaction per upgrade, foreign-key check before commit, batch mode), and migration `6ef3a3452ab7`, which creates `listener_profiles` with a partial unique index allowing one default listener. `upgrade_database()` (`src/intentune/persistence/migrations.py`) runs it from Python.
- 97 tests in `tests/test_persistence_db.py`, `tests/test_migrations.py`, `tests/test_listener_repository.py`, `tests/test_listener_profile.py`, `tests/test_local_listener_service.py`, and `tests/test_architecture_boundaries.py`, with fixtures in `tests/conftest.py`. The suite is 228 tests, all passing; the 131 baseline tests are unchanged.
- **B1 hardening pass (test-only):**
  - The architecture-boundary checks now scan each layer recursively, including nested subpackages, and resolve relative imports before checking.
  - New migration tests prove that a failed migration rolls back both schema and data, and that a failed upgrade from an empty database leaves no partial schema.
  - Brittle assertions on exact table sets, whole reflected dictionaries, and raw DDL text were replaced with behavioral or stable schema checks.
  - The pass found no production bug and required no production-code change.
- TD-012 records the B1 implementation decisions.

### Added — Frontend (F0–F8)

*Recorded during B0 from the Git history (2026-10-13 to 2026-10-15); the changelog had no frontend entries before.*

- React 19 + TypeScript + Vite application in `frontend/`, with oxlint and Vitest (jsdom, Testing Library).
- Approved design reference stored in `docs/frontend/design/approved/`; frontend architecture, agent instructions, and phase plan in `docs/frontend/`.
- Design tokens, mobile app shell, and the approved component vocabulary (recommendation hero and compact cards, Why this fits, TuneBar, RefineControl, PlaylistPicker, Up Next, session drawer, composer with compact now-playing).
- Controlled generative UI: typed session state, a pure composition policy, a block registry, and a safe unknown-block fallback.
- Interactive mock listening sessions, then responsive and motion polish for tablet and desktop.
- Accessibility and browser-quality coverage, including headless-Chrome browser checks.
- An asynchronous `SessionService` boundary with a mock implementation, plus loading, pending, and failure states, ready for a future HTTP client.

### Changed

- The legacy `Recommender` wrapper (`src/recommender.py`) no longer hard-codes `preferred_danceability` to `0.5`; the legacy `UserProfile` dataclass gained a real `preferred_danceability` field (default `0.5`, matching the old hard-coded value so existing call sites score identically) that the wrapper now actually reads.
- The legacy `Recommender` wrapper precomputes song-dict conversions and an id-based lookup once per instance instead of repeating them on every call, and retains the last computed scores/reasons on `self.last_recommendations` instead of discarding them.
- `load_songs()`, `score_song()`, and `recommend_songs()` in `src/recommender.py` now convert their inputs into canonical `MusicCandidate`/`UserProfile` and delegate to the canonical CSV adapter/scorer/ranker, instead of containing their own CSV parsing and scoring math. Public signatures, dictionary shapes, scores, reasons, and CLI output are unchanged; tests verify behavioral equivalence across the full 20-song catalog and protect the documented top-five CLI baseline.
- **B1 (2026-10-19):** the `backend/.env.example` comment for `DATABASE_URL` now says the path resolves against `backend/` and that nothing loads `.env` yet. The value is unchanged.
- **B1 prerequisites (2026-10-18):** `backend/requirements.txt` pins every direct dependency (`pandas==3.0.6`, `pytest==9.1.1`, `fastapi==0.143.0`, `uvicorn[standard]==0.54.0`, `httpx==0.28.1`, `sqlalchemy==2.1.5`) and adds `alembic==1.20.0`. `backend/.env.example` now sets `DATABASE_URL=sqlite:///./data/intentune.db`, the Prototype 1 location.

### Security

- `.gitignore` now ignores the local SQLite database (`backend/data/intentune.db*`, including journal, WAL, and SHM files) and managed media (`backend/data/media/`), before either can exist (2026-10-18).

### Removed

- `_calculate_similarity_points()` and `_validate_numeric_preference()` in `src/recommender.py`, now dead code superseded by `src/intentune/domain/scoring.py`.

### Documentation

- Created the initial Intentune documentation package.
- Defined the product direction from CodePath prototype to modular backend application.
- Recorded the proposed modular-monolith architecture.
- Documented planned AI and YouTube integrations as future adapters.
- Recorded TD-008 (canonical domain models) and TD-009 (canonical domain objects as internal source of truth) in docs/decisions/technical-decisions.md.
- Documented two future milestones in docs/planning/development-phases.md: Expanded and Configurable Scoring Engine, and Context-Aware and User-Configurable Weighting.
- Marked `likes_acoustic` on the legacy `UserProfile` dataclass as deprecated and inert.
- **Phase B0 (2026-10-18): Prototype 1 documentation reconciliation.** Adopted the Prototype 1 backend specification, decision register (D01–D39), and backend execution guide as the approved backend direction (TD-011). Reconciled the architecture, workflow, folder structure, audit, API, database, decisions, trade-offs, phases, risks, testing, security, product, and operations documents so each distinguishes Current, Planned, Superseded, and Future behavior. Earlier plans were kept and marked Superseded rather than deleted. Recorded the verified baseline. No code changed.

### Known Limitations

- The historical dictionary API and historical dataclass API shapes still coexist with the canonical domain models for backward compatibility, though they are now thin boundary conversions rather than separate scoring/ranking implementations.
- The scoring algorithm, its 10-point maximum, and its sharp similarity cutoff are unchanged; it still only uses genre, mood, energy, and danceability.
- `score_candidate()` requires genre, mood, energy, and danceability to be present -- missing-feature normalization for partial YouTube-style metadata is not implemented yet.
- The legacy dict shape (`load_songs()`'s output) assumes every candidate field is present; a `MusicCandidate` with a `None` audio feature would fail converting back to that shape. Not an issue for the current CSV catalog, where every field is always populated.
- The compatibility CLI path performs an extra `MusicCandidate -> legacy dict -> MusicCandidate` conversion; it calls `load_music_candidates()` directly rather than through `CsvCatalog`/`Catalog`, since the legacy dict shape predates the port and rewiring it would change nothing observable.
- The CLI (`src/main.py`) does not yet use `recommend_from_catalog()` -- it still runs the legacy `load_songs()`/`recommend_songs()` path. Wiring a catalog-backed entry point into the CLI is a future decision, not required for Phase 2.
- Found in B0 and fixed the same day as B1 prerequisites: `.gitignore` did not ignore the planned database or managed media; `DATABASE_URL` in `backend/.env.example` resolved to `backend/intentune.db`; `backend/requirements.txt` was unpinned, listed `sqlalchemy` and `httpx` without them being installed, and did not list `alembic`. Transitive dependencies are still not locked.
- The frontend runs only on mock data, has no audio playback, and is not connected to the backend.
- B1 persistence is not wired into any running entry point. Nothing applies migrations or calls `ensure_default_listener()` at startup until B8. `backend/.env` is not loaded, so a different database must be chosen through the `DATABASE_URL` environment variable.

### Current Baseline

Verified in Phase B0 on 2026-10-18:

- CSV-based catalog with 20 songs
- Content-based scoring using genre, mood, energy, and danceability
- Command-line recommendation display
- Human-readable scoring reasons
- Formal `Catalog` port with a `CsvCatalog` implementation
- Catalog-backed application orchestration (`recommend_from_catalog()`)
- Pytest regression suite: 131 tests, all passing (`python -m pytest -q` from `backend/`; re-verified after the B1 prerequisites). This is the pre-B1 baseline; for the suite after B1, see *Added — Phase B1* above.
- Mock-driven React frontend (F0–F8): 214 Vitest tests passing; build and lint clean

## Version Template

```text
## [Version] - YYYY-MM-DD

### Added

### Changed

### Fixed

### Removed

### Security

### Known Limitations
```
