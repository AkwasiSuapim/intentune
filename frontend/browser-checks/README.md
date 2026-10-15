# Browser checks

Checks that need a real browser: layout, motion, focus in a rendered page, measured contrast, and an automated accessibility audit. They complement `npm test` (unit, static-render and DOM-level tests in jsdom), which cannot lay out a page, run animations, or compute what assistive technology sees.

They drive headless Chrome directly over the Chrome DevTools Protocol. There is no browser-testing framework; the only extra dependency is `axe-core`.

## Requirements

- Node 22 or later (the scripts use Node's built-in `WebSocket`).
- Chrome, Chromium or Edge installed. The usual install locations on Windows, macOS and Linux are found automatically; otherwise set `CHROME_PATH` to the browser executable.
- `npm install` in `frontend/`.
- Internet access for `design-compare.mjs`: it waits for the Google web fonts in both the app and the design, because text widths depend on them, reloads a page once if they stall, and fails with a clear message if they still cannot load. The other checks run offline.

## Running

From `frontend/`:

```bash
npm run check:browser                         # build, then run every check
node browser-checks/run.mjs quality           # run some checks against the existing build
node browser-checks/accessibility.mjs keys    # one part of a check: axe | keys | text
```

The checks test the production build in `dist/`, so run `npm run build` after changing code. Each check starts its own browser on free ports and removes its temporary profile. A full run takes about four to five minutes.

Results and screenshots are written to `browser-checks/output/<check>/` (ignored by git). Each check's `results.txt` lists every check as `ok` or `FAIL` with the measured values. A check exits with code 1 if anything failed.

## What each check covers

| Script | Checks | Viewports |
|---|---|---|
| `walkthrough.mjs` | The whole mock flow, clicking and typing as a user would: Tune in, a starter, a typed request, a quick action, Like, Why this fits, tuning energy, mood and genre, saving with an explicit playlist choice, Not for me, Next, Up next, the playback clock, the drawer, switching sessions and back, replaying history, a new session. After every step: one hero at most, at most two quick actions that fit, no sideways overflow. | 390×844, 320×568 |
| `quality.mjs` | Motion (entrances, the hero settling into history, reaction confirmation, nothing looping). Overlays: focus moves in, the rest is inert, Tab stays inside, Escape and the scrim close, focus returns, exit animations finish. Reduced motion. Compact now-playing when the hero's controls scroll away. Intent chips scrolled into view and edge fades. The desktop rail. A drawer left open while the window grows. A responsive audit. Text contrast over artwork measured from rendered pixels. | Responsive audit, 16 sizes × 11 scenes: 320×568, 344×882, 360×740, 375×667, 390×844, 430×932, 600×960, 699×900, 700×900, 768×1024, 1023×768, 1024×768, 1280×800, 1440×900, 1920×1080, 844×390 (landscape phone). Interactive checks at 390×844, 320×568 and 1280×800 |
| `accessibility.mjs` | axe-core over 9 scenes at two widths and with tuning, the playlist sheet and the drawer open. Keyboard only: where focus lands after each main action, arrow keys on the tuning tabs, Tab order. Text at 200%: no sideways overflow, no cut-off control labels, the song title stays in its card. | 390×844, 1280×800 |
| `design-compare.mjs` | Every element's position and size in the 7 design scenes against the approved design export, within 1.5px. | 390×844, 768×1024 |

The responsive audit fails on any sideways page overflow, content off screen, interactive target under 44px (counting invisible hit areas), or clipped label on an intent chip, quick action, reaction, tab or option.

The contrast check hides the text, reads the pixels behind it, and requires 4.5:1 for small text and 3:1 for the song title, including over pure white and bright portrait artwork.

## Expected result

Every check passes. The design comparison allows one approved deviation: at 390px, in the `change` and `refine` scenes, the intent chips sit further left than in the design because a changed or tuned chip is scrolled fully into view (approved in F6).

## What these checks do not cover

- Only Chrome-family browsers. Firefox and Safari engines are not tested.
- Emulated viewports and touch, not physical phones.
- An automated audit and accessibility-tree names, not a real screen reader. VoiceOver, TalkBack, NVDA and JAWS remain untested.
- axe-core runs without preloading stylesheets, so its `css-orientation-lock` rule is not evaluated. The app does not lock orientation.
- They are not wired into CI.
