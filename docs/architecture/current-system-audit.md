# Current System Audit

## Status

**Current**

## Repository Origin

The uploaded repository began as the CodePath Music Recommender Simulation starter project.

## Current Files

- `README.md`
- `model_card.md`
- `ai_interactions.md`
- `backend/requirements.txt`
- `backend/data/songs.csv`
- `backend/src/main.py`
- `backend/src/recommender.py`
- `backend/src/__init__.py`
- `backend/src/intentune/domain/models.py`
- `backend/src/intentune/domain/scoring.py`
- `backend/src/intentune/domain/ranking.py`
- `backend/src/intentune/application/recommendation_service.py`
- `backend/src/intentune/adapters/csv_catalog.py`
- `backend/tests/test_recommender.py`
- `backend/tests/test_domain_models.py`
- `backend/tests/test_canonical_scoring.py`
- `backend/tests/test_canonical_ranking.py`
- `backend/tests/test_csv_catalog.py`
- `backend/tests/test_recommendation_service.py`
- `backend/tests/test_legacy_compatibility.py`

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
3. `recommend_songs()` converts the legacy profile and songs to canonical domain models.
4. `rank_candidates()` calls `score_candidate()` for every candidate and sorts by score, then title, then creator.
5. The top five recommendations and explanations are printed to the terminal.

**Updated internal wiring (Current):** `load_songs()` calls the CSV adapter (`src/intentune/adapters/csv_catalog.py`) and converts `MusicCandidate` objects back to the historical dict shape. `score_song()`/`recommend_songs()` convert their dict inputs into `MusicCandidate`/`UserProfile` and call the canonical scorer/ranker (`src/intentune/domain/scoring.py`, `src/intentune/domain/ranking.py`). The externally observable behavior in steps 1-5 is unchanged; tests compare legacy and canonical results across the full 20-song catalog, while CLI tests protect the documented top-five output.

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

The file still contains both dictionaries and dataclasses -- their public shapes have not changed. The functional recommender uses dictionary profiles with `preferred_energy` and `preferred_danceability`, while the `UserProfile` dataclass uses `target_energy` and `likes_acoustic`.

**Partially addressed (Phase 2):** `src/intentune/domain/models.py` defines a single canonical, typed vocabulary (`preferred_energy`, `preferred_danceability`, etc.).

**Further addressed (this phase):** the two historical shapes are no longer *competing implementations* -- they are thin boundary conversions. `score_song()`/`recommend_songs()` convert their dict inputs into canonical `MusicCandidate`/`UserProfile`, call the single canonical scorer/ranker, and convert the result back. The dictionary and dataclass *shapes* themselves still coexist for backward compatibility (existing callers still pass/receive them), but there is now only one implementation of the scoring and ranking math.

`likes_acoustic` remains on the legacy `UserProfile` dataclass for backward compatibility only. It is now explicitly documented as deprecated and has never had any effect on scoring.

### Hard-Coded Adaptation

**Resolved (Phase 2):** The object-oriented `Recommender` previously hard-coded preferred danceability to `0.5` regardless of what the caller supplied. The legacy `UserProfile` dataclass now has a real `preferred_danceability` field (defaulting to `0.5` to preserve historical behavior for existing call sites); the wrapper reads that field instead of a literal constant, so an explicit value now actually reaches scoring. See docs/decisions/technical-decisions.md, TD-008.

### Side Effects in Data Loading

`load_songs()` prints the loaded-song count. A lower-level data-loading function should usually return data and let the caller decide what to display or log.

### CLI Coupling

The current interaction is terminal-only and the sample profile is hard-coded.

### Catalog Coupling

The engine assumes all candidates have CSV-style genre, mood, energy, and danceability fields. Future YouTube candidates may not have all those values.

**Partially addressed (this phase):** `load_songs()`, `score_song()`, and `recommend_songs()` are now internally wired through `MusicCandidate` (via `src/intentune/adapters/csv_catalog.py` and the boundary converters in `src/recommender.py`), and the canonical scorer (`src/intentune/domain/scoring.py`) raises a clear `ValueError` if a candidate is missing a required scoring field rather than inventing a value. What remains unaddressed: the scorer still *requires* genre, mood, energy, and danceability to be present -- it does not yet skip missing features and renormalize the active weight. That is the "Expanded and Configurable Scoring Engine" future milestone's missing-feature-handling principle (see docs/planning/development-phases.md), needed before a YouTube candidate with partial metadata could be scored at all.

### Compatibility Conversion Overhead

**Temporary limitation:** the CLI compatibility path converts CSV rows into
`MusicCandidate`, converts them back to historical dictionaries in
`load_songs()`, and then converts those dictionaries back to
`MusicCandidate` in `recommend_songs()`. This preserves the public CodePath
API while new canonical callers use `recommend_music()` directly. Removing
the round-trip requires a separate backward-compatibility decision.

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
