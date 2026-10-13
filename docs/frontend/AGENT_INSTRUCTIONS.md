# Intentune Frontend — Agent Execution Instructions

## Purpose

This file is the execution entry point for any coding agent working on the Intentune frontend.

The agent must treat the local repository as the source of truth for what is actually implemented. This folder defines the approved frontend architecture, implementation order, engineering constraints, and quality gates.

Do not implement the whole frontend at once.

---

## Required Reading Order

Before changing any file, read these documents completely:

1. `docs/frontend/AGENT_INSTRUCTIONS.md`
2. `docs/frontend/ARCHITECTURE.md`
3. `docs/frontend/IMPLEMENTATION_PHASES.md`
4. the final approved Intentune design artifact under `docs/frontend/design/approved/` (or, if the repository has not yet stored it there, the explicitly attached final design artifact)
5. the relevant existing repository files for the phase being implemented

The approved design export dated 2026-10-13 is the current visual/interaction reference. Its export may contain `README.md`, `Main.dc.html`, one or more artboard `.dc.html` files, and runtime/vendor files. Read the design `README.md` first, then inspect `Main.dc.html` and the relevant artboards. The exported HTML is a **reference mockup**, not production code to copy wholesale. Translate it into maintainable React components and the project's styling system.

If the final design artifact is unavailable, F0 and basic F1 setup may still be possible if their prerequisites are otherwise satisfied. **F2 or any later visual/product phase must not proceed by guessing the design.** Stop and report the missing artifact.

---

## Source-of-Truth Precedence

When information conflicts, use this order:

1. **Local repository** — what is actually implemented now
2. **`ARCHITECTURE.md`** — frontend engineering boundaries and architectural decisions
3. **`IMPLEMENTATION_PHASES.md`** — what may be implemented in the current phase
4. **Final approved design artifact** — exact visual appearance, hierarchy, spacing, typography, interaction language, and component states
5. **Older project documentation** — historical context only unless still consistent with the current code and the frontend documents above

If the approved design and architecture appear to conflict:

- engineering boundaries and responsibility rules in `ARCHITECTURE.md` win;
- phase scope in `IMPLEMENTATION_PHASES.md` wins;
- the approved design wins for visual detail and approved interaction behavior;
- if the conflict would require changing architecture or phase scope, stop and report it instead of choosing silently.

Do not treat planned documentation as proof that functionality exists.

---

## Phase Authorization Rule

The user must explicitly name the phase to implement, for example:

`Implement frontend phase F2 only.`

If no phase is explicitly authorized:

- inspect the repository,
- determine the current frontend state,
- identify the next likely phase,
- report what you found,
- **do not modify files**.

Never infer permission to continue into the next phase.

After completing an authorized phase:

- run the required verification,
- report the result,
- stop.

Do not begin, scaffold, partially prepare, or pre-implement the next phase.

---

## Mandatory Pre-Change Procedure

Before editing:

1. run `git status`;
2. inspect the repository tree relevant to frontend work;
3. inspect the current `frontend/` contents;
4. inspect package/configuration files if they exist;
5. inspect existing frontend tests if they exist;
6. run the current frontend verification commands if the frontend is runnable;
7. identify any pre-existing failures before making changes;
8. confirm that the requested work belongs to the authorized phase.

Do not modify backend code for a frontend phase unless the phase explicitly requires an integration change and the user has authorized that integration work.

---

## Technology Decisions

The approved frontend stack is:

- React
- TypeScript
- Vite
- responsive CSS / CSS Modules
- oxlint for linting (the scaffold's existing setup)

Do not replace or add major frontend technologies without explicit approval.

Do not introduce by default:

- Next.js
- Vue
- React Native / Expo
- Redux
- Tailwind
- Material UI
- Chakra UI
- shadcn/ui
- React Query
- Axios
- a global state library
- a routing library
- ESLint or another linter in place of oxlint

A dependency may be added only when the current phase has a concrete need that cannot be handled cleanly with the existing stack. Explain the need before adding it.

---

## Product Rule

**Conversation steers. Music leads.**

The interface must feel like a music application, not a general-purpose chatbot.

The frontend must never expose internal recommendation mathematics such as:

- recommendation scores,
- confidence percentages,
- ranking numbers,
- feature-weight calculations.

Music, listening intent, contextual actions, and concise explanations are user-facing. Scoring and ranking remain backend concerns.

---

## Frontend / Backend Boundary

The frontend owns:

- rendering,
- responsive layout,
- interaction state,
- navigation presentation,
- controlled generative UI composition,
- local prototype behavior,
- typed API-facing client models later,
- loading / empty / error states.

The frontend does not own:

- recommendation scoring,
- ranking,
- AI intent interpretation,
- user-profile learning,
- persistence rules,
- database logic,
- provider logic,
- authentication policy,
- backend validation rules.

Do not duplicate backend business logic in React.

---

## Controlled Generative UI Rule

Intentune uses a controlled component vocabulary.

The frontend may dynamically compose approved local components based on typed application state. It must not execute arbitrary server-provided HTML, JavaScript, JSX, styles, or component code.

Approved component categories are defined in `ARCHITECTURE.md` and introduced phase-by-phase in `IMPLEMENTATION_PHASES.md`.

Unknown generative block types must fail safely and visibly during development rather than silently rendering arbitrary content.

---

## Code Quality Rules

Prefer:

- small focused components,
- typed props,
- explicit state models,
- reusable design tokens,
- semantic HTML,
- accessible interactions,
- feature-local state,
- `useReducer` / Context only when state complexity actually requires it,
- isolated mock/service boundaries,
- readable code over clever abstractions.

Avoid:

- giant `App.tsx`,
- giant session components,
- presentation components containing business logic,
- scattered mock data,
- direct API calls inside visual components,
- duplicated style constants,
- speculative folders with no working code,
- abstractions created only for imagined future requirements.

---

## Approved Design Artifact Contract

For F0 and every design-bearing phase, treat the final approved design as a first-class repository artifact.

Preferred repository location:

```text
docs/frontend/design/approved/
├── README.md
├── Main.dc.html
├── S1-NewSession.dc.html
└── ...additional exported artboards/reference files when present
```

Rules:

- read the design export's `README.md` before using the HTML;
- inspect `Main.dc.html` for the complete component/state system and precise design values;
- inspect individual artboards for representative state composition;
- do not import the exported runtime/vendor scripts into the production frontend;
- do not copy the generated markup into React as one monolithic component;
- do not preserve design-tool-specific abstractions such as `<x-dc>`, `<sc-if>`, `<sc-for>`, or inline-template runtime code;
- reproduce the approved experience using semantic React components, TypeScript, CSS Modules/tokens, and the phase architecture;
- preserve accessibility intent such as labels, touch targets, focus semantics, reduced motion, and readable contrast;
- when the export contains mock behavior, reproduce only the behavior authorized by the current implementation phase.

The design artifact is a **specification and reference**, not an implementation dependency.

---

## Design Implementation Rules

Use the final approved design as visual reference, not as production code to paste verbatim.

Preserve:

- mobile-first hierarchy;
- `Tune in` as the new-session entry language;
- dark charcoal foundation with restrained contextual violet/mauve accents;
- Bricolage Grotesque for expressive song/session headings and Instrument Sans for interface text, unless a technical font-loading constraint is reported;
- stable shell;
- horizontally resilient current-intent strip;
- chronological listening-session concept;
- exactly one current hero recommendation;
- compact historical recommendations;
- quiet, expandable `Why this fits`;
- TuneBar behavior: at most two contextual typed-style actions plus `Tune`;
- RefineControl for energy/mood/genre;
- stable composer with adaptive compact now-playing behavior when the hero leaves view;
- session drawer;
- contextual overlays such as PlaylistPicker;
- real-artwork contrast treatment and Intentune fallback artwork.

The implementation must prevent:

- horizontal page overflow,
- clipped intent chips,
- clipped action labels,
- tiny tap targets,
- unreadable text over artwork,
- conversation becoming visually louder than music.

---

## Mock Data Rule

Before the authorized API integration phase:

- use local/mock structured data only;
- isolate mock data from presentation components;
- keep the mock service shape replaceable by the future FastAPI client;
- do not invent production endpoints;
- do not connect databases, LLMs, Spotify, YouTube, or other providers.

Prototype state may reset after refresh unless a phase explicitly adds persistence.

---

## Verification Rule

Every phase must end with the verification listed in `IMPLEMENTATION_PHASES.md`.

At minimum, when applicable:

- run TypeScript/build verification;
- run frontend tests;
- verify responsive behavior required by the phase;
- run `git status`;
- confirm no unrelated backend files changed;
- distinguish pre-existing failures from failures introduced by the phase.

Do not hide, suppress, or silently work around failures.

---

## Git Rule

Unless explicitly instructed otherwise:

- do not commit;
- do not push;
- do not create or switch branches;
- do not rewrite Git history.

---

## Required Final Report for Every Phase

Keep the report concise and factual. Include:

1. phase implemented;
2. files created/modified/deleted;
3. important architectural choices made within the phase;
4. verification commands and results;
5. any pre-existing issue encountered;
6. any remaining issue that blocks approval;
7. confirmation that the next phase was not started.

Then stop and wait for the user's review.
