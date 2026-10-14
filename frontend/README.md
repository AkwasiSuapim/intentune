# Intentune Frontend

React + TypeScript + Vite browser client for Intentune.

Architecture, phase plan, and the approved design reference live in [`docs/frontend/`](../docs/frontend/). Read `AGENT_INSTRUCTIONS.md` there before changing anything.

## Commands

Run from this directory:

```bash
npm install      # install dependencies
npm run dev      # start the development server
npm run build    # typecheck and build for production
npm run lint     # lint with oxlint
npm test         # run the tests with Vitest
npm run preview  # serve the production build locally
```

## What runs

The app root is an interactive listening session on mock data. Nothing is persisted: state resets on reload.

`?demo=…` opens the development demo instead:

- `/?demo=gallery` shows the component gallery: every component in its representative states, from prop fixtures in `src/demo/`.
- `/?demo=<scene>` renders one fixed session state with inert controls. `new`, `initial`, `change`, `save`, `discovery`, `refine` and `drawer` match the scenes of the approved design. `stress`, `stress-tune`, `stress-save` and `stress-drawer` use deliberately long content to check that nothing clips or overflows.

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

`src/mocks/mockSessionService.ts` is the current implementation of the service: fixed phrase tables, hand-ordered song lists and sentence templates. It is wired in at `src/App.tsx`.
