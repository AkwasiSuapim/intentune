# Current System Audit

## Status

**Current.** Last full audit: Phase B0, 2026-10-18, on branch `develop` at commit `c24f518`, with a clean working tree apart from the three untracked Prototype 1 documents. Those documents were committed afterwards (`d493392`), and the B1 prerequisites (ignore rules, database path, pinned dependencies) were applied the same day. Phase B1 (SQLite persistence foundation) was implemented on 2026-10-19 on branch `prototype-1`, on top of `ea6a08a`, and committed as `f000bb2`. Phase B2 (managed local library) was implemented the same day on top of `f000bb2`. The [B1 update](#b1-update-2026-10-19), [B2 update](#b2-update-2026-10-19), Current Files, Dependencies, Configuration, Missing Product Capabilities, and gap analysis sections below reflect both.

This file describes what exists. For what Prototype 1 will add, see the [Prototype 1 specification](../planning/intentune-backend-prototype-implementation-spec.md) and the [gap analysis](#prototype-1-gap-analysis-b0) below.

## Repository Origin

The uploaded repository began as the CodePath Music Recommender Simulation starter project.

## B0 Verified Baseline (2026-10-18)

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest -q`, run from `backend/` with `backend/.venv` active (Python 3.11.9, pytest 9.1.1) | **131 passed** in about 0.5s |
| Backend CLI | `python -m src.main`, from `backend/` | Matches the documented top-five output (Sunrise City 9.94, Rooftop Lights 6.88, Gym Hero 6.58, ...) |
| Frontend tests | `npm test`, from `frontend/` (Node 24.21.0, npm 11.19.0) | **214 passed** in 9 test files |
| Frontend build | `npm run build` (`tsc -b && vite build`) | Succeeds |
| Frontend lint | `npm run lint` (oxlint) | Clean |

Backend tests per file: `test_domain_models.py` 44, `test_recommender.py` 21, `test_canonical_scoring.py` 17, `test_csv_catalog.py` 13, `test_legacy_compatibility.py` 12, `test_recommendation_service.py` 11, `test_canonical_ranking.py` 10, `test_catalog_port.py` 3.

How the backend suite must be run:

- From `backend/`. Tests import `src.…`, and there is no `pytest.ini` or `pyproject.toml`; `backend/tests/conftest.py` (added in B1) holds database fixtures only and does not change import paths. At B0, running `python -m pytest -q backend/tests` from the repository root failed during collection (8 import errors).
- With the backend virtual environment. On this machine the system Python has no pytest, so a bare `python -m pytest -q` outside the venv fails with `No module named pytest`.

The frontend browser checks (`npm run check:browser`) were not run in B0.

## B1 Update (2026-10-19)

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest -q`, from `backend/` with `backend/.venv` active | **228 passed**: the 131 baseline tests, unchanged, plus 97 from B1 |
| Baseline files alone | the eight B0 test files | **131 passed** |
| Clean migration | `alembic upgrade head`, against a new database (`DATABASE_URL` set to a scratch file) | Creates `listener_profiles` and `alembic_version`; journal mode `wal` |
| Migrations vs records | `alembic check` | "No new upgrade operations detected." |
| Default listener | `ensure_default_listener()` in two separate processes on the same database | Both return the same generated UUID; one row stored |

B1 tests per file: `test_persistence_db.py` 26, `test_listener_profile.py` 19, `test_listener_repository.py` 19, `test_architecture_boundaries.py` 15, `test_migrations.py` 14, `test_local_listener_service.py` 4.

These results include the test-only [B1 hardening pass](../planning/development-phases.md#b1-hardening-pass-2026-10-19). It added recursive architecture checks and failed-migration rollback tests, and replaced brittle assertions. It found no production bug and changed no production code.

The frontend was not touched or re-run in B1.

## B2 Update (2026-10-19)

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest -q`, from `backend/` | **404 passed, 1 skipped** (405 collected): 228 from B0 and B1, plus 177 from B2. The skip is the symbolic-link-to-file test, which needs link privileges this Windows machine does not grant; the folder-link and loop tests run here using junctions. |
| Migration | `alembic upgrade head` on a new database; downgrade to `6ef3a3452ab7` and back | Creates the four library tables; round trip clean |
| Migrations vs records | `alembic check` | "No new upgrade operations detected." |
| End to end | A scratch script, with a scratch database, music folders, and media folder: register two folders, scan, delete an original, rescan | Two tracks imported; a cross-source duplicate linked, not duplicated; a broken `.mp3` recorded as unsupported; a `.txt` ignored; tags read; after deletion the file is recorded MISSING and the managed copy remains |
| Mutation checks | Each mechanism disabled in turn: incremental skip, SHA-256 dedupe, media-folder exclusion, copy hash verification | Each disabled mechanism makes its tests fail |

B2 tests per file: `test_library_domain.py` 78, `test_library_repositories.py` 28, `test_mutagen_audio.py` 20, `test_library_service.py` 18, `test_local_folders.py` 16, `test_managed_media.py` 14. `test_architecture_boundaries.py` gained 3 (now 18).

Found and fixed during B2:
- **Junctions:** on Python 3.11, `os.walk` enters Windows junctions and `Path.is_symlink()` reports them as ordinary folders. The walker now enters a folder only if its resolved location is inside the source.
- **Flush order:** without ORM relationships, a flush could insert a child row before the parent row it references. Repositories now flush a parent row as soon as it is added.

## Current Files

### Backend

- `backend/requirements.txt`
- `backend/.env.example`
- `backend/data/songs.csv`
- `backend/src/__init__.py`
- `backend/src/main.py`
- `backend/src/recommender.py`
- `backend/src/intentune/__init__.py` and one `__init__.py` per subpackage
- `backend/src/intentune/domain/models.py`
- `backend/src/intentune/domain/scoring.py`
- `backend/src/intentune/domain/ranking.py`
- `backend/src/intentune/application/recommendation_service.py`
- `backend/src/intentune/ports/catalog.py`
- `backend/src/intentune/adapters/csv_catalog.py`
- `backend/tests/` — the eight test files listed above

Added in B1 (2026-10-19):

- `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`
- `backend/alembic/versions/20261019_6ef3a3452ab7_create_listener_profiles.py`
- `backend/src/intentune/domain/listener.py` — `ListenerProfile`, `new_default_listener_profile()`
- `backend/src/intentune/ports/listener_profiles.py`, `backend/src/intentune/ports/unit_of_work.py`
- `backend/src/intentune/application/local_listener.py` — `ensure_default_listener()`
- `backend/src/intentune/persistence/` — `db.py`, `models.py`, `repositories.py`, `unit_of_work.py`, `migrations.py`
- `backend/tests/conftest.py` and the six B1 test files listed above

Added in B2 (2026-10-19):

- `backend/alembic/versions/20261019_2540be2956b8_create_managed_library.py`
- `backend/src/intentune/domain/library.py`, `backend/src/intentune/domain/validation.py`
- `backend/src/intentune/ports/library.py`, `backend/src/intentune/ports/library_files.py`
- `backend/src/intentune/application/library.py` — `LibraryService`
- `backend/src/intentune/adapters/local_folders.py`, `managed_media.py`, `mutagen_audio.py`
- the six B2 test files listed above

Changed in B2:
- `persistence/models.py`, `persistence/repositories.py`, `persistence/unit_of_work.py`, `ports/unit_of_work.py`: library records and repositories.
- `domain/listener.py`: uses the shared validators; no behavior change.
- `tests/conftest.py`: audio-file builders and a library fixture.
- `tests/test_architecture_boundaries.py`: mutagen and filesystem rules.
- `requirements.txt`: `mutagen`.

### Frontend

`frontend/` holds a React 19 + TypeScript + Vite application built through frontend phases F0–F8: a mobile-first listening-session UI driven by a mock `SessionService`. See [Frontend State](#frontend-state) below.

### Documentation and project files

- `README.md`, `model_card.md`, `ai_interactions.md` (CodePath-era documents)
- `docs/` — this documentation set, including the Prototype 1 specification, decision register, and backend execution guide (untracked in Git at the time of the B0 audit)

The original uploaded archive also contained generated or local artifacts such as screenshots, Python caches, pytest caches, Graphify output, Git metadata, and macOS archive metadata.

## Current Data

The CSV catalog contains 20 songs and these fields:

- `id`
- `title`
- `artist`
- `genre`
- `mood`
- `energy`
- `tempo_bpm`
- `valence`
- `danceability`
- `acousticness`

The current scoring algorithm only uses genre, mood, energy, and danceability.

## Current Scoring Logic

- Exact genre match: 3 points
- Exact mood match: 3 points
- Energy similarity: up to 2 points
- Danceability similarity: up to 2 points
- Maximum score: 10 points

Energy and danceability reward closeness to the user's preferred values. A larger raw value is not automatically better. A difference of 0.5 or more earns no points.

`score_candidate()` raises `ValueError` when any of the four required profile or candidate values is missing. It does not skip missing features or renormalize. `ListeningContext` and `FeatureWeights` exist as validated models but are not used by scoring or ranking.

## Current Main Flow

1. `src.main` calls `load_songs()`.
2. A profile is defined inside `main.py`.
3. `recommend_songs()` converts the legacy profile and songs to canonical domain models.
4. `rank_candidates()` calls `score_candidate()` for every candidate and sorts by score, then title, then creator.
5. The top five recommendations and explanations are printed to the terminal.

**Updated internal wiring (Current):** `load_songs()` calls the CSV adapter (`src/intentune/adapters/csv_catalog.py`) and converts `MusicCandidate` objects back to the historical dict shape. `score_song()`/`recommend_songs()` convert their dict inputs into `MusicCandidate`/`UserProfile` and call the canonical scorer/ranker (`src/intentune/domain/scoring.py`, `src/intentune/domain/ranking.py`). The externally observable behavior in steps 1-5 is unchanged; tests compare legacy and canonical results across the full 20-song catalog, while CLI tests protect the documented top-five output.

## Frontend State

**Current (verified in B0):**

- Frontend phases F0–F8 are implemented and committed on `develop` (commits dated 2026-10-13 to 2026-10-15). Per the local Git metadata, `origin/main` includes them through the merge of pull request #1. The local `main` branch is 14 commits behind `origin/main`. The remote state was not re-fetched during B0.
- The app runs entirely on mock data. Nothing is persisted, and state resets on reload. There is no audio: playback is a timer that advances a position.
- `src/features/session/sessionService.ts` defines the `SessionService` interface: `loadWorkspace()`, `respond(context, request)`, `quickActionsAfter(reaction)`, `suggestPlaylists(context, playlists)`. `src/mocks/mockSessionService.ts` implements it with fixed phrase tables and hand-ordered song lists. `App.tsx` is the only place an implementation is chosen.
- `TurnRequest` kinds are `message` (free text, starters and quick actions all arrive as text), `refine` (mood, genre, or energy set to a discrete option id), `not_for_me`, and `next`.
- Intent is categorical: one value each for mood, genre, and energy. Energy has five levels, from `very-low` to `very-high`.
- Like, Save, Replay, and playlist creation are local state only. The service is consulted only for optional hints (quick actions after a reaction, playlist suggestions).
- There is no HTTP client, no request/response DTOs, and no API base-URL configuration. Frontend phase F9 (FastAPI integration) is waiting for an approved backend contract.

## Existing Strengths

- Working recommendation pipeline
- Simple explainable scoring
- Deterministic ranking
- Input and numerical validation
- Edge-case handling for empty results and invalid `k`
- Canonical, source-independent domain models with a formal `Catalog` port
- Test coverage that runs offline
- Human-readable README and model card
- Clear baseline for future comparison
- A tested, mock-driven frontend with a service boundary ready for an HTTP implementation

## Current Technical Concerns

### Competing Data Shapes

The file still contains both dictionaries and dataclasses -- their public shapes have not changed. The functional recommender uses dictionary profiles with `preferred_energy` and `preferred_danceability`, while the `UserProfile` dataclass uses `target_energy` and `likes_acoustic`.

**Partially addressed (Phase 2):** `src/intentune/domain/models.py` defines a single canonical, typed vocabulary (`preferred_energy`, `preferred_danceability`, etc.).

**Further addressed (this phase):** the two historical shapes are no longer *competing implementations* -- they are thin boundary conversions. `score_song()`/`recommend_songs()` convert their dict inputs into canonical `MusicCandidate`/`UserProfile`, call the single canonical scorer/ranker, and convert the result back. The dictionary and dataclass *shapes* themselves still coexist for backward compatibility (existing callers still pass/receive them), but there is now only one implementation of the scoring and ranking math.

`likes_acoustic` remains on the legacy `UserProfile` dataclass for backward compatibility only. It is now explicitly documented as deprecated and has never had any effect on scoring.

### Hard-Coded Adaptation

**Resolved (Phase 2):** The object-oriented `Recommender` previously hard-coded preferred danceability to `0.5` regardless of what the caller supplied. The legacy `UserProfile` dataclass now has a real `preferred_danceability` field (defaulting to `0.5` to preserve historical behavior for existing call sites); the wrapper reads that field instead of a literal constant, so an explicit value now actually reaches scoring. See docs/decisions/technical-decisions.md, TD-008.

### Side Effects in Data Loading

`load_songs()` prints the loaded-song count. A lower-level data-loading function should usually return data and let the caller decide what to display or log.

### CLI Coupling

The current backend interaction is terminal-only and the sample profile is hard-coded.

### Catalog Coupling

The engine assumes all candidates have CSV-style genre, mood, energy, and danceability fields. Candidates from other sources, such as locally imported tracks still being analyzed, may not have all those values.

**Addressed (this phase):** `load_songs()`, `score_song()`, and `recommend_songs()` are now internally wired through `MusicCandidate` (via `src/intentune/adapters/csv_catalog.py` and the boundary converters in `src/recommender.py`), and the canonical scorer (`src/intentune/domain/scoring.py`) raises a clear `ValueError` if a candidate is missing a required scoring field rather than inventing a value. A formal `Catalog` port (`src/intentune/ports/catalog.py`) now exists, and the application layer's `recommend_from_catalog()` depends on that port rather than a concrete adapter -- a future database catalog can be substituted without changing the application layer. What remains unaddressed: the scorer still *requires* genre, mood, energy, and danceability to be present -- it does not yet skip missing features and renormalize the active weight. Prototype 1 Phase B5 implements that rule (spec §14, decision D21).

### Compatibility Conversion Overhead

**Temporary limitation:** the CLI compatibility path converts CSV rows into
`MusicCandidate`, converts them back to historical dictionaries in
`load_songs()`, and then converts those dictionaries back to
`MusicCandidate` in `recommend_songs()`. This preserves the public CodePath
API while new canonical callers use `recommend_music()` directly. Removing
the round-trip requires a separate backward-compatibility decision.

### Dependencies

**Current (updated 2026-10-18, B1 prerequisites):** `backend/requirements.txt` pins every direct dependency to the version installed and verified in `backend/.venv`:

```text
pandas==3.0.6
pytest==9.1.1
fastapi==0.143.0
uvicorn[standard]==0.54.0
httpx==0.28.1
sqlalchemy==2.1.5
alembic==1.20.0
mutagen==1.48.1        (added in B2)
```

`pip check` reports no broken requirements. `pytest` is used by the tests. Since B1 (2026-10-19), `sqlalchemy` and `alembic` are used by `backend/src/intentune/persistence/`, `backend/alembic/`, and the persistence tests; no domain, port, or application module imports them, and a test enforces that. No source or test file imports `pandas`, `fastapi`, `uvicorn`, or `httpx` yet. B1 added no dependency. B2 added `mutagen==1.48.1`, installed in `backend/.venv` and pinned in `backend/requirements.txt`, as the execution guide prescribes for this phase. `pip check` stays clean. Only `backend/src/intentune/adapters/mutagen_audio.py` and the tests import it.

*Found in B0 and since fixed:* all entries were unpinned, `sqlalchemy` and `httpx` were listed but not installed, and `alembic` (required by D22) was not listed.

### Configuration and ignore rules

**Current (updated 2026-10-18, B1 prerequisites):**

- `backend/.env.example` declares `APP_ENV`, `API_HOST=127.0.0.1`, `API_PORT=8000`, `CORS_ORIGINS=http://localhost:5173`, and `DATABASE_URL=sqlite:///./data/intentune.db`. **Updated in B1:** `backend/src/intentune/persistence/db.py` reads `DATABASE_URL` from the process environment. It resolves a relative path against `backend/`, whatever the working directory, and defaults to `backend/data/intentune.db` when the variable is unset, the Prototype 1 layout (spec §5). The other values are still unread. No code loads `backend/.env`.
- `.gitignore` ignores `backend/data/intentune.db*` (the database plus its SQLite journal, WAL, and SHM files) and `backend/data/media/`, as spec §5 requires. `backend/data/songs.csv` stays tracked.
- A developer's existing, untracked `backend/.env` copied from the old template still points at `sqlite:///./intentune.db` (`backend/intentune.db`, which is not ignored) until it is updated by hand. B1 does not load `.env`, so this has no effect yet. It will matter once a settings loader reads `.env`.
- There is no CI workflow (`.github/` does not exist).

*Found in B0 and since fixed:* `DATABASE_URL` pointed at `backend/intentune.db`, and `.gitignore` did not cover the database or managed media.

### Missing Product Capabilities

There is currently no:

- HTTP API
- Persistence beyond the listener profile and the managed library. B1 and B2 built those tables only, and no running entry point opens the database yet.
- Running library features. The managed library (register sources, scan, import, dedupe, tags) exists as a tested application service, but nothing a listener runs calls it until B8.
- Audio analysis, background jobs, or artwork
- Listening sessions in the backend
- Feedback store
- Playlists in the backend
- Audio playback
- Authentication (none is planned for Prototype 1, D01)
- AI intent parser (deferred, D39)
- YouTube or other provider integration (deferred, D39)
- Structured logging or monitoring
- CI workflow

A browser interface does exist (see [Frontend State](#frontend-state)), but it is not connected to the backend.

## Prototype 1 Gap Analysis (B0)

What Prototype 1 can build on, and what it must add. Phase names refer to the [development phases](../planning/development-phases.md).

| Prototype 1 need | Exists today | Gap |
|---|---|---|
| Canonical models, scoring, ranking, `Catalog` port (D38) | Yes | Preserve. Extend through shared primitives in B5. |
| `ListeningContext` as the source of intent (D29) | Model only | Not used by scoring. Used from B4/B5. |
| Missing-feature scoring with renormalization (D21) | No: the scorer raises on missing values | B5, while keeping complete-input legacy outputs identical |
| SQLite + SQLAlchemy + Alembic (D22) | **Yes (B1, 2026-10-19):** engine configuration, repository and unit-of-work pattern, migrations | Later phases add their tables and repositories |
| Local listener identity (D01) | **Yes (B1, 2026-10-19):** generated by `ensure_default_listener()`, stored in `listener_profiles` | Called at API startup from B8 |
| Managed media library, SHA-256 dedupe, scanning (D02, D03, D24, D25) | **Yes (B2, 2026-10-19):** `LibraryService`, file adapters, library tables | Startup scan and API routes in B8; background scanning in B3 |
| Background analysis jobs (D26, D28) | No | B3 |
| Sessions, turns, recommendation occurrences, feedback events (D31) | No (the frontend has mock sessions only) | B4, B6 |
| Policy v1 staged ranking, rolling top three (D07–D09, D13–D17) | No | B5 |
| Playlists (D34) | No (frontend-local only) | B7 |
| FastAPI routes, error envelope, audio serving | No (FastAPI listed but unused) | B8 |
| Frontend HTTP adapter | Service boundary only | B9 (frontend phase F9) |
| Conservative long-term adaptation (D06) | No | B10 |

## Recommendation

Preserve the current implementation as the Version 1 baseline. Refactor it incrementally behind tests rather than deleting the repository and starting from an empty project. Prototype 1 extends this baseline; it does not replace it (D38).
