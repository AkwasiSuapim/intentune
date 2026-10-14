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
- `/?demo=<scene>` renders one fixed mock session state with inert controls: `new`, `initial`, `change`, `save`, `discovery`, `refine` or `drawer`. These match the scenes of the approved design.

## How a session works

`src/features/session/` holds the session feature:

1. `types.ts` defines the semantic session state (intent, events, recommendations, overlays).
2. `sessionReducer.ts` and `workspaceReducer.ts` are the pure state transitions for one session and for the set of sessions.
3. `commands.ts` lists what the user can ask for and turns each request into reducer actions, consulting the service where a backend would be consulted.
4. `sessionService.ts` is the service interface. The feature never interprets requests or chooses music itself.
5. `composeSession.ts` is the composition policy: a pure function from state to typed blocks (`blocks.ts`).
6. `BlockRenderer.tsx` maps each block type to its approved component. An unrecognised type renders a visible notice in development and nothing in production.

`src/mocks/mockSessionService.ts` is the current implementation of the service: fixed phrase tables, hand-ordered song lists and sentence templates. It is wired in at `src/App.tsx`.
