import { describe, expect, it } from 'vitest'
import { chooseService, wantsMock } from './chooseService.ts'
import { mockSessionService } from './mocks/mockSessionService.ts'

describe('choosing the session service', () => {
  it('talks to the backend unless the mock is asked for explicitly', () => {
    expect(wantsMock({ MODE: 'development' })).toBe(false)
    expect(wantsMock({ MODE: 'production' })).toBe(false)
    expect(wantsMock({ MODE: 'development', VITE_SESSION_SERVICE: 'http' })).toBe(false)
    expect(wantsMock({ MODE: 'mock' })).toBe(true)
    expect(wantsMock({ MODE: 'production', VITE_SESSION_SERVICE: 'mock' })).toBe(true)
  })

  it('builds the HTTP service by default and hands out the mock only on request', () => {
    expect(chooseService({ MODE: 'production' })).not.toBe(mockSessionService)
    expect(chooseService({ MODE: 'mock' })).toBe(mockSessionService)
  })
})
