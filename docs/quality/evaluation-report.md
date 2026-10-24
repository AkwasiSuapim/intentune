# Evaluation Report

## Status

**Current** (Phase B11, 2026-10-23; review corrections 2026-10-24). This covers the Prototype 1 backend at `a5e0525` (B10) with B11's changes. Everything was measured on one machine:
- Windows 11 (10.0.26300), Python 3.11.9, SQLite 3.45.1, 12 logical CPUs.
- Absolute timings depend on the machine, and this one is noisy (run-to-run variation is shown below).
- The tools are in the repository, so every figure can be measured again.

Decisions taken on these results: [TD-022](../decisions/technical-decisions.md#td-022-b11-evaluation-and-hardening).

## How to Reproduce

From `backend/`, with the virtual environment active:

```text
python -m evaluation.performance --runs 3     # about 25 minutes; --json PATH keeps the raw figures
python -m evaluation.scenarios --check        # about 10 seconds; compares with evaluation/baselines/scenarios.json
```

`--only sizes adaptation import contention playlist` runs some parts. Both tools build scratch databases with synthetic libraries and never open `backend/data`. The synthetic values never reach a real track (D21).

What is measured, and how:
- **Library size** (100 to 5,000 tracks). The tracks are what the importer gives: a genre each, a mood for about a third, about four tracks per artist, and no managed audio.
  - **decide:** Policy v1 alone, in memory, with an intent, 10 pieces of evidence, and 20 recent plays.
  - **refresh:** a queue refresh through the real services, reading the library every time. That is the cost right after the library has changed.
  - **The listening loop:** over HTTP through the in-process client, as the frontend drives it. The interactive commands are those that re-rank the queue: start, play, Like, refine, and Next with the player's facts.
    - Each loop is a new session, so the history grows by one session per loop.
    - The first loop after startup is reported on its own (cold), a second warms up, and then 30 loops are timed.
    - Each size is measured three times, and the median run is reported with every run's figures.
  - **Memory:** peak Python allocation (tracemalloc) during one refresh, and what the kept library read holds.
  - **Restart:** startup on the populated database, and what is still there.
- **Long-term adaptation:** histories of 10 to 1,000 sessions, each with two Likes, over 600 tracks. Measured: deriving the profile, and one whole Like.
- **Import and analysis:** 200 real FLAC files of 5 seconds, with tags, scanned, rescanned, and analyzed by the real services.
- **Contention:** start, play, and Like loops while the startup scan imports and the analysis worker runs.
- **Playlists:** a playlist built to 1,000 tracks one add at a time, then add, read, reorder, and remove at that size.
- **Algorithm scenarios:** see [Algorithm Evaluation](#algorithm-evaluation).

## Budgets

| Budget | Value | Why |
|---|---|---|
| Interactive command p95, 1,000 tracks | 100 ms | about the threshold at which a response feels immediate |
| Interactive command p95, 5,000 tracks | 300 ms | well under the 400 ms after which the frontend shows "Working on it…" |
| Startup on a populated database | 5 s | |

These are Prototype 1 engineering targets, set before the first measurement, for a steady-state command (not the first after startup). The budgeted figure is strict: the slowest of the five commands' p95 values, each the second-largest of 30 samples.

## Summary

| Measure | Result |
|---|---|
| Interactive p95 at 1,000 tracks | **Not reliably met on this machine:** 114 ms in the final run's median (106 to 225 ms across five runs), against 100 ms. In the final run's three runs, the slowest command's p50 was 59 to 93 ms. |
| Interactive p95 at 5,000 tracks | **Around the target, not reliably met:** 323 ms in the final run's median (256 to 350 ms across five runs), against 300 ms. In the final run's three runs, the slowest command's p50 was 140 to 186 ms. |
| Startup on a populated database | **Comfortably within:** 0.07 to 0.32 s; nothing lost (below). |
| Before and after B11 | About 4 to 7 times faster at 1,000 to 2,000 tracks: the slowest interactive p50 went from 268 to 65 ms at 1,000 tracks, and from 517 to 74 ms at 2,000 ([below](#before-and-after-hardening)). |
| Contention | No request failed while the scan imported and the worker analyzed. |
| Algorithm outputs | Unchanged by the optimizations: 1,500 recorded Policy v1 decisions were identical before and after them. The later requested-genre correction changes 152 of them by design ([below](#corrections-at-the-b11-review)). |

The tail is mostly this machine's noise, not the library: across the same runs, a 100-track library's p95 was 72 to 135 ms. The budgets were set before the first measurement and stay as they were. The remedies that were measured and not applied are under [Options](#options-measured-and-not-taken).

The latency figures in this report were measured before the review corrections. Those add about 6 ms to `decide()` at 5,000 tracks when a genre is requested, and nothing otherwise.

## Results by Library Size

The final run (`--runs 3`, 30 timed loops per run):

| Tracks | decide p50 / p95 ms | refresh p50 / p95 ms | interactive p95 ms (median run) | each run's interactive p50 / p95 ms | refresh peak KiB | kept read KiB | startup s | database MiB |
|---|---|---|---|---|---|---|---|---|
| 100 | 1.4 / 2.2 | 16 / 82 | 103 | 65 / 91, 66 / 119, 60 / 103 | 285 | | 0.32 | 0.7 |
| 500 | 4.2 / 6.1 | 48 / 108 | 111 | 83 / 105, 69 / 141, 76 / 111 | 886 | | 0.10 | 1.0 |
| 1,000 | 5.2 / 10.8 | 63 / 136 | 114 | 93 / 225, 65 / 114, 59 / 106 | 1,858 | 1,095 | 0.07 | 1.4 |
| 2,000 | 14.0 / 40.1 | 121 / 238 | 166 | 78 / 164, 73 / 173, 74 / 166 | 3,850 | | 0.08 | 2.2 |
| 5,000 | 22.7 / 31.6 | 348 / 472 | 323 | 176 / 323, 186 / 350, 140 / 320 | 9,117 | 5,263 | 0.08 | 4.4 |

The kept read is measured with `--only sizes --sizes 1000 5000`; it holds about 1.1 KiB per track. The database size includes the run's sessions.

Steady state per endpoint, p50 / p95 ms (the median run):

| Tracks | start | play | like | refine | next with facts | list sessions | session detail | vocabulary | tracks page |
|---|---|---|---|---|---|---|---|---|---|
| 100 | 44 / 83 | 28 / 32 | 60 / 101 | 33 / 80 | 57 / 103 | 4.7 / 6.7 | 9.6 / 13 | 3.8 / 5.5 | 4.0 / 6.1 |
| 500 | 46 / 59 | 39 / 51 | 75 / 111 | 47 / 72 | 76 / 99 | 5.7 / 8.8 | 13 / 20 | 9.3 / 15 | 5.6 / 8.8 |
| 1,000 | 40 / 67 | 30 / 54 | 54 / 97 | 45 / 67 | 65 / 114 | 4.1 / 6.6 | 9.6 / 14 | 9.5 / 16 | 3.7 / 6.1 |
| 2,000 | 59 / 114 | 45 / 79 | 71 / 110 | 63 / 133 | 74 / 166 | 3.7 / 5.6 | 8.6 / 12 | 17 / 22 | 3.7 / 6.5 |
| 5,000 | 138 / 323 | 76 / 136 | 103 / 144 | 117 / 195 | 176 / 311 | 5.0 / 11 | 9.9 / 21 | 36 / 54 | 4.4 / 5.8 |

The first loop after startup (cold), ms:

| Tracks | start | play | like | refine | next with facts | vocabulary |
|---|---|---|---|---|---|---|
| 1,000 | 67 | 47 | 64 | 41 | 42 | 7 |
| 5,000 | 133 | 82 | 76 | 99 | 215 | 30 |

What remains, from profiles:
- **Building candidates:** at 5,000 tracks, building Policy v1's candidates from the kept read is the largest piece of a refresh (about 40 ms), ahead of `decide()` (about 20 ms).
- **Commits:** a command makes three or four, at 1 to 10 ms each on this disk.
- **Like and Next with facts** also recompute the long-term profile from the history, which grows by one session per loop here.
- **Next with facts at 5,000 tracks:** its p50 (176 ms) is not a separate cost. In-thread, Like and Next with facts both take a median of about 95 ms, with single calls from 61 to 233 ms.

## Before and After Hardening

The same harness, with the same synthetic libraries, at the start of B11 (before any app change) and at the end. The baseline was timed without warm-up, so p50 values are compared.

| Measure (p50) | Before | After |
|---|---|---|
| decide, 1,000 tracks | 101 ms | 5 ms |
| decide, 2,000 tracks | 190 ms | 14 ms |
| refresh with a fresh read, 1,000 / 2,000 tracks | 129 / 277 ms | 63 / 121 ms |
| slowest interactive command, 1,000 tracks | 268 ms (Like) | 65 ms |
| slowest interactive command, 2,000 tracks | 517 ms (refine) | 74 ms |
| vocabulary, 1,000 / 2,000 tracks | 66 / 135 ms | 9 / 17 ms |
| tracks page, 1,000 / 2,000 tracks | 63 / 166 ms | 4 / 4 ms |
| deriving the long-term profile, 100 / 300 sessions | 129 / 343 ms | 34 / 76 ms |
| a whole Like, 300 past sessions | 525 ms | 129 ms |

What made the difference, measured cause by cause (TD-022 has each change):
- **Re-reading the library:** an unchanged library was read and validated on every command, twice for a start or refinement. Now each command reads it once, and the API reuses its last read while no track has changed.
- **Policy v1's diversity step:** it computed penalties for every candidate three times. It now stops once no later candidate can win.
- **Scoring:** a candidate's targets were rebuilt per candidate; now they are built once per refresh, and alike candidates share a score.
- **Building records:** ORM records were built for every track, label, and history row; now these are plain rows.
- **Long-term adaptation:** it read three queries per past session, and the whole library.

## Long-Term Adaptation and History

| Past sessions | feedback events | first adapt ms | derive p50 / p95 ms | a whole Like ms | database MiB |
|---|---|---|---|---|---|
| 10 | 20 | 17 | 6 / 10 | 72 | 0.8 |
| 100 | 200 | 64 | 34 / 53 | 181 | 1.1 |
| 300 | 600 | 104 | 76 / 183 | 129 | 1.7 |
| 1,000 | 2,000 | 363 | 261 / 363 | 364 | 4.1 |

- **Derivation cost:** it grows linearly, by about 0.25 ms per past session. Each relevant event (feedback, Not for me, Next's skip) pays it once.
- **Storage:** raw history costs about 3.4 KiB per session here (one turn, three occurrences, two events).
- **Retention:** the history is kept in full (TD-022). A thousand sessions take a few MiB and a quarter of a second to derive from.

## Import, Analysis, and Disk

- **Import:**
  - 200 FLAC files of 5 s took 15.4 s (13 tracks per second; 10 to 15 across runs), and an unchanged rescan took 0.03 s.
  - Opening files dominates: about 8 ms per open, with five opens per imported file (reading its tags, hashing it, and the verified copy). That suggests on-access antivirus scanning, so throughput depends on the listener's machine.
  - The copy is verified and flushed to disk by design.
- **Analysis:** 44 tracks per second (221 s of audio per second; 30 to 44 across runs).
- **Managed copies:** they took exactly the bytes of their sources (16,484,091 of 16,484,091): one more copy of the library (D02).

## Contention

- **The load:** 40 start-play-Like loops ran while the startup scan imported 200 files and the worker analyzed them, over 500 seeded tracks. All 40 overlapped the scan, which imported 24 tracks meanwhile.
- **Result:** no errors. A whole loop (three commands) took p50 138 ms, p95 320 ms, max 653 ms.
- **`BEGIN IMMEDIATE`:** commands queue briefly behind the scan's short transactions (TD-019); kept.

At the start of B11 this measurement reported 7 errors. They were the harness's, not the app's. Its synthetic tracks have no managed audio, so the worker rightly marked them `MISSING_MANAGED_FILE`. Whole genres then became unavailable, and the app rightly answered `422 INTENT_UNAVAILABLE`. The harness now seeds them as already analyzed.

## Playlists

Playlists use whole-list writes (TD-018). At 1,000 tracks:

| Operation | p50 / p95 ms |
|---|---|
| add a track | 61 / 134 |
| read | 15 / 56 |
| reorder | 69 / 132 |
| remove a track | 61 / 138 |

Building it to 1,000 tracks one add at a time took 43 s, because each add rewrites the list. That is fine for adds made one at a time by a listener. It grows linearly with the playlist; revisit for playlists of several thousand tracks.

## Restart and Migrations

- **Restart** (spec §30 items 13–14), with every library size above: the restarted app started in 0.07 to 0.32 s, kept every track and every session, and ended every session left open.
- **End-to-end test** (`tests/test_restart_and_upgrade.py`): a library imported over the API, a playlist, feedback in two sessions, and the long-term profile they built, with a session left playing. After a restart:
  - the tracks, metadata, playlist, turns, feedback events, profile, and adjustments are exactly as they were;
  - the open session ended as `app_restarted`, with nothing playing or queued;
  - a new session starts with a fresh queue, and audio still streams.
- **Migrations on existing data:**
  - A database written at the first library migration (`2540be2956b8`), with rows as B2 wrote them, upgrades through every later revision at the app's startup. Its tracks, labels, listener, vocabulary, and a new session then work.
  - Each data-carrying migration (B3, B5, B7, B9, B10, B11) also has its own round-trip test.

## Algorithm Evaluation

`python -m evaluation.scenarios` runs these fixed scenarios. Its output is stored as `backend/evaluation/baselines/scenarios.json`, and a test fails whenever either policy changes it. So an algorithm change arrives as a reviewed difference, never as a claimed improvement (testing strategy).

### Policy v1 on a feature-complete catalog

- **The catalog:** 240 synthetic tracks, 20 per genre, with energy, danceability, tempo, valence, and acousticness clustered by genre, and a mood derived from them.
- **Today's imported tracks have none of these features** (D21), so this part shows what the policy does with them, not what a library does today.
- **The listener:** plays the first queued track to the end, twelve times, with the queue refreshed after each play.

| Scenario | intent | first queue | intent fit, mean / min | mean distance from the targets | mood match | artists in 12 plays |
|---|---|---|---|---|---|---|
| study/calm | moods Calm, Focused; energy 0.3; acousticness 0.6 | Lofi 15, Jazz 09, Jazz 05 | 0.977 / 0.963 | energy 0.039, acousticness 0.063 | 1.0 | 7 |
| workout/high energy | mood Driven; energy 0.9; tempo 140 | Metal 14, Rock 08, Electronic 15 | 0.976 / 0.942 | energy 0.040, tempo 6.2 BPM | 1.0 | 8 |
| party/dance | mood Joyful; energy 0.8; danceability 0.85 | Afrobeats 12, Hip-Hop 14, Pop 06 | 0.980 / 0.957 | energy 0.037, danceability 0.032 | 1.0 | 10 |
| relax | mood Calm; energy 0.2; valence 0.5; acousticness 0.8 | Ambient 18, Classical 04, Jazz 00 | 0.968 / 0.951 | energy 0.036, valence 0.094, acousticness 0.055 | 1.0 | 7 |
| discovery | genre Jazz, with three controls | Jazz 00, Jazz 04, Jazz 08 | 0.917 / 0.0 | (none targeted) | | 6 |

No scenario repeated a track in twelve plays.

**Feedback probe:** on the first queue, Like the second track, or reject the first. The figures are the mean similarity of the next queue to that track:

| Scenario | Like: before → after | Not for me: before → after |
|---|---|---|
| study/calm | 0.82 → 0.94 | 0.71 → 0.47 |
| workout/high energy | 0.72 → 0.85 | 0.73 → 0.71 |
| party/dance | 0.71 → 0.73 | 0.72 → 0.72 |
| relax | 0.72 → 0.95 | 0.71 → 0.70 |

The rejected track never stays queued. A Not for me moves the rest of the queue little when the intent itself asks for tracks like the rejected one: intent weighs 0.55, session evidence 0.30.

**Discovery:** a Jazz session with a control at refreshes 3, 6, and 9.
- **Surprise me** put a novel Jazz track in the last slot.
- **Try something different** put Lofi first, and it played. This is the session's one play outside the intent, so the minimum intent fit is 0.
- **More familiar** explored nothing.

**Automatic exploration:** in a 60-play Jazz session with no controls, it never fired, although its rate is 0.10. The random draw fell under the rate 8 times. Each time, no Jazz track was novel enough:
- **early on:** every remaining Jazz track shared an artist with, or was at least 0.80 similar to, what just played or was queued;
- **once every Jazz track had played:** the only eligible Jazz tracks were the few the cooldown had released.

**Leaving the genre:** before the review's correction, every Jazz track was within the 20-play cooldown from about the 20th play, and the session left Jazz at play 21, briefly (genre match 0.97). Now the genre keeps rotating through its own tracks (genre match 1.0); see [Corrections at the B11 Review](#corrections-at-the-b11-review).

### What a library as imported today can act on

Genre and mood only. The capability rule refuses each scenario's measured targets:
- study/calm: energy and acousticness;
- workout: energy and tempo;
- party: energy and danceability;
- relax: energy, valence, and acousticness;
- discovery: nothing.

The measured scenarios therefore cannot be asked for yet; that waits for a validated feature pipeline (Prototype 1 completion work).

### The long-term neutral point (TD-021)

A stored Jazz preference against what the session says; the genres of the first queue are shown:

| Condition | neutral 0.0 (B10 as first built) | neutral 0.5 (Policy v1) |
|---|---|---|
| nothing said this session | Jazz, Jazz, Jazz | Jazz, Jazz, Jazz |
| one Like of a Rock track this session | Jazz, Jazz, Jazz | Rock, Jazz, Rock |
| the intent asks for Ambient | Ambient, Ambient, Ambient | Ambient, Ambient, Ambient |

At 0.0, history outranks what the listener did this session; at 0.5 it does not, and explicit intent beats both. 0.5 is kept.

### Long-Term Adaptation Policy v1 listeners

- **The library:** 72 labelled tracks (12 genres × 6, each with its genre's mood).
- **The run:** ten sessions per listener, through the real session and adaptation services, adapting after every recorded fact.

| Listener | adaptation-v1 (4 / 2 / 2): first session with a preference, final profile | stricter gate (6 / 3 / 3) |
|---|---|---|
| consistent: two different Jazz tracks liked a session | session 2: Jazz, Focused | session 3: Jazz, Focused |
| one song: the same Jazz track every session | never | never |
| random: two random tracks a session | session 4: Rock; Calm, Driven, Joyful | session 10: Calm, Joyful |
| More like this only, on Jazz tracks | never | never |
| changing: Jazz for five sessions, then Rock | session 2: Jazz, then Rock added at session 7; Driven, Focused | session 3: Jazz, then Rock added at session 8 |
| rejecting: Not for me on two Metal tracks a session | never | never |

**Numeric rule** (energy; `derive_profile()` directly, since no imported track has energy):
- **steady:** two tracks at 0.85 and 0.90 a session set 0.875 at session 2, and it then stays;
- **scattered:** 0.20 and 0.90 each session set nothing in ten sessions;
- **one song:** the same high-energy track every session set nothing.

**Reading:**
- **The gate does what B10 meant:** one song, More like this, and rejections never become preferences, and a consistent listener's do in the second session.
- **A random listener gains chance preferences.** The gate counts support, not how distinctive it is. Moods have few values here, so random likes reach 4 quickly. At .15, as positive affinity, preferences on most moods lift most tracks alike.
- **A stricter gate** delays the chance preferences to the tenth session, but costs every consistent listener a session.
- **No fading:** a change of taste adds to the profile and never replaces the old preference without negative evidence.
- **The decision:** synthetic listeners are no evidence about real ones, so adaptation-v1 stays at 4 / 2 / 2 (TD-022).

### Findings left unresolved

These are reported, not fixed: changing them needs richer real features, or evidence from real listeners.
- Automatic exploration rarely finds a track novel enough within one requested genre.
- A listener who likes broadly gets broad long-term preferences.
- Old long-term preferences never fade without negative evidence.

A fourth finding was fixed at the review, because it broke an approved rule (D17): a requested genre with as few tracks as the 20-play cooldown ran out ([below](#corrections-at-the-b11-review)).

## Options Measured and Not Taken

| Option | Measured effect | Why not taken |
|---|---|---|
| SQLite `synchronous = NORMAL` (WAL) | interactive p50 44 → 33 ms and p95 70 → 54 ms at 1,000 tracks (250 samples each) | Rejected at the review: FULL stays the Prototype 1 setting. With NORMAL, a power cut or OS crash could lose the last committed transactions. The gain does not justify that for the listener's state: feedback, playlists, the long-term profile, and its audit trail. The p95 budgets stay not reliably met. |
| Caching candidates with the kept read | about 40 ms of a 5,000-track refresh | Another cache, for the top of the target range; not needed below about 2,000 tracks. |
| Disabling garbage collection, or WAL auto-checkpoints | no material change in the tail | |

## Corrections at the B11 Review

Made on 2026-10-24 (TD-022, decisions 4 to 6 and 8).

### A requested genre no longer runs out

- **The cause:** Policy v1 held back the most recent plays with one window, set by the whole library (up to 20 plays). In a large library, a requested genre of 20 tracks or fewer was entirely within it after enough plays, and the queue left the genre. D17 says a finite library repeats after a cooldown, and a requested genre is the finite library the listener asked for.
- **The correction:** with an explicit genre request, the genre's own plays are held back only as long as its available tracks allow, after the Not-for-me exclusions. All but a queue's worth stay cooling, and the older ones return in turn, least recently played first.
  - It only releases tracks earlier.
  - The track playing is never released.
  - Tracks outside the genre, sessions without a genre request, the global cooldown, ranking, diversity, exploration, and Replay are unchanged.
- **The tests:** each simulates a 200-track library with a requested genre of 20, 8, 2, or 1 tracks, past the old exhaustion point.
  - Queues stay in the genre, and each track comes back in turn.
  - Two tracks alternate, and a single track returns whenever it is not playing.
  - A rejected track stays out.
  - Without a genre request, or with a genre larger than the cooldown, nothing comes back within 20 plays, as before.
- **The effect on recorded decisions:** 152 of the 1,500 changed, every one where the correction releases a requested track.
- **The effect on the scenarios:** only the 60-play Jazz session changed, its genre match going from 0.97 to 1.0. That is the one baseline update.
- **Cost:** about 6 ms of `decide()` at 5,000 tracks, only with a genre request.

### The library snapshot under concurrent access

- **What was found:** the snapshot already checked the revision on every read, so it never served a stale library. But two refreshes finishing in reverse order could leave the older read installed; only `BEGIN IMMEDIATE`'s serialization prevented that, by accident. And a transaction that had written tracks kept its own uncommitted read.
- **What changed:**
  - **The revision:** an integer the track repository advances with every write.
  - **No uncommitted reads:** a transaction that has written keeps nothing, so a rollback neither publishes nor invalidates.
  - **No going backwards:** `keep()` installs a read only if it is newer, under a lock, and kept values are immutable.
- **The tests:**
  - an older read finishing last never replaces a newer one;
  - eight threads publishing 200 revisions in any order leave the newest installed;
  - three readers alongside a writer never see a library older than a commit that finished before the read began, checked after each of 40 commits;
  - a rollback leaves the kept read valid;
  - only the track repository writes the track tables, and each of its writes advances the revision.
- **For future work:** when measured features join what Policy v1 reads from the library, their writes must advance the revision too.

### SQLite durability

FULL stays; see [Options](#options-measured-and-not-taken).

## Limits of This Evaluation

- **One Windows machine, which is noisy:** the same measurement varies by up to 2× between runs.
- **The in-process test client:** no network or browser in the latency figures.
- **The synthetic libraries:** their tracks have no audio, so commands never touch audio files. Import and analysis use real files.
- **The algorithm scenarios:** synthetic catalogs and listeners, not people. They pin behaviour and expose its consequences; they do not show that recommendations are good.
