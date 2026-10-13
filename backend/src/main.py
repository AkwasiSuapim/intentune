"""Command line runner for the Music Recommender Simulation."""

from src.recommender import load_songs, recommend_songs


def main() -> None:
    songs = load_songs("data/songs.csv")

    default_user_profile = {
        "favorite_genre": "pop",
        "favorite_mood": "happy",
        "preferred_energy": 0.80,
        "preferred_danceability": 0.80,
    }

    recommendations = recommend_songs(default_user_profile, songs, k=5)

    print("\nTop recommendations:\n")
    for rank, recommendation in enumerate(recommendations, start=1):
        song = recommendation["song"]
        score = recommendation["score"]
        reasons = recommendation["reasons"]
        print(f"{rank}. {song['title']} — {song['artist']}")
        print(f"   Genre: {song['genre']} | Mood: {song['mood']}")
        print(f"   Score: {score:.2f}/10")
        print("   Reasons:")
        for reason in reasons:
            print(f"   - {reason}")
        print()


if __name__ == "__main__":
    main()
