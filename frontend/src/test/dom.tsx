// Shared set-up for DOM-level tests (files ending .dom.test.tsx, run in
// jsdom). Supplies the browser APIs jsdom lacks, with fakes the tests can
// drive, and renders the interactive app on the mock service or on one whose
// answers the test holds back.
import { act, cleanup, render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { afterEach, beforeEach, vi } from 'vitest'
import ListeningSessions from '../features/session/ListeningSessions.tsx'
import type { SessionService } from '../features/session/sessionService.ts'
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

/**
 * Lets every service answer already on its way arrive and render. A message
 * through a MessageChannel is a real macrotask, which the fake clock leaves
 * alone, so every settled promise has been handled by the time it arrives.
 */
export async function settle() {
  await act(
    () =>
      new Promise<void>((resolve) => {
        const channel = new MessageChannel()
        channel.port1.onmessage = () => {
          channel.port1.close()
          resolve()
        }
        channel.port2.postMessage(null)
      }),
  )
}

/** A user whose every action also waits for the answers it set off. */
function settling(user: UserEvent): UserEvent {
  return new Proxy(user, {
    get(target, key, receiver) {
      const value: unknown = Reflect.get(target, key, receiver)
      if (typeof value !== 'function') return value
      return async (...args: unknown[]) => {
        const result: unknown = await value.apply(target, args)
        await settle()
        return result
      }
    },
  })
}

/**
 * Renders the interactive app once its sessions have loaded, with a user
 * driving it by pointer and keyboard.
 */
export async function renderApp(service: SessionService = mockSessionService) {
  const user = userEvent.setup({
    advanceTimers: (ms) => vi.advanceTimersByTime(ms),
  })
  const rendered = render(<ListeningSessions service={service} />)
  await settle()
  return { user: settling(user), ...rendered }
}

/**
 * The mock service, except that each answer waits until the test lets it
 * through or makes it fail, so the states in between can be seen.
 */
export function heldService() {
  const waiting: ((outcome: 'answer' | 'fail') => void)[] = []
  const hold =
    <Args extends unknown[], Answer>(ask: (...args: Args) => Promise<Answer>) =>
    (...args: Args) =>
      new Promise<Answer>((resolve, reject) => {
        waiting.push((outcome) =>
          outcome === 'answer'
            ? ask(...args).then(resolve, reject)
            : reject(new Error('The service could not be reached')),
        )
      })

  const service: SessionService = {
    loadWorkspace: hold(mockSessionService.loadWorkspace),
    respond: hold(mockSessionService.respond),
    react: hold(mockSessionService.react),
    savePlaylists: hold(mockSessionService.savePlaylists),
    createPlaylist: hold(mockSessionService.createPlaylist),
    quickActionsAfter: hold(mockSessionService.quickActionsAfter),
    suggestPlaylists: hold(mockSessionService.suggestPlaylists),
  }
  const release = async (outcome: 'answer' | 'fail') => {
    const next = waiting.shift()
    if (!next) throw new Error('No request is waiting for an answer')
    next(outcome)
    await settle()
  }

  return {
    service,
    /** Lets the oldest waiting request through to the mock. */
    answer: () => release('answer'),
    /** Makes the oldest waiting request fail. */
    fail: () => release('fail'),
    /** How many requests are still waiting. */
    waiting: () => waiting.length,
  }
}
