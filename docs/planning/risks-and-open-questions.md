# Risks and Open Questions

## Status

**Living Document.** Last reviewed: Phase B8, 2026-10-21 (full review in B0, 2026-10-18). Questions answered by the [Prototype 1 Decision Register](../decisions/intentune-prototype-decision-register.md) are marked **Resolved** with the decision ID.

## Product Risks

- Recommendations may feel repetitive because the catalog is small. In Prototype 1 the library is whatever the listener imports, so it may still be small; repetition is controlled by cooldown and diversity re-ranking (D17).
- Exact labels may not represent real musical similarity.
- Users may expect the product to play music directly. **Resolved for Prototype 1:** it plays the listener's own local audio.
- Explanations may sound confident even when metadata is weak. Missing and inferred features make this more likely; inferred values carry provenance and confidence (D20).
- Policy v1 weights and thresholds are heuristics. Recommendations may feel wrong until they are evaluated (B11).

## Technical Risks

- Refactoring may change current scoring behavior. B5 must prove complete-input legacy outputs stay identical (D38). **Mitigated (B5, 2026-10-20):** the legacy and canonical tests pass unchanged, the CLI output is unchanged, and a test proves Policy v1's intent fit equals the legacy normalized score for every CSV song.
- Audio analysis dependencies (`librosa` and its numeric stack, and any pretrained model) may be hard to install or slow on the listener's machine (Windows, Python 3.11 in the current environment). Their compatibility is unverified.
- SQLite write contention between the background worker and API requests. **Mitigated (B8, 2026-10-21, TD-019):**
  - **The problem:** with a deferred `BEGIN`, a read-then-write transaction failed with "database is locked" whenever another connection committed in between. This was reproduced.
  - **The fix:** every transaction now begins with `BEGIN IMMEDIATE` and queues on the 5-second busy timeout.
  - **Evidence:** 96 concurrent requests against a live server, scans and the worker included, ran with no errors.
  - **Cost:** reads queue too.
  - **Still open:** contention with thousands of tracks is B11's to measure.
- Large libraries: import throughput, analysis time, and full-library scoring latency are unmeasured (B11).
- Browser seeking depends on correct HTTP range support for audio; the installed Starlette behavior must be verified (B8). **Mitigated (B8):** Starlette 1.8.0's `FileResponse` handles single, open-ended, suffix, and multiple ranges, `416`, and `HEAD`; verified over a real server and pinned by tests. An upgrade that changes it fails those tests. Not yet tried in a real browser `<audio>` element (B9).
- Path traversal or arbitrary file serving through the audio route if path resolution is wrong. **Mitigated (B8):** the route takes only a track id. The managed path is built from the validated UUID and format, never from client input, and path-like ids reach no file (tested).
- *(Raised in B8, 2026-10-21.)* A local `backend/.env` written before B1's default moved still says `DATABASE_URL=sqlite:///./intentune.db` (`backend/intentune.db`, not gitignored). `python -m src.intentune.api` does not read it. A tool that loads `.env` (for example `uvicorn --env-file .env`) would quietly use that database, which git does not ignore. Update or remove that line before using such a tool.
- *(Raised in B8.)* Starlette's test client warns that its httpx support is deprecated in favour of `httpx2`. A future Starlette may drop httpx, and the API tests would then need that package.
- Feedback signals such as skips may be ambiguous. Policy v1 interprets them by played fraction and ignores the first 8 seconds (D10, D11). **Mitigated (B6, 2026-10-20):**
  - explicit actions take precedence over playback, per track in the session;
  - the raw facts are kept, so the thresholds can be re-evaluated (B11) and the same history read again;
  - a single skip changes only the current session and halves, never stops, exploration.
- *(Raised in B6.)* The frontend must report how far a track played (seconds and duration) for a skip to mean anything; it has no real playback yet (B9). Without those facts, a NEXT turn is recorded but is no evidence.
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
- Database and media files could be committed by accident. **Mitigated (2026-10-18):** `.gitignore` covers `backend/data/intentune.db*` and `backend/data/media/`. A local `backend/.env` copied from the old template still points at the unignored `backend/intentune.db` until updated by hand.

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
- *(Raised in B7, 2026-10-21.)* The frontend's Save opens the playlist picker and saves the current song to the playlists chosen. The backend has both a SAVE reaction and PLAYLIST_ADD (an add from a recommendation). Should B9 send the picker's saves as playlist adds only? A SAVE without a playlist would then stay unused. The frontend's playlist colour tone is not stored by the backend (D32), so B9 must keep or derive it.
- *(Raised in B6.)* The frontend replays a past song from the session history. That needs the occurrence id of the earlier play, which B9 must keep or look up.
- *(Raised in B5.)* "Play something from recently liked music" (spec §20) is listed among the controls that shift exploration, but no turn kind or rule exists for it. What should it do, and is it a B6 feedback-driven control or a new turn kind?
- How does the frontend's categorical intent (for example, five energy levels) map to `ListeningContext` numeric targets?
- Where do the frontend's typed messages and quick-action labels become structured turn variants, given that React must not parse language and the backend accepts only limited deterministic commands (D30)? *(Still open after B4: `SessionService.apply_turn()` accepts structured turn kinds and `ListeningContext` only, so the mapping has to happen before it.)*
- *(Raised in B4, 2026-10-20.)* Which call starts a session for the listener at startup or on Play (the "next listening action" of D35)? The B8 startup must call `end_sessions_from_previous_run()` before any request is served. **Resolved in B8:** startup ends a previous run's sessions before serving. `POST /sessions` starts a fresh one with the listener's intent, and a `next` turn while nothing plays is Play.
- The B9 guidance is to satisfy the existing frontend service interface. That interface has no methods for reactions, playback events, or playlist CRUD, which Prototype 1 requires. How far may B9 extend it?
- How is artwork extracted in B2 served to the frontend? The route list has no artwork route. *B2 (2026-10-19) does not extract artwork. Extraction waits until there is a way to serve it, so B8 should settle this first.* *(B8: still open. No artwork route was added, since the spec's routes have none; the frontend needs one in B9, or a placeholder.)*
- *(Raised in B3, 2026-10-20.)* D26 says scanning **and** analysis run in the background. B3 was scoped to analysis only, so scans still run synchronously when called. Which phase makes scanning non-blocking? B8 could run a scan off the request thread, or a `RESCAN_SOURCE` job kind could be added. **Partly resolved in B8:**
  - **Startup scan:** it runs in a background thread.
  - **Manual Import and Rescan:** these run within their request, on the server's thread pool, so other requests are still served, and answer the scan report. A first import of a large folder keeps that request open until it ends.
  - **Still open:** whether to make them `202 Accepted` with a scan-status resource. The spec's routes have none, so that waits for the frontend to need progress.
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
