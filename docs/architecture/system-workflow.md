# System Workflow

## Status

**Current, Planned, Superseded, and Future.** Reconciled with Prototype 1 in Phase B0 (2026-10-18). Section labels say which is which.

## Current Workflow

The public functions the CLI calls (`load_songs()`, `recommend_songs()`) still have their historical signatures and dictionary shapes, but internally they now delegate to the canonical domain flow:

```text
songs.csv
   |
   v
load_songs()  --delegates to-->  CSV adapter (src/intentune/adapters/csv_catalog.py)
                                       |
                                       v
                                 MusicCandidate list
                                       |
                                       v
        load_songs() converts candidates to the historical song dict list
                                       |
hard-coded user profile                |
   |                                   |
   v                                   v
legacy_profile_to_user_profile()   recommend_songs() converts song dicts
   |                               back to MusicCandidate objects
   v                                   |
        canonical UserProfile + MusicCandidate list
                        |
                        v
        rank_candidates() (src/intentune/domain/ranking.py)
          -- calls score_candidate() (src/intentune/domain/scoring.py)
             for every candidate --
                        |
                        v
              list[Recommendation], ranked and assigned ranks
                        |
                        v
        recommend_songs() converts back to the historical
        {"song", "score", "reasons"} dict shape
                        |
                        v
              print recommendations and reasons
```

`score_song()` follows the same conversion pattern for a single song: legacy dict in, `MusicCandidate`/`UserProfile` built, `score_candidate()` called, `(score, reasons)` returned.

The `MusicCandidate -> historical dict -> MusicCandidate` conversion in the
CLI path is intentional legacy compatibility, not the desired path for new
callers. New internal callers can pass canonical candidates directly to
`recommend_music()`, or use `recommend_from_catalog(catalog, profile, limit)`
to request candidates from a `Catalog` port implementation (currently
`CsvCatalog`) instead of assembling the candidate list themselves:

```text
catalog.list_candidates() (src/intentune/ports/catalog.py Catalog protocol)
   |
   v
recommend_from_catalog() (src/intentune/application/recommendation_service.py)
   |
   v
recommend_music() -> rank_candidates() -> score_candidate()
```

The CLI does not use `recommend_from_catalog()` yet -- it still runs through
the legacy `load_songs()`/`recommend_songs()` path shown above, unchanged.

### Current frontend workflow

The React frontend runs its own loop on a mock service and never reaches the backend:

```text
User types, picks a starter or quick action, tunes, presses Next or Not for me
   -> planCommand() (pure) produces local changes plus at most one service question
   -> SessionService.respond() (mock: phrase tables, hand-ordered song lists)
   -> the answer is applied to the session that asked
   -> composeSession() turns state into approved blocks
```

Playback is a mock timer. When a song's duration runs out, the frontend sends `next`, exactly as if the user had pressed Next.

## Planned Prototype 1 Workflows

**Planned (approved), except where a section says Current.** Summarized from the [Prototype 1 specification](../planning/intentune-backend-prototype-implementation-spec.md). The spec is authoritative where detail differs.

### Library import and scanning (B2)

```text
source folder registered (several may coexist; one logical library)
   -> scan
   -> validate (allowlisted format, size limit)
   -> SHA-256 hash
   -> exact duplicate? -> no second logical track
   -> copy into backend/data/media/<track_uuid>.<extension>
   -> persist track, extract basic tags
   -> IMPORTED: playable
   -> queue deeper analysis
```

A lightweight incremental scan runs at startup, and the listener can trigger **Rescan Library**. There is no real-time watcher (D25).

| Source file state | Action |
|---|---|
| unchanged | no work |
| new | import and analyze |
| changed | re-hash; re-import/re-analyze if content changed |
| missing at source | source marked missing; the managed copy stays usable |
| exact duplicate | no second logical track |

**Current (B2, 2026-10-19).** `LibraryService` (`backend/src/intentune/application/library.py`) implements this pipeline and the table above, with these specifics:

- **Validate:**
  - The extension must be allowlisted (`mp3`, `m4a`, `flac`, `ogg`, `opus`, `wav`); files with other extensions are ignored and counted.
  - The file must be at most 1 GiB by default.
  - mutagen must confirm the content is that format. MP3 bytes named `.flac`, or text named `.mp3`, are recorded as UNSUPPORTED.
- **Copy:** the managed copy is written to a temporary file while being hashed, and moved into place only if its SHA-256 matches. A file that changes mid-import is recorded as FAILED and leaves nothing behind.
- **Tags:** title, artist, album, year, and genres are read from the managed copy after the track is stored. If reading fails, the track stays IMPORTED and playable without them.
- **Retries:**
  - FAILED files (I/O errors, changed during import) are retried on the next scan even if unchanged.
  - UNSUPPORTED files are not retried until they change.
  - A changed file whose content is unchanged is re-hashed but not re-imported.
  - A changed file whose content differs becomes a new track; the old track stays in the library.
- **Repair:** a track marked unavailable (`MISSING_MANAGED_FILE`) gets its managed copy back when a source file with the same content is scanned again.
- **Folder safety:** the walker skips symbolic links, never enters a folder whose real location is outside the source (this includes Windows junctions), visits each folder once, and never scans the managed media folder.

Not yet: nothing runs the startup scan; the B8 startup will call `rescan_library()`. Scans run synchronously when called. B3 implemented background *analysis* only, so running scans in the background (D26) is not assigned to a phase yet ([open question](../planning/risks-and-open-questions.md#open-backend-questions)). "Queue deeper analysis" is B3's `AnalysisService.enqueue_pending()`: a track with no `analysis_version` for the current analyzer gets a job.

### Background analysis (B3)

```text
persisted job (IMPORT_TRACK, EXTRACT_TAGS, ANALYZE_AUDIO, REANALYZE_TRACK, RESCAN_SOURCE)
   -> bounded in-process worker (one worker initially)
   -> features stored with source, analyzer version, confidence
   -> track moves DISCOVERED -> IMPORTED -> ANALYZING -> READY
```

Failure states are `UNSUPPORTED`, `FAILED`, and `MISSING_MANAGED_FILE`. One failure never crashes the library. Interrupted jobs resume after restart. Unavailable features stay `NULL`; nothing is invented (D21).

**Current (B3, 2026-10-20).** `AnalysisService` (`backend/src/intentune/application/analysis.py`) runs on one `AnalysisWorker` thread (`application/analysis_worker.py`):

```text
worker start: recover interrupted jobs
loop:
   claim the oldest PENDING job        (one short transaction; attempts + 1; IMPORTED track -> ANALYZING)
   analyze the managed copy            (no transaction held; the library stays readable and writable)
   record the outcome                  (one short transaction: job, features, track status)
   nothing pending?  queue every track the current analyzer has not analyzed
   still nothing?    sleep until wake() or the idle interval (30 s by default)
```

Outcomes:

| Situation | Job | Track |
|---|---|---|
| Analyzed | `SUCCEEDED`; features replaced with provenance | `READY`, `analysis_version = name@version` |
| Format the analyzer cannot decode (M4A for libsndfile) | `SKIPPED`, `FORMAT_NOT_SUPPORTED` | unchanged (`IMPORTED`) |
| Job queued for a different analyzer version | `SKIPPED`, `SUPERSEDED`; re-armed when its own version runs again | unchanged |
| Undecodable content | `FAILED`, `DECODE_ERROR`; not retried for this version | unchanged |
| Managed copy cannot be read (`OSError`) | back to `PENDING`, then `FAILED`, `IO_ERROR` once attempts are used up (3) | unchanged |
| Managed copy missing | `FAILED`, `MISSING_MANAGED_FILE`; re-armed once a rescan repairs the track | `MISSING_MANAGED_FILE` |
| Any other analyzer error | `FAILED`, `ANALYZER_ERROR`; logged; the worker carries on | unchanged |
| Process stopped mid-job | found `RUNNING` at the next start: back to `PENDING`, or `FAILED`, `INTERRUPTED` after 3 attempts | `ANALYZING` returns to its previous state |

Queuing is idempotent: one job per track and analyzer version, enforced by a unique constraint. A new analyzer version therefore re-analyzes the library. The analyzer's version includes the libsndfile version, so a decoder upgrade does the same. During reanalysis a track stays `READY` with its earlier features until the new ones replace them.

The B3 analyzer measures decoded duration, sample peak, and RMS level only. These are exact signal measurements, not perceptual or semantic features; see [TD-014](../decisions/technical-decisions.md#td-014-b3-background-analysis).

Not yet: nothing starts the worker; the B8 startup will. Scanning itself is not a background job (see the library section above).

### Listening session (B4, B5)

```text
listener starts a fresh session and sets structured intent (ListeningContext)
   -> eligibility filter
   -> intent fit -> session fit -> long-term fit
   -> combined rank (0.55 / 0.30 / 0.15, renormalized when a component is unavailable)
   -> diversity / repetition re-rank
   -> controlled exploration (about 90/10)
   -> rolling top three
   -> #2 may play first when within 0.08 of #1 and usefully novel
```

The listener presses Play once. The next candidate is prepared before the current track ends, the next track begins, and the queue is refilled and re-ranked. The frontend owns real playback position and timers; the backend records meaningful events, not per-second ticks.

**Current (B4, 2026-10-20): the session state machine and history, without the ranking above.** `SessionService` (`backend/src/intentune/application/sessions.py`):

```text
start_session(listener, context)    -> ACTIVE session + INITIAL_INTENT turn
                                       (the listener's previous ACTIVE session ends: REPLACED_BY_NEW_SESSION)
queue_recommendations(recs, algo)   -> the given Recommendations become QUEUED occurrences, in list order;
                                       whatever was still queued becomes REPLACED
advance() / play(occurrence)        -> PLAYING -> PLAYED; the next (or the chosen) queued occurrence -> PLAYING
apply_turn(kind, ...)               -> a turn with the context left in force:
                                         REFINE replaces the context
                                         NEXT finishes the current track and starts the next queued one
                                         NOT_FOR_ME / MORE_LIKE_THIS name their occurrence (the playing one by default)
                                         SURPRISE_ME / MORE_FAMILIAR / TRY_SOMETHING_DIFFERENT are recorded only
end_session()                       -> ENDED_BY_LISTENER; queued -> DISCARDED, playing -> PLAYED
```

An ended session refuses every command and stays readable (`get_session`, `history`, `list_sessions`).

What B4 does not do:
- **Recommendations:** it does not produce them, refill the queue, or keep it at three. That is B5.
- **Turn effects:** it does not act on what turns mean (exclusion, affinity, exploration), which is B5 and B6.
- **Feedback:** it does not record feedback events. That is B6, though B4 created their table.
- **Text:** it does not turn typed text into turns (an [open question](../planning/risks-and-open-questions.md#open-backend-questions)).

### Feedback and immediate adaptation (B6)

```text
LIKE / SAVE / REPLAY / SKIP / COMPLETE / NOT_FOR_ME
   -> persist the raw event (played seconds, duration, fraction, occurrence, session)
   -> interpret with Feedback Policy v1
   -> update session evidence
   -> re-rank the remaining queue
```

Explicit actions override passive playback interpretation. The first 0–8 seconds are not preference evidence. Not for me excludes the exact track for the current session and strongly down-ranks similar tracks, without changing the long-term profile (D12, D18).

### Playlists (B7)

Create, rename, delete, add, remove, and reorder. One occurrence of a track per playlist by default. Adding to a playlist is strong positive feedback, but recommendations are never saved automatically.

### Restart (D35)

```text
app restarts
   -> library, playlists, metadata, feedback, and history are kept
   -> the active queue is not restored
   -> the next listening action starts a fresh session
```

**Current (B4) for sessions.** `SessionService.end_sessions_from_previous_run()` ends every session a previous run left `ACTIVE`, with reason `APP_RESTARTED`. Queued occurrences become `DISCARDED` and the playing one `PLAYED`; turns, occurrences, and events are kept. The next `start_session()` creates a fresh session. This was verified with a real hard process exit mid-session. Nothing calls it at startup until B8.

### Long-term adaptation (B10)

Permanent profile change requires at least four consistent strong signals across at least two sessions, and then only a small, bounded, traceable, reversible adjustment (D06).

## Superseded Workflows

**Superseded by the Prototype 1 workflows above.** Kept for history.

### First Backend Workflow (superseded)

Replaced by the session-based routes in spec §24. There is no profile-only `POST /api/v1/recommendations` in Prototype 1.

```text
1. Client sends POST /api/v1/recommendations
2. API validates the request schema
3. Application service requests candidates from a catalog provider
4. Catalog provider loads the internal catalog
5. Domain service scores every candidate
6. Ranking logic sorts candidates
7. Optional diversity logic adjusts repeated artists or genres
8. Application service creates a response
9. API returns JSON with scores and reasons
```

### Planned Feedback Workflow (superseded)

Replaced by the Prototype 1 feedback workflow, which uses a different event set (LIKE, SAVE, REPLAY, SKIP, COMPLETE, NOT_FOR_ME) and changes session ranking immediately. Its rule that permanent profile adaptation waits for a tested policy carries forward as D06.

```text
1. User receives recommendations
2. User chooses like, dislike, skip, save, or open
3. Client sends a feedback event
4. API validates the event
5. Feedback service stores the event
6. The system acknowledges the event
7. Profile adaptation is not performed until a tested policy is introduced
```

## Future Workflows

**Future: deferred beyond Prototype 1 (D30, D39).**

### AI Chatbot Workflow (future)

Prototype 1 uses a structured `ListeningContext` plus a limited set of deterministic commands ("more energetic", "calmer", "surprise me", and so on). LLM intent parsing comes later, behind an `IntentParser` port.

```text
1. User enters a natural-language request
2. AI adapter sends the message to an AI provider
3. Provider returns structured intent
4. Intent validator checks required fields and numerical ranges
5. Invalid or incomplete output receives a clarification request or a safe fallback
6. The validated request enters the same recommendation application service
7. The existing deterministic engine scores and ranks candidates
```

The chatbot is an input adapter. It does not replace backend validation or ranking, and an LLM never chooses tracks directly. Step 5 originally read "receives safe defaults"; any fallback must still respect D21 and must not invent feature values.

### YouTube Workflow (future)

```text
1. The application receives validated user intent
2. Query builder creates a small set of search phrases
3. YouTube adapter calls the official YouTube Data API
4. API results are normalized into Intentune candidate objects
5. Duplicate and invalid results are removed
6. Available metadata is scored carefully
7. Results are ranked and explained
8. Browser displays title, channel, thumbnail, link, and explanation
```

## Failure Workflows

### Invalid Input

Return a structured validation error (`VALIDATION_ERROR`). Do not begin recommendation processing.

### Empty Library or No Eligible Track

Return a controlled result rather than an error page or crash. The spec lists `RECOMMENDATION_UNAVAILABLE` among its potential error codes; exact error semantics are defined in B8.

### Unsupported or Missing Audio

**Planned:** an unsupported or corrupt file fails safely, and a missing managed file makes the track ineligible, without crashing the library. Related potential codes in the spec: `UNSUPPORTED_AUDIO`, `IMPORT_FAILED`, `TRACK_UNAVAILABLE`.

### Analysis Failure

**Planned:** the track stays playable with the features it has. The job is marked failed, and the worker continues with other jobs.

### Database Failure

Recommendation logic that does not require persistence may continue. Session, feedback, playlist, or history operations return a controlled error. Clients never see stack traces or filesystem paths.

### AI Failure (future)

The manual structured-input path stays usable. AI failure must not break the core recommender.

### YouTube Failure (future)

Return a provider-specific unavailable message or fall back to the local library when that behavior is enabled.
