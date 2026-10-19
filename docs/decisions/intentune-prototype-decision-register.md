# Intentune Prototype 1 — Decision Register

**Status:** Approved

| ID | Decision | Main trade-off |
|---|---|---|
| D01 | No production authentication; one generated local listener identity. | Faster prototype; auth deferred. |
| D02 | Import audio into an Intentune-managed local media library. | Uses more disk but survives source deletion. |
| D03 | Multiple source folders feed one logical library. | Better pool; requires dedupe/rescan logic. |
| D04 | Recommendation uses metadata + session context + user behavior + history. | Better personalization; more explicit signal handling. |
| D05 | Session feedback changes ranking immediately. | Responsive without rewriting permanent taste. |
| D06 | Long-term learning requires >=4 consistent strong signals across >=2 sessions. | Conservative; threshold must later be evaluated. |
| D07 | Ranking is staged: eligibility -> intent -> session -> long-term -> diversity -> exploration. | Easier to debug than one giant score. |
| D08 | Intent/session/long-term are separately computed. | More components, but far more explainable. |
| D09 | Initial combination is .55 intent, .30 session, .15 long-term. | Versioned heuristic, not scientific truth. |
| D10 | Like/Save/Replay/Not-for-me are strongest signals; passive playback uses percentage. | Explicit actions carry clearer meaning. |
| D11 | First 0-8 seconds count as no preference evidence. | Reduces accidental noise. |
| D12 | Skip differs from Not-for-me. | Skip meaning depends on progress; Not-for-me is explicit rejection. |
| D13 | Controlled exploration is approximately 90/10 initially. | Discovery without making recommendations random. |
| D14 | Maintain 3 upcoming candidates. | Responsive queue without long stale playlist. |
| D15 | #2 may play before #1 only when close in score and usefully novel. | Preserves creativity without serving a clearly worse choice. |
| D16 | Meaningful feedback can re-rank the remaining queue immediately. | Queue is provisional. |
| D17 | Finite library may repeat tracks after cooldown. | Avoids exhaustion while controlling repetition. |
| D18 | Not-for-me excludes the exact track for the session. | Strong session rejection, not permanent ban. |
| D19 | Hybrid feature pipeline: tags + signal analysis + validated ML when justified. | More sources, better data quality. |
| D20 | Inferred features store provenance/version/confidence. | Supports auditability. |
| D21 | Missing features remain missing; no fabricated midpoint/default. | Lower coverage, higher correctness. |
| D22 | SQLite + SQLAlchemy + Alembic for Prototype 1. | Best fit for local device; PostgreSQL later. |
| D23 | Audio remains outside relational DB. | Simpler, more appropriate file storage. |
| D24 | SHA-256 for exact dedupe initially. | Does not detect transcoded duplicates. |
| D25 | Startup incremental scan + manual rescan; no real-time watcher. | Simpler prototype. |
| D26 | Scanning/analysis runs in background. | Better UX; requires job state. |
| D27 | Progressive readiness. | Tracks playable before full analysis. |
| D28 | In-process bounded worker with persisted job status. | No Redis/Celery; process shutdown interrupts active work but it can recover. |
| D29 | Structured `ListeningContext` is the source of truth. | Testable deterministic core. |
| D30 | Limited deterministic natural-language commands now; unrestricted AI later. | Natural control without LLM dependency. |
| D31 | Session owns current state; turns/recommendations/feedback own history. | Avoids giant session blobs. |
| D32 | UI-only state stays frontend-side. | Keeps backend semantic. |
| D33 | Raw conversational text not persisted by default. | Data minimization. |
| D34 | Playlists included in Prototype 1. | Additional persistence/API work but clear user value. |
| D35 | Reopen app -> fresh active session; history still persists. | Avoids stale queue/playback restoration. |
| D36 | User controls include Surprise me, More familiar, More like this, Try something different. | Gives human control over exploration without technical sliders. |
| D37 | Prototype is local/personal; public licensing/distribution policy is future work. | Avoids production streaming obligations now. |
| D38 | Preserve canonical scoring/ranking/catalog architecture unless change is required. | Avoids unnecessary rewrite and regression. |
| D39 | AI, external providers, vector retrieval, and AI DJ are deferred. | Prevents premature complexity. |

## Feedback Policy v1

```text
LIKE                +1.00
SAVE/PLAYLIST_ADD   +1.00
REPLAY              +1.00
90-100% completion  +0.80
75-89% completion   +0.50
40-74% completion   +0.10
15-39% completion   -0.20
<15% after 8 sec    -0.50
NOT_FOR_ME          -1.00
0-8 sec             0.00
```

Raw playback facts are stored separately so these thresholds can change later.

## Queue Policy v1

```text
keep top 3

if top1_score - top2_score <= 0.08
and top2 has useful novelty:
    top2 may play first
else:
    top1 first

if top2 plays first and nothing changes:
    top1 may follow, then top3

meaningful feedback/refinement:
    rerank immediately
```

## Product hierarchy

```text
Conversation steers.
Music leads.

Current intent > recent session evidence > long-term history
when signals conflict.
```
