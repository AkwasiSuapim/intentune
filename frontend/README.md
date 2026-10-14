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

## Development demo

Until sessions are interactive, the app root is a development demo:

- `/` shows the component gallery: every component in its representative states, from prop fixtures in `src/demo/`.
- `/?demo=<scene>` renders one mock session state from `src/mocks/` through the session view: `new`, `initial`, `change`, `save`, `discovery`, `refine` or `drawer`. These match the scenes of the approved design.

## How a session renders

`src/features/session/` turns session state into the screen in three steps:

1. `types.ts` defines the semantic session state (intent, events, recommendations, overlays).
2. `composeSession.ts` is the composition policy: a pure function from that state to typed blocks (`blocks.ts`).
3. `BlockRenderer.tsx` maps each block type to its approved component. An unrecognised type renders a visible notice in development and nothing in production.
