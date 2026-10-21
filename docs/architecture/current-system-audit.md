# Current System Audit

## Status

**Current.** Last full audit: Phase B0, 2026-10-18, on branch `develop` at commit `c24f518`, with a clean working tree apart from the three untracked Prototype 1 documents. Those documents were committed afterwards (`d493392`), and the B1 prerequisites (ignore rules, database path, pinned dependencies) were applied the same day. Phase B1 (SQLite persistence foundation) was implemented on 2026-10-19 on branch `prototype-1`, on top of `ea6a08a`, and committed as `f000bb2`. Phase B2 (managed local library) was implemented the same day on top of `f000bb2` and committed as `079c6f4`. Phase B3 (background analysis) was implemented on 2026-10-20 on top of `079c6f4` and committed as `e2991cb`. Phase B4 (session domain) was implemented the same day on top of `e2991cb` and committed as `d4060af`. Phase B5 (Recommendation Policy v1) was implemented the same day on top of `d4060af` and committed as `8a1be05`. Phase B6 (feedback and playback events) was implemented the same day on top of `8a1be05`, with review fixes on 2026-10-21. Phase B7 (playlists) followed on 2026-10-21 in the same working tree; B6 and B7 are both uncommitted. The [B1](#b1-update-2026-10-19), [B2](#b2-update-2026-10-19), [B3](#b3-update-2026-10-20), [B4](#b4-update-2026-10-20), [B5](#b5-update-2026-10-20), [B6](#b6-update-2026-10-20), and [B7](#b7-update-2026-10-21) updates, Current Files, Dependencies, Configuration, Missing Product Capabilities, and gap analysis sections below reflect all seven.

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

## B3 Update (2026-10-20)

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest -q`, from `backend/` | **518 passed, 1 skipped** (519 collected): 405 from B0–B2, plus 114 from B3. The skip is the same symbolic-link test as in B2. |
| Migration | `alembic upgrade head`, then `alembic check`; downgrade to `2540be2956b8` and back | The `tracks` rebuild keeps all five CHECK constraints, the primary key, and the unique hash, with only `status` widened. No drift. The round trip is clean. |
| Dependency check | A throwaway venv (Python 3.11.9): install `soundfile`; dry-run `librosa` | `soundfile` 0.14.0 adds `cffi` and `pycparser`, bundles libsndfile 1.2.2, and decodes WAV, FLAC, Ogg Vorbis, Opus, and MP3 (not M4A). `librosa` 0.11.0 would add 20 packages, including `numba`, `llvmlite`, `scipy`, `scikit-learn`, `pooch`, and `requests`. Not needed for B3's measurements, so not added. |
| End to end | A scratch script with a scratch database, music, and media: real tones in five formats, the real worker thread and analyzer | All five tracks READY. Lossless WAV and FLAC: peak 0.5000 and RMS 0.3536 for a 0.5-amplitude tone, as expected. Lossy formats differ slightly, as decoded. |
| Real crash | A second process claims a job, then exits hard with `os._exit` (no cleanup) | The job was left RUNNING; a fresh worker in a new process recovered it, and it completed on attempt 2. An accidental second crash of the scratch script (worker thread mid-job) was recovered too. |
| Reanalysis | An analyzer version bump on the same database | Every track re-queued and re-analyzed; tracks stayed READY throughout; the v1 job history was kept. |
| Mutation checks | Disabled in turn: attempt counting, queue idempotency, recovery, superseding, the worker loop's error guard | Each disabled mechanism makes its tests fail. |

B3 tests per file: `test_analysis_domain.py` 45, `test_analysis_repositories.py` 23, `test_analysis_service.py` 19, `test_signal_levels.py` 14, `test_analysis_worker.py` 10. `test_library_repositories.py` gained 2 (its track-status test now covers four states), and `test_migrations.py` gained 1.

Found and fixed during B3:
- **Reanalysis could be blocked for good.** An older analyzer that processed a newer version's queued job marked it SKIPPED / SUPERSEDED, and the newer version could then never queue it again. Found in manual verification. Superseded jobs are now re-armed by their own version, with a regression test.
- **Constraint order after a table rebuild.** Alembic's batch rebuild emits a rebuilt table's constraints in a varying order, because it copies them from an unordered set. The B1 schema-snapshot tests compared DDL text exactly; they now compare each table's clauses as a set and stay exact about each definition.
- **Two test expectations were wrong.** A lossy-format test assumed the decoded peak stays near the source amplitude; Opus overshoots this tone's abrupt start to about 0.67. The test now checks block-by-block results against a whole-file computation on the same decoded samples. A B2 test used `READY` as its example of an undefined status, and it is now defined.

## B4 Update (2026-10-20)

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest -q`, from `backend/` | **618 passed, 1 skipped** (619 collected): 519 from B0–B3, plus 100 from B4. The skip is the same symbolic-link test as before. |
| Migration | `alembic upgrade head`, then `alembic check`; downgrade to `7a42f0b9c8bf` and back | Four session tables created; no drift; round trip clean |
| Across a restart | A scratch script in two processes: start a session over real imported tracks, queue, play, refine, NEXT, NOT_FOR_ME, then `os._exit` mid-session; a second process applies the restart rule | The session ended `APP_RESTARTED`, with no queue or playing track resumed. All four turns, with their contexts, and every occurrence (PLAYED, PLAYED, DISCARDED) were kept. A fresh session started. Raw rows show only a turn kind and structured, format-versioned context JSON. |
| Mutation checks | Disabled in turn: restart cleanup, ending the previous session on start, replacing the old queue, discarding the queue on end, NEXT advancing, the context codec keeping every field | Each disabled rule makes its tests fail |

B4 tests per file: `test_session_domain.py` 47, `test_session_repositories.py` 27, `test_session_service.py` 26. No dependency was added, and no existing test changed.

## B5 Update (2026-10-20)

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest -q`, from `backend/` | **752 passed, 1 skipped** (753 collected): 619 from B0–B4, plus 134 from B5, including the review decisions and the final policy corrections. The skip is the same symbolic-link test as before. |
| Clock resolution | 200 ms of `datetime.now(timezone.utc)` readings on this machine (Windows, Python 3.11.9) | 187,511 readings, only 214 distinct: the clock moves in steps of about 1 ms. A turn and the refresh after it can read the same time, which is why `SessionService` now orders a session's changes strictly (TD-016 item 13). |
| Legacy behavior | the 115 legacy and canonical tests; `python -m src.main` | Pass unchanged; the CLI prints the documented top five (Sunrise City 9.94, Rooftop Lights 6.88, Gym Hero 6.58, ...) |
| Migration | `alembic upgrade head`, then `alembic check`; downgrade to `dd7360f46b8b` and back, with data | `surfaced_position` and `is_exploration` added, each with its CHECK. The rebuilt table keeps all nine CHECK constraints, the composite unique, both foreign keys, and every index. No drift. Occurrences and the turns about them survive both directions. Pre-B5 rows read `is_exploration = 0`, and their surfaced positions are recovered from insertion order, across sessions and queues, including rank 2 surfaced ahead of rank 1. |
| End to end | A scratch script with a scratch database: 9 real FLAC tones (8 tagged with title, artist, genre; 1 untagged) imported through `LibraryService`, then sessions driven through `SessionService` and `RecommendationService` | Ambient intent queued three ambient tracks by different artists (intent 1.00, session 0.50, combined 0.824). After Not for me, the rejected track was gone and ambient tracks fell to session 0.00 (combined 0.647). A refinement to rock re-ranked at once, with the repeated artist held back a place. More like this gave rock tracks session fit 0.77, as the formula predicts. Twelve further plays kept the 5-play cooldown of an 8-track pool, and the untagged track came last. Raw rows hold `policy-v1`, rank, combined score, `surfaced_position` (on every row), and `is_exploration`. Exploration picks of rank 5 and 6 still read as surfaced at position 2 after they were replaced. |
| Listener controls over real tags | Same script: an ambient session refreshed after each step, with a draw that never explores automatically | **First run** (before the review): with a genre in the intent, nothing was ever explored. Every same-genre track was identical by genre (not novel), and every other genre had intent fit 0 (not plausible). **Final:** each control acted on exactly one refresh, deterministically. No control: three ambient tracks. Surprise me: a rock track at #3, stored as `is_exploration = 1` with no score. The following refresh: ambient again. Try something different: the rock track first (stored rank 6 at surfaced position 0), then ambient. The following refresh: ambient again. Try something different then a refinement: superseded, ambient only. More familiar: no exploration, even with a draw that always explores. In the rock session, where ambient had been rejected, Try something different found nothing that qualified, so it changed nothing. |
| Mutation checks | 63 single-rule mutations: the policy (weights, recency, the session-fit formula, renormalization, eligibility, the cooldown and its shrinking, each penalty, automatic exploration and its rate, each control as a one-refresh directive, setting the genre aside, the fallback rule, unscored picks, the #2 gates, signal extraction), strictly ordered session times, the queue write, the repository (exploration mark, surfaced position, history order), the domain validation, and the migration backfill | All 63 make tests fail. Earlier runs left three alive (an unscored exploration candidate, a promoted exploration pick, and the plausibility floor with the genre set aside), and tests were added for each. |

B5 tests per file:
- `test_policy.py` 96;
- `test_queue_refresh.py` 25;
- `test_migrations.py` gained 2;
- `test_session_domain.py` gained 4;
- `test_session_repositories.py` gained 5;
- `test_session_service.py` gained 2.

Existing tests changed: the two occurrence helpers in `test_session_domain.py` and `test_session_repositories.py` now give a surfaced position, and `test_session_repositories.py` pins the occurrence columns, now including both new columns. No dependency was added.

Found and fixed during B5:
- **A small library alternated two tracks.** The cooldown shrinks so that a small library keeps a full queue. On its own, that left a four-track library playing a1, a2, a1, a2. Found by an integration test. A graded recent-play penalty (spec §19, "same track recently played") now makes it rotate.
- **Exploration never fired over genre-only tags with a genre in the intent.** Found in the end-to-end run. Resolved by the review decisions: controls are deterministic one-refresh directives, part of current intent, with an explicit fallback rule and no invented scores (TD-016 items 11 and 14).
- **Turns and surfaced queues could tie in time.** At the clock's 1 ms resolution, a control turn and the refresh right after it, or two quick refreshes, could share a timestamp. That made "acted on since" ambiguous and could interleave two queues in history. Found while designing the one-refresh rule. `SessionService` now gives every change in a session a strictly later time (TD-016 item 13).
- **An unscored #2 could have played ahead of a scored #1.** That could happen when #1 was by the artist that just played. Found while reviewing the #2 gate; it is now refused, with a test.
- **Rejected tracks used up the cooldown.** Plays of tracks no longer eligible (rejected, unavailable) counted toward the cooldown window, so a just-played track could come straight back. Only plays of eligible tracks count now. Found while reviewing the code for the mutation checks; a test was added.

## B6 Update (2026-10-20)

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest -q`, from `backend/` | **830 passed, 1 skipped** (831 collected): 753 from B0–B5, plus 78 from B6, including the two review fixes. The skip is the same symbolic-link test as before. |
| Legacy behavior | `python -m src.main` | Unchanged top five (Sunrise City 9.94, ...) |
| Schema | `alembic upgrade head`, then `alembic check` | No migration in B6; the B4 `feedback_events` table already holds every raw fact. No drift. |
| End to end | A scratch script with a scratch database: 8 real FLAC tones tagged with title, artist, and genre (ambient, rock, jazz), imported through `LibraryService`; one session listened through with `FeedbackService`; a draw that never explores automatically | See the steps below. |
| Mutation checks | 32 single-rule mutations of Feedback Policy v1, precedence, evidence from history, the D18 exclusion, playback effects, the use case, and the read-only preview | All 32 make tests fail |

End-to-end steps, in order:
1. A skip at 4 s of 210 was within the grace period: the next track played and nothing was counted.
2. A skip at 20 s of 200 (10%) counted −0.50, and rock tracks fell (combined 0.647).
3. A Like on a queued ambient track counted +1.00, and the queue re-ranked at once.
4. A completed track counted +0.80.
5. A Like, then a skip at 7.5% of the same track: the Like decided (+1.00).
6. Not for me on the playing track moved on to the prepared next track. The track never returned in six further plays, and a new session had no exclusions and no evidence.
7. Replay of an earlier track started it again as a `listener-replay` occurrence with rank 1 and no score.
8. The raw rows hold only event type, seconds, duration, and capped fraction. Read again with a 25-second grace period, the same history dropped the 20-second skip from the evidence.

B6 tests per file:
- `test_feedback_policy.py` 51;
- `test_feedback_service.py` 24;
- `test_session_service.py` gained 2;
- `test_queue_refresh.py` gained 1 (the read-only preview).

Three existing tests changed, because Not for me about the playing track now moves on: one turn test in `test_session_service.py`, the B5 migration data test, and the signals test in `test_queue_refresh.py`. No dependency was added.

Fixed at the B6 review, before commit:
- **`decide()` advanced the random generator.** The preview drew from the service's generator, so a preview before a refresh could change what the refresh chose. It now restores the generator's state and no longer sets `last_decision`. A regression test previews and then refreshes with a seed whose first draw explores and second does not.
- **A later Like or Replay lifted the Not for me exclusion.** Evidence still follows the latest explicit action. Exclusion is now separate and sticky: once refused, a track stays out of automatic recommendations for the session (D18). A Replay may still play it manually; tests check it never comes back automatically.

Found and fixed during B6:
- **Evidence per occurrence missed precedence across a refresh.** Each re-rank surfaces upcoming tracks as new occurrences. A Like on a queued card and the skip after the track played were therefore about different occurrences: the Like did not take precedence, and the track counted twice. Found in the end-to-end run. Evidence is now combined per track within the session, with tests for both cases.

## B7 Update (2026-10-21)

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest -q`, from `backend/` | **905 passed, 1 skipped** (906 collected): 831 from B0–B6, plus 75 from B7. The skip is the same symbolic-link test as before. |
| Legacy behavior | `python -m src.main` | Unchanged top five (Sunrise City 9.94, ...) |
| Migration | `alembic upgrade head`, then `alembic check`; downgrade to `de244c476f3a` and back, with data | Both tables created with their keys, uniques, CHECKs, and foreign keys. The rebuilt `feedback_events` keeps all seven CHECKs, both foreign keys, and its index. No drift. The downgrade drops the playlist tables and only PLAYLIST_ADD events, keeping every other event exactly; the upgrade accepts PLAYLIST_ADD again. |
| End to end, across a restart | A scratch script in two processes, with a scratch database: 6 real FLAC tones tagged with title, artist, and genre, imported through `LibraryService` | See the steps below. |
| Mutation checks | 24 single-rule mutations of the playlist domain, service, repository, feedback weight, and migration | All 24 make tests fail |

End-to-end steps, in order:
1. Two playlists were created, with the name trimmed; a second "Evening" was refused.
2. Adding an upcoming rock recommendation from the session recorded PLAYLIST_ADD (+1.00), and the queue re-ranked toward rock at once.
3. Adding the playing track to the other playlist left playback alone.
4. A duplicate add was refused with no event.
5. Three plain adds were not feedback.
6. Reorder worked, an order missing tracks was refused, remove closed the gap, and rename worked.
7. A second process listed both playlists with their exact order.
8. The tables hold only the identifying columns, positions, and times, and exactly the two PLAYLIST_ADD events were stored.

B7 tests per file:
- `test_playlist_domain.py` 27;
- `test_playlist_repositories.py` 18;
- `test_playlist_service.py` 28;
- `test_migrations.py` gained 1;
- `test_feedback_policy.py` gained 1 (the PLAYLIST_ADD weight).

No existing test changed, and no dependency was added.

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

Added in B4 (2026-10-20):

- `backend/alembic/versions/20261020_dd7360f46b8b_create_listening_sessions.py`
- `backend/src/intentune/domain/session.py`
- `backend/src/intentune/ports/sessions.py`
- `backend/src/intentune/application/sessions.py` (`SessionService`)
- the three B4 test files listed above

Changed in B4: `persistence/models.py`, `persistence/repositories.py`, `persistence/unit_of_work.py`, and `ports/unit_of_work.py` (session records, repositories, and the context JSON codec).

Added in B5 (2026-10-20):

- `backend/alembic/versions/20261020_de244c476f3a_record_surfaced_position_and_exploration.py`
- `backend/src/intentune/domain/policy.py` (Recommendation Policy v1)
- `backend/src/intentune/application/recommendations.py` (`RecommendationService`)
- `backend/tests/test_policy.py`, `backend/tests/test_queue_refresh.py`

Changed in B5:
- `domain/scoring.py`: `category_match()` and `closeness()` extracted for reuse; `score_candidate()` output unchanged.
- `domain/session.py`, `application/sessions.py`, `persistence/models.py`, `persistence/repositories.py`: the occurrence's `surfaced_position` and `is_exploration`, `queue_recommendations(..., exploration_track_ids)`, and history in surfaced order.
- `application/sessions.py`: strictly increasing times for every change within a session.
- `tests/test_migrations.py`: data tests for the B5 rebuild and the surfaced-position backfill.
- `tests/test_session_domain.py`, `tests/test_session_repositories.py`, `tests/test_session_service.py`: the surfaced position (helpers, invariants, storage, order, immutability), the pinned occurrence columns, and strictly ordered times.

Added in B7 (2026-10-21):

- `backend/alembic/versions/20261021_ce0b59df2cd1_create_playlists.py`
- `backend/src/intentune/domain/playlist.py`
- `backend/src/intentune/ports/playlists.py`
- `backend/src/intentune/application/playlists.py` (`PlaylistService`)
- `backend/tests/test_playlist_domain.py`, `backend/tests/test_playlist_repositories.py`, `backend/tests/test_playlist_service.py`

Changed in B7:
- `domain/session.py`: `FeedbackEventType.PLAYLIST_ADD`.
- `domain/policy.py`: `playlist_add_weight` (+1.00).
- `application/feedback.py`: `record_playlist_add()`; `react()` refuses PLAYLIST_ADD.
- `persistence/models.py`, `persistence/repositories.py`, `persistence/unit_of_work.py`, `ports/unit_of_work.py`: playlist records and repository.
- `tests/test_migrations.py`, `tests/test_feedback_policy.py`.

Added in B6 (2026-10-20):

- `backend/src/intentune/application/feedback.py` (`FeedbackService`)
- `backend/tests/test_feedback_policy.py`, `backend/tests/test_feedback_service.py`

Changed in B6:
- `domain/policy.py`: the Feedback Policy v1 constants and `passive_weight()`, `event_weight()`, `interpret_feedback()`; `signals_from_session()` reads feedback events, per track.
- `domain/session.py`: listener replays (`LISTENER_REPLAY_ALGORITHM`, `RecommendationOccurrence.replayed()`).
- `application/sessions.py`: `record_feedback()`; a `NOT_FOR_ME` turn about the playing track moves on.
- `application/recommendations.py`: reads feedback events; exposes its policy.
- `tests/test_session_service.py`, `tests/test_migrations.py`, `tests/test_queue_refresh.py`: Not for me moving on.

Added in B3 (2026-10-20):

- `backend/alembic/versions/20261020_7a42f0b9c8bf_create_background_analysis.py`
- `backend/src/intentune/domain/analysis.py`
- `backend/src/intentune/ports/analysis.py`
- `backend/src/intentune/application/analysis.py` (`AnalysisService`) and `analysis_worker.py` (`AnalysisWorker`)
- `backend/src/intentune/adapters/signal_levels.py` (`SignalLevelAnalyzer`)
- the five B3 test files listed above

Changed in B3:
- `domain/library.py`: two track states, `available_status`, `with_analysis()`.
- `application/library.py`: a repaired analyzed track returns to READY.
- `persistence/models.py`, `persistence/repositories.py`, `persistence/unit_of_work.py`, `ports/unit_of_work.py`: analysis records and repositories.
- `tests/conftest.py`: `AudioSamples.tone()`.
- `tests/test_migrations.py`: order-insensitive snapshots and a downgrade test.
- `tests/test_library_repositories.py`: one example value.
- `tests/test_architecture_boundaries.py`: soundfile and numpy rules.
- `requirements.txt`: `numpy`, `soundfile`.

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

*(B5)* That is still true of `score_candidate()` and the CLI. Recommendation Policy v1 (`domain/policy.py`) is a separate path for library tracks in a session. It uses `ListeningContext` as current intent and `FeatureWeights` as feature importance. It skips missing features and renormalizes, comparing features with the same two primitives as `score_candidate()`.

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

**Addressed (this phase):** `load_songs()`, `score_song()`, and `recommend_songs()` are now internally wired through `MusicCandidate` (via `src/intentune/adapters/csv_catalog.py` and the boundary converters in `src/recommender.py`), and the canonical scorer (`src/intentune/domain/scoring.py`) raises a clear `ValueError` if a candidate is missing a required scoring field rather than inventing a value. A formal `Catalog` port (`src/intentune/ports/catalog.py`) now exists, and the application layer's `recommend_from_catalog()` depends on that port rather than a concrete adapter -- a future database catalog can be substituted without changing the application layer. What remains unaddressed: the scorer still *requires* genre, mood, energy, and danceability to be present -- it does not yet skip missing features and renormalize the active weight. Prototype 1 Phase B5 implements that rule (spec §14, decision D21). *(Done in B5, in Recommendation Policy v1, which ranks library tracks; the legacy scorer keeps its contract.)*

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
numpy==2.4.6           (B3: already installed through pandas; now used directly, so pinned)
soundfile==0.14.0      (added in B3)
```

`pip check` reports no broken requirements. `pytest` is used by the tests. Since B1 (2026-10-19), `sqlalchemy` and `alembic` are used by `backend/src/intentune/persistence/`, `backend/alembic/`, and the persistence tests; no domain, port, or application module imports them, and a test enforces that. No source or test file imports `pandas`, `fastapi`, `uvicorn`, or `httpx` yet. B1 added no dependency. B2 added `mutagen==1.48.1`, installed in `backend/.venv` and pinned in `backend/requirements.txt`, as the execution guide prescribes for this phase. `pip check` stays clean. Only `backend/src/intentune/adapters/mutagen_audio.py` and the tests import it.

B3 added `soundfile==0.14.0` (with its dependencies `cffi` and `pycparser`, not pinned, like other transitive dependencies) and pinned `numpy==2.4.6`. Only `backend/src/intentune/adapters/signal_levels.py` and the tests import them. `librosa` was evaluated and not added (see the B3 update).

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
- Running background analysis. The worker and analyzer exist and are tested, but nothing starts the worker until B8.
- Estimated or semantic audio features (tempo, key, loudness in LUFS, energy, mood, and so on), background scanning, or artwork
- Running listening sessions. Since B4, the session state machine and its history exist as a tested service, and since B5 Recommendation Policy v1 fills its queue (`RecommendationService`), but nothing calls either until B8.
- Running feedback. Since B6, recording and interpreting feedback exist as tested use cases (`FeedbackService`), but nothing a listener runs calls them until B8.
- Running playlists. Since B7, playlists exist as tested use cases (`PlaylistService`), but nothing a listener runs calls them until B8, and the frontend's playlists are still local.
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
| Canonical models, scoring, ranking, `Catalog` port (D38) | Yes; **B5** extracted the shared feature primitives, with legacy outputs unchanged | Preserve |
| `ListeningContext` as the source of intent (D29) | **Yes (B4, B5):** a session's stored intent, kept per session and per turn, and the current intent Policy v1 ranks by | — |
| Missing-feature scoring with renormalization (D21) | **Yes (B5)**, in Policy v1; the legacy scorer still raises on missing values, by contract | — |
| SQLite + SQLAlchemy + Alembic (D22) | **Yes (B1, 2026-10-19):** engine configuration, repository and unit-of-work pattern, migrations | Later phases add their tables and repositories |
| Local listener identity (D01) | **Yes (B1, 2026-10-19):** generated by `ensure_default_listener()`, stored in `listener_profiles` | Called at API startup from B8 |
| Managed media library, SHA-256 dedupe, scanning (D02, D03, D24, D25) | **Yes (B2, 2026-10-19):** `LibraryService`, file adapters, library tables | Startup scan and API routes in B8; background *scanning* (D26) is not assigned to a phase (B3 covered analysis only) |
| Background analysis jobs (D26, D28) | **Yes (B3, 2026-10-20):** persisted jobs, one worker thread, recovery, provenance-tagged signal measurements | Worker started at app startup in B8; estimated features need an evaluation set first |
| Sessions, turns, recommendation occurrences, feedback events (D31) | **Yes (B4, B6, 2026-10-20):** session state machine, turns, occurrences, restart rule (D35); raw feedback recorded and read through Feedback Policy v1, with immediate re-ranking | Routes in B8; PLAYLIST_ADD in B7 |
| Policy v1 staged ranking, rolling top three (D07–D09, D13–D17) | **Yes (B5, 2026-10-20):** `domain/policy.py` and `RecommendationService.refresh_queue()` | Feedback events as evidence in B6; long-term profile in B10; constants tuned in B11 |
| Playlists (D34) | **Yes (B7, 2026-10-21):** CRUD, add, remove, reorder; one entry per track; a playlist add from a recommendation is PLAYLIST_ADD feedback | Routes in B8; frontend in B9 |
| FastAPI routes, error envelope, audio serving | No (FastAPI listed but unused) | B8 |
| Frontend HTTP adapter | Service boundary only | B9 (frontend phase F9) |
| Conservative long-term adaptation (D06) | No | B10 |

## Recommendation

Preserve the current implementation as the Version 1 baseline. Refactor it incrementally behind tests rather than deleting the repository and starting from an empty project. Prototype 1 extends this baseline; it does not replace it (D38).
