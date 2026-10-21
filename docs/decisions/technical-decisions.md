# Technical Decisions

## Status

**Living Document**

This file records important architectural and implementation decisions. Each decision should include its context, chosen option, alternatives, consequences, status, and date.

Prototype 1 decisions D01–D39 live in the [Prototype 1 Decision Register](intentune-prototype-decision-register.md) and are adopted by TD-011. Where an entry below conflicts with that register, the register wins; affected entries carry a dated update note rather than being rewritten.

## TD-001: Preserve the Existing Prototype

**Status:** Accepted

**Decision:** Keep the current CodePath recommender as the Version 1 baseline and refactor incrementally.

**Reason:** It already contains working scoring, ranking, explanations, tests, and documentation.

**Alternative:** Delete the project and rebuild from an empty repository.

**Consequence:** Some transitional duplication may exist while the new domain structure is introduced.

## TD-002: Use a Modular Monolith

**Status:** Accepted

**Decision:** Build one application with clearly separated internal modules.

**Reason:** The product is early, the team is small, and domain boundaries are still changing.

**Alternative:** Microservices.

**Consequence:** Deployment remains simple, but internal boundaries must be enforced through code organization and tests.

## TD-003: Develop Deterministic Logic Before AI

**Status:** Accepted

**Decision:** Improve validation, scoring, ranking, diversity, explanations, and feedback logic before adding a chatbot.

**Reason:** AI should translate user language into structured input, not hide weak backend logic.

**Consequence:** The first product increments may feel less advanced, but they will be easier to test and understand.

## TD-004: Add AI as an Adapter

**Status:** Future (deferred beyond Prototype 1). Was: Planned.

**Decision:** AI will implement an intent-parser interface and return validated structured data.

**Alternative:** Let AI control recommendation ranking and application flow directly.

**Consequence:** Intentune can change AI providers or disable AI without rewriting the core recommender.

**Update (2026-10-18, B0):** Prototype 1 uses structured `ListeningContext` plus a limited set of deterministic commands, and defers LLM parsing behind a future `IntentParser` port (D29, D30, D39). The principle stands: an LLM never chooses tracks directly.

## TD-005: Add YouTube as a Catalog Provider

**Status:** Future (deferred beyond Prototype 1). Was: Planned.

**Decision:** YouTube will provide candidates through an adapter using the official API.

**Alternative:** Scrape YouTube pages or make YouTube the recommendation engine.

**Consequence:** Intentune retains control of ranking but must handle missing music features and API quotas.

**Update (2026-10-18, B0):** Prototype 1's catalog is the listener's own music, imported into an Intentune-managed local library (D02, D03). Spotify/YouTube catalogs are deferred (D39). YouTube is no longer the first external catalog.

## TD-006: Use FastAPI for the Backend

**Status:** Accepted (not implemented yet; Phase B8)

**Reason:** The project is Python-based, the user is learning FastAPI, and typed request validation fits the architecture.

**Update (2026-10-18, B0):** confirmed by Prototype 1. `fastapi` and `uvicorn` are listed in `backend/requirements.txt` but no code uses them yet.

## TD-007: Use Streamlit for the First Browser Interface

**Status:** Superseded by TD-010

**Reason:** Fast Python delivery and current dependency availability.

**Alternative:** React or Next.js frontend.

**Revisit When:** The product requires stronger UI customization, multiple clients, or a separate frontend team.

## TD-008: Establish Canonical, Source-Independent Domain Models

**Status:** Accepted

**Decision:** Intentune's domain models must not depend on CSV formats, provider responses, HTTP frameworks, AI providers, or database schemas.

**Detail:** `src/intentune/domain/models.py` introduces typed dataclasses -- `MusicCandidate`, `UserProfile`, `ListeningContext`, `FeatureWeights`, `ScoreComponent`, `ScoreBreakdown`, `Recommendation` -- that any future FastAPI request, AI adapter, CSV loader, database repository, or YouTube adapter can produce or consume. They replace neither the existing dictionary-based functional API nor the existing dataclass-based OOP wrapper in `src/recommender.py`; both remain available with backward-compatible behavior.

**Reason:** The current implementation mixes dictionary profiles (`preferred_energy`, `preferred_danceability`) with a dataclass profile (`target_energy`, no danceability field, an inert `likes_acoustic` field). A single canonical vocabulary must exist before FastAPI, AI, YouTube, or a database can be added, otherwise each new adapter would invent its own shape.

**Alternative:** Keep extending the existing dictionaries and dataclasses ad hoc as new candidate sources are added.

**Consequence:** Three co-existing shapes exist during the transition: the historical dict API, the historical dataclass API, and the new canonical domain models. This is intentional duplication, tracked in docs/decisions/trade-offs.md, and will shrink as scoring and ranking are migrated onto the canonical models in a later phase.

**Also fixed as part of this decision:** the OOP `Recommender` wrapper no longer hard-codes `preferred_danceability` to `0.5` -- the legacy `UserProfile` dataclass gained a real `preferred_danceability` field (default `0.5`, matching the old hard-coded value exactly so existing call sites are unaffected) that the wrapper now actually reads.

## TD-009: Canonical Domain Objects Are the Internal Source of Truth

**Status:** Accepted

**Approval note:** Phase 2 explicitly approved source-independent domain
models, boundary conversion, and preservation of the legacy public
interfaces. The completed implementation also moved scoring and ranking into
canonical modules and added an application service and CSV adapter. The
owner has approved continuing with this canonical modular architecture,
including the module-boundary expansion beyond the earlier
model-only/minimal-structure scope.

**Decision:** Canonical domain objects are the internal source of truth. Storage formats, HTTP schemas, provider responses, and legacy dictionaries must be converted at system boundaries.

**Detail:** `src/intentune/domain/scoring.py` (`score_candidate`) and `src/intentune/domain/ranking.py` (`rank_candidates`) now contain the only implementation of the current four-feature scoring and ranking rules. `src/recommender.py`'s legacy `score_song()` and `recommend_songs()` convert their dict inputs into `MusicCandidate`/`UserProfile` at the top of the function, delegate to the canonical modules, and convert the result back into the historical `{"song", "score", "reasons"}` shape. `src/intentune/adapters/csv_catalog.py` is the only module that knows about CSV column names or file paths; `load_songs()` calls it and converts `MusicCandidate` objects back into the historical dict shape.

**Update (this phase):** a formal `Catalog` port (`src/intentune/ports/catalog.py`, a `Protocol` with `list_candidates()`) now sits between the application layer and any catalog implementation. `CsvCatalog` (`src/intentune/adapters/csv_catalog.py`) implements the port around the existing `load_music_candidates()` loader. `recommend_from_catalog()` (`src/intentune/application/recommendation_service.py`) depends on the `Catalog` port rather than the concrete CSV adapter, so it can be tested with an in-memory fake catalog and is ready to accept a future database or YouTube catalog without a rewrite. `recommend_music()` is unchanged and still accepts a candidate list directly.

**Reason:** TD-008 introduced the canonical models but left scoring and ranking duplicated between the legacy dict/dataclass path and the (until now, unused) canonical models. Keeping two implementations of the same scoring math in sync by hand is exactly the kind of drift the canonical models were meant to prevent.

**Alternative:** Keep the legacy dict-based scoring/ranking as the "real" implementation and let the canonical domain models remain a documentation-only vocabulary until FastAPI arrives.

**Consequence:** `src/recommender.py` no longer contains scoring math -- `_calculate_similarity_points()` and `_validate_numeric_preference()` were removed as dead code. A full-catalog regression test (`tests/test_legacy_compatibility.py`) confirms behaviorally equivalent scores, reasons, and ordering between the legacy and canonical paths for all 20 songs, not only the previously documented top five.

**Temporary limitation:** preserving `load_songs()` and `recommend_songs()`
causes an extra canonical-to-legacy-to-canonical conversion in the CLI path.
The compatibility requirement was explicitly approved; retiring that path is
a future decision.

**Revisit When:** The "Expanded and Configurable Scoring Engine" milestone (see docs/planning/development-phases.md) extends `score_candidate()` to tempo/valence/acousticness and missing-feature normalization; at that point the legacy dict API's four-field shape may need its own documented limitation notice, since it cannot express the wider feature set.

**Update (2026-10-18, B0):** that milestone is superseded by Prototype 1 Phase B5 (Recommendation Policy v1). D38 keeps this decision in force: B5 extends or refactors shared scoring primitives instead of creating a second copy of the scoring math, and must prove complete-input legacy outputs stay identical.

## TD-010: Use React, Vite, and TypeScript for the Frontend

**Status:** Accepted

**Decision:** The browser interface is a separate React application built with Vite and TypeScript in `frontend/`. It communicates with the backend only through the FastAPI HTTP API (TD-006). Streamlit is not used.

**Reason:** A separate frontend gives full control over the interface and keeps the Python backend a plain API with no UI concerns.

**Alternative:** Streamlit for the first browser interface (TD-007).

**Consequence:** The repository is split into `backend/` (Python) and `frontend/` (TypeScript). `streamlit` was removed from `backend/requirements.txt`. The browser interface cannot be built until the API exists, so the backend API phase comes first.

**Update (2026-10-18, B0):** in practice the frontend was built first, on mock data. Frontend phases F0–F8 (2026-10-13 to 2026-10-15) produced the full session UI behind a `SessionService` interface with a mock implementation. Frontend phase F9 (FastAPI integration) waits for the backend API, which corresponds to backend phases B8 and B9. The sentence above about building the API first describes the plan at the time, not what happened.

## TD-011: Adopt Prototype 1 — Local-First, Session-Aware Recommendation

**Status:** Accepted

**Date:** 2026-10-18 (recorded in Phase B0)

**Context:** Earlier planning aimed at a profile-based recommendation API, then an AI chatbot, then YouTube as the first external catalog, followed by hosted deployment. The approved direction is now different: a local-first application that imports the listener's own music, runs continuous listening sessions, and adapts within a session.

**Decision:** Adopt the [Prototype 1 Backend Implementation Specification](../planning/intentune-backend-prototype-implementation-spec.md) and the [Prototype 1 Decision Register](intentune-prototype-decision-register.md) (D01–D39) as the approved backend direction, executed in phases B0–B11 as described in the [backend execution guide](../agents/CLAUDE_BACKEND_EXECUTION_GUIDE.md).

Key consequences for earlier decisions:

| Earlier decision | Effect |
|---|---|
| TD-001 Preserve the existing prototype | Reaffirmed (D38) |
| TD-002 Modular monolith | Reaffirmed; no Redis, Celery, Kafka, or microservices in Prototype 1 |
| TD-003 Deterministic logic before AI | Reaffirmed (D29, D30, D39) |
| TD-004 AI as an adapter | Deferred to Future |
| TD-005 YouTube as a catalog provider | Deferred to Future; replaced for Prototype 1 by a managed local library |
| TD-006 FastAPI | Reaffirmed; built in B8 |
| TD-008, TD-009 Canonical domain | Reaffirmed and protected (D38) |
| TD-010 React frontend | Reaffirmed; integrated in B9 |

New technical choices introduced by the register include SQLite + SQLAlchemy + Alembic (D22), audio outside the database (D23), SHA-256 exact deduplication (D24), and a bounded in-process worker with persisted job state (D28).

**Alternatives Considered:** Continue the earlier roadmap (profile API, then AI, then YouTube); build on an external provider catalog first.

**Consequences:** Prototype 1 works without AI, external providers, accounts, or internet. It adds persistence, background work, and audio handling to a codebase that today has none. Hosted deployment, authentication, PostgreSQL, and provider integrations move to Future.

**Revisit When:** Prototype 1 meets its definition of done (spec §30), or evaluation in B11 shows a decision in the register does not hold.

## TD-012: B1 SQLite Persistence Foundation

**Status:** Accepted, awaiting B1 review

**Date:** 2026-10-19

**Context:** D22 fixes SQLite, synchronous SQLAlchemy, and Alembic, and the execution guide asks for UTC timestamps, enforced foreign keys, WAL only if verified, and one generated local listener. Several implementation details were left open, including one recorded in [risks and open questions](../planning/risks-and-open-questions.md): whether a relative database path resolves from the working directory or from the backend root.

**Decision:**

1. **Database location.** `DATABASE_URL` is read from the process environment. When it is unset, the default is `backend/data/intentune.db`. A relative SQLite path resolves against `backend/`, as the CSV adapter does, not against the working directory. Non-SQLite URLs are rejected. `backend/.env` is not loaded; that waits for a settings loader (B8) and would need a new dependency.
2. **Transactions.** SQLAlchemy emits `BEGIN` (driver `isolation_level = None` plus a `begin` event), so SQLite DDL is transactional and SAVEPOINTs behave on Python 3.11. Python 3.12's `autocommit=False` connect argument is the later alternative.
3. **Foreign keys and WAL.** Foreign keys are on for every connection. They are off during migrations, as SQLite's table-rebuild procedure requires, followed by `PRAGMA foreign_key_check` before commit. File databases use WAL, which tests verify.
4. **Identifiers and time.** UUID strings in canonical form (`String(36)`) rather than SQLAlchemy's `Uuid` type, which stores 32 hex characters without hyphens on SQLite. UTC timestamps through a `UtcDateTime` type that rejects naive datetimes.
5. **Layering.** `ListenerProfile` is a pure domain model. `ListenerProfileRepository` and `UnitOfWork` are ports. SQLAlchemy implementations live in `src/intentune/persistence/`, and ORM records never leave it.
6. **Transaction pattern.** An explicit-commit unit of work. Repositories never commit. Leaving the `with` block rolls back anything uncommitted.
7. **Default listener.** Created by the application use case `ensure_default_listener()`, not by a data migration. The database enforces at most one default with a partial unique index.
8. **Schema discipline.** A constraint naming convention from the first table, Alembic batch mode, migrations that use plain SQLAlchemy types, and a test that migrations and ORM records agree.

**Alternatives Considered:** Resolving the path from the working directory (SQLite's default; it ties correctness to where the process starts). Creating the listener inside the migration (every database would get one, but a deleted row would never come back, and tests that build schemas without migrating would lack it). A commit-on-success context manager (one less call, but a read-only or early-return path could write by accident). SQLAlchemy's `Uuid` type. Leaving the driver's legacy transaction mode (DDL would autocommit, so a failed migration could leave a half-applied schema). Async SQLAlchemy (no measured need).

**Consequences:** The database location does not depend on the working directory. A failed migration rolls back completely. Domain, port, and application code stays free of SQLAlchemy, and a test enforces that. Driver-independent `BEGIN` makes "database is locked" errors more likely under concurrent writers; WAL, short transactions, and the 5-second busy timeout mitigate this until B3 measures real contention. Nothing calls `ensure_default_listener()` or applies migrations at startup until B8. *(B3 update, 2026-10-20: the worker holds no transaction while analyzing; claim and finish are one short transaction each, and a rescan during analysis succeeds in the tests. Contention under real load was not measured; that moves to B11.)*

**Revisit When:** the backend moves to Python 3.12 or later (decision 2); B3's worker shows lock contention (decision 3); B8 introduces settings loading (decision 1); PostgreSQL is adopted (D22).

*B8 update (2026-10-21, TD-019):* decision 2 now emits `BEGIN IMMEDIATE`, because the API runs request threads, the worker, and the startup scan together, and a deferred `BEGIN` made read-then-write transactions fail with "database is locked". Decision 1 stands: B8 reads settings from the process environment and still does not load `backend/.env`.

## TD-013: B2 Managed Local Library

**Status:** Accepted, awaiting B2 review

**Date:** 2026-10-19

**Context:** D02, D03, D24, and D25 and the execution guide §5 fix the library's behavior: several source folders, managed copies, SHA-256 dedupe, an incremental rescan, and the validate → hash → dedupe → copy → persist → tag → analyze pipeline. Several implementation details were left open.

**Decision:**

1. **Formats.** The allowlist is MP3, M4A, FLAC, Ogg (Vorbis or Opus), Opus, and WAV. The extension only selects candidates; mutagen must confirm the content is that format. Files with other extensions are ignored and counted, not recorded. Allowlisted files that fail validation are recorded as UNSUPPORTED.
2. **Size limit.** 1 GiB per file by default (`LibraryPolicy`).
3. **File and track states.** Readiness is split between files and tracks. Source files are IMPORTED, UNSUPPORTED (not retried until the file changes), FAILED (retried on every scan), or MISSING. Tracks are IMPORTED or MISSING_MANAGED_FILE. DISCOVERED, ANALYZING, and READY are not written yet.
4. **Scan state.** A new table, `source_files`, holds the incremental-scan state the spec requires: size, mtime, hash, status, failure reason, and track link. Tracks store no path; the managed copy is `<track_uuid>.<extension>`.
5. **Copy safety.** The copy is written to a temporary file while hashing, flushed, and moved into place only if it matches the earlier hash.
6. **Changed content.** A source file whose content changes becomes a new track. The old track stays, because managed copies outlive their sources (D02).
7. **Repair.** A track marked MISSING_MANAGED_FILE is repaired when a source file with its content is scanned again.
8. **Tags.** Tags are read from the managed copy after the track is stored. A failure leaves the track playable. Title, artist, album, year, and declared genres are read, with genres split on `;` and stored as `track_labels` (source `embedded_tags`, no confidence). Artwork is not extracted.
9. **Folder walking.** No symbolic links are followed. A folder is entered only if its resolved location is inside the source, which also covers Windows junctions. Each folder is visited once, and managed media is excluded.
10. **Layering.** `LibraryService` uses ports only, and file I/O lives in adapters. CHECK constraints guard every enumerated column. Domain validators shared with the listener model moved to `domain/validation.py`.
11. **Analysis hand-off.** "Queue deeper analysis" is not built in B2. A null `analysis_version` marks a track as waiting; B3 creates the job queue (D28).

**Alternatives Considered:**
- Recording a row for every non-audio file (noise from covers and notes).
- Storing a managed path column (redundant, and a path to leak).
- Re-importing changed content over the old track (would rewrite a managed copy in place).
- Following symbolic links (could escape the source or loop).
- Building a placeholder analysis queue in B2 (half of B3, without its design).

**Consequences:**
- Scans are safe to repeat and cheap when nothing changed.
- One bad file never stops a scan.
- Content changed at the source leaves its previous version in the library, using disk space until a removal feature exists.
- Scans run synchronously. *(B3 built background analysis only, so background scanning (D26) is not assigned to a phase yet.)*
- Orphaned `.partial` files are possible after a crash mid-copy, and a crash between copy and commit can leave an unreferenced managed file. Neither is ever served; cleanup is not built yet.

**Revisit When:** B3 adds background jobs (decisions 3, 11); B8 decides how sources and artwork are presented (decision 8); real libraries show many content changes at the source (decision 6) or large orphan counts (decision 5).

## TD-014: B3 Background Analysis

**Status:** Accepted, awaiting B3 review

**Date:** 2026-10-20

**Context:** D19–D21, D26–D28, and the execution guide §6 ask for persisted analysis jobs, a bounded in-process worker, recovery, versioned provenance, and tracks that stay usable. Two constraints shaped the choices. "Safe initial features" are duration, tempo, levels, key, and onsets, but semantic features must come from a validated model or stay `NULL`. And `librosa` may be added "only if needed".

**Decision:**

1. **Measurements.** Analyzer revision 1 measures decoded duration, sample peak, and RMS level over every decoded sample, all exact. Levels are stored as linear fractions of full scale, because digital silence is a real level (0.0) with no finite dBFS value.
   - These are not loudness in LUFS, not "energy", and not any perceptual or semantic attribute.
   - Tempo, key, and onset estimates are not produced. They are estimates whose error depends on algorithm and genre, and Intentune has no evaluation set to measure that error yet (B11).
2. **Decoder.** `soundfile==0.14.0` (libsndfile 1.2.2), verified in a throwaway Python 3.11.9 venv on this Windows machine.
   - It decodes WAV, FLAC, Ogg Vorbis, Opus, and MP3, and adds only `cffi` and `pycparser`. `numpy` was already installed (through pandas) and is now pinned.
   - **`librosa` was not added.** A dry run showed 20 extra packages, including `numba`, `llvmlite`, `scipy`, `scikit-learn`, and network-capable `pooch` and `requests`, for capabilities B3 does not use. `scipy` (for an ITU-R BS.1770 loudness filter) was not added either.
   - libsndfile cannot decode M4A; those jobs are SKIPPED, `FORMAT_NOT_SUPPORTED`.
3. **Versioning.** The analyzer's identity is `intentune.signal-levels@1+libsndfile-1.2.2`. Lossy formats decode slightly differently across decoder builds, so a libsndfile upgrade changes the version and re-analyzes the library. `tracks.analysis_version` stores the key.
4. **Jobs.**
   - **Uniqueness:** one `analysis_jobs` row per track, kind, and analyzer key, so queuing is idempotent.
   - **Kinds:** only `ANALYZE_AUDIO`; a new version is a new job, so `REANALYZE_TRACK` is unnecessary.
   - **Claims:** a single `UPDATE … RETURNING` statement that counts the attempt.
   - **Attempts:** at most 3; interruptions count too.
5. **Queuing.** `enqueue_pending()` sweeps all tracks instead of the import queuing each one. It covers new tracks, pre-B3 tracks, repaired tracks, and version changes with one rule (`needs_analysis`), and leaves B2's import pipeline unchanged.
6. **Outcomes.**
   - Decode errors are deterministic and not retried.
   - Read errors (`OSError`) are retried.
   - A missing managed copy marks the track `MISSING_MANAGED_FILE` and is re-queued after repair.
   - A job for another analyzer version is SUPERSEDED, and re-armed when its own version runs (a fix found in manual verification).
   - Unexpected analyzer errors are logged, recorded, and isolated.
   - Stored messages never contain paths.
7. **Track states.** IMPORTED → ANALYZING → READY on first analysis. A READY track stays READY during reanalysis, with its earlier features, until the new ones replace them in the same transaction that completes the job. A failure or skip restores the previous state. A repaired analyzed track returns to READY.
8. **Worker.** `AnalysisWorker` is one daemon thread with its own unit of work, two events (stop and wake), and a 30-second idle sweep. It is not a process pool or task queue (D28). Analysis runs outside any transaction; claim and finish are each one short transaction.
9. **Layering.** The `AudioAnalyzer` port only measures. The job lifecycle lives in `AnalysisService`. soundfile and numpy stay in one adapter, enforced by the architecture test.

**Alternatives Considered:**
- `librosa` for tempo and onsets, which is heavier and estimates without an evaluation set.
- `scipy` plus a BS.1770 implementation for LUFS, a defensible standard, but not needed in B3 and a large dependency.
- PyAV or FFmpeg for M4A, a much larger dependency or an external binary.
- Storing dBFS, which has no finite value for silence.
- Queuing inside B2's import transaction, which would miss pre-B3 and repaired tracks without a sweep anyway.
- Several worker threads (SQLite has one writer; no measured need).
- Keeping only failed jobs re-armable, which blocked reanalysis after a rollback.

**Consequences:**
- Every track has exact level and duration measurements once analyzed, except M4A.
- Recommendation features in the spec (BPM, key, energy, and so on) remain `NULL`.
- The analysis library can be re-run safely at any time.
- Old jobs stay as history.
- A crash leaves at most one job RUNNING, recovered on the next start.
- Two processes with different analyzer versions would keep superseding each other's jobs; Prototype 1 runs one process.

**Revisit When:**
- An evaluation set exists (B11): estimated features as a new analyzer version.
- B8 starts the worker at startup.
- M4A becomes common in real libraries.
- Measured analysis throughput (B11) calls for more than one worker.

## TD-015: B4 Session Domain

**Status:** Accepted, awaiting B4 review

**Date:** 2026-10-20

**Context:** Spec §10 and D29–D35 fix a session model: the session owns current state while history is separate; `Recommendation` and `RecommendationOccurrence` stay distinct; no raw prompts; and no resumed queue after a restart. Left open were the storage of context and queue (an open trade-off in the database design), and how B4 divides work with B5 (ranking) and B6 (feedback).

**Decision:**

1. **Storage of context and queue.**
   - The `ListeningContext` is a JSON column (`{"format": 1, "context": {...}}`). It is read and written whole and never queried by field, and loading refuses unknown formats and fields.
   - The current track and queue are not stored on the session row. They are the session's one `PLAYING` occurrence and its `QUEUED` occurrences in position order, constrained by partial unique indexes.
2. **One active session per listener**, enforced by a partial unique index. `start_session()` first ends the previous one as `REPLACED_BY_NEW_SESSION`. Startup calls `end_sessions_from_previous_run()`, which ends sessions as `APP_RESTARTED`, discards queued occurrences, and keeps history (D35).
3. **Turns.**
   - Every turn records the context in force after it, so history shows how intent changed.
   - `REFINE` replaces the context, and `NEXT` advances the queue.
   - `NOT_FOR_ME` and `MORE_LIKE_THIS` name an occurrence, the playing one by default.
   - The exploration turns are recorded only.
   - What turns mean for ranking belongs to B5 and B6. No turn carries text.
4. **Recommendation versus occurrence.** `queue_recommendations()` takes domain `Recommendation`s and records occurrences.
   - Each occurrence copies the track id, the algorithm's rank, its normalized score, and an algorithm label.
   - Queue order is the given order, which may differ from rank order (B5's #2-first rule).
   - A new queue marks what was still queued as `REPLACED`. History is never rewritten.
5. **Feedback events.** B4 defines the raw-fact model, table, and repository, because spec §29 places `FeedbackEvent` in B4. It adds no use case to record events: the API design and the execution guide assign recording, Feedback Policy v1, and re-ranking to B6.
6. **Integrity.**
   - Composite foreign keys (`occurrence_id`, `session_id`) keep a turn's or event's occurrence inside its own session.
   - CHECK constraints tie every status to the columns it implies.
   - Occurrence writes flush immediately, so the partial unique indexes hold after every statement.
7. **No new dependency.** `ListeningContext` and `Recommendation` (protected models) are used unchanged.

**Alternatives Considered:**
- A JSON queue on the session row (the database could not enforce it).
- Context as columns plus child tables (more schema for a value that is always loaded whole).
- Storing the current occurrence id on the session (a foreign-key cycle with occurrences).
- Recording feedback in B4 (it would pre-empt B6's rules).
- Allowing several active sessions per listener (the spec has one current state).

**Consequences:**
- Every queue change and every steering action is recoverable from history.
- A crash can never resume a stale queue.
- The database rejects inconsistent sessions, cross-session references, and stored text.
- B5 must supply `Recommendation`s whose candidate ids are library track ids, and enforce the three-candidate queue.
- B6 adds event recording on top of the existing table.

**Revisit When:**
- B5 needs to query context fields in SQL.
- B9 shows the frontend needs more session state.
- Multiple listeners arrive (Future).

## TD-016: B5 Recommendation Policy v1

**Status:** Accepted, awaiting B5 review

**Date:** 2026-10-20

**Context:** Spec §12–21 and execution guide §8 fix most of Policy v1:
- the stage order;
- the .55 / .30 / .15 stage weights;
- the missing-feature rule;
- the session-fit formula with 0.85 recency;
- about 90/10 exploration;
- the 0.08 gate for playing #2 first.

They also forbid a second copy of the scoring math. Several things were left open:
- how features are compared;
- what "no meaningful score" means;
- how long the cooldown is in a small library;
- what counts as a near-duplicate or as useful novelty;
- which track exploration picks and how outcomes move the rate;
- whether a steering control may take exploration outside an explicitly requested genre, how long it lasts, and where its pick goes (settled at the B5 review);
- what counts as session evidence before B6 records feedback;
- how a surfaced order, such as #2 queued ahead of #1, stays reconstructable once the queue moves on (settled at the B5 review).

**Decision:**

1. **One versioned policy object.** `RecommendationPolicy` (`domain/policy.py`, frozen) holds every constant, validated, as `policy-v1`. The version is the `algorithm` recorded on each occurrence, so a changed constant needs a new version.
2. **Feature scoring reuses the legacy primitives.**
   - `category_match()` and `closeness()` were extracted from `score_candidate()`, whose output is unchanged.
   - A fit is a weighted average over the features where both a target and a value exist. The weights are the legacy 3/3/2/2 for genre, mood, energy, and danceability, and 1 each for tempo, valence, and acousticness. Tempo is compared on a 100 BPM scale.
   - A test proves that intent fit equals `score_candidate()`'s normalized score for every CSV song.
3. **Targets.**
   - Per feature, the current `ListeningContext` wins, and the long-term profile fills only what it leaves open.
   - Target moods are `temporary_moods`, else `desired_mood`. `current_mood` describes the listener, not the music they want, so it is not a target.
4. **Stage availability.**
   - Intent and long-term fit are unavailable when nothing can be compared, and the stage weights are renormalized.
   - Session fit is always present: neutral 0.5 without evidence.
   - A candidate whose only stage is that neutral 0.5 has "no meaningful score" (spec §13). It never outranks a scorable candidate and only fills a queue they cannot fill. It is surfaced without a score (item 14).
5. **Session evidence before B6.**
   - Evidence comes from turns: `MORE_LIKE_THIS` is +1.0, and `NOT_FOR_ME` is −1.0 and excludes the track for the session.
   - Feedback events join in B6 with Feedback Policy v1's weights. The domain already takes any weight in [−1, 1]; tests use −0.5 for an early skip.
6. **Diversity: a greedy re-rank against the last play and the picks so far.**
   - **Recent-play cooldown:** 20 plays, shrinking to `max(1, eligible − 3)` so a small library keeps a full queue. Only plays of tracks that are still eligible count, so a rejected or unavailable track does not use up the window.
   - **Recent-play penalty:** a track that is eligible again only because the library is small takes up to 0.10, fading over 20 plays, so a small library rotates.
   - **Repeated artist:** 0.10. Unknown artists never count as repeats.
   - **Near-duplicate:** 0.15, for similarity ≥ 0.95 over at least 3 shared features, so a library described by genre alone is not all duplicates.
   - The penalties are small next to intent, so diversity never overrides explicit intent. Genre/mood monotony beyond near-duplicates is not penalized.
7. **Automatic exploration** (no control pending).
   - **Rate:** 0.10. Each of the last 3 exploration outcomes multiplies it: ×0.5 for a failure, ×1.25 for a success. It is capped at 0.50. Listener controls do not move it (item 11).
   - **Whether:** the injected random generator decides only whether to explore.
   - **Which:** deterministic. It is the best candidate that has a score, is plausible (scores at least 0.40), and is novel: a different artist from, and similarity below 0.80 to, the last play and the kept picks. It must be within the explicitly requested genre. The cooldown already keeps recent plays out.
   - **Where:** it replaces #3 of a full queue.
   - **Record:** every exploration pick, automatic or directed, is marked in `recommendation_occurrences.is_exploration` (migration `de244c476f3a`), so its outcome can be found in history.
8. **#2 first** (spec §21). #2 plays first when the gap between the penalized scores is ≤ 0.08 (inclusive) and #2 offers useful novelty, which requires all of these:
   - something has played;
   - #2 is not by the artist that just played;
   - either #1 is by that artist, or #2 is less similar to the last play than #1 is.

   No swap involves an exploration pick, at #1 or #2. An unscored #2 never goes ahead of a scored #1. Occurrences keep the policy's ranks, and queue order is play order (2, 1, 3).
9. **Application.** `RecommendationService.refresh_queue(session_id)` works in three steps:
   - it reads the session, its history, and the library in one short transaction;
   - it decides in memory;
   - it surfaces the result through `SessionService.queue_recommendations()`, which replaces the old queue.

   `decide()` is a read-only preview of what `refresh_queue()` would choose now. It writes nothing and uses up no pending control. It leaves the random generator where it was: the decision runs on the service's generator, whose state is then restored. So a preview never changes what the next refresh chooses, and it shows exactly that choice. Only `refresh_queue()` draws, and only it sets `last_decision`. *(Made fully read-only at the B6 review; a regression test previews, then refreshes, against a seed whose first draw explores and second does not.)* Callers refresh after every meaningful change (B6, B8).
10. **No new dependency, no new table.** Two columns were added (items 7 and 12).
11. **Listener controls are one-refresh directives, part of current intent** (settled at the B5 review, then corrected before commit).
    - **One refresh:** Surprise me, Try something different, and More familiar each direct the next refresh only. A control is pending from its turn until a queue is surfaced after it, which acts on it. A refinement made before that refresh restates the whole intent and supersedes the control. So does a newer control. `decide()` without writing does not use it up. A refresh that surfaces nothing leaves it pending.
    - **Deterministic:** a pending control decides without the random draw. When a qualifying track exists, the control acts on that refresh.
    - **Explicit genre:** the requested genre is `ListeningContext.temporary_genres`, not long-term history. Without a control, exploration never leaves it (item 7).
    - **Surprise me:** it takes the last slot. It looks for a scored, plausible, novel track within the genre first, and sets the genre aside only when the genre has none.
    - **Try something different:** it sets the genre aside at once and puts its track first in the queue, the next to play. The two best in-intent picks follow.
    - **More familiar:** it suppresses exploration, automatic or directed, for that refresh.
    - **Setting the genre aside** drops the genre target from intent fit for that one choice. A track is judged on what can still be compared: the rest of the intent, the session's evidence, a long-term profile. If something can, it needs a score at or above the floor, so a genre the listener rejected stays out.
    - **When nothing can be compared**, the track gets no score: no value is invented. It may still be the control's pick under an explicit fallback rule: it is trustworthy (a known genre from its own labels, and playable) and unrejected (not refused with Not for me in this session). Eligibility already guarantees playable and unrejected. A track with a score is always preferred over one admitted by the rule, and an unknown track (no genre) is never a pick.
    - **The rest of the queue** still follows the explicit intent. Diversity never overrides intent; the listener's newer command changes it.
12. **An immutable surfaced position** (settled at the B5 review).
    - **The column:** `recommendation_occurrences.surfaced_position` (not null, ≥ 0) records where in its queue an occurrence was surfaced.
    - **Never rewritten:** it is written once by `add()`. Like rank, score, algorithm, and the exploration mark, it is never changed by `save()`.
    - **queue_position:** it stays the mutable current-queue state, cleared when the occurrence leaves the queue.
    - **History order:** history reads in surfaced order (surfaced time, then position), so an order such as rank 2 ahead of rank 1 can be reconstructed after the queue moves on.
    - **Migration:** it is added in the same, still uncommitted B5 migration, `de244c476f3a`, extended in place; no local database had been upgraded to it. The committed B4 migration is unchanged.
    - **Backfill:** older rows are recovered from insertion order. B4 inserted each queue's occurrences one at a time, in order, with one surfaced time, so within a session and surfaced time, rowid order is the surfaced order. It is read before the rebuild, while rowids are original.
13. **Strictly ordered times within a session** (with item 11).
    - **The problem:** this machine's clock moves in steps of about 1 ms (measured: 214 distinct readings in 200 ms). So a control turn and the refresh right after it could carry the same time, and two refreshes within a millisecond could share a surfaced time.
    - **The rule:** `SessionService` gives every change to a session a time strictly later than the session's last change, which every command records in `updated_at`. That is the clock, or `updated_at` plus 1 µs when the clock has not moved.
    - **What it buys:** "after" within a session is exact. A refresh is always later than the turn it follows, and no two queues of a session share a surfaced time.
    - **No schema change.**
14. **A pick with no meaningful score is surfaced without one.** Its `Recommendation` has an empty breakdown, so its occurrence's `score` is `NULL`. The neutral session fit (0.5) is how a stage reads with no evidence (spec §15); it is not a score for the track. This applies to directed picks admitted by the fallback rule and to unscored tracks that only fill a queue.

**Alternatives Considered:**
- Scoring written afresh for the policy (a second copy of the math, forbidden by the guide).
- Defaults for missing features (D21).
- A randomly chosen exploration track (spec §20 requires plausible exploration, and it would make tests nondeterministic).
- A fixed 20-play cooldown (small libraries run dry).
- A hard cooldown alone: a test showed a four-track library alternating two tracks.
- Constants in the database (unneeded before tuning in B11).
- Persisting decisions (the occurrence keeps rank, score, version, surfaced position, and the exploration mark; `decide()` can explain the current one).
- Letting default exploration leave the genre whenever other features make a track plausible (diversity would silently override intent).
- Setting the genre aside for the whole queue under Try something different (the request is for something different, not a new intent).
- Controls as persistent session modes, or as rate changes (the first B5 version). A control then outlasted the request that made it, and its effect depended on the random draw, landing at #3 only some of the time.
- A neutral 0.5 standing in for a track nothing can be compared with (the first review version): that invents plausibility. Replaced by the explicit fallback rule.
- Telling "after" from raw clock readings (ties at about 1 ms resolution would make a control apply twice or not at all), or a new column linking each queue to the turn it followed (a schema change that item 13 makes unnecessary).
- Keeping queue position as the only position (it is cleared when an occurrence leaves the queue, so a surfaced order was lost).
- A new, separate migration for the surfaced position (the B5 migration was still uncommitted and unapplied outside tests).

**Consequences:**
- Every pick is explainable from its stage scores, renormalized weights, penalties, and exploration mark.
- A library with only tag labels is ranked by genre, mood, and session evidence. Numeric features stay absent until an analyzer estimates them (TD-014).
- Without a stored long-term profile (B10), Policy v1 ranks by intent and session alone.
- Once a profile exists, it counts in the long-term stage and, for features the current intent leaves open, in intent fit too.
- *(Before item 11)* With a genre in the intent and tracks described by genre alone, nothing was both plausible and novel, so exploration never fired and its controls had no effect.
  - Item 11 resolves this through the controls. Without one, exploration still stays in the genre. Surprise me, or Try something different, takes the next refresh outside it through the fallback rule.
  - Verified over real tagged files.
- A control's effect is immediate and predictable: Try something different changes the very next track, Surprise me the third. Neither lasts past that refresh.
- Over genre-only tags, which track outside the genre the fallback rule admits comes down to the deterministic tie-break, because nothing distinguishes them.
- Occurrence history can reconstruct every surfaced queue in order, including exploratory orders, even when the clock does not move between them.

**Revisit When:**
- B6 records feedback events as evidence.
- B10 stores a long-term profile.
- B11 evaluation tunes the constants (as a new version).
- An analyzer estimates numeric features.
- "Play something from recently liked music" (spec §20) is defined; it is not implemented.

## TD-017: B6 Feedback and Playback Events

**Status:** Accepted, awaiting B6 review

**Date:** 2026-10-20

**Context:** Execution guide §9 and spec §15, §17, and §22 fix several things:
- the six events (LIKE, SAVE, REPLAY, SKIP, COMPLETE, NOT_FOR_ME);
- the raw facts to store;
- the Feedback Policy v1 weights, with the 8-second grace period;
- explicit actions over passive playback;
- the order: persist, then interpret, then evidence, then re-rank;
- Not for me excluding a track for the session only.

B4 had already created the `feedback_events` table. Left open:
- how events combine when there are several;
- whether evidence is stored;
- what each event does to playback;
- how the `NOT_FOR_ME` and `MORE_LIKE_THIS` turns relate to the events.

The approved frontend settles two of the playback questions. Replay of a past song plays it again "as a fresh recommendation", and Not for me moves on to the next song.

**Decision:**

1. **Feedback Policy v1 lives in the one versioned policy object.** `RecommendationPolicy` gains the explicit weights (Like, Save, Replay 1.0; Not for me −1.0), `grace_seconds` (8), the passive bands, and `full_play_weight` (0.80), all validated.
   - **Passive bands:** each applies below its upper bound: under 15% −0.50; 15–39% −0.20; 40–74% +0.10; 75–89% +0.50; 90% and up +0.80.
   - **Grace period:** it includes its last second, so 8.0 s is no evidence. It is read from seconds played, and the bands from the fraction, capped at 1.
   - **Version:** it stays `policy-v1`. B5 and B6 together implement the spec's Policy v1, and occurrences surfaced by B5's turns-only reading exist only in test databases, because no entry point runs the policy.
2. **Interpretation is per track within the session** (`interpret_feedback()`).
   - **Signals read:** every explicit signal about a track: the LIKE, SAVE, REPLAY, and NOT_FOR_ME events, and the `MORE_LIKE_THIS` (+1.0) and `NOT_FOR_ME` (−1.0) turns.
   - **Precedence, for the evidence:** the track's effective evidence is decided by the latest explicit signal, so the evidence follows a listener who changes their mind. Without one, the latest playback event decides.
   - **Why per track, not per occurrence:** each re-rank surfaces upcoming tracks as new occurrences. A Like on a queued card and the skip after the track plays are then about different occurrences of one listening. The B6 end-to-end run found this.
   - **Exclusion, separate and sticky (D18):**
     - Once a track has been refused with Not for me in the session, by turn or event, it stays excluded from automatic recommendations for the rest of the session.
     - A later Like or Replay changes its evidence, so similar tracks may rise, but never makes it automatically eligible again.
     - A Replay may still play it, as the listener's own choice.

     *(Made precise at the B6 review; before, a later explicit action also lifted the exclusion.)*
   - **Exploration outcome:** it follows the occurrence the deciding signal was about.
   - **Raw events:** they stay stored per occurrence, never merged, for B10's long-term evidence and B11's evaluation. Only the reading is per track.
3. **Evidence is never stored.** Policy v1 recomputes it from the raw facts at every refresh. Only the raw event is persisted (type, seconds, duration, capped fraction, occurrence, session, time), so different thresholds can read the same history differently, which a test demonstrates. No profile or other session is touched (D18; long-term adaptation is B10).
4. **Effects on playback** (`SessionService.record_feedback()`, one transaction with the event):
   - **SKIP, COMPLETE, or NOT_FOR_ME about the playing occurrence:** it is played, and the prepared next track starts (spec §22). A report about an occurrence that has already finished, such as a SKIP after a NEXT turn, moves nothing.
   - **REPLAY of a track that already finished:** the playing occurrence, if any, is played, and a fresh occurrence of the replayed track starts now.
     - It carries `algorithm = "listener-replay"`, rank 1, and no score: the listener chose it.
     - It ignores the cooldown (spec §19).
     - It is not a surfaced queue, so it does not use up a pending control.
   - **REPLAY of the playing occurrence:** it changes nothing; the player restarts it.
   - **SKIP, COMPLETE, and REPLAY** need an occurrence that has played. SKIP and COMPLETE also need played and total seconds.
   - **The `NOT_FOR_ME` turn** about the playing occurrence now also moves on, so the turn and the event agree. B4 recorded it without moving playback.
5. **The use case** (`FeedbackService`, `application/feedback.py`):
   - **Calls:** `react()` takes LIKE, SAVE, REPLAY, or NOT_FOR_ME; `report_playback()` takes SKIP or COMPLETE, with the seconds played and the duration.
   - **Steps:** each records the event, then refreshes the queue (re-rank and refill, D05, D16).
   - **Result:** it returns the event, its own weight, the track's interpretation after precedence, and the session state.
   - **No ticks:** only discrete events exist; there is no event type for progress.
6. **No schema change, no new dependency.**

**Alternatives Considered:**
- Interpreting per occurrence (refresh churn breaks precedence and double-counts a track).
- Interpreting per event, summing every event (a double Like would count twice, and precedence would mean nothing).
- Storing interpreted weights (the spec forbids storing only the label, and stored weights would lock in today's thresholds).
- Advancing playback on every reaction, or on none (Like and Save should not interrupt; a rejected track should not keep playing).
- Re-ranking before the next track starts (the player has already started the prepared next track, spec §22).
- Recording a feedback event for every `NOT_FOR_ME` turn as well (the turn is already the record; reading both is enough).

**Consequences:**
- The queue adapts immediately to every piece of feedback.
- A track is judged once per session, however many occurrences it had.
- Each refresh replaces the queue with new occurrences, so occurrence ids of upcoming tracks change after every event. The frontend must read the session state again (B9).
- A Like on a queued card counts like a Like on the playing track.
- Replay creates an occurrence no algorithm chose. History shows it by its label.

**Revisit When:**
- B7 adds PLAYLIST_ADD (+1.0 in Feedback Policy v1).
- B8 maps routes to events: which events come as playback events and which as reactions, and how NEXT and SKIP are sent together.
- B9 wires the frontend's playback position.
- B10 reads feedback across sessions for long-term evidence.
- B11 evaluation tunes the thresholds (as a new version).

## TD-018: B7 Playlists

**Status:** Accepted, awaiting B7 review

**Date:** 2026-10-21

**Context:** Spec §9 and execution guide §10 fix the B7 scope:
- create, rename, delete, add, remove, and reorder;
- a track at most once per playlist by default;
- a playlist add is strong positive feedback (SAVE/PLAYLIST_ADD, +1.00), but recommendations are never auto-saved;
- the `playlists` and `playlist_items` tables and a `PlaylistRepository` port.

The approved frontend:
- gives a playlist an id, a name, and an optional colour tone;
- keeps names unique, numbering a new name when it is taken;
- saves the current song to one or more playlists from a picker.

**Decision:**

1. **Model** (`domain/playlist.py`):
   - **`Playlist`:** an id, the listener, a name (trimmed, 1–100 characters), and created and updated times.
   - **`PlaylistItem`:** a track at a position.
   - **`PlaylistContents`:** a playlist with its items in order, positions 0, 1, 2… with no gaps. Its pure operations return new contents with the playlist touched:
     - add at the end (`TrackAlreadyInPlaylist` if present);
     - remove, closing the gap (`TrackNotInPlaylist`);
     - reorder (`InvalidPlaylistOrder` unless the new order lists exactly the playlist's tracks, each once).
2. **Names are unique per listener** (exact match after trimming), as the frontend keeps them. `PlaylistNameTaken` on create or rename; keeping one's own name is fine. The database backs it with a unique (listener, name) constraint.
3. **One entry per track per playlist.** The primary key of `playlist_items` is (playlist, track), with unique (playlist, position) and position ≥ 0.
4. **Whole-list writes.** A change rewrites a playlist's items as a whole: delete, then insert in order, in one transaction. A swap never trips the unique positions, and the order cannot be left half-applied.
5. **Any library track can be added,** even one whose managed copy is missing. Availability can change (B2 repairs copies), so it is shown when a playlist is read (B8), not used to refuse.
6. **Not stored:** presentation, such as the frontend's colour tone or artwork (D32). Deleting a playlist removes its items, never the tracks or any feedback history.
7. **A playlist add as feedback** (`PlaylistService.add_track(playlist, track, session_id, occurrence_id)`):
   - **When:** the listener adds the track of a recommendation from a session.
   - **Order of steps:**
     1. The occurrence is checked: an active session, an occurrence of it, and the same track.
     2. The item is stored.
     3. FeedbackService records a PLAYLIST_ADD event (+1.00, a new `FeedbackEventType` and `RecommendationPolicy.playlist_add_weight`) and re-ranks the queue.
   - **Refusals:** a refused add, for a duplicate or a bad occurrence, stores neither an item nor an event.
   - **Several playlists:** saving one recommendation to several playlists records an event per playlist. That is still one piece of evidence: Feedback Policy v1 reads each track once.
   - **Plain adds:** without a session, an add is not feedback.
   - **Playback:** a playlist add does not touch playback.
   - **Separate from SAVE:** PLAYLIST_ADD is not accepted as a plain reaction; it always stands for a stored item.
8. **Never auto-saved.** No code path but `add_track()` writes a playlist item; a test runs likes, saves, completions, and refreshes and finds none.
9. **Migration `ce0b59df2cd1`:**
   - **Upgrade:** it creates both tables and rebuilds `feedback_events` (batch mode) so its type CHECK accepts PLAYLIST_ADD, keeping its rows, index, and composite foreign key.
   - **Downgrade:** it deletes PLAYLIST_ADD events before restoring the earlier constraint, since their playlists are dropped too.
10. **No new dependency.**

**Alternatives Considered:**
- Duplicate names (the frontend avoids them, and names are how the listener tells playlists apart).
- Duplicate entries (not approved; spec default).
- Position updates in place (a swap breaks unique positions mid-update).
- Fractional positions (no gaps would be visible, but they drift).
- Recording playlist adds as SAVE (two different raw facts with the same weight; keeping them apart keeps the history exact).
- Storing the playlist on the feedback event (not needed by Feedback Policy v1; the playlist item records it).
- Refusing unavailable tracks (would lose a listener's choice over a temporary state).

**Consequences:**
- Playlists persist across restarts with their exact order.
- A playlist add from a recommendation adapts the session at once.
- Playlist names are user text, kept as written (trimmed), up to 100 characters.

**Revisit When:**
- The product approves duplicate entries.
- B8 maps the routes (`PATCH …/items/order` takes the full order).
- B9 maps the frontend's Save to playlist adds.
- Playlists need artwork or sharing (Future).

## TD-019: B8 FastAPI Boundary

**Status:** Accepted, awaiting B8 review

**Date:** 2026-10-21

**Context:** Execution guide §11 and spec §24–§26 fix the B8 scope:
- a thin HTTP boundary with Pydantic schemas separate from ORM and domain models;
- the spec's routes;
- one error envelope with request IDs, and no stack traces or paths;
- audio served by track ID, with the installed Starlette range behavior verified (and a tested range response only if it falls short).

B8 is also the first phase that runs everything at once: request threads, the analysis worker, and the startup scan share one SQLite file.

**Decision:**

1. **Package** `backend/src/intentune/api/`:
   - `container.py` and `settings.py` are the composition root, the only API modules that import persistence or adapters;
   - `routes/` (one module per resource), `schemas.py`, `views.py` (domain → schema mapping), `errors.py`, and `dependencies.py` do not, and an architecture test enforces it;
   - no inner layer may import the API (the same test).
2. **Per-request services.** The engine and adapters are built once. Every request builds its services with a fresh unit of work, because units of work are neither re-entrant nor thread-safe and synchronous routes run on FastAPI's thread pool. Services that call each other share that one unit of work in sequence, as the B6/B7 tests do.
3. **Two thin use cases** in the application layer:
   - **`ListeningService`** (`application/listening.py`): `start()` = start session + refresh queue, and `steer()` = apply turn + refresh queue. These are the same two-step pattern FeedbackService uses.
   - **`LibraryScanCoordinator`** (`application/library_scans.py`): scans never overlap. One that would start while another runs is refused with `ScanInProgress` (`409 CONFLICT`), not queued. The startup scan runs in a thread. Each scan gets a fresh `LibraryService`, and the analysis worker is woken after it.

   The library also gains `get_tracks(ids)` and `track_audio(id)`. The latter raises the new domain error `TrackUnavailable` and marks a track whose copy is gone `MISSING_MANAGED_FILE`.
4. **Startup and shutdown** run in the FastAPI lifespan, never at import:
   - **startup:** migrate → ensure the local listener → end sessions from the previous run (D35) → start the worker (D28) → start the background startup scan (D25, D26);
   - **shutdown:** stop the worker after its job → wait for a scan → dispose the engine.

   A failed startup stops what it started.
5. **`BEGIN IMMEDIATE`.** Every transaction takes SQLite's write lock when it begins (`persistence/db.py`).
   - **Why:** with the deferred `BEGIN` of TD-012, a transaction that reads and then writes fails at once with "database is locked" when another connection commits in between. Its snapshot is stale, so the busy timeout cannot help. B8 makes that interleaving routine: a turn's read-then-write against the worker or a scan. It was reproduced before the change.
   - **Effect:** transactions now queue on the 5-second busy timeout.
   - **Cost:** reads also take the lock, so WAL's concurrent readers are given up. Transactions are short (file and analysis work happen between them), so the queueing is brief.
   - **Evidence:** the full suite takes no longer. A test proves the read-then-write case. One B1 test of two overlapping units of work in one thread was rewritten to use two threads. In a live run, 96 concurrent requests (turns, reactions, playlist writes, reads, audio ranges, and rescans) caused no errors.
6. **Range requests: Starlette's `FileResponse`, unmodified.** Verified on Starlette 1.8.0:
   - `Accept-Ranges: bytes`;
   - `206` for single, open-ended, and suffix ranges, with the end clamped;
   - `multipart/byteranges` for several;
   - `416` with `bytes */size` past the end;
   - `400` for a malformed range.

   That is what browser seeking needs, so no custom range code exists. Tests pin each behavior, to catch an upgrade that changes one. `HEAD` is declared on the route. The 400 and 416 replies are Starlette's plain text, outside the envelope.
7. **Errors** (`errors.py`):
   - **Request IDs:** a pure-ASGI middleware gives each request an id, which a client may supply if it is safe, and sets `X-Request-ID`. It also turns any unexpected error into a logged, generic `500 INTERNAL_ERROR`. It sits inside CORS, so that envelope carries CORS headers.
   - **Domain errors:** these map by class. Resource errors get fixed messages that echo no id or path, and transitions and domain validation pass their own messages through.
   - **Pydantic errors outside request parsing:** these are `500`, not `422`.
   - **Codes and statuses:** `SOURCE_NOT_FOUND`, `NOT_FOUND`, and `METHOD_NOT_ALLOWED` are added to the spec's potential codes. `400` is for a body that is not JSON. `409` covers transitions, unavailable tracks, and conflicts.
8. **Schemas are strict:**
   - unknown fields are refused;
   - numbers must be JSON numbers and finite;
   - text is trimmed and length-limited (labels 100, at most 20 genres or moods, playlist names by the domain's constant);
   - wire enums are lowercase.

   Turns have no text field, so no raw prompt can be stored (D33).
9. **Feedback routing:**
   - SKIP/COMPLETE are playback events;
   - LIKE/SAVE/REPLAY/NOT_FOR_ME are reactions;
   - PLAYLIST_ADD only goes through playlist items;
   - Play is a `next` turn while nothing plays;
   - `initial_intent` as a turn is `409`.
10. **Library scans run inside the request** for Import and Rescan, which answer their scan reports; only the startup scan is a background thread. Paging is `limit`/`offset` over the loaded list.
11. **Settings** come from the process environment only: `DATABASE_URL`, `MEDIA_ROOT` (new, relative to `backend/`), `CORS_ORIGINS`, `API_HOST`, `API_PORT`. `backend/.env` is still not loaded, and no settings or dotenv dependency was added.
12. **No new dependency.** FastAPI, Uvicorn, and httpx were already pinned.

**Alternatives Considered:**
- **Keeping deferred `BEGIN`** and retrying on "database is locked": retries in every use case, and a retried read-then-write must re-read.
- **One process-wide lock around all writes:** it would not cover the worker's own engine use, and it duplicates SQLite's lock.
- **A custom range response:** unneeded once the installed behavior was verified, and more code to keep safe.
- **`202 Accepted` with background scans** for Import and Rescan: closer to D26, but it needs a scan-status resource the spec's routes do not have, and the report would be lost.
- **Queueing a second scan** instead of refusing it: a caller could wait minutes with no feedback.
- **Loading `.env` with python-dotenv** (installed with `uvicorn[standard]`): it would silently pick up the listener's stale `DATABASE_URL` (see Consequences).
- **Async routes:** every use case is synchronous, so they would block the event loop or need wrapping.
- **Module-level `app`:** importing it would read the environment and open the database.

**Consequences:**
- Every Prototype 1 use case is now reachable over HTTP, and the backend runs as one process: `python -m src.intentune.api`.
- The worker and the startup scan run for the first time outside tests.
- SQLite transactions serialize, reads included.
- A long first import keeps its request open until the scan ends (other requests are still served).
- A local `backend/.env` written before B1's default moved still says `DATABASE_URL=sqlite:///./intentune.db` (backend/intentune.db, not gitignored). It is not read by `python -m src.intentune.api`. A tool that loads `.env` would use that file instead of `backend/data/intentune.db`, so such a `.env` should be updated or removed first.
- The Starlette test client warns that its httpx support is deprecated (it asks for `httpx2`); no dependency was added for it.

**Revisit When:**
- **Concurrency:** B11 measures contention with thousands of tracks, or many readers need WAL concurrency back (deferred reads with retrying writes).
- **Scans:** the frontend needs scan progress (background Import/Rescan with a status resource).
- **Settings:** settings loading is wanted (and the `.env` above is dealt with).
- **Frontend:** B9 maps the frontend to these routes.
- **Upgrades:** Starlette or FastAPI changes the range behavior the tests pin, or drops httpx from its test client.

## New Decision Template

```text
## TD-XXX: Decision Title

Status:
Date:
Owner:

Context:

Decision:

Alternatives Considered:

Consequences:

Revisit When:
```
