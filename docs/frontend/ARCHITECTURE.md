# Intentune Frontend Architecture

## Status

**Accepted frontend direction. Final approved design reference: 2026-10-13 export. Implement incrementally.**

This document defines the architecture of the Intentune browser client. It is intentionally limited to frontend responsibilities. Recommendation algorithms, backend domain models, AI intent interpretation, persistence, databases, and provider integrations are outside this document except where they define a frontend boundary.

---

## 1. Product Goal

Intentune is a **mobile-first, responsive, conversational music application**.

The product principle is:

> **Conversation steers. Music leads.**

Natural language is a control mechanism for the listening experience. Music remains the primary visual and emotional focus.

Intentune must not feel like:

- a marketing site,
- a generic dashboard,
- an analytics product,
- a general-purpose chatbot,
- a Spotify clone,
- a TikTok clone.

---

## 2. Chosen Frontend Stack

Use:

- **React** for component-based interactive UI;
- **TypeScript** for typed props, state, controlled UI schemas, and future API contracts;
- **Vite** for development/build tooling;
- **CSS Modules plus a small global token/reset layer** for styling and responsive layout;
- **oxlint** as the frontend linter (the scaffold's existing setup);
- **Vitest** as the frontend unit-test runner, with **jsdom** and **Testing Library** for DOM-level tests.

Do not use by default:

- Next.js,
- Vue,
- React Native / Expo,
- Redux,
- Tailwind,
- a heavy component framework,
- ESLint or another linter in place of oxlint.

These may be reconsidered only when a real requirement justifies the cost.

---

## 3. Product Form

The first frontend is a **mobile-first responsive web application**.

Priority order:

1. phone — primary design and interaction target;
2. tablet — expanded spacing and layout;
3. desktop — wider layout, with persistent session navigation when useful.

A PWA or native mobile client may be evaluated later. Neither is required for the first implementation.

---

## 4. Repository Boundary

Target repository structure:

```text
intentune/
├── backend/
│   └── ... Python / FastAPI application
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   ├── vite.config.ts
│   └── ...
├── docs/
│   └── frontend/
│       ├── AGENT_INSTRUCTIONS.md
│       ├── ARCHITECTURE.md
│       ├── IMPLEMENTATION_PHASES.md
│       └── design/
│           └── approved/
│               ├── README.md
│               ├── Main.dc.html
│               └── ...reference artboards
├── README.md
└── .gitignore
```

`backend/src/` and `frontend/src/` are separate source trees for separate applications.

### Approved design artifact

The exported Claude Design HTML is stored as a **reference specification**, not application source. It should live under `docs/frontend/design/approved/` when committed to the repository. `Main.dc.html` is the primary detailed reference for component states, exact visual values, and simulated interactions; individual artboards show representative compositions. Production React must not depend on the design export runtime.

---

## 5. Responsibility Boundary

### Frontend owns

- visual rendering;
- mobile-first responsive layout;
- session/navigation presentation;
- local interaction state;
- controlled generative UI composition;
- empty/loading/error states;
- user input collection;
- reaction controls;
- recommendation presentation;
- explanation presentation;
- translation of structured backend responses into approved local components.

### Frontend does not own

- recommendation scoring;
- recommendation ranking;
- model logic;
- long-term profile learning;
- AI intent interpretation;
- persistence policy;
- database rules;
- provider logic;
- authentication policy;
- server-side business validation.

A recommendation card may display a recommendation. It must not calculate why that recommendation should rank above another song.

### Intent interpretation boundary

React components, reducers, and UI composition must not perform natural-language phrase matching. Any temporary phrase interpretation belongs only behind the session-service boundary (the mock), so the backend can replace it without rewriting UI components.

**Hybrid input (B9 / F9, 2026-10-21).** If the UI already knows what the listener did, it sends that meaning; if all it has is language, the backend interprets it:
- **Starters:** a starter is sent as `{kind: 'starter', starterId, phrase}`. The service that offered the starter knows its structured intent, and the phrase is only shown as the listener's words.
- **Quick actions:** a quick action carries its own request (`QuickAction.request`). The label is presentation only, so relabelling "More like this" changes nothing it does.
- **Other controls:** Tune values, Next, Not for me, Like, Replay, and playlist choices are structured requests or service calls.
- **Typed words:** only what the listener typed travels as text (`{kind: 'message', text}`), unread. The backend's deterministic interpreter answers what it meant, or that it cannot act on it.

`src/architecture.test.ts` checks that no file in the session feature, the components, or the app shell imports a service implementation, calls the network, or matches words.

---

## 6. Data Flow

### Prototype stage

```text
User interaction
      ↓
React UI
      ↓
Feature/session state
      ↓
Mock service / mock structured state
      ↓
Controlled UI composition
      ↓
Approved React components
```

### Integrated stage

```text
User interaction
      ↓
React + TypeScript
      ↓ HTTP / JSON
FastAPI
      ↓
Backend application / intent / recommendation systems
      ↓
Structured response
      ↓
Frontend service layer
      ↓
Typed session state
      ↓
Controlled UI composition
      ↓
Approved React components
```

The browser client never calls Python directly.

---

## 7. Controlled Generative UI

Intentune uses **controlled generative UI**.

This means the application has a fixed, tested component vocabulary. Structured state determines which approved components appear and in what order.

```text
Structured session state
        ↓
UI composition policy
        ↓
Approved semantic block types
        ↓
Local component registry
        ↓
Rendered React components
```

The system does **not** generate arbitrary React code, HTML, JavaScript, or visual layouts at runtime.

A future backend may return semantic instructions such as:

```json
{
  "type": "quick_actions",
  "actions": ["more_like_this", "calmer"]
}
```

The frontend maps known values to local, approved components.

Unknown block types must fail safely.

---

## 8. Stable Shell vs Contextual Regions

### Stable shell

These remain structurally consistent:

- `AppShell`;
- `MobileHeader`;
- navigation behavior;
- typography system;
- color/token system;
- session identity;
- composer location/behavior;
- core recommendation visual language.

### Contextual / generative regions

These may appear, disappear, reorder, or change content according to typed session state:

- `IntentSummary`;
- `UserMessage`;
- `Ack`;
- `RecommendationCardHero`;
- `RecommendationCardCompact`;
- `WhyThisFits`;
- `QuickActions`;
- `TuneBar`;
- `RefineControl`;
- `PlaylistPicker`;
- `UpNext`;
- `SessionSummary`;
- `DiscoveryPrompt`.

The composition may change. The Intentune identity must not.

---

## 9. Listening Session Model

A listening session is a chronological stream.

```text
older content
    ↑
UserMessage
Ack
Recommendation history
UserMessage
Ack
Current hero recommendation
Contextual controls
    ↓
newer content
```

Conversation and music history belong to the same session. Do not create a separate general-purpose chat surface unless a later product requirement clearly justifies it.

### Recommendation hierarchy

Exactly one recommendation is the current hero at a time.

When a new recommendation becomes current:

- the prior hero transitions to `RecommendationCardCompact`;
- its reaction/outcome remains visible;
- it stays in chronological history;
- it can be revisited without turning the session into a full queue UI.

---

## 10. Intent Visibility

The current interpreted listening intent must remain visible once it exists.

Example:

```text
INTENT  [ Emotional ] [ Afrobeats ] [ Medium energy ]
```

Rules:

- intent state has a single source of truth;
- `Ack` must not contradict `IntentSummary`;
- changed dimensions may receive a subtle temporary marker;
- chips must remain readable on narrow screens;
- the strip may scroll horizontally when needed;
- tapping a chip may open the relevant refinement control.

---

## 11. Recommendation Presentation

The current recommendation is the dominant content element.

A hero recommendation may contain:

- artwork;
- title;
- artist;
- concise music descriptors;
- playback state/controls;
- quiet `WhyThisFits` explanation;
- reactions.

Do not expose:

- numerical recommendation score;
- rank numbers;
- confidence percentages;
- internal feature weights.

### Real artwork rule

The visual design must remain readable with bright, dark, busy, colorful, portrait, and low-contrast artwork.

Use controlled scrims/contrast treatment when text overlays artwork. Provide a graceful Intentune-branded fallback for missing artwork.

---

## 12. Why This Fits

Explain recommendation meaning, not mathematics.

Default state should be visually quiet and concise, for example:

```text
Why this fits
Keeps the emotional Afrobeats feel while staying relaxed.  ›
```

An expanded state may show a small number of concise reasons.

Avoid repetitive generic bullets when one strong explanation is enough.

---

## 13. Reaction Controls vs Refinement Controls

These are different concepts.

### Song reactions

Stable actions tied to a song:

- Like;
- Not for me;
- Save.

### Session refinement

Contextual actions tied to the listening direction:

- More like this;
- A bit calmer;
- More energetic;
- Keep this mood;
- Change genre;
- Something different.

Do not crowd the screen with all possible refinements.

---

## 14. Quick Actions and Tune

Use a restrained contextual tune area.

The approved interaction pattern is **at most two high-value, typed-style immediate actions plus a consistent `Tune` entry point**. Do not render a third long action merely because space appears available on one device.

Example:

```text
[ More like this ]  [ A bit calmer ]      Tune
```

`Tune` can expose `RefineControl` for more precise adjustments such as energy, mood, or genre.

This solves action overflow while preserving controlled generative behavior.

---

## 15. Playlist Picker

`PlaylistPicker` is a contextual overlay, preferably a mobile bottom sheet.

The system may hint that a playlist matches the session, but it must not silently preselect a playlist on the user's behalf.

Example:

```text
ADD TO PLAYLIST

○ Favorites
○ Study
○ Workout
○ Afrobeats
  Fits this session

+ Create playlist
```

The user explicitly chooses the destination.

---

## 16. Composer and Mini-Player Behavior

The composer is a stable control.

Example placeholder:

`Tell Intentune what you want next…`

When the current hero recommendation is visible, the composer primarily behaves as conversational input.

When the hero scrolls out of view, the leading area of the composer may expose compact now-playing context. Avoid stacking a second large mini-player above the composer.

The transition should be subtle and preserve available vertical space.

---

## 17. New Session / Tune In

A new session should feel open and musical, not like a form.

Preferred interaction language:

```text
TUNE IN
What do you need from your music right now?

[ Focus ] [ Unwind ] [ Move ] [ Discover ]
```

These starter actions represent prewritten first intents and should pass through the same eventual interaction path as typed requests.

The composer is always available as the primary free-form entry point.

---

## 18. Contextual Theme System

Intentune has one brand, not multiple generated themes.

Stable foundation:

- deep charcoal / near-black;
- violet;
- mauve;
- lavender;
- light primary text.

Only a small set of accent tokens may shift subtly with context.

Examples:

- Emotional — richer violet / mauve;
- Focused — quieter/cooler violet;
- Relax — softer mauve/lavender;
- Driven — stronger/brighter violet.

Do not remap entire palettes by mood.

---

## 19. Design Tokens

### Typography

The approved design uses:

- **Bricolage Grotesque** for expressive song titles, session titles, and selected display headings;
- **Instrument Sans** for interface text, controls, explanations, and supporting copy.

Use a documented fallback stack and avoid blocking core usability if remote fonts fail to load. Keep the number of weights restrained and preserve the design hierarchy.

### Color

Directional palette:

```text
--color-ground:        #0F0D16;
--color-surface:       #181423;
--color-raised:        #211B2D;
--color-violet:        #7C3AED;
--color-violet-high:   #A855F7;
--color-mauve:         #C084FC;
--color-lavender:      #E9D5FF;
--color-text:          #F8F7FB;
--color-text-muted:    #A79FB8;
```

The implementation may tune exact values against the approved design, but charcoal must dominate. Violet/mauve are accents, not full-screen decoration.

### Shape rule

Avoid “bubble soup.” Radius should decrease as surfaces become smaller/nested:

- overlays/sheets — largest radius;
- hero card — large radius;
- controls/buttons — medium radius;
- chips — pill radius;
- rows — smaller/subtle radius.

### Touch rule

Interactive targets should generally be at least 44px in effective touch size.

---

## 20. Motion Principles

Use motion to explain state change, not decorate.

Appropriate examples:

- Ack fade/slide;
- intent-chip state transition;
- new recommendation reveal;
- hero → compact history collapse;
- bottom-sheet entrance;
- session-drawer reveal;
- reaction confirmation.

Avoid constant motion, excessive bounce, or decorative glow animation.

Respect `prefers-reduced-motion`.

---

## 21. State Management Strategy

Start with the simplest state ownership that matches the current phase.

Preferred progression:

1. local component state for isolated interactions;
2. feature/session-level hooks;
3. `useReducer` when session transitions become multi-step and explicit;
4. Context only where shared state genuinely crosses component boundaries;
5. external global state library only if later complexity clearly justifies it.

Do not add Redux at project start.

### Session state should model concepts, not visual coordinates

Examples of useful state concepts:

- active session id;
- current intent;
- ordered session events;
- current recommendation id;
- reaction state;
- active contextual overlay;
- active refine mode;
- composer value.

---

## 22. UI Composition Model

The controlled GenUI layer should operate on typed semantic blocks rather than arbitrary view code.

Conceptual TypeScript shape:

```ts
type SessionBlock =
  | { type: 'user_message'; id: string; text: string }
  | { type: 'ack'; id: string; /* typed payload */ }
  | { type: 'recommendation'; id: string; /* typed payload */ }
  | { type: 'quick_actions'; id: string; /* typed payload */ }
  | { type: 'refine_control'; id: string; /* typed payload */ }
  | { type: 'up_next'; id: string; /* typed payload */ }
  | { type: 'session_summary'; id: string; /* typed payload */ };
```

The exact types are introduced during the implementation phase that needs them. Do not create speculative types earlier than necessary.

---

## 23. Service Boundary

Presentation components do not call the backend directly.

Use a frontend service boundary so prototype mocks can later be replaced by a real FastAPI client.

Conceptually:

```text
components
   ↓
feature/session logic
   ↓
frontend service interface
   ↓
mock implementation now
FastAPI implementation later
```

Do not scatter `fetch()` across visual components.

### Service interface (F8)

`SessionService` (`src/features/session/sessionService.ts`) is the only way the session feature reaches whatever answers it. Two implementations exist:
- **The HTTP client** (`src/services/http/`, B9/F9): the backend, and the default runtime.
- **The mock** (`src/mocks/`): the implementation the tests, the design demo, and the browser checks use.

`App.tsx` is the only place one is chosen, through `chooseService()` (`src/chooseService.ts`): the HTTP client, unless Vite's `mock` mode (`npm run dev:mock`, `npm run build:mock`) or `VITE_SESSION_SERVICE=mock` asks for the mock. Until the B9 review (2026-10-22) the mock was the default.

**Extended in B9 (F9):**
- **TurnContext and new requests:** `TurnContext` carries the frontend session id and the service's reference for the song in view (`currentRef`). The new requests are `starter`, `control`, `track_ended`, and `replay`, and `next` and `message` may carry the player's facts (`PlaybackFacts`).
- **New answers:** `TurnResponse` can be `not_understood`, which the feature shows as such, not as a failure. A `SessionTurn` whose `recommendation` is null keeps the hero playing ("music leads"), and `restart` starts it again.
- **Recorded, not local:** `react()` records a Like or an Unlike, `savePlaylists()` saves to and removes from playlists, and `createPlaylist()` creates one. A Like or save the service does not record is undone, so the card shows the truth.
- **Recommendations:** a recommendation carries the service's `ref` and an `audioUrl`, and its `why` is optional; real recommendations carry none, so Why this fits is not shown for them.
- **What the library can use** (B9 review, 2026-10-22): the environment's `unavailableDimensions` lists the Tune dimensions the library has no evidence for (from the backend vocabulary's `support`; the mock has none). Tune keeps all three tabs, as the approved design does, but marks an unavailable one: the tab is struck through and its accessible name adds "unavailable", the panel explains why, and its options are `aria-disabled` and do nothing. A single value can be unavailable too (`IntentValue.unavailable`: a mood no track declares, from the vocabulary's `usable_moods`), dimmed with a note. `planCommand` never sends either.
- **Starters** (B9 consistency, 2026-10-22): a starter whose mood or energy the library lacks carries `unavailableReason`. `DiscoveryPrompt` shows it in the same language (struck through, dimmed, "unavailable" in its accessible name), with the reason visible and linked by `aria-describedby`; pressing it does nothing, and `planCommand` sends nothing for it. Discover is a control, so it stays usable. The mock reports full capability, so the design and the browser checks show every starter.
- **A library that is not ready** (readiness model, 2026-10-22): `libraryReady` is false while nothing is playable. That is one reason, about the library, so no dimension is marked for it: every starter (Discover included) shows "Your library has no playable music yet", Tune locks every tab with a library note, and `LIBRARY_NOT_READY` is answered as `library_not_ready` ("Library not ready").
- **The `unavailable` answer:** the backend refuses an intent it understood but the library cannot act on (`INTENT_UNAVAILABLE`), and the service answers `{kind: 'unavailable', echo?, message}`. It is shown as "Not available yet" with the reason, not as a failure, and changes nothing. A past session whose intent the library can no longer act on answers it too: it cannot continue, in part or at all, and says so.

- **Asynchronous.** Every method returns a promise and rejects when it cannot answer. The mock answers at once through the same interface.
- **Failure is opaque.** The feature never inspects a rejection: any failure means "the request did not go through". Mapping specific backend errors (validation, rate limits, provider failures) to different UI waits for approved error semantics.
- **Commands stay pure.** `planCommand` takes no service. It returns the changes to make at once plus, at most, one `ServiceQuestion`. `ask` puts the question to the service and returns the answer, or the failure, as one action for the session that asked. `ask` never rejects.
- **One request at a time per session.** While a request that moves the session forward (a message, starter, quick action, tuning value, Next, Not for me) is pending, further ones are not sent. Local actions (play/pause, Why this fits, opening Tune, the drawer, switching sessions) carry on.
- **Answers go to the session that asked**, even if the user has opened another session since.
- **Hints are optional.** Quick actions after a reaction and playlist suggestions never block anything. If one fails it is left out. If it arrives after the song has changed it is dropped.

Loading and error states:

- **Sessions loading.** `WorkspaceStatus` shows the wordmark and "Loading your sessions…". It fades in only after 600ms, so a fast load shows nothing but the background.
- **Sessions failed to load.** The screen says so and offers Try again. The button stays (`aria-disabled`) while a retry loads, so focus is not lost.
- **Answer pending.** The user's words appear at once with a `turn_status` note, "Working on it…", where the answer will appear. The note fades in after 400ms. A typed draft is kept, not sent, until the answer arrives.
- **Answer failed.** The note becomes "That didn't go through." with Try again. The words, the song and the intent stay as they were. Try again resends the same request; anything else the user asks replaces it.

### Backend contract status

**Integrated (B9 / F9, 2026-10-21).** The contract is `docs/design/api-design.md` (backend B8, extended in B9). `src/services/http/httpSessionService.ts` implements `SessionService` over it:

- **Requests:**
  - **Starters:** `POST /sessions` with the starter's structured context. Discover is `surprise_me`.
  - **Controls, Tune, Not for me, and Next:** `POST …/turns`. Next carries the player's facts, recorded as the skip.
  - **A song that ended:** a `complete` playback event.
  - **Replay, Like, and Unlike:** reactions.
  - **Saves:** playlist items, which are PLAYLIST_ADD feedback when the song is a recommendation of the playing session.
  - **Typed words:** a `message` turn, or the start's `message`. `422 MESSAGE_NOT_UNDERSTOOD` becomes the `not_understood` answer.
- **Play:** a new hero starts playing in the approved UI, so a session that has just started is told to play (a `next` turn while nothing plays).
- **Tuning:** the options come from `GET /listening/vocabulary`: the library's genres, the five curated moods, and the energy scale. Energy is kept and shown but ranks nothing until it is measured.
- **The drawer:** it opens with the 20 most recent backend sessions, rebuilt from their history.
- **Past sessions:** the backend keeps one active session, so a past session continued from the drawer becomes a new backend session with its last context. Its old songs can still be saved to playlists, but not liked or replayed.
- **Not provided by the backend:** artwork (the Intentune fallback shows), playlist suggestions, and explanations (Why this fits is hidden). Playlist tones are derived from the playlist id, as presentation.

Vite proxies `/api` to the backend in development (`INTENTUNE_API_URL`, default `http://127.0.0.1:8000`), so the app calls its own origin.

### Playback authority boundary

**Current (B9 / F9).** A recommendation with an `audioUrl` plays through an audio element (`src/features/session/useAudioPlayback.ts`), and that element is the playback authority:
- **Reported to the session:** its position and duration (`playback_progressed`) and its end (`track_ended`, sent as a `complete` with the player's facts).
- **Applied to it:** the session's play and pause.
- **Refused playback:** a browser that refuses to start playing leaves the session paused.

The simulated clock (`tick`) runs only for a recommendation without audio, the mock's, so the two never run together. The element is created only once a recommendation with audio appears.

---

## 24. Suggested Frontend Structure

Create directories only when working code requires them.

A likely mature shape is:

```text
frontend/
├── src/
│   ├── app/
│   ├── components/
│   ├── features/
│   │   └── session/
│   ├── services/
│   ├── mocks/
│   ├── styles/
│   ├── types/
│   ├── App.tsx
│   └── main.tsx
├── public/
├── package.json
└── vite.config.ts
```

This is a direction, not permission to create every directory immediately.

---

## 25. Accessibility and Responsive Requirements

The frontend must handle:

- narrow phone widths;
- long song titles;
- long artist names;
- long session names;
- text scaling;
- keyboard navigation where applicable;
- visible focus states;
- reduced motion;
- readable artwork overlays;
- non-color-only state indication.

Intent chips and quick actions must never clip text or create page-level horizontal overflow.

### Keyboard and announcement rules

- Use an ARIA widget role only with the keyboard behavior it implies. The tuning tabs follow the tabs pattern: one Tab stop, arrow keys and Home/End move and select, and the panel is labelled by its tab. Tuning values are toggle buttons (`aria-pressed`), not radios, because choosing one retunes the session immediately; radio arrow keys would start a new turn on every keypress.
- When a control the user is focused on is replaced (a new recommendation, the refine control replacing the quick actions), focus moves to its counterpart rather than falling to the page. Controls that can be replaced carry `data-focus-key`.
- Overlays make the rest of the screen inert, take focus when they open, close on Escape, and hand focus back to whatever opened them.
- New turns are announced once, politely, by the shell's single live region. Items in the session history are not live regions.
- While an answer is pending, focus that has lost its control (a starter, Try again) waits on the pending note. It then moves to the new song or, if the request failed, to Try again. A failure is announced; waiting is not.

---

## 26. Testing Strategy

Test user-visible behavior and architectural boundaries, not implementation trivia.

**Vitest** is the approved unit-test runner (`npm test` in `frontend/`). It reuses the Vite configuration. Tests live next to the code they cover as `*.test.ts` / `*.test.tsx`. Do not add further test libraries merely for completeness; add one only when a phase has a concrete need that the existing setup cannot meet.

DOM-level tests (`*.dom.test.tsx`) run in **jsdom** with **@testing-library/react** (and its peer **@testing-library/dom**) and **@testing-library/user-event**. They exist because event wiring, focus management, keyboard behavior, and effect-driven behavior cannot be checked by rendering to static markup. `src/test/dom.tsx` supplies what jsdom lacks (IntersectionObserver, ResizeObserver, `matchMedia`, scrolling) as fakes the tests can drive, and runs Vitest's fake clock.

What each layer protects:

- **Pure tests:** composition policy, reducers, commands, the mock service, announcement wording, and the service boundary: what is sent and when, pending and failed requests, retries, late answers, and hints that fail or arrive late.
- **Static-render tests:** every block type through the registry, and the unknown-block fallback.
- **DOM tests:** the interactive app by pointer and keyboard: commands reaching the session, focus moves, overlays, Escape, tuning keyboard behavior, the announcer, the playback clock, compact now-playing. They also cover loading, waiting and failure states, using a service whose answers the test releases or fails (`heldService` in `src/test/dom.tsx`).
- **Browser checks (`npm run check:browser`, not part of `npm test`):** the full mock walkthrough, layout and overflow across a fixed viewport matrix, motion and reduced motion, overlay focus and exit animations, contrast over artwork, text at 200%, an automated accessibility audit (axe-core), a keyboard-only probe, and a comparison with the approved design. jsdom has no layout or animation, so these need a real browser. They live in `frontend/browser-checks/`, which documents requirements, viewports and expected results.

**Not yet validated:** the frontend has not been tested on physical phones (iOS Safari, Android Chrome) or with real screen readers (VoiceOver, TalkBack, NVDA, JAWS). Emulated devices and automated audits are not a substitute and must not be reported as such.

Important coverage includes:

- empty/new-session state;
- current-intent rendering;
- known controlled block rendering;
- unknown block fallback;
- user message + Ack sequence;
- hero → compact recommendation transition;
- reaction states;
- PlaylistPicker behavior;
- session switching;
- responsive behavior where practical;
- service-boundary behavior during API integration.

Do not over-test purely decorative CSS.

---

## 27. Architecture Success Criteria

The frontend architecture is successful when:

- the app feels like one coherent music product;
- controlled UI states can change without arbitrary layout generation;
- business logic remains outside presentation components;
- mock data can later be replaced by FastAPI without redesigning the UI;
- the mobile experience is excellent;
- tablet/desktop adaptation does not require a second frontend;
- the component system remains understandable to another engineer;
- new UI behavior can be tested and debugged deterministically.
