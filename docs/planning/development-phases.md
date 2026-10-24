# Development Phases

## Status

**Planned roadmap.** Reconciled with Prototype 1 in Phase B0 (2026-10-18).

The backend roadmap is now the Prototype 1 phase plan **B0–B11** from the [Prototype 1 specification](../planning/intentune-backend-prototype-implementation-spec.md) §29, executed one phase at a time under the [backend execution guide](../agents/CLAUDE_BACKEND_EXECUTION_GUIDE.md). The frontend has its own phase plan, **F0–F9**, in [frontend implementation phases](../frontend/IMPLEMENTATION_PHASES.md).

The original roadmap (Phases 0–10) is kept below as history. Phases 0–2 are complete. The rest are superseded by B-phases or deferred to Future, as marked.

## Prototype 1 Backend Phases

Each phase ends with the full test suite, documentation updates, a report, and a stop for review. No phase starts without explicit authorization.

| Phase | Scope | Status |
|---|---|---|
| **B0** Reconcile/freeze baseline | Inspect the repository and frontend, run tests, record the baseline, reconcile documentation. No feature code. | **Complete and reviewed** (2026-10-18). Baseline: 131 backend tests pass. |
| **B1** SQLite persistence foundation | SQLAlchemy, SQLite, Alembic, local listener, repositories, migration tests | **Complete and committed** (2026-10-19, `f000bb2`). 228 backend tests pass (131 baseline + 97 from B1, including the hardening pass). |
| **B2** Local library + managed media | Sources, safe copy, SHA-256 dedupe, tags, progressive status, scanning | **Complete and committed** (2026-10-19, `079c6f4`). 404 backend tests pass and 1 is skipped (405 collected; B2 adds 177). |
| **B3** Background analysis | Persisted jobs, in-process worker, audio analysis, recovery, provenance/versioning | **Complete and committed** (2026-10-20, `e2991cb`). 518 backend tests pass and 1 is skipped (519 collected; B3 adds 114). |
| **B4** Session domain | `ListeningSession`, `SessionTurn`, `RecommendationOccurrence`, `FeedbackEvent`, repositories | **Complete and committed** (2026-10-20, `d4060af`). 618 backend tests pass and 1 is skipped (619 collected; B4 adds 100). |
| **B5** Recommendation Policy v1 | Intent/session/long-term scores, missing features, similarity, diversity, exploration, rolling top 3, legacy preservation | **Complete and committed** (2026-10-20, `8a1be05`), including the review decisions and the final policy corrections. 752 backend tests pass and 1 is skipped (753 collected; B5 adds 134). |
| **B6** Feedback/playback events | Like, Save, Replay, Skip, Complete, Not-for-me; raw event persistence; immediate re-ranking | **Complete and committed** (2026-10-20; review fixes 2026-10-21; committed with B7 as `116276b`). 830 backend tests pass and 1 is skipped (831 collected; B6 adds 78). |
| **B7** Playlists | CRUD, add/remove/reorder, persistence | **Complete and committed** (2026-10-21, `116276b`, together with B6). 905 backend tests pass and 1 is skipped (906 collected; B7 adds 75). |
| **B8** FastAPI | Library/session/feedback/playlist/audio routes, errors, request IDs, API tests | **Complete and committed** (2026-10-21, `ac23287`), on top of `116276b`. 1075 backend tests pass and 1 is skipped (1076 collected; B8 adds 170). |
| **B9** Frontend integration | Inspect the actual F8 service boundary; add an HTTP adapter without rewriting frontend state architecture | **Complete, reviewed, and committed** (2026-10-22, `886cf66`), on top of `ac23287`, with its review corrections. Corresponds to frontend phase F9. 1270 backend tests pass and 1 is skipped; 276 frontend tests pass. GitHub Actions CI passed. |
| **B10** Conservative long-term adaptation | 4 strong signals / 2 sessions gate, bounded changes, audit trail, reversibility | **Complete, reviewed, and committed** (2026-10-23, `a5e0525`), on top of `886cf66`, with its review corrections. 1343 backend tests pass and 1 is skipped (B10 adds 73); 276 frontend tests pass (no frontend change). |
| **B11** Evaluation/hardening | Performance with hundreds to thousands of tracks, restart behavior, migrations, algorithm evaluation | **Complete, awaiting review** (2026-10-23; review corrections 2026-10-24), on top of `a5e0525`. 1374 backend tests pass and 1 is skipped (B11 adds 31); 276 frontend tests pass (no frontend source change; a dev-dependency lockfile patch). |

Acceptance criteria for each phase are in the execution guide §4–§14. Prototype 1 is done when every item in spec §30 holds.

### B0 record (2026-10-18)

- Backend: 131 tests pass (`python -m pytest -q` from `backend/` with the venv active). CLI output matches the documented baseline.
- Frontend: F0–F8 implemented; 214 Vitest tests pass; build and lint clean.
- No feature code was changed. Documentation was reconciled to distinguish Current, Planned, Superseded, and Future behavior.
- Findings carried into B1: `.gitignore` did not cover the database or managed media; `.env.example`'s `DATABASE_URL` pointed to `backend/intentune.db` rather than `backend/data/intentune.db`; `sqlalchemy` was listed in `requirements.txt` but not installed, `alembic` was not listed, and all entries were unpinned.

Details: [current system audit](../architecture/current-system-audit.md).

### B1 prerequisites (2026-10-18)

Done before any B1 feature code:

- The three Prototype 1 documents were committed (`d493392`).
- `.gitignore` now ignores `backend/data/intentune.db*` and `backend/data/media/`.
- `backend/.env.example` now sets `DATABASE_URL=sqlite:///./data/intentune.db`.
- SQLAlchemy 2.1.5, Alembic 1.20.0, and httpx 0.28.1 were installed, and every direct dependency in `backend/requirements.txt` is pinned to its verified version. `pip check` is clean, and the backend suite still passes (131).

At that point no persistence code, migration, or database file existed.

### B1 record (2026-10-19)

On branch `prototype-1`. Acceptance (execution guide §4):

- **Clean migration works:** `alembic upgrade head` creates `listener_profiles` from an empty database. Tests cover a clean upgrade, downgrade, a round trip, a no-op re-upgrade, a single head, migrations matching the ORM records (`alembic check` agrees), and a failing migration rolling back completely.
- **Repository smoke tests work:** the listener repository and unit of work run against migrated temporary SQLite files: commit, rollback on exit or exception, isolation, the one-default rule, and restart persistence.
- **Existing suite remains green:** the 131 baseline tests pass unchanged, and no existing source module was modified.

Built: synchronous SQLAlchemy engine configuration (foreign keys on, WAL, SQLAlchemy-emitted `BEGIN` for transactional DDL); `DATABASE_URL` resolution against `backend/`, with a default of `backend/data/intentune.db`; UTC timestamp type; ORM naming convention; `ListenerProfile` domain model; `ListenerProfileRepository` and `UnitOfWork` ports with SQLAlchemy implementations; the `ensure_default_listener()` use case, which generates one default local listener; Alembic setup and the first migration. No dependency was added. Decisions: [TD-012](../decisions/technical-decisions.md#td-012-b1-sqlite-persistence-foundation). Schema: [Database Design](../design/database-design.md#current-schema-b1).

Not done in B1, by scope: nothing calls `ensure_default_listener()` or applies migrations at startup yet (B8), and `.env` is not loaded.

### B1 hardening pass (2026-10-19)

A test-only pass after the B1 architectural review. It changed `tests/test_architecture_boundaries.py` and `tests/test_migrations.py` only.

- The architecture-boundary checks scan every layer recursively, including nested subpackages. They resolve relative imports to absolute module names before checking, so `from ..persistence import db` is caught like the absolute form.
- A deliberately failing migration changes the schema, confirms the change, and raises. The tests verify that the failed migration rolls back both schema and data, and that a failed upgrade from an empty database leaves no partial schema, not even `alembic_version`. With B1's transaction handling removed, both tests fail.
- Brittle assertions were replaced. Exact table-set equality became checks against the tables the ORM declares and before/after schema snapshots. Whole reflected dictionaries became lookups of stable fields. The raw DDL text check on the partial unique index became behavior: a second default is refused on both INSERT and UPDATE, and several non-defaults are allowed.
- It found no production bug and required no production-code change.

### B2 record (2026-10-19)

On branch `prototype-1`, on top of `f000bb2`. The guide's required proofs (execution guide §5), each tested in `backend/tests/test_library_service.py` with real files, real adapters, and a migrated database:

- **Multiple sources coexist:** two registered folders feed one library, and registering the second leaves the first intact.
- **An exact duplicate is not duplicated:** the same content twice in one folder and again in another folder gives one track and one managed file, with every source file linked to it.
- **The managed copy survives deletion of the original:** the managed bytes are unchanged, the track stays IMPORTED, and the rescan records the file as MISSING.
- **Unsupported formats fail safely:** a text file named `.mp3`, MP3 bytes named `.flac`, and an oversized file are recorded as UNSUPPORTED with a reason, with no track and no managed file. Non-audio files are ignored. The good file still imports, and the scan completes.
- **Rescan is incremental:** an unchanged rescan hashes, probes, and copies nothing (counted by spies). A touched file with the same content is re-hashed only, and changed content becomes a new track.

Also built and tested:
- source path normalization, with registration made idempotent;
- missing-source handling;
- retry of FAILED files;
- rejection of a file that changes mid-import, leaving no partial copy;
- tolerance of tag-read failures;
- mark-unavailable and repair;
- exclusion of managed media from scans;
- link, junction, and loop safety in the folder walker;
- CHECK constraints on every enumerated column.

`mutagen==1.48.1` was added. Decisions: [TD-013](../decisions/technical-decisions.md#td-013-b2-managed-local-library). Schema: [Database Design](../design/database-design.md#current-schema-b2). Workflow: [System Workflow](../architecture/system-workflow.md#library-import-and-scanning-b2).

Not done in B2, by scope:
- No startup scan or API route calls the library (B8).
- Scans run synchronously; "queue deeper analysis" is represented by a null `analysis_version`. *(Updated in B3: B3 built background analysis, including that queue, but not background scanning. D26's background scanning is not assigned to a phase yet.)*
- Artwork is not extracted; how it would be served is an open question.

### B3 record (2026-10-20)

On branch `prototype-1`, on top of `079c6f4`. B3 was scoped to background analysis only. The guide's required tests (execution guide §6), each in `backend/tests/test_analysis_service.py` or `test_analysis_worker.py`:

- **Ready tracks are usable during analysis.** While a job runs, the track can be read and listed, and a rescan (a write) succeeds, because no transaction is held during analysis. A READY track being re-analyzed stays READY with its earlier features.
- **A failed track does not kill the worker.** An analyzer error on one track is recorded as `ANALYZER_ERROR`, and the other tracks are analyzed. The worker thread also survives errors outside any job, such as a locked database.
- **Interrupted jobs recover.** A job left RUNNING returns to PENDING with its attempt counted, and fails as `INTERRUPTED` after 3 attempts. Manually verified with a real hard process exit.
- **Reanalysis works after an analyzer version change.** A new version queues every track, replaces features and `analysis_version`, and keeps the earlier jobs as history. Jobs queued for another version are superseded, and re-armed when their own version runs.

Also built and tested:
- idempotent queuing, enforced by a unique constraint;
- the atomic single-statement claim;
- retry of read errors, and no retry of decode errors;
- skipping formats the analyzer cannot decode (M4A);
- handling of a missing managed copy, re-queued after repair;
- no file paths in stored error messages;
- the worker's start, wake, stop, and restart.

**Measurements.** The analyzer measures decoded duration, sample peak, and RMS level. These are exact signal measurements, verified against known tones and against a whole-file computation on the same decoded samples.

**Dependencies.** `soundfile==0.14.0` was added and `numpy==2.4.6` pinned. `librosa` was evaluated in a throwaway venv and not added.

Decisions: [TD-014](../decisions/technical-decisions.md#td-014-b3-background-analysis). Schema: [Database Design](../design/database-design.md#current-schema-b3). Workflow: [System Workflow](../architecture/system-workflow.md#background-analysis-b3).

Not done in B3, by scope:
- Nothing starts the worker (B8).
- No tempo, key, loudness in LUFS, or semantic features: estimates need an evaluation set (B11).
- No background scanning; it is not assigned to a phase.
- No `IMPORT_TRACK`, `EXTRACT_TAGS`, or `RESCAN_SOURCE` job kinds.

### B4 record (2026-10-20)

On branch `prototype-1`, on top of `e2991cb`. The guide's B4 rules (execution guide §7), each tested:

- **The four concepts are introduced**, with repositories: `ListeningSession`, `SessionTurn`, `RecommendationOccurrence`, `FeedbackEvent` (`domain/session.py`, `ports/sessions.py`, `persistence/`).
- **The algorithm `Recommendation` stays separate from the surfaced `RecommendationOccurrence`.** `SessionService.queue_recommendations()` takes in-memory `Recommendation`s, including those from the existing `rank_candidates()`, and records occurrences that copy track, rank, score, and algorithm.
- **The session owns current state; history is separate.** The session row holds status and context. The current track and queue are occurrence rows (one PLAYING; QUEUED in order). Turns, occurrences, and feedback events are append-only history.
- **No raw natural-language prompt is persisted.** Turns carry a kind and structured context only. The tables have no text column, and a test pins their exact column sets.
- **App restart:** history is retained, the active queue is not resumed, and a new listening action creates a fresh session. `end_sessions_from_previous_run()` was verified with a real hard process exit, and starting a session always ends the previous active one.
- **Pure application tests before HTTP:** `tests/test_session_service.py` drives the use cases directly.

Decisions: [TD-015](../decisions/technical-decisions.md#td-015-b4-session-domain). Schema: [Database Design](../design/database-design.md#current-schema-b4). Workflow: [System Workflow](../architecture/system-workflow.md#listening-session-b4-b5).

Not done in B4, by scope:
- No recommendation production, queue refill, or three-candidate rule (B5).
- No effects of turns on ranking (B5, B6).
- No recording or interpreting of feedback events (B6; the table and repository exist).
- No mapping of typed text to turns (open question).
- No routes (B8).

### B5 record (2026-10-20)

On branch `prototype-1`, on top of `d4060af`. Policy v1 is `domain/policy.py`, and the use case is `RecommendationService.refresh_queue()` (`application/recommendations.py`). The guide's B5 rules (execution guide §8):

- **Stage order.** Eligibility, intent fit, session fit, long-term fit, combine, diversity/cooldown, exploration, then the top three. Each stage is computed and kept separately, so a pick can be explained.
- **Missing features are never invented.** A feature counts only when the target and the track both have it. Feature weights and stage weights are renormalized over what is available. A track with nothing to compare never outranks one with a score.
- **One reusable `candidate_similarity()`** over common features, used for session fit, near-duplicates, and novelty.
- **Session fit** follows spec §15 exactly: 0.85 recency, and 0.5 without evidence.
- **Diversity.** Recent-play cooldown, repeated artist, and near-duplicate penalties, plus a graded recent-play penalty so small libraries rotate.
- **Exploration.** Automatic exploration runs at about 90/10, moved by recent exploration outcomes, and stays in an explicitly requested genre. Listener controls are deterministic one-refresh directives (see the review decisions below).
- **#2 plays first** within 0.08 when it is more novel.
- **All constants** are in one versioned `RecommendationPolicy` (`policy-v1`).
- **No duplicated scoring math.** `category_match()` and `closeness()` were extracted from `score_candidate()`, and the policy reuses them. The 115 legacy and canonical tests pass unchanged, and the CLI output is unchanged. A test proves intent fit equals the legacy normalized score for every CSV song.

Acceptance scenarios, each a deterministic test (`tests/test_policy.py`, with the session path in `tests/test_queue_refresh.py`):
- no feedback;
- positive feedback (More like this);
- early skip (a −0.5 evidence weight);
- Not for me (excluded for the session, similar tracks lowered);
- current intent conflicting with history;
- missing features;
- a finite library (cooldown, rotation, a one-track library);
- exploration success and failure, and the listener controls;
- the #2 safety threshold, including the inclusive margin, no play yet, a less novel #2, a same-artist #2, and an exploration pick at #2.

Decisions from the B5 review, applied before commit ([TD-016](../decisions/technical-decisions.md#td-016-b5-recommendation-policy-v1) items 11–14):
- **Listener controls are one-refresh directives, part of current intent.**
  - Surprise me, Try something different, and More familiar each act on the next refresh only, and deterministically.
  - A refinement made before that refresh supersedes the control.
  - Without a control, exploration never leaves an explicitly requested genre.
  - Surprise me takes the last slot, looking for novelty within the genre first and setting the genre aside only when the genre offers none.
  - Try something different steps outside the genre at once and makes its track the next to play.
  - More familiar suppresses exploration for that refresh.
- **No invented scores.**
  - With the genre set aside, a track is judged on what can still be compared.
  - When nothing can be compared, it gets no score. A control may still pick it under an explicit fallback rule: a known genre, playable, not refused.
  - Any pick with no meaningful score is surfaced without a score.
- **Strictly ordered times within a session**, so "a queue was surfaced after this control" is exact even though this machine's clock moves in about 1 ms steps.
- **Every occurrence keeps an immutable surfaced position.**
  - It records where in its queue the occurrence was surfaced, so an order such as rank 2 ahead of rank 1 can be reconstructed after the queue has moved on.
  - `queue_position` stays the mutable current-queue state.

Schema: migration `de244c476f3a` adds `recommendation_occurrences.surfaced_position` (backfilled from insertion order) and `is_exploration`. It was extended in place, being uncommitted and unapplied outside tests; the committed B4 migration is unchanged. Its data tests cover two things: occurrences and the turns that reference them survive the rebuild in both directions, and older surfaced positions are recovered. Decisions: [TD-016](../decisions/technical-decisions.md#td-016-b5-recommendation-policy-v1). Schema: [Database Design](../design/database-design.md#current-schema-b5). Workflow: [System Workflow](../architecture/system-workflow.md#listening-session-b4-b5).

Also verified:
- an end-to-end run over real tagged FLAC files imported through the library;
- 63 single-rule mutations, each of which makes tests fail.

Details: [current system audit](../architecture/current-system-audit.md#b5-update-2026-10-20).

Two defects were found while B5 was being built, and both were fixed before completion:
- With only the hard cooldown, a four-track library alternated two tracks.
- Plays of rejected tracks used up the cooldown.

Observed in the first end-to-end run, and resolved by the first review decision: with a genre in the intent and libraries described by genre tags alone, exploration never fired. Same-genre tracks were not novel, and other genres were not plausible. Now, without a control, exploration still stays in the genre. Surprise me or Try something different takes the next refresh outside it, through the fallback rule, with no invented score. Verified over the real tagged files.

Not done in B5, by scope:
- Feedback events are not yet evidence; recording and Feedback Policy v1 are B6. Turns are the only evidence.
- No long-term profile is stored (B10), so the long-term stage is unavailable and its weight is renormalized away.
- Library tracks carry only tag labels (genre, mood). No numeric features are estimated (TD-014).
- No caller refreshes the queue automatically; B6 and B8 call `refresh_queue()` after meaningful changes.
- "Play something from recently liked music" (spec §20) is not implemented.
- No routes (B8).

*(B6 since added feedback events as evidence and the refresh after each one.)*

### B6 record (2026-10-20)

On branch `prototype-1`, on top of `8a1be05`. The use cases are `FeedbackService.react()` and `report_playback()` (`application/feedback.py`) over `SessionService.record_feedback()`. The interpretation is Feedback Policy v1 in `domain/policy.py`. The guide's B6 rules (execution guide §9), each tested:

- **Meaningful events only:** LIKE, SAVE, REPLAY, SKIP, COMPLETE, and NOT_FOR_ME, each one discrete event; there is no progress tick.
- **Raw facts persisted:** type, played seconds, duration, and fraction where relevant (SKIP and COMPLETE require them), with occurrence, session, and time. No interpreted weight is stored.
- **Feedback Policy v1:**
  - first 8 seconds: 0;
  - then by the fraction played: under 15% −0.50, 15–39% −0.20, 40–74% +0.10, 75–89% +0.50, 90% and up +0.80;
  - Like, Save, and Replay +1.00, Not for me −1.00.
  - The boundary tests cover 8.0 s against 8.01 s, each band edge and just below it, a capped fraction, and short tracks.
- **Explicit actions take precedence over passive duration,** per track in the session, with the latest explicit action deciding the track's evidence. The raw events stay stored per occurrence for B10 and B11.
- **Persist, then interpret, then update evidence, then re-rank:** every event is recorded, then the queue is refreshed at once.
- **Not for me** excludes the exact track for the session. A new session plays it again; nothing long-term changes.

Playback effects, from the approved frontend:
- a skip, completion, or Not for me about the playing track moves on to the prepared next track;
- Replay of a past track plays it again now as a fresh, listener-chosen occurrence.

The `NOT_FOR_ME` turn moves on too. No schema change was needed. Decisions: [TD-017](../decisions/technical-decisions.md#td-017-b6-feedback-and-playback-events). Workflow: [System Workflow](../architecture/system-workflow.md#feedback-and-immediate-adaptation-b6).

Also verified:
- an end-to-end run over real tagged FLAC files imported through the library;
- 32 single-rule mutations, each of which makes tests fail.

Details: [current system audit](../architecture/current-system-audit.md#b6-update-2026-10-20).

Found and fixed while B6 was being built: evidence was first combined per occurrence. Each re-rank surfaces upcoming tracks as new occurrences, so a Like on a queued card did not take precedence over the skip when that track later played, and one track could count twice. Evidence is now combined per track within the session.

Fixed at the B6 review, before commit:
- **`decide()` is a read-only preview.** It restores the random generator's state, so a preview never changes the next refresh (a carried-over B5 fix).
- **Not for me keeps the exact track out of automatic recommendations for the rest of the session (D18).** A later Like or Replay changes its evidence, never its exclusion. A Replay may still play it manually.

Not done in B6, by scope:
- PLAYLIST_ADD (B7).
- No routes (B8). Which events travel as playback events or reactions, and how a NEXT turn and a SKIP report combine, are B8's to decide.
- No playback position from the frontend yet (B9).
- No long-term use of feedback (B10).

### B7 record (2026-10-21)

On branch `prototype-1`, in the same working tree as the uncommitted B6. The use cases are `PlaylistService` (`application/playlists.py`) over a `PlaylistRepository` port, with the model in `domain/playlist.py`. The guide's B7 rules (execution guide §10), each tested:

- **Playlist CRUD** (create, rename, delete, list with track counts, read in order) **plus add, remove, and reorder.**
- **One entry per track per playlist,** in the domain and as the primary key of `playlist_items`. Positions run 0, 1, 2… without gaps.
- **A playlist add is strong positive feedback:** adding a recommendation from a session records PLAYLIST_ADD (+1.00) and re-ranks the queue.
- **Never auto-save:** only an explicit add puts a track in a playlist; likes, saves, completions, and refreshes never do.

Also:
- names are unique per listener, as the frontend keeps them;
- a refused add stores neither an item nor an event;
- playlists survive a restart;
- presentation (the frontend's colour tone) is not stored.

Schema: migration `ce0b59df2cd1` creates `playlists` and `playlist_items` and lets `feedback_events` accept PLAYLIST_ADD. Decisions: [TD-018](../decisions/technical-decisions.md#td-018-b7-playlists). Schema: [Database Design](../design/database-design.md#current-schema-b7). Workflow: [System Workflow](../architecture/system-workflow.md#playlists-b7).

Also verified:
- an end-to-end run over real tagged FLAC files, with a restart in a new process;
- 24 single-rule mutations, each of which makes tests fail.

Details: [current system audit](../architecture/current-system-audit.md#b7-update-2026-10-21).

Not done in B7, by scope:
- No routes (B8).
- The frontend's Save is not mapped to playlist adds yet (B9).
- No artwork, sharing, or duplicate entries.

### B8 record (2026-10-21)

On branch `prototype-1`, on top of `116276b`. The HTTP boundary is `backend/src/intentune/api/` (FastAPI 0.143.0, Starlette 1.8.0, both already pinned), run with `python -m src.intentune.api`. The guide's B8 rules (execution guide §11), each tested:

- **A thin HTTP boundary with Pydantic schemas separate from ORM and domain models.** Routes parse, call one use case, and map. An architecture test keeps persistence and adapter imports in the composition root (`api/container.py`, `api/settings.py`).
- **The spec's routes** (§24), all 22, plus `HEAD` on audio. Request and response bodies and status codes: [API Design](../design/api-design.md).
- **One error envelope with request IDs** (§26). `X-Request-ID` is on every response. Errors carry no stack traces, paths, or echoed ids, and unexpected errors are logged and answered `500 INTERNAL_ERROR`.
- **Audio by track ID, never path** (§25). Starlette's `FileResponse` range behavior was verified, so no custom range code was needed: 206 for single, open-ended, and suffix ranges; multipart for several; 416 past the end; 400 when malformed. Tests pin each behavior. A missing managed copy answers `409 TRACK_UNAVAILABLE` and marks the track.

Also:
- **Startup runs in the FastAPI lifespan:** migrate, then the local listener, then the end of a previous run's sessions (D35), then the analysis worker (D28), then the background startup scan (D25). Shutdown stops them.
- **Two thin application use cases:**
  - `ListeningService`: start or steer, then re-rank;
  - `LibraryScanCoordinator`: scans never overlap, and a second one is `409 CONFLICT`.
- **`BEGIN IMMEDIATE`** replaces the deferred `BEGIN` of B1. Concurrent read-then-write transactions failed with "database is locked"; that was reproduced, then fixed, and is now tested.
- **Strict request schemas:**
  - no unknown fields;
  - JSON numbers only, finite;
  - text length limits;
  - no text field on turns (D33).
- **Settings come from the process environment** only, plus a new optional `MEDIA_ROOT`. `backend/.env` is not loaded.

Decisions: [TD-019](../decisions/technical-decisions.md#td-019-b8-fastapi-boundary). Workflow: [System Workflow](../architecture/system-workflow.md#http-api-b8).

Also verified:
- **A real Uvicorn server, over real tagged FLAC files:**
  - import, with background analysis of 7/7 tracks;
  - range requests over TCP and with `curl`;
  - a full listening session;
  - a playlist add as feedback;
  - 96 concurrent requests (turns, reactions, playlist writes, reads, audio ranges, and rescans) with no errors;
  - a restart that ended the previous session.
- **44 single-rule mutations,** each of which makes tests fail. Four survived the first run and were killed by tightening tests.

Details: [current system audit](../architecture/current-system-audit.md#b8-update-2026-10-21).

Not done in B8, by scope:
- **Frontend:** the frontend does not call the API (B9), and its message, refine, Save, and playlist flows are not mapped yet.
- **Library:** no artwork route, no scan progress, and manual Import and Rescan answer when the scan ends.
- **Sessions:** no explanation text for recommendations (Policy v1's reasons are not stored).
- **Settings:** no `.env` loading.

Carry-forward hardening after the B8 review (2026-10-21), before B9:
- **CI:** a minimal GitHub Actions workflow (`.github/workflows/ci.yml`) runs the backend suite (Python 3.11) and the frontend's `npm ci`, test, lint, and build (Node 24) on every push and pull request. Details: [Testing Strategy](../quality/testing-strategy.md#continuous-integration).
- **Legacy database:** `.gitignore` covers the legacy `backend/intentune.db*`, and the local `.env` points at the canonical database.
- **Flaky tests:** two B8 API tests no longer assume an order for sources registered within one clock tick (one failed once).
- **Kept as they are, by decision:**
  - the B8 scan design: the startup scan stays in the background, and manual Import and Rescan stay within their request;
  - `BEGIN IMMEDIATE` with WAL.

  B11 measures contention and scan performance before either changes, unless B9 shows concrete UX evidence sooner.

### B9 record (2026-10-21)

On branch `prototype-1`, on top of `ac23287` (B8, committed by the user) and the post-review hardening (CI, the legacy database path). Corresponds to frontend phase F9. The F8 boundary was inspected first. The user then decided four product questions, and they shape everything below:
- **Input:** the hybrid input model.
- **Tune moods:** the curated moods.
- **Like:** an explicit, reversible Like (UNLIKE).
- **Explanations:** Why this fits is hidden.

The guide's B9 rules (execution guide §12), each tested:
- **The F8 boundary was extended, not rewritten.** `SessionService` gained session identity, structured requests (starters, quick-action controls, track ended, replay), the player's facts, a "not understood" answer, and calls for Like/Unlike, saves, and new playlists. The reducers, the composition policy, and the components keep their shape.
- **React state is not mirrored in Python.** The HTTP adapter keeps only the backend session each frontend session maps to and that session's last context, as the backend reported it.
- **The backend owns session identity, context, history, reactions, and playlists; the frontend owns its UI state.** The browser never sends reconstructed history.
- **No backend logic in the frontend, and no invented behavior.** React parses no language (a test enforces it). The backend interprets typed words with a small deterministic vocabulary and refuses what it cannot act on (`MESSAGE_NOT_UNDERSTOOD`), and nothing is guessed. No explanation, artwork, or playlist hint is made up.

Backend additions:
- **Interpreter:** the `IntentInterpreter` port and `DeterministicIntentInterpreter`.
- **Messages:** `MessageService`, which hands typed meanings to the same use cases as the controls.
- **Next:** `ListeningService.next()`, which records NEXT and then the player's SKIP facts, re-ranking once.
- **UNLIKE:** a raw event and its Feedback Policy v1 reading, with migration `4b1e9c7d2a6f`.
- **Vocabulary:** the library's genres, the curated moods, the energy scale, and which dimensions the library supports, served at `GET /listening/vocabulary`.
- **API:** the `message` input on turns and session starts, `playback` facts on `next`, and `unlike` reactions.

Frontend additions:
- **HTTP adapter:** the client, pure mappings, and the HTTP session service in `src/services/http/`, the default runtime, with Vite proxying `/api`. The mock runs only in Vite's `mock` mode (or with `VITE_SESSION_SERVICE=mock`).
- **Real audio:** an audio element is the playback authority (`useAudioPlayback.ts`), and the simulated clock runs only for the mock's songs.

Review corrections (2026-10-22), requested before the commit:
- **Default runtime:** the HTTP service is the default; the mock is explicit (`npm run dev:mock`, `npm run build:mock`, or `VITE_SESSION_SERVICE=mock`) and stays the test double. The browser checks build in mock mode.
- **Tune capability:** the vocabulary reports `support`. Tune marks dimensions the library has no evidence for and never sends them, and typed refinements of them are refused as `unavailable`. With today's importer a real library supports genre only.
- **Vite 8.2.4:** `npm audit` reports 0 vulnerabilities.
- **Next re-ranks once:** regression tests count the refreshes, clicked and typed, and check that one queue is surfaced through HTTP.

Capability consistency (2026-10-22), the last correction before the commit:
- **One rule:** `IntentCapability` is the single source of truth for genre, mood, and energy, asked by the vocabulary route, typed messages, and every structured start and REFINE.
- **Structured intent:** a start or refinement the library cannot act on answers `422 INTENT_UNAVAILABLE`, changing nothing. Typed intent gets the same answer.
- **Starters:** Focus, Unwind, and Move are shown unavailable on a library without mood and energy, with their reason, and send nothing; Discover stays. Tune also dims unusable mood values.
- **Past sessions:** one whose intent the library can no longer act on cannot continue, and says so.

Readiness model (2026-10-22), the final correction: today's library is judged as it is, not taken as Prototype 1's permanent capability.
- **Not ready:** with no playable tracks, nothing starts (`409 LIBRARY_NOT_READY`), and no dimension is called unsupported.
- **Per dimension:** each of the seven dimensions Policy v1 ranks by is `usable` or `no_data`, computed from the playable library, and becomes usable by itself once its data exists. No target was removed.
- **Unmapped fields:** `current_mood`, `listening_goal`, and `activity` are kept and stored, reported as not yet mapped into Policy v1.

**Before Prototype 1 is declared finished** (not B9 work, and not to be faked by inventing values):
- **Mood data:** a trusted source of mood labels (the importer reads genre tags only), so mood can be usable.
- **Measured features:** a validated pipeline for energy, danceability, tempo, valence, and acousticness (D21; B3 measures signal levels only), feeding `candidate_from_track()`, so those dimensions become usable.
- **Unmapped fields:** an approved deterministic mapping, or interpretation rule, for `current_mood`, `listening_goal`, and `activity`.
- **Importing:** a library screen, since importing is an API step today.

Decisions: [TD-020](../decisions/technical-decisions.md#td-020-b9-frontend-integration-and-hybrid-intent-input). Contract: [API Design](../design/api-design.md#typed-messages-b9). Frontend: [frontend architecture](../frontend/ARCHITECTURE.md) §5, §23.

Also verified:
- **The approved UI against the real backend:** the Vite dev server against `python -m src.intentune.api`, with 7 real FLAC files (genre tags only). A headless-Chrome walkthrough checked each step against the backend's own records. It passed 26/26 on 2026-10-21, 30/30 after the review corrections on plain `vite` with no service setting, 34/34 after the capability consistency correction, and 34/34 after the readiness model; a separate run against an empty library passed 7/7:
  - starter, real audio, a typed refinement, not understood with Tune opening (since the consistency correction: Focus, Unwind, and Move marked unavailable and sending nothing, and Discover starting the session);
  - a Tune genre refine; Energy and Mood marked unavailable, with High energy sending nothing and a typed "a bit calmer" refused with the reason;
  - Like/Unlike, a quick-action control, Next with the skip facts;
  - typed "save this" with an explicit playlist choice, and reload with the drawer;
  - a past Focused session refusing to continue, with its reason, and starting no backend session;
  - with an empty library: every starter, Discover included, unavailable for the library reason, pressing one starting nothing, and typed words answered "Library not ready";
  - no console errors.
- **Mock regression:** the frontend browser checks pass against the mock build.
- **Mutations:** 87 single-rule mutations (45 backend, 42 frontend), each of which makes tests fail. The readiness model added 15. The review corrections added three: a second refresh in Next, a refine of an unavailable dimension being sent, and unavailable options not being disabled. The consistency correction added 22, over the rule, both enforcement points, the error code, starters, Tune values, and the frontend's refusals. One first-run survivor (a starter's own click guard, also covered by planning) was a test gap, closed with component-level tests. Three survived the first run: one was a no-op mutation, rerun correctly; two were test gaps, closed with new tests (a typed reaction about the card in view, and a starter's phrase while pending).

Details: [current system audit](../architecture/current-system-audit.md#b9-update-2026-10-21).

Not done in B9, by scope:
- **Library:** no library screen (importing is an API step) and no artwork.
- **Explanations:** none (Policy v1's reasons are not stored).
- **Past sessions:** a past session's songs cannot be replayed (no route plays a specific track).
- **Features:** energy and most moods do not affect ranking until such features are measured.

### B10 record (2026-10-22)

On branch `prototype-1`, on top of `886cf66` (B9, committed, reviewed, and CI-green). Decisions: [TD-021](../decisions/technical-decisions.md#td-021-b10-conservative-long-term-adaptation).

B9 carry-forward, done first:
- The mood dimension is usable with any real mood label.
- Tune still offers only the approved five, and only those present.

What was built:
- **Long-Term Adaptation Policy v1** (`domain/adaptation.py`), pure and versioned (`adaptation-v1`):
  - strong evidence: one effective item per track per session, read by Feedback Policy v1;
  - the gate: 4 consistent strong items from 2 sessions about 2 distinct tracks;
  - genre and mood: net support per value, at most 3 kept;
  - numeric features: coherent single-polarity batches, the first setting the median, later ones moving at most 0.05 (tempo 5 BPM), each batch consumed once;
  - recomputation from raw history, with a planned adjustment per change.
- **Persistence** (migration `5d8e2b7a9c41`): the current profile, and append-only adjustments with relational evidence references to sessions, tracks, feedback events, and turns.
- **`LongTermAdaptationService`:** runs between persisting a relevant fact and the single refresh, from `FeedbackService` and from `ListeningService` (the Not for me turn, Next's SKIP).
- **`RecommendationService`:** passes the stored profile to Policy v1, which scores it in its own .15 stage only, as positive affinity. The intent stage reads current intent only. No profile means unchanged outputs.

What was verified:
- **Suites:** 1343 backend tests pass and 1 is skipped (B10 adds 73); 276 frontend tests pass, and lint, build, and `npm audit` (0) are clean, with no frontend change.
- **Mutations:** 24 single-rule mutations of the policy, wiring, carry-forward, and review corrections, each caught.
- **Manual end-to-end run:** over the real HTTP API, on a scratch database with synthetic genre-only test tracks, 14 of 14 checks passed:
  - two Likes in session 1 and a third in session 2 left the profile unchanged;
  - the fourth made exactly one adjustment, citing the four LIKE events;
  - the profile and audit trail survived a restart, with no drift;
  - a new session with no intent ranked with the long-term stage;
  - asking for Jazz outranked the Afrobeats preference;
  - numeric adaptation, shown on synthetic candidates, set and then moved energy by one bounded step.

Review corrections (2026-10-23), before the commit:
- **Long-term preference is positive affinity:** the long-term stage scores `0.5 + 0.5 × similarity`, so a mismatch is neutral, not penalized. With no intent, session evidence now beats a conflicting long-term preference, and current intent still beats both. No tie-break, and no weight change.
- **More like this is session-only:** it stays strong session evidence, but never counts toward the long-term gate.
- **Two distinct tracks:** no feature preference, categorical or numeric, is established from one song alone (`min_distinct_tracks`).

**Still required before Prototype 1 is finished** (not B10, and not faked):
- a trusted mood-label source;
- a validated feature pipeline for energy, danceability, tempo, valence, and acousticness (D21), so numeric preferences can be learned;
- a mapping for `current_mood`, `listening_goal`, and `activity`;
- a library and import screen;
- B11 evaluation of the thresholds and the long-term neutral point.

### B11 record (2026-10-23)

On branch `prototype-1`, on top of `a5e0525` (B10, reviewed and committed). Decisions: [TD-022](../decisions/technical-decisions.md#td-022-b11-evaluation-and-hardening). Results: [Evaluation Report](../quality/evaluation-report.md).

What was built:
- **Evaluation tooling** (`backend/evaluation/`, not part of the app):
  - `python -m evaluation.performance`: latency by library size (100 to 5,000 tracks) in steady state and cold; long-term adaptation by history size; import, analysis, contention, memory, restart, disk, and playlists; with budgets and repeated runs.
  - `python -m evaluation.scenarios`: spec §28's five scenarios, what an imported library can act on today, the long-term listeners, and two comparisons. The output is a stored baseline that a test checks.
  - Scratch databases and synthetic libraries only.
- **Hardening, each step from a measured cause, with outputs unchanged** (1,500 recorded Policy v1 decisions identical before and after the optimizations):
  - Policy v1's diversity step stops early, and a refresh scores alike candidates once;
  - the library and a listener's history are read as rows;
  - each command reads the library once;
  - the API reuses its last library read while no track has changed (`TrackSnapshot`, migration `5ed16a5d9ff5`);
  - adaptation reads the history in three queries and only the tracks it mentions.

What was measured, and decided:
- **Before and after:** about 4 to 7 times faster at 1,000 to 2,000 tracks. The slowest interactive command's p50 went from 268 to 65 ms at 1,000 tracks, and from 517 to 74 ms at 2,000.
- **Budgets** (set before the first measurement, not revised):
  - **1,000 tracks: not reliably met.** p95 was 106 to 225 ms across five runs, against 100 ms.
  - **5,000 tracks: around the target, not reliably met.** p95 was 256 to 350 ms, against 300 ms.
  - **Startup:** comfortably within, at 0.07 to 0.32 s.
  - **The tail** is mostly this one noisy Windows machine.
- **Kept on the evidence:**
  - `BEGIN IMMEDIATE` and WAL: no errors under the scan and worker;
  - synchronous manual scans;
  - paging after a full load, since a page is about 4 ms;
  - full raw-history retention, at about 3.4 KiB per session;
  - managed copies, one more copy of the library;
  - whole-list playlist writes, about 60 to 70 ms at 1,000 tracks;
  - the whole-history recompute, about 0.25 ms per past session;
  - B10's thresholds and the 0.5 long-term neutral point;
  - SQLite `synchronous` FULL, decided at the review: NORMAL measured faster (p50 about 44 → 33 ms, p95 about 70 → 54 ms at 1,000 tracks), but not enough to weaken commit durability for the listener's state;
  - no vector search, no new service, and no new runtime dependency.
- **Restart and migrations:** a restart keeps the library, metadata, playlists, feedback, history, and the long-term profile, and listening starts fresh. A database from the first library migration upgrades with its data, and the app serves it.

What was verified:
- **Suites:** 1374 backend tests pass and 1 is skipped (B11 adds 31). After `npm ci`, 276 frontend tests pass, lint and build are clean, and `npm audit` finds 0 vulnerabilities.
- **Mutations:** 20 single-rule mutations of the hardening and the review corrections, each caught.
- **Manual run over a real server** (`python -m src.intentune.api` on a scratch database, with the startup scan and worker on, over HTTP): **15/15**.
  - An import, start, play, and Like.
  - Changes made while it ran were each seen by the very next read: a rescan's new genre (in the vocabulary, the track list, and a start in that genre), a managed copy found missing, and the worker's status changes.
  - After a hard stop and restart: the library and its metadata were the same (except the missing copy, which the startup scan repaired, as designed); the open session had ended `app_restarted`; the Like and every session were kept; and a new session started fresh.
  - Repeated after the review corrections: 15/15 again.

Review corrections (2026-10-24), before the commit:
- **SQLite durability:** `synchronous` stays FULL, and the decision is recorded in TD-022. It does not satisfy the budgets, which stay reported as not reliably met.
- **A requested genre no longer runs out:** a correctness correction to Policy v1 under D17.
  - With an explicit genre request, the genre's own plays are held back only as long as its available tracks allow, so it keeps rotating in a large library.
  - It only releases tracks earlier; the track playing, other tracks, sessions without a genre request, and the global cooldown are unchanged.
  - 152 of the 1,500 recorded decisions change, every one where a requested track is released. One scenario baseline changed: the 60-play Jazz session's genre match, from 0.97 to 1.0.
- **`TrackSnapshot` under concurrency:** the revision is now an integer the track repository advances. A transaction that has written keeps nothing, so a rollback neither publishes nor invalidates. Publication never goes backwards, under a lock. Concurrency tests check that a read never sees a library older than a commit finished before it began.
- **Frontend dev-dependency maintenance:** `npm audit fix` (no `--force`) patched `undici` 8.12.1 → 8.12.3 in `package-lock.json` only. `undici` reaches the frontend only through the test environment (`jsdom`), not the browser build.

**Findings left unresolved** (reported, not fixed; they need richer real features or real-listener evidence):
- automatic exploration rarely fires within one genre;
- broad listeners get broad long-term preferences;
- long-term preferences never fade.

**Still required before Prototype 1 is finished** (not B11, and not faked):
- a trusted mood-label source;
- a validated feature pipeline (D21);
- a mapping for `current_mood`, `listening_goal`, and `activity`;
- a library and import screen.

## Frontend Phases

| Phase | Status |
|---|---|
| F0–F8 (readiness through API-ready service boundary) | Complete (2026-10-13 to 2026-10-15) |
| F9 FastAPI integration | Waiting for an approved, implemented backend contract; carried out with B9 |

---

## Original Roadmap (historical)

The phases below were planned before Prototype 1. Their status notes record what happened to each.

## Phase 0: Preserve and Audit the Baseline

**Status:** Complete.

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

**Status:** Complete. Reconciled with Prototype 1 in B0.

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

**Status:** Complete. The current four-feature baseline milestone, the formal
catalog port, and catalog-backed application orchestration are all
implemented and verified.

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

### Progress So Far (Current)

- Unified typed models introduced in `src/intentune/domain/models.py` (`MusicCandidate`, `UserProfile`, `ListeningContext`, `FeatureWeights`, `ScoreComponent`, `ScoreBreakdown`, `Recommendation`).
- Hard-coded `preferred_danceability` bug fixed in the legacy `Recommender` wrapper.
- Pure scoring module (`src/intentune/domain/scoring.py`) and pure ranking module (`src/intentune/domain/ranking.py`) added, implementing the current four-feature rule and tie-breaking as the single source of truth.
- CSV adapter added (`src/intentune/adapters/csv_catalog.py`), converting raw CSV rows into `MusicCandidate`; `load_songs()` now delegates to it instead of parsing CSV itself.
- A first application-service orchestrator added (`src/intentune/application/recommendation_service.py`, `recommend_music()`).
- `src/recommender.py`'s legacy `score_song()`/`recommend_songs()` now convert to canonical models and delegate to the canonical scorer/ranker, rather than containing a second copy of the scoring math; the now-dead `_calculate_similarity_points()`/`_validate_numeric_preference()` helpers were removed.
- Regression tests confirmed: 119 tests passed before this phase's catalog-port work; 131 tests pass now. CLI output matches the documented baseline; legacy and canonical outputs are behaviorally equivalent across the full 20-song catalog, not only the top five.
- Completion criteria for the current four-feature scoring path are met: the domain layer is independent of FastAPI/Streamlit/AI/YouTube/databases, and current and new tests pass. `score_candidate()` already matches a candidate's genre/mood against *any* of a profile's `preferred_genres`/`preferred_moods` (still an exact, case-insensitive match, not partial similarity) -- the legacy dict converter simply never supplies more than one of each, since the legacy dict profile only ever carries a single favorite genre and mood.
- A formal catalog port is implemented: `src/intentune/ports/catalog.py` defines `Catalog`, a `Protocol` with a single `list_candidates() -> Sequence[MusicCandidate]` method. `src/intentune/adapters/csv_catalog.py` adds `CsvCatalog`, a thin class binding a CSV path to `list_candidates()` around the existing `load_music_candidates()` loader. `src/intentune/application/recommendation_service.py` adds `recommend_from_catalog(catalog, profile, limit)`, which depends on the `Catalog` port rather than the concrete CSV adapter and is tested with an in-memory fake catalog. `recommend_music(candidates, profile, limit)` is unchanged.
- Deferred to Phase 3: configurable weights, partial similarity, missing-feature handling, and diversity re-ranking.

## Phase 3: Recommendation Logic Improvements

**Status:** Superseded by B5 (Recommendation Policy v1). Missing-feature handling, diversity re-ranking, and context-aware targets move into B5 with the rules fixed by the specification. The other increments (partial genre/mood similarity, match levels, configurable per-feature weights, context presets) are not part of Prototype 1 unless a B-phase needs them.

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

### Future Milestone: Expanded and Configurable Scoring Engine

**Status:** Superseded by B5. The draft weighting below was never implemented or tuned. B5's missing-feature rule (spec §14) keeps the same principle: no invented target, omit a missing feature, renormalize the active weights.

The current scoring algorithm (genre 3 pts, mood 3 pts, energy up to 2 pts, danceability up to 2 pts, 10-point maximum, sharp similarity cutoff at a 0.5 difference) is preserved unchanged through this phase. A later milestone must extend it to also weigh tempo, valence, and acousticness. A draft default weighting has been proposed for evaluation (not yet implemented or tuned):

```text
Genre             3.0
Mood              3.0
Energy            1.5
Danceability      1.0
Tempo             0.5
Valence           0.5
Acousticness      0.5
Maximum          10.0
```

These numbers require evaluation using real recommendation profiles, comparison experiments, and user feedback before adoption. This milestone should also implement: configurable feature weights (using `FeatureWeights`), partial genre/mood matching, energy/danceability/tempo/valence/acousticness similarity, missing-feature handling (see below), score normalization, confidence calculation, ranking evaluation, and comparison across multiple user profiles.

**Missing-feature handling principle (for this future milestone):**

```text
User explicitly specifies a preference -> include the feature when candidate data is available
User does not specify a preference -> do not invent a target value
Candidate does not contain the feature -> exclude the feature from the active score
Fewer useful features are available -> normalize by the total active weight and lower confidence
```

For example, if only genre (3.0), mood (3.0), and energy (1.5) are active, the total active weight is 7.5, and a normalized score may be `earned active points / total active weight`. `FeatureWeights.total_active_weight` already supports this calculation; the normalization itself is not implemented yet.

### Future Milestone: Context-Aware and User-Configurable Weighting

**Status:** Partly absorbed by B5, the rest Future. B5 builds effective *targets* from system policy, the long-term profile, and the current `ListeningContext`, with current explicit intent winning (spec §14). Context presets and user-editable per-feature weights are not in Prototype 1. The five evaluation scenarios in spec §28 (study/calm, workout/high energy, party/dance, relax, discovery) are test scenarios, not presets.

Feature importance must eventually vary by both long-term user taste (`UserProfile`) and moment-specific need (`ListeningContext`), producing session-specific `FeatureWeights`:

```text
default system weights
+ long-term user preferences
+ current listening context
+ explicit user overrides
= session-specific feature weights
```

Examples of how weighting should shift by context: workouts favor tempo and energy; study favors mood, moderate energy, acousticness, and low danceability; parties favor danceability, tempo, and energy; sleep favors low energy, low tempo, and acousticness; discovery may intentionally reduce genre weight to increase variety. Future context presets (study, workout, relax, party, sleep, commute, focus, mood improvement, discovery) must provide editable defaults, not rigid rules, and users must be able to override any feature weight. None of this is implemented yet -- `FeatureWeights`, `UserProfile`, and `ListeningContext` are modeled so it can be added later without a domain redesign.

## Phase 4: Backend API

**Status:** Superseded by B8. The API is session-based, not a profile-only recommendation route (see [API Design](../design/api-design.md)).

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

**Status:** Superseded by frontend phases F0–F9. A conversational listening-session UI was built instead of a preference form (F0–F8 complete; F9 integration pending, with B9).

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

**Status:** Superseded by B1 (persistence), B4 (session history), and B6 (feedback events). SQLite is chosen (D22).

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

**Status:** Superseded by B10, which fixes the gate at 4 consistent strong signals across 2 sessions (D06). Session-level adaptation happens earlier, in B5/B6.

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

**Status:** Future. Deferred beyond Prototype 1 (D30, D39). Prototype 1 has limited deterministic commands only.

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

**Status:** Future. Deferred beyond Prototype 1 (D39).

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

**Status:** Future for hosted deployment (Prototype 1 is local and personal, D37). Local performance and restart hardening are part of B11.

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
