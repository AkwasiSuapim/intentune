// The frontend's boundaries (ARCHITECTURE.md §5, §23; the B9 input decision):
// presentation and the session feature never reach a service implementation
// or the network directly, and never read the listener's words. Only App.tsx
// chooses a service; only src/services/ talks HTTP; only the mock reads phrases.
import { describe, expect, it } from 'vitest'

const ALL = import.meta.glob<string>(['./features/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './app/**/*.{ts,tsx}'], {
  query: '?raw',
  import: 'default',
  eager: true,
})
const PRESENTATION = Object.entries(ALL).filter(([path]) => !/\.test\.tsx?$/.test(path))

const offending = (pattern: RegExp) => PRESENTATION.filter(([, source]) => pattern.test(source)).map(([path]) => path)

describe('frontend boundaries', () => {
  it('checks the session feature, the components, and the app shell', () => {
    expect(PRESENTATION.length).toBeGreaterThan(40)
  })

  it('keeps service implementations out of presentation and the session feature', () => {
    expect(offending(/from ['"][^'"]*\/(mocks|services)\//)).toEqual([])
  })

  it('makes no network calls outside src/services', () => {
    expect(offending(/\bfetch\(|XMLHttpRequest|new WebSocket/)).toEqual([])
  })

  it('never matches what the listener typed against phrases', () => {
    // Text matching on words is the service's (the mock's, or the backend's): never here.
    expect(offending(/\.(includes|startsWith|endsWith|match|search)\(\s*['"`][a-z][^'"`]*\s[^'"`]*['"`]/i)).toEqual([])
    expect(offending(/\.toLowerCase\(\)\.(includes|indexOf)\(/)).toEqual([])
  })
})
