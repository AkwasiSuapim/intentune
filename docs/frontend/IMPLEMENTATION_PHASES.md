# Intentune Frontend Implementation Phases

## Status

**Approved incremental implementation plan. Execute exactly one authorized phase at a time.**

This document controls implementation order. It exists specifically to prevent a coding agent from building ahead of the reviewed milestone.

The local repository is the source of truth for what already exists. `ARCHITECTURE.md` defines frontend boundaries. The final approved design artifact defines visual direction.

---

## Global Rule

For every authorized phase:

1. inspect current repository state;
2. establish baseline verification when possible;
3. implement only the authorized phase;
4. preserve all working behavior from previous phases;
5. run the phase's verification;
6. report results;
7. stop.

Never automatically advance to the next phase.

---

# F0 — Readiness, Repository Audit, and Design Freeze

## Goal

Confirm that the repository, frontend location, documentation, and approved design are internally consistent before implementation begins.

## Allowed work

- inspect repository structure;
- inspect `frontend/` and `backend/` boundaries;
- inspect current Git status;
- inspect Node/npm availability;
- read all frontend documents;
- inspect the final approved design artifact, including its `README.md`, `Main.dc.html`, and representative artboards;
- confirm the design is the approved 2026-10-13 refinement (Tune In, TuneBar, quiet expandable Why This Fits, adaptive composer/mini-player, hero→compact history);
- map the design's component vocabulary to the architecture/phase plan without writing product code;
- identify conflicts between local code, architecture, phase plan, and design;
- identify stale documentation that could mislead later phases.

## Prohibited work

- no frontend product code;
- no scaffolding unless F1 is separately authorized;
- no backend changes;
- no dependency installation;
- no documentation rewrites beyond a tiny factual correction explicitly requested by the user.

## Expected product state

No visual change.

## Completion criteria

- frontend implementation location is unambiguous;
- the agent understands the final design/component vocabulary;
- no unresolved structural conflict blocks F1;
- current repository risks are reported clearly.

## Verification

- `git status`;
- repository tree inspection;
- Node/npm version inspection when available.

## Stop condition

Report readiness and stop.

---

# F1 — React / TypeScript / Vite Foundation

## Goal

Create a clean, working frontend application without implementing Intentune product UI yet.

## Allowed work

- scaffold React + TypeScript with Vite inside `frontend/` if not already scaffolded;
- install generated dependencies;
- remove default Vite demo content/assets;
- establish minimal `main.tsx`;
- establish minimal `App.tsx`;
- add only minimal reset/base CSS needed for a clean root;
- ensure `.gitignore` covers frontend generated output and dependencies.

## Prohibited work

Do not build:

- sidebar/drawer;
- recommendation card;
- session timeline;
- Tune controls;
- PlaylistPicker;
- mock service/orchestration;
- API integration.

Do not install extra libraries unless necessary to make the base React/Vite/TypeScript project function.

## Expected product state

A minimal clean Intentune root renders successfully. No attempt is made to reproduce the final design yet.

## Completion criteria

- development server runs;
- TypeScript compiles;
- production build succeeds;
- existing backend is untouched.

## Verification

Use the package scripts created by the project, typically including build/typecheck as available.

## Stop condition

Report the created frontend tree and verification results, then stop.

---

# F2 — Design Tokens and Mobile App Shell

## Goal

Establish the visual foundation and mobile-first page shell from the approved design without product behavior.

## Allowed work

- global design tokens;
- charcoal/violet/mauve palette;
- typography foundations using the approved Bricolage Grotesque / Instrument Sans hierarchy with fallbacks;
- spacing scale;
- radius hierarchy;
- border/surface rules;
- base responsive container;
- `AppShell`;
- `MobileHeader`;
- main session content region;
- reserved stable composer region;
- approved contextual ambient-glow/token foundation without implementing session behavior;
- mobile viewport behavior.

## Prohibited work

- no session logic;
- no recommendation logic;
- no mock orchestration;
- no API calls;
- no playlist logic;
- no controlled block registry yet.

## Expected product state

At phone width the app already feels unmistakably like Intentune: dark, premium, mobile-first, with the correct header/content/composer proportions, but the central content is mostly empty/placeheld.

## Completion criteria

- no page-level horizontal overflow;
- shell proportions closely follow the approved design;
- base touch targets/typography are usable;
- wider viewports do not break the shell;
- styles are token-driven rather than scattered constants.

## Verification

- build/typecheck;
- manual check at representative narrow, standard phone, and wider viewport widths;
- `git status`.

## Stop condition

Report visual shell status and verification, then stop.

---

# F3 — Static Component Vocabulary

## Goal

Implement the approved component vocabulary as reusable presentational components with typed props and no orchestration logic.

## Allowed components

Implement only components supported by the final approved design and architecture, including as applicable:

- `IntentSummary`;
- `UserMessage`;
- `Ack`;
- `RecommendationCardHero`;
- `RecommendationCardCompact`;
- `WhyThisFits` with quiet collapsed and concise expanded states;
- `QuickActions`;
- `TuneBar` with a maximum of two contextual actions plus `Tune`;
- `RefineControl`;
- `PlaylistPicker`;
- `UpNext`;
- `SessionSummary`;
- `DiscoveryPrompt` / `Tune in` state using Focus / Unwind / Move / Discover starter intent fixtures;
- `Composer` with presentational states for default input and compact now-playing leading slot;
- `SessionDrawer`.

Use representative fixture props only to render components for visual verification.

## Prohibited work

- no session orchestration;
- no backend calls;
- no reducer for complete session behavior;
- no recommendation algorithm;
- no persistence;
- no automatic dynamic block selection.

## Expected product state

A development/demo composition can display each approved component in representative states. All pieces look like one design system.

## Completion criteria

- components are reusable and prop-driven;
- presentation components contain no recommendation/business logic;
- no scattered mock arrays inside components;
- hero and compact recommendation variants are clearly different;
- artwork fallback exists;
- artwork contrast treatment is robust;
- chips/actions do not clip on target phone widths.

## Verification

- build/typecheck;
- existing tests if present;
- manual narrow-width check;
- `git status`.

## Stop condition

Report component inventory and verification, then stop.

---

# F4 — Controlled GenUI State Model and Renderer

## Goal

Create the typed frontend mechanism that composes approved components from structured local session state.

## Allowed work

- typed session/event/block models actually required by the approved UI;
- controlled block discriminated unions;
- local component registry/renderer;
- safe unknown-block behavior;
- feature-local reducer or equivalent deterministic state transition model if needed;
- mock fixtures isolated from presentation components;
- clear separation between semantic state and visual components.

## Prohibited work

- no AI/LLM integration;
- no FastAPI integration;
- no arbitrary server-driven JSX/HTML;
- no backend scoring/ranking logic;
- no global state library unless separately approved.

## Expected product state

The same visual components from F3 can now be rendered from typed structured state instead of being manually hard-coded into a page.

## Completion criteria

- only approved block types can render;
- unknown blocks fail safely;
- one source of truth exists for current intent;
- visual components remain business-logic free;
- mock data is isolated;
- current hero vs compact history is representable in state.

## Verification

- build/typecheck;
- targeted tests for known block rendering and unknown block fallback;
- `git status`.

## Stop condition

Report the state/rendering architecture and verification, then stop.

---

# F5 — Interactive Mock Listening Session

## Goal

Make the approved prototype genuinely interactive using local/mock state only.

## Allowed work

Implement simulated behavior for:

- create/open listening session;
- composer input;
- append `UserMessage`;
- simulate `Ack`;
- update `IntentSummary`;
- replace current recommendation;
- hero → compact history transition;
- Like;
- Not for me;
- Save;
- QuickAction selection with no more than two visible contextual actions;
- Tune / RefineControl for energy, mood, and genre;
- PlaylistPicker open/select/close;
- Up Next behavior;
- SessionDrawer switching using local mock sessions.

## Important behavior rules

- exactly one current hero recommendation at a time;
- earlier recommendations become compact history;
- intent summary and Ack never contradict each other;
- playlist sheet never preselects a playlist without user action;
- Quick Actions are contextual and restrained;
- reactions are distinct from session refinement;
- no page reload is required for session interaction.

## Prohibited work

- no FastAPI;
- no database;
- no LLM;
- no Spotify/YouTube integration;
- no persistent production storage.

## Expected product state

A user can complete the primary mobile Intentune flow and experience one coherent, reactive listening session.

## Completion criteria

- session history remains coherent;
- current intent updates correctly;
- reactions visibly update;
- Tune/Refine behavior works;
- Save opens an explicit playlist choice;
- session switching works with mock state;
- no clipped quick-action text or page overflow.

## Verification

- build/typecheck;
- tests for important state transitions added in this phase;
- manual walkthrough of the full mock flow;
- `git status`.

## Stop condition

Report the walkthrough and verification, then stop.

---

# F6 — Motion, Visual Polish, and Responsive Adaptation

## Goal

Bring the working mobile prototype to polished product-quality frontend behavior and adapt it cleanly to tablet/desktop.

## Allowed work

- spacing/typography refinement against final design;
- restrained motion for Ack, recommendation changes, hero → history, sheets, drawer, reactions;
- `prefers-reduced-motion` support;
- horizontal intent-strip behavior;
- polished QuickActions / Tune layout;
- adaptive composer / compact now-playing behavior when hero leaves viewport;
- real-artwork contrast validation across bright, dark, busy, portrait, and missing-artwork cases;
- long-title/artist/session/intent handling;
- tablet layout;
- desktop adaptation, including persistent session navigation when supported by the approved design.

## Prohibited work

- no backend integration;
- no unrelated feature additions;
- no visual redesign that abandons the approved system.

## Expected product state

The mobile implementation should closely match the final approved design and feel deliberate, tactile, calm, and stable. Wider layouts should adapt rather than simply stretch the phone screen.

## Completion criteria

- no page-level horizontal overflow on supported widths;
- no clipped intent/action labels;
- real artwork remains readable;
- focus/selected states are clear;
- reduced motion works;
- mobile, tablet, and desktop layouts are coherent;
- music remains visually dominant;
- the implementation is compared directly against the approved design artifact rather than reconstructed from memory.

## Verification

- build/typecheck;
- frontend tests;
- manual responsive checkpoints;
- accessibility sanity check;
- `git status`.

## Stop condition

Report responsive checkpoints and verification, then stop.

---

# F7 — Frontend Testing and Quality Gate

## Goal

Protect the frontend architecture and core user behavior before real API integration.

## Allowed work

Add focused tests for user-visible behavior and controlled GenUI safety, including:

- new-session empty/Tune In state;
- current intent rendering;
- known block rendering;
- unknown block fallback;
- UserMessage + Ack sequence;
- hero → compact recommendation transition;
- Like / Not for me / Save states;
- PlaylistPicker behavior;
- Tune/Refine behavior;
- session switching;
- critical accessibility behavior where practical.

Also clean up test utilities/fixtures only as required by these tests.

## Prohibited work

- no backend integration;
- no broad refactor just to increase test coverage;
- no tests for trivial implementation details or decorative CSS.

## Expected product state

No major visual change. Critical frontend behavior is protected by repeatable automated checks.

## Completion criteria

- critical flows have meaningful coverage;
- controlled block safety is tested;
- all frontend verification passes;
- no flaky tests introduced.

## Verification

- full frontend test suite;
- build/typecheck;
- `git status`.

## Stop condition

Report quality-gate results and stop.

---

# F8 — API-Ready Frontend Service Boundary

## Goal

Make the frontend ready to replace mock services with FastAPI without changing presentation components.

## Allowed work

- define frontend service interfaces around real use cases;
- define typed request/response client shapes based only on an approved backend contract;
- move/normalize mock implementations behind the same service interface;
- add loading/error states required by future HTTP behavior;
- prepare runtime configuration such as API base URL only if required by the approved contract.

## Important rule

Do not invent an API contract.

If the backend contract is not approved or implemented, stop at the frontend service abstraction and report the missing contract.

## Expected product state

The UI still runs on mocks, but presentation and feature code no longer care whether the service implementation is mock or HTTP.

## Completion criteria

- presentation components contain no direct network calls;
- mock implementation satisfies the same interface intended for the future API client;
- loading/error states exist where required;
- no backend logic is duplicated.

## Verification

- tests for service boundary and UI error/loading behavior;
- build/typecheck;
- full frontend tests;
- `git status`.

## Stop condition

Report API readiness and stop.

---

# F9 — FastAPI Integration

## Goal

Replace the appropriate mock service path with the approved FastAPI HTTP integration while preserving the frontend architecture and user experience.

## Prerequisites

Do not start F9 unless:

- FastAPI endpoints exist;
- request/response schemas are approved;
- error semantics are known;
- local backend can be run for integration testing.

## Allowed work

- implement HTTP client/service adapter;
- runtime API configuration;
- map API responses into the existing typed frontend state model;
- integrate recommendation/session behavior covered by the approved API;
- robust loading/error handling;
- integration tests using mocks or local backend as appropriate.

## Prohibited work

- do not redesign UI because of API shape;
- do not move backend business logic into frontend to compensate for missing endpoints;
- do not silently invent missing backend behavior.

## Expected product state

The existing approved Intentune UI is powered by real backend responses for the integrated use cases. The component system and interaction model remain essentially unchanged.

## Completion criteria

- real API path works for approved use cases;
- frontend handles documented error states;
- mocks remain usable for tests where appropriate;
- no direct network calls leak into presentation components;
- full frontend verification passes.

## Verification

- frontend tests;
- build/typecheck;
- integration verification against the approved FastAPI backend;
- manual primary-flow walkthrough;
- `git status`.

## Stop condition

Report integration results and stop.

---

# Final Frontend Target

After the implemented phases are approved, the frontend should provide one coherent responsive application with:

- mobile-first Intentune visual system;
- listening sessions;
- visible current intent;
- chronological conversational/music timeline;
- one current hero recommendation;
- compact historical recommendations;
- concise explainability;
- Like / Not for me / Save reactions;
- contextual Quick Actions;
- Tune / Refine controls;
- PlaylistPicker;
- Up Next when contextually useful;
- stable composer;
- controlled generative UI composition;
- safe typed component registry;
- responsive tablet/desktop adaptation;
- service boundary ready for or connected to FastAPI according to the approved phase.

The frontend must remain presentation-focused. Recommendation intelligence, intent interpretation, persistence, and other domain concerns remain outside the React UI.
