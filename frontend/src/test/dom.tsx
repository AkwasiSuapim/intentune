// Shared set-up for DOM-level tests (files ending .dom.test.tsx, run in
// jsdom). Supplies the browser APIs jsdom lacks, with fakes the tests can
// drive, and renders the interactive app on the mock service.
import { act, cleanup, render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, vi } from 'vitest'
import ListeningSessions from '../features/session/ListeningSessions.tsx'
import { mockSessionService } from '../mocks/mockSessionService.ts'

// --- IntersectionObserver: reports only when a test says so ---------------

type Watcher = {
  callback: IntersectionObserverCallback
  observer: IntersectionObserver
  targets: Set<Element>
}
const watchers = new Set<Watcher>()

class FakeIntersectionObserver {
  private readonly watcher: Watcher

  constructor(callback: IntersectionObserverCallback) {
    this.watcher = {
      callback,
      observer: this as unknown as IntersectionObserver,
      targets: new Set(),
    }
    watchers.add(this.watcher)
  }

  observe(target: Element) {
    this.watcher.targets.add(target)
  }

  unobserve(target: Element) {
    this.watcher.targets.delete(target)
  }

  disconnect() {
    watchers.delete(this.watcher)
  }

  takeRecords() {
    return []
  }
}

/** Reports every observed element as scrolled into or out of view. */
export function setObservedVisible(visible: boolean) {
  act(() => {
    for (const { callback, observer, targets } of [...watchers]) {
      callback(
        [...targets].map(
          (target) =>
            ({ target, isIntersecting: visible }) as IntersectionObserverEntry,
        ),
        observer,
      )
    }
  })
}

// --- matchMedia: phone width unless a test widens the screen ---------------

let wideScreen = false

/** Makes `(min-width: …)` queries match, as on a desktop window. */
export function useWideScreen(wide: boolean) {
  wideScreen = wide
}

function fakeMatchMedia(query: string): MediaQueryList {
  return {
    matches: wideScreen && query.includes('min-width'),
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }
}

class FakeResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.useFakeTimers()
  // Testing Library only knows how to move Jest's fake clock; without this it
  // waits forever on a timer that never fires. Point it at Vitest's clock.
  vi.stubGlobal('jest', {
    advanceTimersByTime: (ms: number) => vi.advanceTimersByTime(ms),
  })
  wideScreen = false
  vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver)
  vi.stubGlobal('ResizeObserver', FakeResizeObserver)
  vi.stubGlobal('matchMedia', fakeMatchMedia)
  // jsdom has no layout, so scrolling is a no-op rather than missing.
  Element.prototype.scrollTo = () => {}
  Element.prototype.scrollIntoView = () => {}
})

afterEach(() => {
  cleanup()
  watchers.clear()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

/** Moves the fake clock on, applying whatever React does in response. */
export function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms)
  })
}

/** Renders the interactive app, with a user driving it by pointer and keyboard. */
export function renderApp() {
  const user = userEvent.setup({
    advanceTimers: (ms) => vi.advanceTimersByTime(ms),
  })
  return { user, ...render(<ListeningSessions service={mockSessionService} />) }
}
