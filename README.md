# Intentune

## Project Summary

Intentune began as a CodePath Music Recommender Simulation and is being developed into a larger personalized music recommendation platform. The current application is a command-line content-based music recommendation simulator. It loads a catalog of songs from `backend/data/songs.csv`, compares each song with an individual user profile, assigns a personalized score out of 10, and ranks the strongest matches. The scoring system uses genre, mood, energy, and danceability. Each recommendation also includes human-readable reasons explaining how the final score was calculated.

---

## How The System Works

This project uses a simple content-based recommender. Each song is described by a small set of features from the catalog, and each user has a taste profile that represents what they seem to like. The recommender compares songs to that profile and ranks them from best match to weakest match.

### Recommendation Workflow

1. Load the song catalog from `backend/data/songs.csv`.
2. Convert numerical fields such as energy and danceability into floats.
3. Load or define an individual user profile.
4. Use every song in the small catalog as a recommendation candidate.
5. Compare each song with the user profile.
6. Give each song a score out of 10.
7. Store the score and human-readable reasons.
8. Sort all songs from highest score to lowest score.
9. Return the top `k` recommendations.
10. In a future version, use likes, skips, saves, replays, and listening history to update each user's profile.

### Algorithm Recipe

The first version uses a simple scoring rule with four main features:

- Exact genre match: `+3.0` points
- Exact mood match: `+3.0` points
- Energy similarity: up to `+2.0` points
- Danceability similarity: up to `+2.0` points
- Maximum possible score: `10.0`

Energy and danceability are scored by how close they are to the user's preferred values. A higher value is not automatically better. For example, if a user prefers calm and less energetic music, a very high energy value may receive a lower score than a value that is closer to the user's preference.

The default CLI profile used by the program is:

```python
default_user_profile = {
    "favorite_genre": "pop",
    "favorite_mood": "happy",
    "preferred_energy": 0.80,
    "preferred_danceability": 0.80,
}
```

The earlier lofi/focused profile is still useful for comparison, but the main CLI verification uses the pop/happy profile shown above.



### Potential Biases and Limitations

This first version is simple, but it has some important limits:

- Genre and mood receive six of the ten available points, so the system may over-prioritize exact genre and mood matches.
- A good song with a related mood, such as `chill` instead of `focused`, may rank too low because the first version uses exact text matching.
- Content-based recommendations may repeatedly suggest very similar songs and reduce variety.
- The small dataset may over-represent some genres and under-represent others.
- The system does not yet use listening history, skips, saves, replays, tempo, valence, acousticness, or feedback.
- Future versions could add partial matches, diversity controls, adaptive profiles, and user feedback.

### Testing

The project uses pytest to cover CSV loading and type conversion, perfect and partial matches, numerical boundaries, invalid data, ranking, top-k behavior, determinism for tied scores, empty inputs, and mutation protection.

---

## Getting Started

### Setup

The Python backend lives in `backend/`. Run the commands below from that directory.

1. Create a virtual environment:

   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the app:

   ```bash
   python -m src.main
   ```

### Running Tests

Run the starter tests from the `backend/` directory with:

```bash
pytest
```

You can add more tests in `backend/tests/test_recommender.py`.

---

## Sample Recommendation Output

Run the recommender from the `backend/` directory with:

```bash
python -m src.main
```

Example output:

```text
Loaded songs: 20

Top recommendations:

1. Sunrise City — Neon Echo
   Genre: pop | Mood: happy
   Score: 9.94/10
   Reasons:
   - genre match (+3.0)
   - mood match (+3.0)
   - energy similarity (+1.96)
   - danceability similarity (+1.98)

2. Rooftop Lights — Indigo Parade
   Genre: indie pop | Mood: happy
   Score: 6.88/10
   Reasons:
   - genre did not match (+0.0)
   - mood match (+3.0)
   - energy similarity (+1.92)
   - danceability similarity (+1.96)

3. Gym Hero — Max Pulse
   Genre: pop | Mood: intense
   Score: 6.58/10
   Reasons:
   - genre match (+3.0)
   - mood did not match (+0.0)
   - energy similarity (+1.74)
   - danceability similarity (+1.84)

4. Blinding Lights — The Weeknd
   Genre: synth-pop | Mood: energetic
   Score: 3.86/10
   Reasons:
   - genre did not match (+0.0)
   - mood did not match (+0.0)
   - energy similarity (+1.86)
   - danceability similarity (+2.00)

5. Calm Down — Rema
   Genre: afrobeats | Mood: romantic
   Score: 3.86/10
   Reasons:
   - genre did not match (+0.0)
   - mood did not match (+0.0)
   - energy similarity (+1.88)
   - danceability similarity (+1.98)
```
---

## Experiments You Tried

I compared two different user profiles using the existing recommender functions. For the pop/happy profile, Sunrise City by Neon Echo ranked highest with a score of 9.94/10, followed by Rooftop Lights and Gym Hero. For the lofi/focused profile, Focus Flow by LoRoom ranked highest at 9.40/10, followed by Library Rain and Midnight Coding. The results changed because the recommender favors exact genre and mood matches first, then rewards energy and danceability when they are close to the profile. That makes sense with the current scoring rule: a pop/happy profile naturally favors upbeat pop-style songs, while a lofi/focused profile favors calm, low-energy tracks.

---

## Limitations and Risks

This recommender is intentionally simple, but it has some important limitations.

- The catalog is small, so the recommendations are fairly narrow.
- Exact genre and mood matching can be too strict because they contribute six of the ten available points.
- Related moods such as focused and chill receive no partial match, even though they may feel similar.
- The recommender may repeatedly suggest similar songs because it ranks by profile similarity.
- Some genres may be over-represented in the dataset while others are under-represented.
- Listening history, skips, saves, replays, and adaptive feedback are not implemented.
- Tempo, valence, and acousticness are available in the CSV but are not used in the first scoring model.

---

## Reflection

Read and complete the model card here:

[**Model Card**](model_card.md)


My biggest learning moment was understanding the difference between scoring one song and ranking the full catalog. The scoring function measures how well one song matches a user, while the ranking function compares all the scores and places the strongest matches first. I also learned that a song is not automatically a good recommendation for everyone. Its value depends on the preferences of the individual user.

AI tools helped me brainstorm the system design, scoring rules, tests, edge cases, refactoring, and documentation. However, I still had to double-check the AI-generated work. Some tests initially failed, and the command-line program later revealed a mismatch between the result structure and the way `main.py` displayed it. Pytest and CLI verification helped me find and correct these problems. I was surprised that a simple weighted algorithm could still make the results feel personalized. If I extended the project, I would allow the profile to learn from likes, skips, saves, and replays, while also adding partial matches and more diverse recommendations.


