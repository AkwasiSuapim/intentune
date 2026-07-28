# Changelog

All meaningful product, architecture, and behavior changes should be recorded here.

## Unreleased

### Added

- Canonical, source-independent domain models in `src/intentune/domain/models.py`: `MusicCandidate`, `UserProfile`, `ListeningContext`, `FeatureWeights`, `ScoreComponent`, `ScoreBreakdown`, `Recommendation`, each with explicit validation and no CSV/HTTP/database/provider dependencies.
- `tests/test_domain_models.py` covering the new models plus compatibility checks (danceability fix, legacy result shapes, CLI output, top-five ranking).

### Changed

- The legacy `Recommender` wrapper (`src/recommender.py`) no longer hard-codes `preferred_danceability` to `0.5`; the legacy `UserProfile` dataclass gained a real `preferred_danceability` field (default `0.5`, matching the old hard-coded value so existing call sites score identically) that the wrapper now actually reads.
- The legacy `Recommender` wrapper precomputes song-dict conversions and an id-based lookup once per instance instead of repeating them on every call, and retains the last computed scores/reasons on `self.last_recommendations` instead of discarding them.

### Documentation

- Created the initial Intentune documentation package.
- Defined the product direction from CodePath prototype to modular backend application.
- Recorded the proposed modular-monolith architecture.
- Documented planned AI and YouTube integrations as future adapters.
- Recorded TD-008 (canonical domain models) in docs/technical-decisions.md.
- Documented two future milestones in docs/development-phases.md: Expanded and Configurable Scoring Engine, and Context-Aware and User-Configurable Weighting.
- Marked `likes_acoustic` on the legacy `UserProfile` dataclass as deprecated and inert.

### Known Limitations

- The historical dictionary API, historical dataclass API, and new canonical domain models coexist; they are not yet unified.
- `load_songs()`, `score_song()`, and `recommend_songs()` still operate on CSV-shaped dictionaries, not `MusicCandidate`.
- The scoring algorithm, its 10-point maximum, and its sharp similarity cutoff are unchanged.

### Current Baseline

- CSV-based catalog with 20 songs
- Content-based scoring using genre, mood, energy, and danceability
- Command-line recommendation display
- Human-readable scoring reasons
- Pytest regression suite

## Version Template

```text
## [Version] - YYYY-MM-DD

### Added

### Changed

### Fixed

### Removed

### Security

### Known Limitations
```
