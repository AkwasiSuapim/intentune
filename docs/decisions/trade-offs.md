# Trade-offs

## Status

**Living Document**

A trade-off records what the project gains and what it accepts in return.

Every Prototype 1 decision has its main trade-off listed in the [Prototype 1 Decision Register](intentune-prototype-decision-register.md). The [Prototype 1 Trade-offs](#prototype-1-trade-offs) section below expands the ones with the largest consequences. Older entries were reconciled in Phase B0 (2026-10-18).

## Modular Monolith Instead of Microservices

### Gain

- Simpler development
- Easier local debugging
- One deployment
- Fewer distributed-system failures

### Cost

- Strong module boundaries depend on discipline
- Independent scaling is limited

### Revisit When

Clear modules need separate ownership, scaling, or deployment.

## CSV Catalog Before a Database

**Status:** Current for the recommendation catalog; its revisit condition is met. Prototype 1 stores a library, sessions, feedback, and playlists, so SQLite arrived in B1 (2026-10-19, D22), so far holding only the local listener profile. Library tracks move into it in B2. The CSV adapter stays as a compatibility source.

### Gain

- Simple baseline
- Easy inspection
- No migration or database setup

### Cost

- Limited querying and concurrent updates
- Not suitable for persistent users and feedback

### Revisit When

The product stores profiles, feedback, or recommendation history.

## Deterministic Scoring Before Machine Learning

### Gain

- Explainability
- Easier testing
- Lower cost
- Easier debugging

### Cost

- Limited ability to learn complex preference patterns
- Manual feature and weight design

### Revisit When

Enough quality feedback data exists to evaluate a learned model responsibly.

**Prototype 1 note:** ranking stays deterministic and staged (D07). No model is trained before an evaluation dataset exists. Validated pretrained audio analyzers may supply features where justified (D19), but they do not rank.

## Separate React Frontend Instead of Streamlit

### Gain

- Full control over the interface and interaction
- Backend stays a plain HTTP API that any client can use
- Frontend and backend can be developed and deployed independently

### Cost

- Slower first browser MVP than a Python-only Streamlit page
- Two languages and two toolchains (Python and TypeScript)
- The API must exist before the interface can be built

**Update (2026-10-18, B0):** the last cost did not hold. The frontend was built first against a mock service (F0–F8). The real cost is reconciliation: the mock service boundary and the Prototype 1 API were designed separately and must be aligned in B8/B9 (see [API Design](../design/api-design.md#frontend-contract-alignment)).

### Revisit When

Maintaining a separate frontend is slowing delivery of the core recommendation features.

## External AI Provider

**Status:** Future. Deferred beyond Prototype 1 (D39).

### Gain

- Strong natural-language interpretation without training a model

### Cost

- API cost
- Latency
- Provider availability
- Privacy considerations
- Output variability

### Mitigation

Structured output, validation, timeouts, fallback behavior, and provider abstraction.

## YouTube as the First External Catalog

**Status:** Superseded. Prototype 1 uses the listener's own music in a managed local library (D02, D03), and external catalogs are deferred (D39). Kept for history.

### Gain

- Broad visible catalog
- Thumbnails, links, channels, and embeddable videos

### Cost

- API quota
- Search metadata may not include precise audio features
- Availability and regional restrictions

### Mitigation

Use official APIs, normalize metadata, avoid unsupported claims, and keep the internal catalog available.

## Canonical Domain Internals with Legacy Boundary Compatibility

**Status:** Implemented and accepted (TD-009)

**Approval note:** Preserving the existing dictionary, dataclass, scoring,
ranking, and CLI behavior was explicitly approved. Moving scoring/ranking
into canonical modules and adding application/port/adapter modules went
beyond the earlier model-only/minimal-structure boundary; the owner has since
approved continuing with this canonical modular architecture.

### Gain

- A single typed, source-independent vocabulary (`MusicCandidate`, `UserProfile`, `ListeningContext`, `FeatureWeights`, `ScoreComponent`, `ScoreBreakdown`, `Recommendation`) exists for future FastAPI, AI, YouTube, and database work to target.
- Existing scoring, ranking, CLI output, and all original tests are provably unchanged.
- **Update (this phase):** scoring and ranking have since been rewired onto the canonical models (`src/intentune/domain/scoring.py`, `src/intentune/domain/ranking.py`) as the single source of truth, resolving the "not yet unified" cost below for scoring/ranking specifically.
- **Update (this phase):** a formal `Catalog` port (`src/intentune/ports/catalog.py`) and application-level catalog dependency injection (`recommend_from_catalog()`) now exist, so the application layer depends on an abstraction rather than the concrete CSV adapter.

### Cost

- Two dict/dataclass *shapes* still coexist at the legacy boundary (the historical dictionary API and the historical dataclass API in `src/recommender.py`) alongside the canonical domain models -- but they are now thin conversions at the boundary, not separate implementations of the scoring/ranking math.
- The legacy `UserProfile` dataclass still carries a deprecated, inert `likes_acoustic` field for backward compatibility.
- `load_songs()`'s legacy dict shape assumes every candidate field is present (`int(candidate.tempo_bpm)` would fail on a `None` value); this remains true for the current CSV catalog but would need to change before a source with genuinely missing fields could flow through the legacy dict path.
- The CLI path performs an extra `MusicCandidate -> legacy dict -> MusicCandidate`
  conversion so the historical `load_songs()` and `recommend_songs()` shapes
  remain unchanged.

### Revisit When

The "Expanded and Configurable Scoring Engine" milestone (see docs/planning/development-phases.md, Phase 3) extends scoring to tempo/valence/acousticness and missing-feature normalization -- at that point the legacy dict API's fixed four-field shape will need a documented limitation notice or a wider replacement, since it cannot express per-feature weights or partial data.

**Update (2026-10-18, B0):** that milestone is superseded by Prototype 1 Phase B5. The revisit point is now B5.

**Update (2026-10-20, B5):** B5 did not widen the legacy dict API. Missing-feature scoring and the extra features live in Recommendation Policy v1, a separate path for library tracks, and the legacy four-field shape keeps its contract. The two share the feature primitives, so the scoring math is still not duplicated.

## Prototype 1 Trade-offs

**Accepted (2026-10-18).** The trade-offs below carry the largest consequences. Every decision's main trade-off is in the [decision register](intentune-prototype-decision-register.md).

### Managed copies of imported music (D02, D23)

- **Gain:** the library keeps working when the original files move or are deleted; storage names are generated, so filenames never become identifiers.
- **Cost:** uses extra disk space, roughly one more copy of every imported track. Since B2, content that changes at the source adds a new copy and keeps the old one, until a removal feature exists (TD-013).
- **Status:** Current since B2 (2026-10-19).
- **Revisit when:** disk use becomes a problem for real libraries (B11). *Measured in B11:* the managed copies of 200 imported files took exactly the bytes of their sources.

### SQLite + SQLAlchemy + Alembic (D22)

- **Gain:** no server to run; fits one listener on one device; versioned migrations from the start.
- **Cost:** limited write concurrency, which matters because a background worker writes while the app reads; a later move to PostgreSQL needs a migration path. B1's correct transaction handling (SQLAlchemy emits `BEGIN`, so DDL is transactional) makes "database is locked" errors somewhat more likely than the driver's legacy mode would (TD-012).
- **Mitigation:** short transactions, one worker initially, the driver's 5-second busy timeout, and WAL mode, enabled for file databases in B1 and verified by tests. Real contention is measured when B3 adds the worker.

### In-process bounded worker instead of a task queue (D28)

- **Gain:** no Redis or Celery; simple to run and debug.
- **Cost:** shutting the process down interrupts active work. One worker analyzes one track at a time.
- **Mitigation:** job state persisted in SQLite; idempotent jobs that resume after restart.
- **Status:** Current since B3 (2026-10-20): one `AnalysisWorker` thread. A hard exit mid-job was verified to recover on the next start, with the attempt counted and a limit of 3 (TD-014).

### SHA-256 exact deduplication (D24)

- **Gain:** simple, exact, and testable.
- **Cost:** the same song in two encodings (for example, an MP3 and a FLAC) counts as two tracks. So does the same audio with different embedded tags, since tags are part of the file's bytes.
- **Status:** Current since B2 (2026-10-19).
- **Revisit when:** duplicate transcodes become common; perceptual fingerprinting is deferred.

### Missing features stay missing (D21)

- **Gain:** scores never rest on invented values.
- **Cost:** fewer active features for partly analyzed tracks, so lower coverage and less discriminating scores until analysis finishes.
- **Status:** Current since B5 (2026-10-20), in Policy v1. Today's library tracks carry tag labels only (genre, rarely more), so Policy v1 ranks them on genre and session evidence alone. A track that has a genre is not penalized for lacking energy. A track with nothing to compare has no meaningful score and only fills an otherwise short queue (TD-016).

### Staged ranking with fixed heuristic weights (D07–D09)

- **Gain:** each stage can be explained, tested, and debugged separately.
- **Cost:** the weights (0.55/0.30/0.15), feedback values, and thresholds are versioned heuristics, not proven values.
- **Mitigation:** one versioned policy module; deterministic evaluation scenarios; no claim of improvement without comparison evidence.
- **Status:** Current since B5 (2026-10-20): `RecommendationPolicy` (`policy-v1`) holds every constant, and each occurrence records the version (TD-016).

### Plausible exploration within explicit intent (D13, D36, spec §19–§20)

- **Gain:** automatic exploration never contradicts what the listener asked for. It stays in an explicitly requested genre. Its pick is deterministic (the best scored, plausible, novel track), so it can be explained and tested; only the decision *whether* to explore is random.
- **Gain (B5 review):** a listener control is a one-refresh directive, part of current intent, and deterministic. Try something different leaves the genre and changes the very next track. Surprise me leaves the genre only when the genre offers no novelty. More familiar stops exploration for that refresh. None outlasts its refresh.
- **Gain:** no score is invented. A track nothing can be compared with has no score and is surfaced without one. It reaches a control's pick only through an explicit, stated rule.
- **Cost:** with no control, a library described by genre alone never explores within a requested genre. Outside the genre, tracks admitted by the fallback rule are indistinguishable, so which one plays comes down to the deterministic tie-break. A control that finds no qualifying track has no effect, and the next refresh does not retry it.
- **Status:** Current since B5 (2026-10-20); the control rules were settled at the B5 review and corrected before commit (TD-016 items 11, 13, 14).
- **Revisit when:** numeric features make partial fits possible, or B6 evidence (skips, likes) gives the fallback rule something to compare.

### Shrinking cooldown for small libraries (D17)

- **Gain:** a small library keeps a full three-track queue; it repeats tracks after a cooldown instead of running dry, and a graded recent-play penalty makes it rotate rather than alternate two tracks.
- **Cost:** in a library of a few tracks, a track can return after only a few plays.
- **Status:** Current since B5 (2026-10-20). The cooldown is 20 plays, or the number of eligible tracks minus three, whichever is smaller (at least one). *Since the B11 review (2026-10-24):* with an explicit genre request, the genre's own plays follow the same rule over the genre's own available tracks, so a requested genre rotates instead of running out in a large library (TD-022).

### Feedback read from raw facts, per track (D10–D12)

- **Gain:** only raw facts are stored, so Feedback Policy v1's thresholds can change, and the same history can be read again, without losing evidence. Reading everything about a track in a session at once makes explicit actions reliably take precedence over playback, even across queue refreshes, and a track never counts twice.
- **Cost:** evidence is recomputed from the whole session at every refresh (cheap at session scale; measured in B11: part of a refresh, which reading and ranking the library dominates). A track heard twice in one session is judged once, by its latest explicit action or, without one, its latest playback.
- **Status:** Current since B6 (2026-10-20, TD-017).
- **Revisit when:** B11 evaluates the thresholds, or B10 needs evidence across sessions.

### Playlists: unique names, one entry per track, whole-list writes (D34)

- **Gain:**
  - Names identify playlists to the listener, as the frontend keeps them.
  - A track cannot appear twice by accident.
  - Writing a playlist's items as a whole keeps positions gap-free and lets two tracks swap without breaking the unique positions.
  - Only an explicit add saves a recommendation.
- **Cost:**
  - Two playlists cannot share a name.
  - Duplicates need a product decision before they are allowed.
  - A whole-list write costs more than moving one row (negligible for playlists of hundreds of tracks).
- **Status:** Current since B7 (2026-10-21, TD-018).
- **Revisit when:** duplicates are approved, or playlists grow to thousands of tracks (B11 measurements). *Measured in B11:* at 1,000 tracks an add, remove, or reorder takes about 60 to 70 ms (p50) and a read 15 ms. Kept.

### Playback effects of feedback (D12, D18, spec §22)

- **Gain:** the backend's state matches what the listener hears. A skip, completion, or Not for me moves on to the prepared next track, and Replay plays a past track again, as the approved frontend does.
- **Cost:** each event refreshes the queue, so upcoming occurrence ids change after every event, and history grows with replaced occurrences. A replay is an occurrence no algorithm chose; history marks it `listener-replay`.
- **Status:** Current since B6 (2026-10-20, TD-017).
- **Revisit when:** B8/B9 show the churn of occurrence ids is a problem for the frontend. *(B8: every command answers the session after its re-rank, with the current occurrence ids, so a client always has fresh ones. Whether the frontend copes is B9's to see.)*

### `BEGIN IMMEDIATE` for every transaction (TD-019)

- **Gain:** request threads, the analysis worker, and the startup scan can share one SQLite file. A read-then-write transaction no longer fails with "database is locked" when another connection commits in between; it waits its turn on the busy timeout. No use case needs retry logic.
- **Cost:** transactions serialize, reads included, so WAL's concurrent readers are given up. A long transaction would stall every request; all of them are short today (file and analysis work happen between transactions), and the full suite runs no slower.
- **Status:** Current since B8 (2026-10-21).
- **Revisit when:** B11 measures contention with thousands of tracks, or a read-heavy load appears. The alternative is a deferred `BEGIN` for read-only units of work plus retries for writes. *Measured in B11 (TD-022):* no request failed while the startup scan imported 200 files and the worker analyzed them; a start-play-Like loop took p50 138 ms and p95 320 ms meanwhile. Kept.

### Manual scans inside the request (D26)

- **Gain:** Import and Rescan answer the actual scan report, with no scan-status resource the spec's routes lack. Scans never overlap. The server keeps answering other requests meanwhile, because a scan holds no long transaction.
- **Cost:** a first import of a large folder keeps its request open until the scan ends, with no progress shown. D26 asks for background scanning; only the startup scan is fully in the background.
- **Status:** Current since B8 (2026-10-21, TD-019).
- **Revisit when:** the frontend gains a library screen that needs progress. That would mean `202 Accepted`, a scan-status resource, and keeping the last report. *B11 (TD-022):* kept; a first import of 200 five-second files took 15 s here.

### Starlette's range support instead of our own (spec §25)

- **Gain:** no custom byte-range code to get wrong. Range parsing, clamping, multipart, and `416` are the framework's, verified on the installed version.
- **Cost:** the behavior can change with an upgrade (tests pin it). Malformed ranges answer Starlette's plain text, not our envelope.
- **Status:** Current since B8 (2026-10-21).
- **Revisit when:** a Starlette upgrade changes the pinned behavior, or a browser needs something it does not do.

### Hybrid intent input (TD-020)

- **Gain:** a control's meaning never depends on its wording, and relabelling changes nothing. Only language needs interpreting, and that happens in one place, the backend, behind a port an LLM could later implement. The policy never sees text, and refusals are honest.
- **Cost:** two kinds of request instead of one. A deliberately small vocabulary means many free sentences are not understood.
- **Status:** Current since B9 (2026-10-21).
- **Revisit when:** listeners need more vocabulary, or the LLM port is approved (D30, D39).

### A refinement re-ranks what follows; the song plays on (TD-020)

- **Gain:** "music leads". The backend's queue and the UI agree, there is no forced skip that would record a false listening fact, and the next song reflects the new intent.
- **Cost:** in the mock, a refinement changed the song at once, so the integrated app feels less immediate after a Tune change.
- **Status:** Current since B9 (2026-10-21).
- **Revisit when:** listeners expect the immediate switch. A "play the new direction now" action would be a product decision.

### A past session continues as a new backend session (TD-020)

- **Gain:** D35 holds (one active session, no stale queue), and the UI keeps showing one session.
- **Cost:**
  - Each continuation adds a backend session to the history.
  - The past session's own songs can be saved to playlists, but not liked or replayed in the new one.
- **Status:** Current since B9 (2026-10-21).
- **Revisit when:** session history views need the continuations linked, or replaying a past song becomes a need.

### Conservative long-term learning (D06)

- **Gain:** one session or one skip never rewrites long-term taste.
- **Cost:** the profile adapts slowly. The 4-signal, 2-session threshold itself must later be evaluated.

### Recompute from raw history instead of updating the profile (TD-021, B10)

- **Gain:** the same history always gives the same profile. A withdrawn Like takes its change back, as a new adjustment, and old evidence can never drift the profile.
- **Cost:** each relevant event rereads the listener's history (B11 measured it: about 0.25 ms per past session, 261 ms at 1,000 sessions). After withdrawn evidence, a numeric preference can move more than one step, to what the remaining evidence supports.

### Long-term history in its own stage only (TD-021, B10)

- **Gain:** history counts once, at .15, and never fills what the listener left open in the intent stage.
- **Cost:** none found so far beyond the .15 cap itself.

### Long-term preference as positive affinity (TD-021, B10 review)

- **Gain:** a stored preference lifts what the listener has repeatedly liked without penalizing everything else. Session evidence outweighs it, and current intent outweighs both, under the locked weights and without a tie-break.
- **Cost:** a full match moves the long-term stage only from 0.5 to 1.0, so history's lift is gentler. The 0.5 neutral point is a heuristic for B11 to evaluate. *Evaluated in B11:* at 0.0 a session's Like could not outrank a stored preference; at 0.5 it does. Kept.

### Two distinct tracks before a feature preference (TD-021, B10 review)

- **Gain:** one favourite song never becomes a genre, mood, or feature preference by itself.
- **Cost:** a listener who loves only one song in a genre builds no preference for it. Its raw evidence is kept for future work. *Evaluated in B11:* a one-song listener built nothing in ten sessions, and a consistent listener's preference came in the second session.

### Reusing the last full library read (TD-022, B11)

- **Gain:** a command no longer reads and validates the whole library when nothing in it changed. That was most of every command's time from 1,000 tracks up. Exact, because every track write advances the library revision in its own transaction. Only committed reads are kept, and a newer one is never replaced by an older one (verified under concurrency at the B11 review).
- **Cost:** one table, a revision write on every track write, and a process-wide copy of the library in memory (about 1.1 KiB per track). A write to `tracks` made outside the app's repository, by hand, would not be seen until the app writes a track itself or restarts.
- **Status:** Current since B11 (2026-10-23).
- **Revisit when:** something other than the track repository writes tracks; measured features join what Policy v1 reads from the library (their writes must advance the revision); or the library is large enough that holding it in memory matters.

### Commit durability over latency (TD-022, B11 review)

- **Gain:** SQLite keeps `synchronous` at FULL, so a committed change survives a power cut or OS crash. That covers the listener's feedback, playlists, long-term profile, and audit trail.
- **Cost:** an fsync per commit. Measured, NORMAL would have improved interactive p50 from about 44 to 33 ms and p95 from about 70 to 54 ms at 1,000 tracks. The p95 budgets stay not reliably met.
- **Status:** Current, decided at the B11 review (2026-10-24).
- **Revisit when:** measurements on listeners' machines show the commit cost matters to them.

### No raw conversational text by default (D33)

- **Gain:** data minimization.
- **Cost:** past sessions cannot show exactly what the listener typed, and future intent-parser work has no stored examples to learn from.

### Fresh session after restart (D35)

- **Gain:** no stale queue or playback state is restored.
- **Cost:** the listener cannot pick up a queue exactly where it stopped.
- **Status:** Current since B4 (2026-10-20). `end_sessions_from_previous_run()` ends left-over sessions as `APP_RESTARTED`, discards their queues, and keeps their history; verified across a hard process exit (TD-015).

## Trade-off Entry Template

```text
## Trade-off Title

Date:
Related Decision:

Gain:

Cost:

Mitigation:

Revisit When:
```
