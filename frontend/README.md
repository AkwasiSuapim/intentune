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
npm run preview  # serve the production build locally
```

## Component demo

Until the session renderer exists, the app root is a development demo built from static fixtures in `src/demo/`:

- `/` shows the component gallery: every component in its representative states.
- `/?demo=<scene>` shows one static scene from the approved design: `new`, `initial`, `change`, `save`, `discovery`, `refine` or `drawer`.
