# Intentune Frontend

React + TypeScript + Vite browser client for Intentune.

Architecture, phase plan, and the approved design reference live in [`docs/frontend/`](../docs/frontend/). Read `AGENT_INSTRUCTIONS.md` there before changing anything.

## Commands

Run from this directory:

```bash
npm install      # install dependencies
npm run dev      # start the development server, against the backend
npm run dev:mock # start it on the mock service instead
npm run build    # typecheck and build for production (against the backend)
npm run build:mock  # build on the mock service (what the browser checks use)
npm run lint     # lint with oxlint
npm test         # run all tests with Vitest (unit, static-render and DOM-level)
npm run check:browser  # build on the mock, then run the browser checks (see browser-checks/README.md)
npm run preview  # serve the production build locally
```

## What runs

The app root is an interactive listening session. By default it runs against the backend (B9 / F9), so start the backend first (`python -m src.intentune.api` in `backend/`), then:

```bash
npm run dev                                          # backend on 127.0.0.1:8000
INTENTUNE_API_URL=http://127.0.0.1:8888 npm run dev  # or wherever it listens
```

The dev server proxies `/api` to the backend. Sessions, likes, playlists, and history live in the backend, and songs play from your imported library with real audio. Importing music has no screen yet: register and import a folder through the API (`POST /api/v1/library/sources`, then `POST /api/v1/library/import`).

Tune offers energy, mood, and genre, as the approved design does, but marks a dimension your library has no information for as unavailable, and does not send it. The same goes for the starters that need it: Focus, Unwind, and Move are defined by a mood and an energy, so they show as unavailable, with the reason, while Discover always works. Today the importer reads genre tags only, so energy and mood show as unavailable. With no playable music at all, the library is not ready: every starter, Discover included, says so, and nothing starts until music is imported. What is available is read from the backend when the app loads, so it changes as the library does.

The mock service runs only when asked for: `npm run dev:mock` (Vite's `mock` mode), or `VITE_SESSION_SERVICE=mock`. It uses mock data, persists nothing, and resets on reload. The tests, the design demo, and the browser checks use it.

`?demo=…` opens the development demo instead:

- `/?demo=gallery` shows the component gallery: every component in its representative states, from prop fixtures in `src/demo/`.
- `/?demo=<scene>` renders one fixed session state with inert controls. `new`, `initial`, `change`, `save`, `discovery`, `refine` and `drawer` match the scenes of the approved design. `stress`, `stress-tune`, `stress-save` and `stress-drawer` use deliberately long content to check that nothing clips or overflows. `turn-pending` and `turn-failed` show an answer on its way and one that failed; `loading` and `load-failed` show the screen before the sessions have loaded.

## Layout and motion

- Phone first. From 700px the session keeps a centred 600px column and the artwork grows taller, as in the approved design. From 1024px the session navigation stands as a rail beside the session instead of opening as a drawer.
- Motion explains a state change and then stops: new stream items rise in, a new recommendation is revealed, the previous one settles into history, and sheets and the drawer slide in and out. Everything is cut to nothing under `prefers-reduced-motion`.
- While a sheet or the drawer is open the rest of the screen is inert, focus moves into the overlay, and Escape closes it.
- When the hero's playback controls scroll out of view, the composer's leading slot shows compact now-playing.

## How a session works

`src/features/session/` holds the session feature:

1. `types.ts` defines the semantic session state (intent, events, recommendations, overlays).
2. `sessionReducer.ts` and `workspaceReducer.ts` are the pure state transitions for one session and for the set of sessions.
3. `commands.ts` lists what the user can ask for and turns each request into reducer actions, consulting the service where a backend would be consulted.
4. `sessionService.ts` is the service interface. The feature never interprets requests or chooses music itself.
5. `composeSession.ts` is the composition policy: a pure function from state to typed blocks (`blocks.ts`).
6. `BlockRenderer.tsx` maps each block type to its approved component. An unrecognised type renders a visible notice in development and nothing in production.

There are two implementations of the service:
- **`src/mocks/mockSessionService.ts`:** fixed phrase tables, hand-ordered song lists, and sentence templates.
- **`src/services/http/httpSessionService.ts`:** the backend. Requests carry meaning (a starter, a quick action's control, a Tune value); only typed words travel as text, for the backend to interpret.

`src/App.tsx` chooses between them. Real audio plays through `useAudioPlayback.ts`, whose audio element is the playback authority; the simulated clock runs only for the mock's songs.
