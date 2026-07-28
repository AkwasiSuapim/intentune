# Current System Audit

## Status

**Current**

## Repository Origin

The uploaded repository began as the CodePath Music Recommender Simulation starter project.

## Current Files

- `README.md`
- `model_card.md`
- `ai_interactions.md`
- `requirements.txt`
- `data/songs.csv`
- `src/main.py`
- `src/recommender.py`
- `src/__init__.py`
- `tests/test_recommender.py`

The archive also contains generated or local artifacts such as screenshots, Python caches, pytest caches, Graphify output, Git metadata, and macOS archive metadata.

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

Energy and danceability reward closeness to the user's preferred values. A larger raw value is not automatically better.

## Current Main Flow

1. `src.main` calls `load_songs()`.
2. A profile is defined inside `main.py`.
3. `recommend_songs()` calls `score_song()` for every song.
4. Results are sorted by score, then title, then artist.
5. The top five recommendations and explanations are printed to the terminal.

## Existing Strengths

- Working recommendation pipeline
- Simple explainable scoring
- Deterministic ranking
- Input and numerical validation
- Edge-case handling for empty results and invalid `k`
- Test coverage
- Human-readable README and model card
- Clear baseline for future comparison

## Current Technical Concerns

### Competing Data Shapes

The file still contains both dictionaries and dataclasses -- this has not been rewritten. The functional recommender uses dictionary profiles with `preferred_energy` and `preferred_danceability`, while the `UserProfile` dataclass uses `target_energy` and `likes_acoustic`.

**Partially addressed (Phase 2):** `src/intentune/domain/models.py` now defines a single canonical, typed vocabulary (`preferred_energy`, `preferred_danceability`, etc.) that both the dictionary and dataclass APIs can converge toward later. The two existing historical APIs still coexist unchanged for compatibility; unifying them is left to a future phase.

`likes_acoustic` remains on the legacy `UserProfile` dataclass for backward compatibility only. It is now explicitly documented as deprecated and has never had any effect on scoring.

### Hard-Coded Adaptation

**Resolved (Phase 2):** The object-oriented `Recommender` previously hard-coded preferred danceability to `0.5` regardless of what the caller supplied. The legacy `UserProfile` dataclass now has a real `preferred_danceability` field (defaulting to `0.5` to preserve historical behavior for existing call sites); the wrapper reads that field instead of a literal constant, so an explicit value now actually reaches scoring. See docs/technical-decisions.md, TD-008.

### Side Effects in Data Loading

`load_songs()` prints the loaded-song count. A lower-level data-loading function should usually return data and let the caller decide what to display or log.

### CLI Coupling

The current interaction is terminal-only and the sample profile is hard-coded.

### Catalog Coupling

The engine assumes all candidates have CSV-style genre, mood, energy, and danceability fields. Future YouTube candidates may not have all those values.

**Not yet addressed:** `src/intentune/domain/models.py` now defines a source-independent `MusicCandidate` model whose audio-feature fields are optional for exactly this reason, but `load_songs()`, `score_song()`, and `recommend_songs()` still operate on CSV-shaped dictionaries and have not been rewired to use `MusicCandidate`. That wiring is deferred to a later phase so this milestone could focus on the models themselves without touching scoring behavior.

### Missing Product Capabilities

There is currently no:

- HTTP API
- Database
- Persistent user profile
- Feedback store
- Browser interface
- Authentication
- AI intent parser
- YouTube integration
- Structured logging or monitoring
- CI workflow confirmed in the uploaded archive

## Recommendation

Preserve the current implementation as the Version 1 baseline. Refactor it incrementally behind tests rather than deleting the repository and starting from an empty project.
