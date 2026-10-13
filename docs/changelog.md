# Changelog

All meaningful product, architecture, and behavior changes should be recorded here.

## Unreleased

### Added

- Canonical, source-independent domain models in `src/intentune/domain/models.py`: `MusicCandidate`, `UserProfile`, `ListeningContext`, `FeatureWeights`, `ScoreComponent`, `ScoreBreakdown`, `Recommendation`, each with explicit validation and no CSV/HTTP/database/provider dependencies.
- `tests/test_domain_models.py` covering the new models plus compatibility checks (danceability fix, legacy result shapes, CLI output, top-five ranking).
- Canonical scoring (`src/intentune/domain/scoring.py`, `score_candidate()`) implementing the current four-feature rule (genre, mood, energy, danceability) as the single source of truth, producing typed `ScoreBreakdown`/`ScoreComponent` output.
- Canonical ranking (`src/intentune/domain/ranking.py`, `rank_candidates()`) implementing the current score/title/creator tie-breaking rule and rank assignment, returning typed `Recommendation` objects.
- CSV catalog adapter (`src/intentune/adapters/csv_catalog.py`, `load_music_candidates()`/`music_candidate_from_csv_row()`) converting raw CSV rows into `MusicCandidate`; `id`/`title`/`artist` are required, genre/mood/audio features are optional (missing or blank becomes `None`).
- A first application-service orchestrator (`src/intentune/application/recommendation_service.py`, `recommend_music()`) coordinating canonical scoring and ranking for one use case.
- Legacy boundary converters in `src/recommender.py`: `legacy_profile_to_user_profile()` and `song_dict_to_music_candidate()`.
- `tests/test_csv_catalog.py`, `tests/test_canonical_scoring.py`, `tests/test_canonical_ranking.py`, `tests/test_recommendation_service.py`, `tests/test_legacy_compatibility.py`.

### Changed

- The legacy `Recommender` wrapper (`src/recommender.py`) no longer hard-codes `preferred_danceability` to `0.5`; the legacy `UserProfile` dataclass gained a real `preferred_danceability` field (default `0.5`, matching the old hard-coded value so existing call sites score identically) that the wrapper now actually reads.
- The legacy `Recommender` wrapper precomputes song-dict conversions and an id-based lookup once per instance instead of repeating them on every call, and retains the last computed scores/reasons on `self.last_recommendations` instead of discarding them.
- `load_songs()`, `score_song()`, and `recommend_songs()` in `src/recommender.py` now convert their inputs into canonical `MusicCandidate`/`UserProfile` and delegate to the canonical CSV adapter/scorer/ranker, instead of containing their own CSV parsing and scoring math. Public signatures, dictionary shapes, scores, reasons, and CLI output are unchanged; tests verify behavioral equivalence across the full 20-song catalog and protect the documented top-five CLI baseline.

### Removed

- `_calculate_similarity_points()` and `_validate_numeric_preference()` in `src/recommender.py`, now dead code superseded by `src/intentune/domain/scoring.py`.

### Documentation

- Created the initial Intentune documentation package.
- Defined the product direction from CodePath prototype to modular backend application.
- Recorded the proposed modular-monolith architecture.
- Documented planned AI and YouTube integrations as future adapters.
- Recorded TD-008 (canonical domain models) and TD-009 (canonical domain objects as internal source of truth) in docs/decisions/technical-decisions.md.
- Documented two future milestones in docs/planning/development-phases.md: Expanded and Configurable Scoring Engine, and Context-Aware and User-Configurable Weighting.
- Marked `likes_acoustic` on the legacy `UserProfile` dataclass as deprecated and inert.

### Known Limitations

- The historical dictionary API and historical dataclass API shapes still coexist with the canonical domain models for backward compatibility, though they are now thin boundary conversions rather than separate scoring/ranking implementations.
- The scoring algorithm, its 10-point maximum, and its sharp similarity cutoff are unchanged; it still only uses genre, mood, energy, and danceability.
- `score_candidate()` requires genre, mood, energy, and danceability to be present -- missing-feature normalization for partial YouTube-style metadata is not implemented yet.
- The legacy dict shape (`load_songs()`'s output) assumes every candidate field is present; a `MusicCandidate` with a `None` audio feature would fail converting back to that shape. Not an issue for the current CSV catalog, where every field is always populated.
- The compatibility CLI path performs an extra `MusicCandidate -> legacy dict -> MusicCandidate` conversion.
- A formal catalog interface/port has not been introduced; the legacy compatibility layer calls the CSV adapter directly.

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
