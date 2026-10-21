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

   `decide()` returns the same decision without writing. Callers refresh after every meaningful change (B6, B8).
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
