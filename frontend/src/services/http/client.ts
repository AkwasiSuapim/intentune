// A small JSON client for the backend. Requests go to `baseUrl` + path; with
// the Vite dev proxy the base is empty and `/api` reaches the backend.
import type { ErrorBody } from './api.ts'

/** An answer in the backend's error envelope (spec §26). */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>
  readonly requestId: string | null

  constructor(status: number, body: ErrorBody | null) {
    super(body?.error.message ?? `The backend answered ${status}.`)
    this.name = 'ApiError'
    this.status = status
    this.code = body?.error.code ?? 'HTTP_ERROR'
    this.details = body?.error.details ?? {}
    this.requestId = body?.error.request_id ?? null
  }
}

export type Fetch = typeof fetch

export type ApiClient = {
  get<T>(path: string): Promise<T>
  post<T>(path: string, body?: unknown): Promise<T>
  delete(path: string): Promise<void>
  /** Turns a path the backend gave (such as an audio URL) into one to load. */
  url(path: string): string
}

export function createApiClient(baseUrl = '', fetchImpl: Fetch = fetch): ApiClient {
  const base = baseUrl.replace(/\/+$/, '')

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const response = await fetchImpl(`${base}${path}`, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    if (response.status === 204) return undefined as T
    const text = await response.text()
    const parsed: unknown = text ? JSON.parse(text) : null
    if (!response.ok) {
      const envelope =
        parsed && typeof parsed === 'object' && 'error' in parsed ? (parsed as ErrorBody) : null
      throw new ApiError(response.status, envelope)
    }
    return parsed as T
  }

  return {
    get: (path) => request('GET', path),
    post: (path, body) => request('POST', path, body ?? {}),
    delete: (path) => request<void>('DELETE', path),
    url: (path) => `${base}${path}`,
  }
}
