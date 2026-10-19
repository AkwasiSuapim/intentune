# Project Description

## Status

**Current, Planned, and Future.** Reconciled with Prototype 1 in Phase B0 (2026-10-18).

## Product Name

**Intentune**

Intentune began as a CodePath Music Recommender Simulation and is being developed into a larger personalized music recommendation platform.

The name represents a system that connects a listener's **intent** with music that fits the listener's mood, activity, and desired emotional state.

## Problem

People often know how they feel and what they need to do, but they do not always know what song, genre, artist, or playlist to search for. Existing music platforms can provide large catalogs, but a user may still struggle to express a request such as:

> I feel tired, but I need music that will help me focus and study.

Intentune aims to translate that type of need into a small set of understandable recommendations.

## Target Users

The first users are:

- College students
- Friends and family
- People choosing music for studying, exercising, relaxing, working, commuting, or changing their mood
- Learners who want to understand why a recommendation was made

## Current Product

The current repository is a CodePath command-line prototype. It:

1. Loads 20 songs from `data/songs.csv`.
2. Reads a user profile containing genre, mood, energy, and danceability preferences.
3. Scores each song out of 10.
4. Sorts the songs from strongest to weakest match.
5. Returns the top recommendations.
6. Shows human-readable scoring reasons.
7. Uses pytest to verify loading, scoring, ranking, and edge cases.

Separately, a React frontend (`frontend/`) presents a mobile-first conversational listening session. It runs entirely on mock data and is not yet connected to the backend.

## Prototype 1

**Planned (approved).** The next version is a **local-first, session-aware, continuously adapting** music application ([specification](../planning/intentune-backend-prototype-implementation-spec.md)). The listener will be able to:

1. run Intentune locally, with no account, AI, external provider, or internet connection
2. import music from several folders on their own device into an Intentune-managed library
3. keep using the app while new tracks are analyzed in the background
4. start a fresh listening session and set a structured listening intent
5. press Play once and get continuous music, with three upcoming candidates managed dynamically
6. skip, like, replay, save, or say Not for me, and see what comes next adapt immediately
7. get controlled variety and discovery
8. create and manage playlists
9. restart without losing the library, playlists, metadata, feedback, or history

Product principle: **Conversation steers. Music leads.**

## Long-Term Product Vision

Intentune will become a backend-driven music recommendation application that can:

- Accept structured preferences through a form *(Prototype 1: structured listening intent in a session)*
- Accept natural-language requests through an AI chatbot *(Future: deferred beyond Prototype 1, D39)*
- Interpret current mood, desired mood, activity, and listening goal
- Search an external music catalog, beginning with the official YouTube API *(Future: Prototype 1 uses the listener's own music; external catalogs are deferred, D39)*
- Rank real candidates through Intentune's own recommendation logic
- Explain why each result fits the user
- Learn carefully from likes, dislikes, skips, saves, and opens *(Prototype 1: from likes, saves, replays, skips, completions, and Not for me, D05, D06, D10)*
- Preserve privacy and keep external API integrations replaceable

## Product Principles

1. **Explain recommendations.** Users should understand the main reasons behind a result.
2. **Keep the core deterministic.** AI can interpret language, but validated backend logic controls ranking and system behavior.
3. **Build in small complete slices.** Each phase must produce a testable improvement.
4. **Protect user data and secrets.** Prompts, feedback, and API credentials must be handled deliberately.
5. **Do not pretend uncertain data is known.** For example, YouTube metadata does not automatically provide true audio energy or danceability.
6. **Start simple and evolve from evidence.** The architecture should support growth without assuming large-scale traffic prematurely.

## Non-Goals for the First Release

The first production-minded release will not attempt to replace Spotify, YouTube Music, or Apple Music. It will not include payments, social networking, automatic playlist publishing, microservices, or advanced machine-learning training.
