# System Workflow

## Status

**Current and Planned**

## Current Workflow

The public functions the CLI calls (`load_songs()`, `recommend_songs()`) still have their historical signatures and dictionary shapes, but internally they now delegate to the canonical domain flow:

```text
songs.csv
   |
   v
load_songs()  --delegates to-->  CSV adapter (src/intentune/adapters/csv_catalog.py)
                                       |
                                       v
                                 MusicCandidate list
                                       |
                                       v
        load_songs() converts candidates to the historical song dict list
                                       |
hard-coded user profile                |
   |                                   |
   v                                   v
legacy_profile_to_user_profile()   recommend_songs() converts song dicts
   |                               back to MusicCandidate objects
   v                                   |
        canonical UserProfile + MusicCandidate list
                        |
                        v
        rank_candidates() (src/intentune/domain/ranking.py)
          -- calls score_candidate() (src/intentune/domain/scoring.py)
             for every candidate --
                        |
                        v
              list[Recommendation], ranked and assigned ranks
                        |
                        v
        recommend_songs() converts back to the historical
        {"song", "score", "reasons"} dict shape
                        |
                        v
              print recommendations and reasons
```

`score_song()` follows the same conversion pattern for a single song: legacy dict in, `MusicCandidate`/`UserProfile` built, `score_candidate()` called, `(score, reasons)` returned.

The `MusicCandidate -> historical dict -> MusicCandidate` conversion in the
CLI path is intentional legacy compatibility, not the desired path for new
callers. New internal callers can pass canonical candidates directly to
`recommend_music()`.

## First Backend Workflow

```text
1. Client sends POST /api/v1/recommendations
2. API validates the request schema
3. Application service requests candidates from a catalog provider
4. Catalog provider loads the internal catalog
5. Domain service scores every candidate
6. Ranking logic sorts candidates
7. Optional diversity logic adjusts repeated artists or genres
8. Application service creates a response
9. API returns JSON with scores and reasons
```

## Planned Feedback Workflow

```text
1. User receives recommendations
2. User chooses like, dislike, skip, save, or open
3. Client sends a feedback event
4. API validates the event
5. Feedback service stores the event
6. The system acknowledges the event
7. Profile adaptation is not performed until a tested policy is introduced
```

## Planned AI Chatbot Workflow

```text
1. User enters a natural-language request
2. AI adapter sends the message to an AI provider
3. Provider returns structured intent
4. Intent validator checks required fields and numerical ranges
5. Invalid or incomplete output receives safe defaults or a clarification request
6. The validated request enters the same recommendation application service
7. The existing deterministic engine scores and ranks candidates
```

The chatbot is an input adapter. It does not replace backend validation or ranking.

## Planned YouTube Workflow

```text
1. The application receives validated user intent
2. Query builder creates a small set of search phrases
3. YouTube adapter calls the official YouTube Data API
4. API results are normalized into Intentune candidate objects
5. Duplicate and invalid results are removed
6. Available metadata is scored carefully
7. Results are ranked and explained
8. Browser displays title, channel, thumbnail, link, and explanation
```

## Failure Workflows

### Invalid Input

Return a structured validation error. Do not begin recommendation processing.

### Empty Catalog

Return an empty recommendation list with a clear message.

### AI Failure

The manual structured-input path should remain usable. AI failure should not break the core recommender.

### YouTube Failure

Return a provider-specific unavailable message or fall back to the internal catalog when that behavior is enabled.

### Database Failure

Recommendation logic that does not require persistence may continue. Feedback or saved-history operations should return a controlled service-unavailable error.
