// Which session service the app talks to. Normally the backend, at
// VITE_API_BASE_URL (empty means this origin, which the Vite dev server
// proxies to the backend). The mock answers only when asked for explicitly:
// the `mock` mode (`npm run dev:mock`, `npm run build:mock`) or
// VITE_SESSION_SERVICE=mock. So nobody running the integrated app gets
// simulated recommendations by accident.
import type { SessionService } from './features/session/sessionService.ts'
import { mockSessionService } from './mocks/mockSessionService.ts'
import { createApiClient } from './services/http/client.ts'
import { createHttpSessionService } from './services/http/httpSessionService.ts'

type Env = { MODE: string; VITE_SESSION_SERVICE?: string; VITE_API_BASE_URL?: string }

export function wantsMock(env: Env): boolean {
  return env.MODE === 'mock' || env.VITE_SESSION_SERVICE === 'mock'
}

export function chooseService(env: Env): SessionService {
  if (wantsMock(env)) return mockSessionService
  return createHttpSessionService(createApiClient(env.VITE_API_BASE_URL ?? ''))
}
