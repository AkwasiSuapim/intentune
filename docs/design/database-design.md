# Database Design

## Status

**Future Draft**

The current project does not use a database. The internal catalog is stored in `data/songs.csv`. A database should be introduced only when persistence is required.

## Initial Recommendation

- Continue using the CSV catalog while refactoring the recommendation domain.
- Introduce SQLite when feedback, recommendation history, or persistent profiles are needed locally.
- Consider PostgreSQL for deployed multi-user persistence.

## Proposed Entities

### `users`

Purpose: Represents an account or anonymous persistent user.

Possible fields:

- `id`
- `email` or external identity reference, if accounts are added
- `display_name`
- `created_at`
- `updated_at`
- `status`

### `user_profiles`

Purpose: Stores recommendation preferences.

Possible fields:

- `id`
- `user_id`
- `preferred_energy`
- `preferred_danceability`
- `profile_version`
- `created_at`
- `updated_at`

Multiple genres, moods, and weights may use child tables or JSON depending on the final query requirements.

### `profile_genres`

- `profile_id`
- `genre`
- `preference_strength`

### `profile_moods`

- `profile_id`
- `mood`
- `preference_strength`

### `catalog_items`

Purpose: Stores normalized candidates when internal or cached external catalog items need persistence.

Possible fields:

- `id`
- `source`
- `external_id`
- `title`
- `creator`
- `genre`
- `mood`
- `energy`
- `danceability`
- `tempo_bpm`
- `valence`
- `acousticness`
- `url`
- `thumbnail_url`
- `metadata_json`
- `created_at`
- `updated_at`

### `recommendation_requests`

Purpose: Records one recommendation session when history is enabled.

Possible fields:

- `id`
- `user_id`, nullable for anonymous sessions
- `input_type`
- `raw_prompt`, nullable and subject to privacy policy
- `profile_snapshot_json`
- `catalog_source`
- `algorithm_version`
- `created_at`

### `recommendation_results`

- `id`
- `request_id`
- `catalog_item_id` or external candidate reference
- `rank`
- `score`
- `match_level`
- `reason_json`
- `created_at`

### `feedback_events`

- `id`
- `request_id`
- `user_id`, nullable
- `candidate_reference`
- `action`
- `created_at`

## Relationship Sketch

```text
users 1 ---- 1..n user_profiles
users 1 ---- 0..n recommendation_requests
recommendation_requests 1 ---- n recommendation_results
recommendation_requests 1 ---- 0..n feedback_events
catalog_items 1 ---- 0..n recommendation_results
```

## Data Retention Questions

Before implementation, decide:

- Whether raw natural-language prompts should be stored
- How long anonymous feedback should be retained
- Whether users can delete their profile and history
- Whether external video metadata may be cached and for how long
- What information is required for analytics versus product behavior

## Migration Strategy

Use version-controlled migrations when a database is introduced. Do not edit production tables manually.

## Open Trade-offs

- Normalized genre and mood tables versus JSON storage
- Storing recommendation results versus calculating them on demand
- Anonymous session support versus required accounts
- SQLite simplicity versus PostgreSQL concurrency and deployment support
