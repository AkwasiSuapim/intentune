# Risks and Open Questions

## Status

**Living Document.** Last reviewed: Phase B11, 2026-10-24 (full review in B0, 2026-10-18). Questions answered by the [Prototype 1 Decision Register](../decisions/intentune-prototype-decision-register.md) are marked **Resolved** with the decision ID.

## Product Risks

- Recommendations may feel repetitive because the catalog is small. In Prototype 1 the library is whatever the listener imports, so it may still be small; repetition is controlled by cooldown and diversity re-ranking (D17).
- Exact labels may not represent real musical similarity.
- Users may expect the product to play music directly. **Resolved for Prototype 1:** it plays the listener's own local audio.
- Explanations may sound confident even when metadata is weak. Missing and inferred features make this more likely; inferred values carry provenance and confidence (D20).
- Policy v1 weights and thresholds are heuristics. Recommendations may feel wrong until they are evaluated (B11). **Evaluated against fixed scenarios (B11, 2026-10-23; [evaluation report](../quality/evaluation-report.md)):** the five scenarios and the long-term listeners are a stored baseline, so every change shows as a reviewed difference. They are synthetic: no real listener has been measured, so the heuristics stay heuristics. Findings left to a later policy version:
  - **Exploration within a genre:** automatic exploration rarely finds a track novel enough within one requested genre, so it seldom fires there.
  - **Broad listeners:** a listener who likes broadly gets broad long-term preferences, since the gate counts support, not how distinctive it is. At .15 and as positive affinity, they lift most tracks alike.
  - **No fading:** an old long-term preference stays until negative evidence offsets it; a change of taste adds to it.

  These three need richer real features or real-listener evidence before any change. A fourth finding was fixed at the B11 review (2026-10-24), because it broke D17: a small requested genre ran out once its tracks were all within the large library's 20-play cooldown. A requested genre now has a cooldown bounded by its own tracks (TD-022).

## Technical Risks

- Refactoring may change current scoring behavior. B5 must prove complete-input legacy outputs stay identical (D38). **Mitigated (B5, 2026-10-20):** the legacy and canonical tests pass unchanged, the CLI output is unchanged, and a test proves Policy v1's intent fit equals the legacy normalized score for every CSV song.
- Audio analysis dependencies (`librosa` and its numeric stack, and any pretrained model) may be hard to install or slow on the listener's machine (Windows, Python 3.11 in the current environment). Their compatibility is unverified.
- SQLite write contention between the background worker and API requests. **Mitigated (B8, 2026-10-21, TD-019):**
  - **The problem:** with a deferred `BEGIN`, a read-then-write transaction failed with "database is locked" whenever another connection committed in between. This was reproduced.
  - **The fix:** every transaction now begins with `BEGIN IMMEDIATE` and queues on the 5-second busy timeout.
  - **Evidence:** 96 concurrent requests against a live server, scans and the worker included, ran with no errors.
  - **Cost:** reads queue too.
  - **Still open:** contention with thousands of tracks is B11's to measure. *Decided after the B8 review: `BEGIN IMMEDIATE` and WAL stay until B11 has measured; no separate read/write transactions or retry logic before then.* **Measured (B11, TD-022):** no request failed in 40 start-play-Like loops while the startup scan imported 200 files and the worker analyzed them, over 500 tracks; a whole loop took p50 138 ms and p95 320 ms. They stay.
- Large libraries: import throughput, analysis time, and full-library scoring latency are unmeasured (B11). **Measured (B11, 2026-10-23, TD-022):** at the start of B11 a command took 0.27 s (p50) at 1,000 tracks and 0.52 s at 2,000, mostly re-reading and re-scoring the library. After hardening, the slowest interactive command's p50 is 59 to 93 ms at 1,000 tracks and 140 to 186 ms at 5,000. Its p95 is 106 to 225 ms and 256 to 350 ms across five runs, against budgets of 100 and 300 ms: not reliably met at 1,000, and around the target but not reliably met at 5,000, on this noisy machine. The budgets stay as set, and SQLite stays at `synchronous` FULL (TD-022). Import runs at 10 to 15 tracks per second and analysis at 30 to 44 (five-second files) on this machine. **Still open:** measured on one Windows machine only, through the in-process client.
- Browser seeking depends on correct HTTP range support for audio; the installed Starlette behavior must be verified (B8). **Mitigated (B8):** Starlette 1.8.0's `FileResponse` handles single, open-ended, suffix, and multiple ranges, `416`, and `HEAD`; verified over a real server and pinned by tests. An upgrade that changes it fails those tests. Not yet tried in a real browser `<audio>` element (B9).
- Path traversal or arbitrary file serving through the audio route if path resolution is wrong. **Mitigated (B8):** the route takes only a track id. The managed path is built from the validated UUID and format, never from client input, and path-like ids reach no file (tested).
- *(Raised in B8, 2026-10-21.)* A local `backend/.env` written before B1's default moved still says `DATABASE_URL=sqlite:///./intentune.db` (`backend/intentune.db`, not gitignored). `python -m src.intentune.api` does not read it. A tool that loads `.env` (for example `uvicorn --env-file .env`) would quietly use that database, which git does not ignore. Update or remove that line before using such a tool. **Resolved (2026-10-21, after B8):** the local `.env` now says `sqlite:///./data/intentune.db`, and `.gitignore` covers `backend/intentune.db*` as a safeguard.
- *(Raised in B8.)* Starlette's test client warns that its httpx support is deprecated in favour of `httpx2`. A future Starlette may drop httpx, and the API tests would then need that package.
- *(Raised at the B11 review, 2026-10-24.)* The predeclared p95 budgets are not reliably met on the benchmark machine (TD-022). They stay as set, and SQLite stays at `synchronous` FULL for durability. Measurements on listeners' machines would show whether it matters.
- *(Raised in B11, 2026-10-23.)* The API keeps its last full read of the library in memory while the library is unchanged (TD-022). Every write to a track goes through the track repository, which changes the library revision. A tool that wrote to `tracks` or `track_labels` directly, outside the app, would not, so the running app would keep its read until the next write it makes itself. Nothing does that today; restart the app after editing the database by hand.
- *(Raised in B11.)* Importing on this machine is bound by opening files (about 8 ms per open, five opens per imported file), which suggests on-access antivirus scanning. Real throughput depends on the listener's machine.
- Feedback signals such as skips may be ambiguous. Policy v1 interprets them by played fraction and ignores the first 8 seconds (D10, D11). **Mitigated (B6, 2026-10-20):**
  - explicit actions take precedence over playback, per track in the session;
  - the raw facts are kept, so the thresholds can be re-evaluated (B11) and the same history read again;
  - a single skip changes only the current session and halves, never stops, exploration.
- *(Raised in B6.)* The frontend must report how far a track played (seconds and duration) for a skip to mean anything; it has no real playback yet (B9). Without those facts, a NEXT turn is recorded but is no evidence. **Resolved in B9:** songs play with real audio, and Next carries the audio element's position and duration, which the backend records as the SKIP. A song that ends is a COMPLETE.
- *(Raised in B9, 2026-10-21.)* Typed control is deliberately narrow: spec §11's commands, typed reactions, energy up and down, and the library's genres and moods. Listeners may find most free sentences "not understood". Tune opens to show what can be asked. Widening the vocabulary, or adding the LLM port (D30), is the remedy.
- *(Raised in B9.)* Energy and most moods change no ranking yet: tracks carry no measured energy, and mood tags are rare. Tune shows them as the approved design does. Listeners may expect an effect they do not get. **Mitigated at the B9 review (2026-10-22):** the vocabulary reports which dimensions the library supports. Tune marks the others as unavailable and explains why, their options do nothing, and a typed refinement of them is refused with the reason. **Still open:**
  - **Real libraries:** the importer reads genre tags only, so today every real library shows Energy and Mood as unavailable. Mood tags or measured features would make them usable.
  - **Starters:** *resolved by the consistency correction (2026-10-22):* Focus, Unwind, and Move are shown unavailable on such a library, with their reason, and send nothing; Discover stays. On a real library today, Discover is the only starter, until mood tags or measured energy exist.
  - **Past sessions:** one whose intent the library can no longer act on cannot continue; the listener starts a new session. Sessions created before this correction with a starter's mood and energy are such sessions.
- *(Raised at the B9 consistency correction, 2026-10-22.)* The capability rule covered only the three Tune dimensions. **Resolved by the readiness model (the same day):** all seven dimensions Policy v1 ranks by are judged from the library as it is, and become usable by themselves once their data exists. **Still open:**
  - **Feature coverage:** no source provides mood labels beyond genre tags, and no validated pipeline provides energy, danceability, tempo, valence, or acousticness (D21). Until one does, those dimensions stay `no_data` on real libraries. This is Prototype 1 completion work, listed in [Development Phases](development-phases.md).
  - **Unmapped fields:** `current_mood`, `listening_goal`, and `activity` are accepted and stored but not mapped into Policy v1. The vocabulary reports them as `unmapped_fields`; a deterministic mapping still needs a decision.
  - **Freshness:** the frontend reads capability when the workspace loads. A library that gains data mid-visit shows it after a reload.
- *(Raised in B10, 2026-10-22.)* Session evidence could at best tie a conflicting long-term genre preference when there was no intent. **Resolved at the review (2026-10-23):** the long-term stage now reads a stored preference as positive affinity (a mismatch is neutral, 0.5). Session evidence beats it, and current intent beats both, with the locked weights (TD-021). B11 evaluates the neutral point. **Evaluated (B11):** on the feature-complete catalog, at 0.0 one Like of a Rock track cannot move a stored Jazz preference off the first queue; at 0.5 it leads the queue, and an explicit intent beats both. 0.5 stays.
- *(Raised in B10.)* Long-term thresholds are Prototype 1 heuristics: the gate (4/2), the bounded list (3), the coherence spans, and the steps. B11 evaluates them against fixed scenarios. **Evaluated (B11):** a consistent listener gains a preference in their second session; a one-song, More-like-this-only, or rejecting listener never does; a random listener gains chance preferences from the fourth. A stricter 6 / 3 / 3 gate holds the random listener back to the tenth session and costs the consistent one a session. Kept at 4 / 2 / 2: synthetic listeners are no evidence about real ones (TD-022).
- *(Raised in B10.)* Each relevant event rereads the listener's whole history to recompute the profile. That is fine at Prototype 1 scale; B11 measures it, and incremental derivation is the remedy if needed. **Measured (B11):** with the history read in three queries, it grows by about 0.25 ms per past session: deriving takes 34 ms at 100 sessions and 261 ms at 1,000. Kept; incremental derivation is the remedy beyond about 1,000 sessions.
- *(Raised in B10.)* One favourite song could carry its genre to the gate across sessions. **Resolved at the review:** every feature-level change needs at least two distinct tracks (`min_distinct_tracks`). B11 evaluates whether it should be stricter. **Evaluated (B11):** a one-song listener builds no preference in ten sessions with 2; a stricter count would only slow consistent listeners further.
- *(Raised at the B10 review, 2026-10-23.)* More like this is no longer long-term evidence, so a listener who only steers with it never builds a profile from it. That is intended: it is a session instruction.
- *(Raised in B10.)* Numeric preferences cannot be learned from a real library yet: no pipeline provides the features. A preference only appears once one does, and nothing is invented.
- *(Raised in B9.)* A refinement re-ranks what follows while the current song plays on ("music leads"). In the mock, a refinement changed the song at once. Watch whether listeners expect the immediate change.
- Dependency drift. **Mitigated (2026-10-18):** direct dependencies are now pinned and installed. Transitive dependencies are not locked, and `pandas` is pinned but unused.
- AI output may be malformed or inconsistent. *(Future: AI is deferred.)*
- YouTube results may lack precise audio features. *(Future: YouTube is deferred.)*
- External API quotas may limit usage. *(Future.)*
- A public deployment may be abused or generate unexpected cost. *(Future: Prototype 1 is local.)*

## Data Risks

- Small catalogs can over-represent certain genres or cultures.
- User prompts may contain sensitive personal information. Mitigated by not persisting raw conversational text by default (D33).
- Adaptive profiles may overreact to a small number of actions. Mitigated by the 4-signal, 2-session gate and bounded changes (D06).
- Managed media copies roughly double the disk space used by imported music (D02).
- Database and media files could be committed by accident. **Mitigated (2026-10-18):** `.gitignore` covers `backend/data/intentune.db*` and `backend/data/media/`. A local `backend/.env` copied from the old template still points at the unignored `backend/intentune.db` until updated by hand. *(2026-10-21: updated by hand, and `backend/intentune.db*` is now ignored too.)*

## Open Product Questions

- Should users select both current mood and desired mood manually?
- Which recommendation modes should exist first? *(Partly resolved: Surprise me, More familiar, More like this, Try something different, D36.)*
- How many results should be shown by default? *(Partly resolved: three upcoming candidates are kept, D14; the UI shows one hero and at most one Up Next.)*
- Should explanations display raw point values or plain-language reasons? *(Resolved by the frontend architecture: plain language; no scores, ranks, or confidence.)*
- Can the listener continue a historical session after restart, or does any listening action start a new one? D35 says a fresh active session starts and the queue is not restored. The current frontend lets the listener reopen an earlier session from the drawer and keep going.
- What should a past session show in place of the listener's words, given that raw text is not stored by default (D33)? The current frontend shows user messages in the session history.

## Open Backend Questions

- How should missing candidate features affect score normalization? **Resolved:** omit the feature and renormalize active weights; never invent a midpoint (D21, spec §14).
- How should genre and mood similarity be represented? *(Policy v1, B5: exact match, ignoring case and surrounding space, the legacy rule. Partial genre similarity, such as "indie pop" to "pop", is not attempted.)*
- How should diversity penalties interact with relevance scores? **Resolved:** diversity is a separate re-ranking stage after the combined rank and must not override explicit intent (D07, spec §19).
- What is the first stable API response schema? **Resolved in B8 (TD-019):** [API Design](../design/api-design.md). B9 may still need to extend it for the frontend.
- What counts as "useful novelty" for letting candidate #2 play first (D15)? The spec does not define it. **Interpreted in B5 (TD-016):** something has played, #2 is not by that track's artist, and either #1 is, or #2 is less similar to it than #1. Open to revision at review.
- *(Raised in B5, 2026-10-20.)* With a genre in the intent, a library described by genre tags alone never explores. A same-genre track is identical by genre, so it is not novel, and another genre has intent fit 0, so it is not plausible. Surprise me and Try something different then raise a rate that has nothing to act on. This follows spec §19 (diversity must not override explicit intent), and exploration resumes when the intent names no genre or once numeric features exist. Should these controls be allowed to step outside an explicit genre, for example by relaxing the plausibility floor? That is a product decision. **Resolved at the B5 review (TD-016 items 11, 13, 14):** a listener control is a deterministic one-refresh directive, part of current intent.
  - Without a control, exploration stays in the requested genre.
  - Surprise me prefers novelty within the genre and sets it aside only when the genre offers none.
  - Try something different steps outside it and makes its track the next to play.
  - More familiar suppresses exploration for that refresh.
  - A refinement before the refresh supersedes the control.
  - With the genre set aside, a track nothing can be compared with gets no score. It qualifies only by an explicit fallback rule: a known genre, playable, not refused.
- *(Raised in B6, 2026-10-20.)* How should B8 carry the frontend's Next and Not for me? Today both travel as turns (`next`, `not_for_me`), and the playback facts of a skip as a SKIP event. B6 makes any combination safe:
  - a NEXT turn and a later SKIP report move playback once;
  - a Not for me turn and a Not for me event are read as one rejection.

  The route design should still pick one path per action. **Resolved in B8:**
  - **Next:** the frontend's Next is a `next` turn, with a SKIP playback event when it knows how far the track played; both are safe together.
  - **Not for me:** it may be a `not_for_me` turn or reaction; both move on and are read as one rejection.
  - **Play:** it is a `next` turn while nothing plays.
- *(Raised in B7, 2026-10-21.)* The frontend's Save opens the playlist picker and saves the current song to the playlists chosen. The backend has both a SAVE reaction and PLAYLIST_ADD (an add from a recommendation). Should B9 send the picker's saves as playlist adds only? A SAVE without a playlist would then stay unused. The frontend's playlist colour tone is not stored by the backend (D32), so B9 must keep or derive it. **Resolved in B9:** the picker's saves are playlist adds only (PLAYLIST_ADD from the playing session). The SAVE reaction stays unused, and tones are derived from the playlist id.
- *(Raised in B6.)* The frontend replays a past song from the session history. That needs the occurrence id of the earlier play, which B9 must keep or look up. **Resolved in B9 for the playing session:** each recommendation keeps the occurrence id as its `ref`. **Still open:** a past session's songs cannot be replayed, because the backend has no route to play a specific track in a new session.
- *(Raised in B5.)* "Play something from recently liked music" (spec §20) is listed among the controls that shift exploration, but no turn kind or rule exists for it. What should it do, and is it a B6 feedback-driven control or a new turn kind?
- How does the frontend's categorical intent (for example, five energy levels) map to `ListeningContext` numeric targets? **Resolved in B9 (TD-020):** mood maps to `temporary_moods` (the curated design moods in Tune), genre to `temporary_genres` (the library's genres), and energy to `target_energy` on a fixed scale from 0.1 to 0.9, served by `GET /listening/vocabulary`.
- Where do the frontend's typed messages and quick-action labels become structured turn variants, given that React must not parse language and the backend accepts only limited deterministic commands (D30)? *(Still open after B4: `SessionService.apply_turn()` accepts structured turn kinds and `ListeningContext` only, so the mapping has to happen before it.)* **Resolved in B9 (the user's hybrid input decision):**
  - Starters and quick actions are sent as their meaning.
  - Typed words are sent unread, as a `message` turn.
  - The backend's deterministic `IntentInterpreter` maps them onto the same use cases, and refuses what it cannot read.
- *(Raised in B4, 2026-10-20.)* Which call starts a session for the listener at startup or on Play (the "next listening action" of D35)? The B8 startup must call `end_sessions_from_previous_run()` before any request is served. **Resolved in B8:** startup ends a previous run's sessions before serving. `POST /sessions` starts a fresh one with the listener's intent, and a `next` turn while nothing plays is Play.
- The B9 guidance is to satisfy the existing frontend service interface. That interface has no methods for reactions, playback events, or playlist CRUD, which Prototype 1 requires. How far may B9 extend it? **Resolved in B9:** it was extended in place, without rewriting the reducers or components: session identity, structured requests, `react()`, `savePlaylists()`, `createPlaylist()`, and a `not_understood` answer.
- How is artwork extracted in B2 served to the frontend? The route list has no artwork route. *B2 (2026-10-19) does not extract artwork. Extraction waits until there is a way to serve it, so B8 should settle this first.* *(B8: still open. No artwork route was added, since the spec's routes have none; the frontend needs one in B9, or a placeholder.)*
- *(Raised in B3, 2026-10-20.)* D26 says scanning **and** analysis run in the background. B3 was scoped to analysis only, so scans still run synchronously when called. Which phase makes scanning non-blocking? B8 could run a scan off the request thread, or a `RESCAN_SOURCE` job kind could be added. **Partly resolved in B8:**
  - **Startup scan:** it runs in a background thread.
  - **Manual Import and Rescan:** these run within their request, on the server's thread pool, so other requests are still served, and answer the scan report. A first import of a large folder keeps that request open until it ends.
  - **Still open:** whether to make them `202 Accepted` with a scan-status resource. The spec's routes have none, so that waits for the frontend to need progress. *Decided after the B8 review (2026-10-21): they stay synchronous for Prototype 1, and B11 revisits them, unless B9 integration gives concrete UX evidence sooner.* **Revisited (B11, TD-022):** they stay synchronous. A first import keeps its request open while it runs (15 s for 200 five-second files here), which is acceptable until the library screen needs progress.
- *(Raised in B3.)* Tempo, key, and loudness in LUFS are planned features, but they are estimates (LUFS is a standard, but needs a K-weighting filter). Which algorithms, and evaluated against what, before they are trusted? This needs the B11 evaluation set. Semantic features (energy, mood, danceability, valence, acousticness) still need a validated model, or stay `NULL` (D21).
- *(Raised in B3.)* libsndfile cannot decode M4A (AAC/ALAC), so M4A tracks are imported and playable but never analyzed. Is a larger decoder (for example PyAV) worth it, given how common M4A is in real libraries?
- How does `GET /api/v1/library/sources` let the listener recognize a folder they registered, given the rule that raw local paths are never exposed to the frontend? `POST /api/v1/library/sources` necessarily receives a path from the client. **Resolved in B8:** each source shows its folder's own name (`Music`), never the full path. Two folders with the same name are told apart by when they were added.
- *(Raised in B8.)* The API carries `rank` and `score` but no explanation for a recommendation, because Policy v1's reasons are not stored. The frontend's `why` needs either stored reasons or a backend rule to phrase them. B9 must decide, without inventing reasons.

## Open Persistence Questions

- Do first users need accounts? **Resolved:** no; one generated local listener (D01).
- Should anonymous sessions persist across browser visits? **Resolved:** session history persists; the active queue does not (D35).
- Should raw prompts be stored? **Resolved:** not by default (D33).
- Which feedback actions should influence profiles? **Resolved:** session ranking changes immediately (D05); permanent change needs at least 4 consistent strong signals across at least 2 sessions (D06).
- Where should the database file live? **Resolved:** `backend/data/intentune.db` (spec §5); `.env.example` updated 2026-10-18. **Resolved in B1 (2026-10-19, TD-012):** a relative path resolves against the backend root, as the CSV adapter does, not the working directory, and the same file is the default when `DATABASE_URL` is unset.

## Open AI Questions

*Future: AI is deferred (D39).*

- Which provider will be used?
- What structured schema will the model return?
- When should the chatbot ask a clarifying question?
- What deterministic fallback should exist?

## Open YouTube Questions

*Future: external providers are deferred (D39).*

- How should search queries be generated?
- How many API calls should one recommendation request make?
- How should duplicates and long playlist videos be handled?
- Which metadata can be used safely for ranking?

## Review Rule

Review this file at the beginning and end of every development phase.
