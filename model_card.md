# Model Card: Intentune

## Model Name

Intentune Baseline 1.0. This name identifies the initial deterministic recommendation model used by Intentune.

## Goal / Task

This recommender compares songs with an individual user profile and suggests the strongest matches. The current system uses genre, mood, energy, and danceability to build a simple recommendation score.

## Data Used

The recommender uses the catalog in data/songs.csv. The file contains 20 songs and includes each song's ID, title, artist, genre, mood, energy, tempo, valence, danceability, and acousticness. The first recommendation algorithm only uses genre, mood, energy, and danceability. The dataset is small, so it may not represent every genre, artist, culture, or musical preference fairly.

## Algorithm Summary

The scoring system starts from zero and adds points for how well a song matches the user's preferences. An exact genre match gives 3 points, an exact mood match gives 3 points, energy similarity gives up to 2 points, and danceability similarity gives up to 2 points. The maximum possible score is 10 points. Energy and danceability are scored by closeness to the user's preferred values, so higher values are not automatically better. Every song receives a score, the songs are sorted from highest to lowest, and the top results are recommended.

## Observed Behavior / Biases

The system can overvalue exact genre and mood matches because those features contribute six of the ten points. Related moods such as focused and chill receive no partial credit, even if they feel similar. A song can match a user's energy and danceability well but still rank lower if its genre or mood is different. The small catalog can also make the recommendations feel narrow or repetitive.

## Evaluation Process

The behavior of the recommender was checked with pytest unit tests and CLI-based integration tests. The tests covered CSV loading and type conversion, perfect and partial matches, numerical boundary values, invalid input, top-k ranking, empty input, negative-k handling, and mutation protection. The final pytest run reported 21 passed tests. The system was also compared using a pop/happy profile and a lofi/focused profile, and changing the profile changed which songs ranked highest.

## Intended Use

This system is intended for learning how recommendation systems work. It is useful for demonstrating content-based filtering, practicing Python, CSV processing, scoring, ranking, testing, and documentation, and experimenting with small song catalogs and user profiles.

## Non-Intended Use

This system should not be used as a production replacement for services like Spotify or YouTube Music. It should not be used to make high-stakes decisions, to judge the quality of artists or songs, or to represent every listener's musical taste. It also should not be treated as a reliable recommendation tool for a large commercial catalog.

## Ideas for Improvement

A future version could update user profiles using likes, skips, saves, replays, and listening history. It could also give partial points for related genres and moods instead of relying only on exact matches. Adding diversity-aware ranking would help the top recommendations feel less repetitive and would make the system more useful for real users.

## Personal Reflection

The biggest learning moment was understanding the difference between scoring one song and ranking the whole catalog. A recommendation is not just about whether a song is good in general; it depends on how well it matches a specific user profile.

AI helped a lot with brainstorming the architecture, scoring rules, tests, edge cases, refactoring, and documentation. The work still needed to be checked carefully, though, because some pytest tests initially failed and the CLI exposed a mismatch between the recommendation structure and the main script. It was also surprising that a simple weighted algorithm could still feel personalized. A future version would add behavior-based learning, partial-match logic, and more diversity in the recommendations.
