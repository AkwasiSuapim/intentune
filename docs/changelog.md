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

### Added — Phase B2: Managed local library (2026-10-19)

- `src/intentune/domain/library.py`:
  - **Models:** library sources, source files, tracks, and provenance-tagged labels.
  - **Rules:** the format allowlist (MP3, M4A, FLAC, Ogg, Opus, WAV), a relative-path rule that cannot escape a source folder, and tag interpretation (year from date tags, genres split on `;`).
  - **States:** file and track readiness.
  - **Values:** scan reports.

  Shared validators moved to `src/intentune/domain/validation.py`.
- `LibraryService` (`src/intentune/application/library.py`):
  - **Capabilities:** register and list sources, scan one source or rescan all, import one file, list and get tracks, mark a track unavailable.
  - **Import pipeline:** validate → hash → dedupe → copy → persist → tag.
  - **Incremental scans:** unchanged files skipped; FAILED files retried; changed content imported as a new track; missing files and folders recorded while managed copies stay usable; unavailable tracks repaired.
- Ports `LibrarySourceRepository`, `SourceFileRepository`, `TrackRepository` (`src/intentune/ports/library.py`) and `SourceFolders`, `AudioInspector`, `ManagedMedia` (`src/intentune/ports/library_files.py`). The library repositories are exposed through `UnitOfWork`.
- Adapters:
  - `LocalSourceFolders`: link-, junction-, and loop-safe folder walking that excludes managed media.
  - `LocalManagedMedia`: atomic, SHA-256-verified copies to `backend/data/media/<track_uuid>.<extension>`.
  - `MutagenAudioInspector`: validation by content, and ID3, Vorbis-comment, and MP4 tag mapping.
  - SQLAlchemy repositories for sources, source files, and tracks.
- Migration `2540be2956b8`: `library_sources`, `source_files`, `tracks`, `track_labels`, with CHECK constraints on every enumerated column and one primary label per kind.
- `mutagen==1.48.1` in `backend/requirements.txt`.
- 177 tests: six new files and three new architecture checks (mutagen and filesystem modules forbidden in inner layers). The suite is 404 passed and 1 skipped (a symbolic-link test this machine cannot run); the 228 earlier tests are unchanged.
- TD-013 records the B2 implementation decisions.

### Added — Phase B3: Background analysis (2026-10-20)

- `src/intentune/domain/analysis.py`:
  - **Jobs:** analysis jobs and their transitions; retry, interruption, and re-arming rules.
  - **Identity and features:** analyzer identity (`name@version`), measured features with provenance, and the needs-analysis rule.
- **Track states:** `ANALYZING` and `READY` join the library domain. A repaired analyzed track returns to `READY`.
- `AnalysisService` (`src/intentune/application/analysis.py`):
  - **Queuing:** idempotent `enqueue_pending()`.
  - **Recovery:** `recover_interrupted()`.
  - **Processing:** `process_next()` and `run_until_idle()`, with analysis outside any transaction.
  - **Outcomes:** retries for read errors; no retry for decode errors; skips for unsupported formats and superseded versions; missing-copy handling; path-free error messages.
- `AnalysisWorker` (`src/intentune/application/analysis_worker.py`): one background thread that recovers on start, processes one job at a time, queues new work when idle, survives errors, and stops after the current job.
- Ports `AudioAnalyzer`, `AnalysisJobRepository` (with an atomic `claim_next`), and `TrackFeatureRepository` (`src/intentune/ports/analysis.py`).
- `SignalLevelAnalyzer` (`src/intentune/adapters/signal_levels.py`):
  - **Measures:** decoded duration, sample peak, and RMS level, all exact, read in blocks through soundfile and numpy.
  - **Not:** loudness in LUFS, tempo, key, or any semantic feature.
  - **Version:** `1+libsndfile-1.2.2`.
- Migration `7a42f0b9c8bf`: `analysis_jobs`, `track_features`, and a rebuild of `tracks` allowing the new states; its downgrade keeps every track.
- `soundfile==0.14.0` and `numpy==2.4.6` pinned in `backend/requirements.txt`. `librosa` was evaluated and not added (TD-014).
- 114 tests: five new files, plus three in existing files. The suite is 518 passed and 1 skipped.
- TD-014 records the B3 implementation decisions.

### Added — Phase B4: Session domain (2026-10-20)

- `src/intentune/domain/session.py`:
  - `ListeningSession` holds current state: ACTIVE or ENDED, with an end reason, and the `ListeningContext` in force.
  - `SessionTurn` holds steering history: eight turn kinds, each with the context left in force, and no text.
  - `RecommendationOccurrence` is a surfaced recommendation: QUEUED → PLAYING → PLAYED, or REPLACED or DISCARDED.
  - `FeedbackEvent` is a raw listening fact with a derived, capped `played_fraction`.
  - The read models are `SessionState` and `SessionHistory`.
- `SessionService` (`src/intentune/application/sessions.py`):
  - **Lifecycle:** start (ending the listener's previous active session), end, and `end_sessions_from_previous_run()` for D35 (end left-over sessions, discard their queues, keep history).
  - **Steering and playback:** apply a turn, queue recommendations (algorithm `Recommendation`s become persisted occurrences), play, and advance.
  - **Reads:** session state, the session list, and full history.
- Ports `ListeningSessionRepository`, `SessionTurnRepository`, `RecommendationOccurrenceRepository`, `FeedbackEventRepository` (`src/intentune/ports/sessions.py`), with SQLAlchemy implementations and a strict, versioned context JSON codec.
- Migration `dd7360f46b8b`: `listening_sessions`, `session_turns`, `recommendation_occurrences`, `feedback_events`.
  - **Uniqueness:** partial unique indexes allow one active session per listener, one playing occurrence per session, and unique queue positions.
  - **References:** composite foreign keys keep turns and events inside their own session.
  - **Status checks:** CHECK constraints tie every status to the columns it implies.
- 100 tests in `tests/test_session_domain.py`, `tests/test_session_repositories.py`, and `tests/test_session_service.py`. The suite is 618 passed and 1 skipped; no existing test changed, and no dependency was added.
- TD-015 records the B4 implementation decisions.

### Added — Phase B5: Recommendation Policy v1 (2026-10-20)

- `src/intentune/domain/policy.py`, pure, with randomness only from an injected generator:
  - `RecommendationPolicy`, with every constant validated and versioned as `policy-v1` (`POLICY_V1`).
  - The stages in the guide's order: eligibility, intent fit, session fit, long-term fit, combined score with renormalized weights, diversity (recent-play cooldown and penalty, repeated artist, near-duplicate), controlled exploration, and the top three with #2 able to play first.
  - The reusable `candidate_similarity()`.
  - `candidate_from_track()` and `signals_from_session()`: Not for me excludes the track and counts −1.0; More like this counts +1.0. A pending listener control is one with no queue surfaced and no refinement after it.
  - Automatic exploration at about 10%, moved only by how recent exploration picks went, and only within an explicitly requested genre.
  - Listener controls as deterministic one-refresh directives, part of current intent (from the B5 review):
    - Surprise me takes the last slot, within the genre first.
    - Try something different makes a track outside the genre the next to play.
    - More familiar suppresses exploration for that refresh.
    - A refinement before the refresh supersedes the control.
  - With the genre set aside, a track nothing can be compared with gets no score. It qualifies only by an explicit fallback rule (a known genre, playable, not refused). A pick with no meaningful score is surfaced without one.
- `RecommendationService` (`src/intentune/application/recommendations.py`): `refresh_queue(session_id)` surfaces Policy v1's decision through `SessionService.queue_recommendations()`, and `decide(session_id)` returns it without writing.
- `RecommendationOccurrence.is_exploration` and `queue_recommendations(..., exploration_track_ids)`.
- `RecommendationOccurrence.surfaced_position` (from the B5 review): where the occurrence was surfaced in its queue. It is written once, never changed, and kept after the occurrence leaves the queue, so an order such as rank 2 ahead of rank 1 can be reconstructed. `queue_position` stays the current queue state.
- Migration `de244c476f3a` adds `recommendation_occurrences.surfaced_position` (not null, CHECK ≥ 0, backfilled from insertion order) and `is_exploration` (not null, default 0, CHECK).
- 134 tests: 121 in `tests/test_policy.py` and `tests/test_queue_refresh.py`, and 13 added to the migration and B4 session test files. The suite is 752 passed and 1 skipped. No dependency was added.
- TD-016 records the B5 implementation decisions.

### Changed — Phase B5 (2026-10-20)

- `src/intentune/domain/scoring.py`: the per-feature rules are extracted as `category_match()` and `closeness()`, which Policy v1 reuses. `score_candidate()` output, the legacy API, and the CLI are unchanged.
- Occurrence history (`list_for_session()` without a status, and `SessionService.history()`) reads in surfaced order, by surfaced time and then surfaced position. Before, it read in rank order within each queue.
- `SessionService` gives every change within a session a strictly later time than the one before: the clock, or 1 µs past the session's last change when the clock has not moved. It moves in about 1 ms steps on this machine. Turns and surfaced queues are therefore totally ordered.
- `tests/test_session_domain.py`, `tests/test_session_repositories.py`: the occurrence helpers give a surfaced position, and the pinned occurrence columns include `surfaced_position` and `is_exploration`.

### Fixed — during B5 (2026-10-20)

- Two defects found while B5 was being built, before completion:
  - With only the hard cooldown, a four-track library alternated two tracks. It now rotates through them.
  - Plays of rejected or unavailable tracks used up the cooldown, so a just-played track could return at once.
- Found during the final corrections:
  - A turn and the refresh after it, or two quick refreshes, could share a timestamp, so whether a control had been acted on was ambiguous.
  - An unscored #2 could have played ahead of a scored #1 when #1 was by the artist that just played.

### Fixed — during B4 (2026-10-20)

- `docs/changelog.md` had a B2 limitation sentence attached to the B3 limitation, from the B3 edit.

### Fixed — during B3 (2026-10-20)

- A newer analyzer version could be permanently blocked from re-analyzing a track after an older version had marked its queued job SUPERSEDED. Found in manual verification; superseded jobs are now re-armed by their own version.
- Schema-snapshot tests compared DDL text exactly, but Alembic's batch rebuild emits a rebuilt table's constraints in a varying order. They now compare each table's clauses as a set.
- `docs/quality/testing-strategy.md` had a duplicated `### Frontend` heading from the B2 edit.

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
- `score_candidate()` requires genre, mood, energy, and danceability to be present -- missing-feature normalization for partial YouTube-style metadata is not implemented yet. *(Since B5, missing-feature scoring exists in Recommendation Policy v1, for library tracks; `score_candidate()` keeps its contract.)*
- The legacy dict shape (`load_songs()`'s output) assumes every candidate field is present; a `MusicCandidate` with a `None` audio feature would fail converting back to that shape. Not an issue for the current CSV catalog, where every field is always populated.
- The compatibility CLI path performs an extra `MusicCandidate -> legacy dict -> MusicCandidate` conversion; it calls `load_music_candidates()` directly rather than through `CsvCatalog`/`Catalog`, since the legacy dict shape predates the port and rewiring it would change nothing observable.
- The CLI (`src/main.py`) does not yet use `recommend_from_catalog()` -- it still runs the legacy `load_songs()`/`recommend_songs()` path. Wiring a catalog-backed entry point into the CLI is a future decision, not required for Phase 2.
- Found in B0 and fixed the same day as B1 prerequisites: `.gitignore` did not ignore the planned database or managed media; `DATABASE_URL` in `backend/.env.example` resolved to `backend/intentune.db`; `backend/requirements.txt` was unpinned, listed `sqlalchemy` and `httpx` without them being installed, and did not list `alembic`. Transitive dependencies are still not locked.
- The frontend runs only on mock data, has no audio playback, and is not connected to the backend.
- B1 persistence is not wired into any running entry point. Nothing applies migrations or calls `ensure_default_listener()` at startup until B8. `backend/.env` is not loaded, so a different database must be chosen through the `DATABASE_URL` environment variable.
- B2's library is not wired into any running entry point either. There is no startup scan or route until B8. Scans run synchronously; background scanning (D26) is not assigned to a phase, since B3 covered analysis only. Artwork is not extracted. A crash mid-import can leave an unreferenced managed file or a `.partial` file; neither is served, and cleanup is not built.
- B3's worker is not started by any running entry point until B8. Only exact signal measurements exist (duration, peak, RMS level); BPM, key, loudness in LUFS, and semantic features stay `NULL`. M4A tracks are never analyzed, because libsndfile cannot decode them.
- B4's session service is not called by any running entry point until B8, and nothing produces the recommendations it queues until B5. Turns are recorded but do not yet change ranking. Feedback events have a table but no recording use case (B6). *(Since B5, Policy v1 produces the queue and acts on turns.)*
- B5's Policy v1 is not called by any running entry point until B8. Turns are its only evidence until B6 adds feedback events. No long-term profile is stored until B10, so its long-term stage is unavailable. Library tracks carry tag labels only, so ranking uses genre (and mood, when tagged) and session evidence. With a genre in the intent and genre-only tags, exploration happens only on the refresh after Surprise me or Try something different. Among tracks the fallback rule admits, the choice comes down to a deterministic tie-break. "Play something from recently liked music" is not implemented.

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
