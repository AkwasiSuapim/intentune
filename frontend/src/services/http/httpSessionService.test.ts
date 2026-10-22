import { beforeEach, describe, expect, it } from 'vitest'
import type { TurnContext, TurnResponse } from '../../features/session/sessionService.ts'
import type { CapabilityDimension, ContextBody, DimensionState, OccurrenceBody, SessionStateBody, VocabularyBody } from './api.ts'
import { createApiClient } from './client.ts'
import { createHttpSessionService } from './httpSessionService.ts'
import { EMPTY_CONTEXT } from './mapping.ts'

// A fake backend: each route answers from a handler, and every call is kept.
type Call = { method: string; path: string; body: unknown }
type Handler = (body: unknown, path: string) => { status?: number; body?: unknown }

function fakeBackend(routes: Record<string, Handler>) {
  const calls: Call[] = []
  const fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    calls.push({ method, path: url, body })
    const key = Object.keys(routes).find((route) => {
      const [routeMethod, pattern] = route.split(' ')
      return routeMethod === method && new RegExp(`^${pattern}$`).test(url.split('?')[0])
    })
    if (!key) return new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: 'No route', details: {}, request_id: 'r' } }), { status: 404 })
    const answer = routes[key](body, url)
    const status = answer.status ?? 200
    return new Response(status === 204 ? null : JSON.stringify(answer.body ?? {}), { status })
  }
  return { calls, fetch: fetch as typeof globalThis.fetch }
}

const ALL_DIMENSIONS: CapabilityDimension[] = ['mood', 'genre', 'energy', 'danceability', 'tempo', 'valence', 'acousticness']

/** Each dimension's state in a ready library where only these have usable data. */
const usable = (...dimensions: CapabilityDimension[]) =>
  Object.fromEntries(ALL_DIMENSIONS.map((dimension) => [dimension, dimensions.includes(dimension) ? 'usable' : 'no_data'])) as Record<
    CapabilityDimension,
    DimensionState
  >

/** A library with nothing playable: not ready, and no dimension judged. */
const NOT_READY: Partial<VocabularyBody> = {
  genres: [],
  library: { ready: false, playable_tracks: 0 },
  dimensions: Object.fromEntries(ALL_DIMENSIONS.map((dimension) => [dimension, 'library_not_ready'])) as Record<CapabilityDimension, DimensionState>,
  usable_moods: [],
}

const VOCABULARY: VocabularyBody = {
  genres: ['Ambient', 'Jazz'],
  moods: ['Emotional', 'Focused', 'Calm', 'Joyful', 'Driven'],
  energy: [
    { id: 'very-low', label: 'Very low', target_energy: 0.1 },
    { id: 'low', label: 'Low', target_energy: 0.3 },
    { id: 'medium', label: 'Medium', target_energy: 0.5 },
    { id: 'high', label: 'High', target_energy: 0.7 },
    { id: 'very-high', label: 'Very high', target_energy: 0.9 },
  ],
  // As a library the importer filled: genre tags, but no mood tags, and nothing measured.
  library: { ready: true, playable_tracks: 7 },
  dimensions: usable('genre'),
  usable_moods: [],
  unmapped_fields: ['current_mood', 'listening_goal', 'activity'],
}

const CURATED = ['Emotional', 'Focused', 'Calm', 'Joyful', 'Driven']

/** A 422 the backend answers for an intent it understood but the library cannot act on. */
const unavailable = (message: string, details: Record<string, unknown>) => ({
  status: 422,
  body: { error: { code: 'INTENT_UNAVAILABLE', message, details, request_id: 'r1' } },
})

function occurrence(id: string, status: OccurrenceBody['status'], title: string, extra: Partial<OccurrenceBody> = {}): OccurrenceBody {
  return {
    occurrence_id: id,
    track: {
      track_id: `track-${title}`,
      title,
      file_name: `${title}.flac`,
      artist: 'Artist',
      album: null,
      duration_seconds: 200,
      status: 'ready',
      playable: true,
      genres: ['Jazz'],
      moods: [],
      audio_url: `/api/v1/tracks/track-${title}/audio`,
    },
    status,
    rank: 1,
    score: 0.8,
    algorithm: 'policy-v1',
    is_exploration: false,
    surfaced_position: 0,
    queue_position: status === 'queued' ? 0 : null,
    surfaced_at: '2026-10-21T10:00:00Z',
    started_at: status === 'queued' ? null : '2026-10-21T10:00:01Z',
    finished_at: null,
    ...extra,
  }
}

function state(context: Partial<ContextBody>, playing: OccurrenceBody | null, queue: OccurrenceBody[] = [], status: 'active' | 'ended' = 'active'): SessionStateBody {
  return {
    session: {
      session_id: 'backend-1',
      status,
      context: { ...EMPTY_CONTEXT, ...context },
      started_at: '2026-10-21T10:00:00Z',
      updated_at: '2026-10-21T10:00:00Z',
      ended_at: null,
      end_reason: null,
    },
    playing,
    queue,
  }
}

const fresh: TurnContext = {
  sessionId: 'session-1',
  intent: null,
  currentSongId: null,
  currentRef: null,
  playedSongIds: [],
  recommendationsSinceIntentChange: 0,
}

const WORKSPACE = {
  'GET /api/v1/listening/vocabulary': () => ({ body: VOCABULARY }),
  'GET /api/v1/playlists': () => ({ body: { items: [{ playlist_id: 'p-1', name: 'Evening', track_count: 0 }] } }),
  'GET /api/v1/sessions': () => ({ body: { items: [], total: 0, limit: 20, offset: 0 } }),
}

const queued = [occurrence('q1', 'queued', 'Blue'), occurrence('q2', 'queued', 'Late')]
const startedState = state({ temporary_moods: ['Focused'], target_energy: 0.5 }, null, [occurrence('q0', 'queued', 'Drift'), ...queued])
const playingState = state({ temporary_moods: ['Focused'], target_energy: 0.5 }, occurrence('q0', 'playing', 'Drift'), queued)

function turnOf(response: TurnResponse) {
  if (response.kind !== 'turn') throw new Error(`Expected a turn, got ${response.kind}`)
  return response.turn
}

describe('the HTTP session service', () => {
  let backend: ReturnType<typeof fakeBackend>
  let service: ReturnType<typeof createHttpSessionService>

  async function open(routes: Record<string, Handler> = {}) {
    backend = fakeBackend({ ...WORKSPACE, ...routes })
    service = createHttpSessionService(createApiClient('', backend.fetch))
    return service.loadWorkspace()
  }

  /** A frontend session started from the Focus starter, with Drift playing. */
  async function focusing(routes: Record<string, Handler> = {}) {
    await open({
      'POST /api/v1/sessions': () => ({ status: 201, body: startedState }),
      'POST /api/v1/sessions/backend-1/turns': () => ({ body: { turn: null, state: playingState } }),
      ...routes,
    })
    const started = turnOf(await service.respond(fresh, { kind: 'starter', starterId: 'focus', phrase: 'Help me focus' }))
    backend.calls.length = 0
    return { ...fresh, intent: started.intent, currentSongId: 'track-Drift', currentRef: 'q0' }
  }

  beforeEach(async () => {
    await open()
  })

  it('opens with the curated moods, the library genres, the energy scale, the playlists, and the starters', async () => {
    const seed = await open()

    expect(seed.refineOptions.mood.map((value) => value.label)).toEqual(['Emotional', 'Focused', 'Calm', 'Joyful', 'Driven'])
    expect(seed.refineOptions.genre.map((value) => value.label)).toEqual(['Ambient', 'Jazz', 'Any genre'])
    expect(seed.refineOptions.energy.map((value) => value.id)).toEqual(['very-low', 'low', 'medium', 'high', 'very-high'])
    expect(seed.unavailableDimensions).toEqual(['mood', 'energy'])
    expect(seed.refineOptions.mood.every((value) => value.unavailable)).toBe(true)
    expect(seed.starters.map((starter) => [starter.id, starter.unavailableReason])).toEqual([
      ['focus', 'Your music has no mood or energy information for this yet.'],
      ['unwind', 'Your music has no mood or energy information for this yet.'],
      ['move', 'Your music has no mood or energy information for this yet.'],
      ['discover', undefined], // an exploration control, which needs no features
    ])
    expect(seed.playlists).toEqual([{ id: 'p-1', name: 'Evening', tone: expect.any(String) }])
    expect(seed.starters.map((starter) => [starter.label, starter.phrase])).toEqual([
      ['Focus', 'Help me focus'],
      ['Unwind', 'Something to unwind to'],
      ['Move', 'Get me moving'],
      ['Discover', 'Surprise me'],
    ])
  })

  it('marks nothing unavailable when the library describes every dimension', async () => {
    const seed = await open({
      'GET /api/v1/listening/vocabulary': () => ({
        body: { ...VOCABULARY, dimensions: usable('mood', 'genre', 'energy'), usable_moods: CURATED },
      }),
    })

    expect(seed.libraryReady).toBe(true)
    expect(seed.unavailableDimensions).toEqual([])
    expect(seed.refineOptions.mood.some((value) => value.unavailable)).toBe(false)
    expect(seed.starters.some((starter) => starter.unavailableReason)).toBe(false)
  })

  it('marks a starter or a mood unavailable for exactly what the library lacks', async () => {
    const onlyCalm = await open({
      'GET /api/v1/listening/vocabulary': () => ({
        body: { ...VOCABULARY, dimensions: usable('mood', 'genre', 'energy'), usable_moods: ['Calm'] },
      }),
    })
    expect(onlyCalm.unavailableDimensions).toEqual([])
    expect(onlyCalm.refineOptions.mood.filter((value) => !value.unavailable).map((value) => value.label)).toEqual(['Calm'])
    expect(onlyCalm.starters.map((starter) => starter.unavailableReason)).toEqual([
      'None of your music is tagged Focused yet.',
      undefined,
      'None of your music is tagged Driven yet.',
      undefined,
    ])

    const noEnergy = await open({
      'GET /api/v1/listening/vocabulary': () => ({
        body: { ...VOCABULARY, dimensions: usable('mood', 'genre'), usable_moods: CURATED },
      }),
    })
    expect(noEnergy.starters.map((starter) => starter.unavailableReason)).toEqual([
      'Your music has no energy information for this yet.',
      'Your music has no energy information for this yet.',
      'Your music has no energy information for this yet.',
      undefined,
    ])
  })

  it('treats a library with nothing playable as not ready, with one reason, not as dimensions it lacks', async () => {
    const seed = await open({ 'GET /api/v1/listening/vocabulary': () => ({ body: { ...VOCABULARY, ...NOT_READY } }) })

    expect(seed.libraryReady).toBe(false)
    // Discover too: exploration needs music to explore.
    expect(seed.starters.map((starter) => starter.unavailableReason)).toEqual(
      Array(4).fill('Your library has no playable music yet. Import music to start listening.'),
    )
    expect(seed.unavailableDimensions).toEqual(['mood', 'genre', 'energy'])
  })

  it('answers a library that is not ready as such, for typed words and for a starter alike', async () => {
    const message = 'Your library has no playable music yet. Import some music to start listening.'
    await open({
      'POST /api/v1/sessions': () => ({ status: 409, body: { error: { code: 'LIBRARY_NOT_READY', message, details: {}, request_id: 'r1' } } }),
    })

    expect(await service.respond(fresh, { kind: 'message', text: 'some jazz' })).toEqual({ kind: 'library_not_ready', echo: 'some jazz', message })
    expect(await service.respond(fresh, { kind: 'starter', starterId: 'discover', phrase: 'Surprise me' })).toEqual({
      kind: 'library_not_ready',
      echo: undefined,
      message,
    })
  })

  it('shows typed words the library cannot act on as unavailable, not as not understood or a failure', async () => {
    const message = "Your library doesn't describe energy yet, so that can't change what plays. Try a genre."
    const context = await focusing({
      'POST /api/v1/sessions/backend-1/turns': (body) =>
        (body as { kind: string }).kind === 'message'
          ? unavailable(message, { unavailable: ['energy'], dimensions: ['genre'] })
          : { body: { turn: null, state: playingState } },
    })

    expect(await service.respond(context, { kind: 'message', text: 'a bit calmer' })).toEqual({
      kind: 'unavailable',
      echo: 'a bit calmer',
      message,
      refineTab: 'genre',
    })
  })

  it('answers a structured refine the backend refuses as unavailable, with no words to echo', async () => {
    const message = "Your library doesn't describe that mood yet, so that can't change what plays. Try a genre."
    const context = await focusing({
      'POST /api/v1/sessions/backend-1/turns': (body) =>
        (body as { kind: string }).kind === 'refine'
          ? unavailable(message, { unavailable: ['mood'], dimensions: ['genre'] })
          : { body: { turn: null, state: playingState } },
    })

    expect(await service.respond(context, { kind: 'refine', dimension: 'mood', valueId: 'mood:Calm' })).toEqual({
      kind: 'unavailable',
      echo: undefined,
      message,
      refineTab: 'genre',
    })
  })

  it('does not continue a past session the library can no longer act on, in part or at all, and says why', async () => {
    const past = {
      ...state({ temporary_moods: ['Focused'], target_energy: 0.5 }, null, [], 'ended'),
      turns: [],
      occurrences: [occurrence('old-1', 'played', 'Old')],
      feedback_events: [],
    }
    past.session.session_id = 'past-1'
    const seed = await open({
      'GET /api/v1/sessions': () => ({ body: { items: [{ session_id: 'past-1' }], total: 1, limit: 20, offset: 0 } }),
      'GET /api/v1/sessions/past-1': () => ({ body: past }),
      'POST /api/v1/sessions': () =>
        unavailable("Your library doesn't describe that mood or energy yet, so that can't change what plays. Try a genre.", {
          unavailable: ['mood', 'energy'],
          dimensions: ['genre'],
        }),
    })
    backend.calls.length = 0
    const context: TurnContext = { ...fresh, sessionId: 'past-1', intent: seed.sessions[0].intent, currentSongId: 'track-Old', currentRef: 'old-1' }

    const answer = await service.respond(context, { kind: 'next' })

    expect(answer).toEqual({
      kind: 'unavailable',
      echo: undefined,
      message:
        'This session asks for a mood and an energy level that your music doesn’t describe, so it can’t continue. Start a new session to keep listening.',
    })
    expect(backend.calls.map((call) => [call.path, call.body])).toEqual([
      ['/api/v1/sessions', { context: { ...EMPTY_CONTEXT, temporary_moods: ['Focused'], target_energy: 0.5 } }],
    ])
  })

  it('starts a starter with its structured intent, then plays, and never sends its phrase', async () => {
    await open({
      'POST /api/v1/sessions': () => ({ status: 201, body: startedState }),
      'POST /api/v1/sessions/backend-1/turns': () => ({ body: { turn: null, state: playingState } }),
    })

    const turn = turnOf(await service.respond(fresh, { kind: 'starter', starterId: 'focus', phrase: 'Help me focus' }))

    const posts = backend.calls.filter((call) => call.method === 'POST')
    expect(posts.map((call) => [call.path, call.body])).toEqual([
      ['/api/v1/sessions', { context: { ...EMPTY_CONTEXT, temporary_moods: ['Focused'], target_energy: 0.5 } }],
      ['/api/v1/sessions/backend-1/turns', { kind: 'next' }],
    ])
    expect(JSON.stringify(posts)).not.toContain('Help me focus')
    expect(turn).toMatchObject({ userText: 'Help me focus', acknowledgement: 'intent', title: 'Focused' })
    expect(turn.intent.mood.label).toBe('Focused')
    expect(turn.intent.energy.id).toBe('medium')
    expect(turn.recommendation).toMatchObject({ title: 'Drift', ref: 'q0', audioUrl: '/api/v1/tracks/track-Drift/audio', artworkUrl: null })
    expect(turn.recommendation?.why).toBeUndefined()
    expect(turn.upNext).toMatchObject({ title: 'Blue', ref: 'q1' })
    expect(turn.quickActions.map((action) => action.request)).toEqual([
      { kind: 'control', control: 'more_like_this', label: 'More like this' },
      { kind: 'control', control: 'try_something_different', label: 'Try something different' },
    ])
  })

  it('starts Discover as surprise me', async () => {
    await open({
      'POST /api/v1/sessions': () => ({ status: 201, body: state({}, null, queued) }),
      // As the backend does: a control re-ranks the queue; only next starts playing.
      'POST /api/v1/sessions/backend-1/turns': (body) => ({
        body: { turn: null, state: (body as { kind: string }).kind === 'next' ? playingState : state({}, null, queued) },
      }),
    })

    await service.respond(fresh, { kind: 'starter', starterId: 'discover', phrase: 'Surprise me' })

    expect(backend.calls.filter((call) => call.method === 'POST').map((call) => call.body)).toEqual([
      { context: EMPTY_CONTEXT },
      { kind: 'surprise_me' },
      { kind: 'next' },
    ])
  })

  it('sends typed words unread and shows what the backend understood', async () => {
    await open({
      'POST /api/v1/sessions': () => ({ status: 201, body: { ...state({ temporary_genres: ['Jazz'] }, null, queued), meaning: { kind: 'refine', turn: null, reaction: null } } }),
      'POST /api/v1/sessions/backend-1/turns': () => ({ body: { turn: null, state: state({ temporary_genres: ['Jazz'] }, occurrence('q1', 'playing', 'Blue'), []) } }),
    })

    const turn = turnOf(await service.respond(fresh, { kind: 'message', text: 'some jazz please' }))

    expect(backend.calls.find((call) => call.path === '/api/v1/sessions')?.body).toEqual({ message: 'some jazz please' })
    expect(turn).toMatchObject({ userText: 'some jazz please', acknowledgement: 'intent', title: 'Jazz' })
    expect(turn.intent.genre.label).toBe('Jazz')
  })

  it('shows words the backend cannot act on as not understood, starting nothing', async () => {
    const refusal = {
      status: 422,
      body: { error: { code: 'MESSAGE_NOT_UNDERSTOOD', message: "Intentune can't act on that yet. Try a mood, a genre, or more or less energy.", details: { reason: 'unrecognized' }, request_id: 'r1' } },
    }
    await open({ 'POST /api/v1/sessions': () => refusal })

    const response = await service.respond(fresh, { kind: 'message', text: 'driving through Accra at 2am' })

    expect(response).toEqual({
      kind: 'not_understood',
      echo: 'driving through Accra at 2am',
      message: "Intentune can't act on that yet. Try a mood, a genre, or more or less energy.",
      refineTab: 'genre',
    })
    await service.respond(fresh, { kind: 'message', text: 'still nothing' })
    expect(backend.calls.filter((call) => call.path === '/api/v1/sessions')).toHaveLength(2) // no session was linked
  })

  it('rejects other failures, so the UI offers to try again', async () => {
    await open({ 'POST /api/v1/sessions': () => ({ status: 500, body: { error: { code: 'INTERNAL_ERROR', message: 'x', details: {}, request_id: 'r' } } }) })

    await expect(service.respond(fresh, { kind: 'message', text: 'jazz' })).rejects.toThrow()
  })

  it('maps typed reactions and save requests onto the existing answers', async () => {
    const meaningOf = (meaning: object) => () => ({ body: { meaning, turn: null, feedback: null, state: playingState } })
    const context = await focusing({ 'POST /api/v1/sessions/backend-1/turns': meaningOf({ kind: 'reaction', turn: null, reaction: 'like' }) })

    expect(await service.respond(context, { kind: 'message', text: 'love this' })).toEqual({ kind: 'liked', echo: 'love this' })
    expect(backend.calls[0].body).toEqual({ kind: 'message', text: 'love this', occurrence_id: 'q0' })

    const saving = await focusing({ 'POST /api/v1/sessions/backend-1/turns': meaningOf({ kind: 'save_requested', turn: null, reaction: null }) })
    expect(await service.respond(saving, { kind: 'message', text: 'save this' })).toEqual({ kind: 'save_requested', echo: 'save this' })
  })

  it('sends the player facts with typed words, for a typed next', async () => {
    const context = await focusing({
      'POST /api/v1/sessions/backend-1/turns': () => ({ body: { meaning: { kind: 'turn', turn: 'next', reaction: null }, turn: null, state: state({}, occurrence('q1', 'playing', 'Blue'), []) } }),
    })

    const turn = turnOf(await service.respond(context, { kind: 'message', text: 'next', playback: { playedSeconds: 12, durationSeconds: 200 } }))

    expect(backend.calls[0].body).toEqual({ kind: 'message', text: 'next', occurrence_id: 'q0', playback: { played_seconds: 12, duration_seconds: 200 } })
    expect(turn).toMatchObject({ acknowledgement: 'none', recommendation: { ref: 'q1' } })
  })

  it('sends a quick action as its control, acknowledged by its meaning', async () => {
    const context = await focusing()

    const turn = turnOf(await service.respond(context, { kind: 'control', control: 'more_like_this', label: 'Keep this vibe' }))

    expect(backend.calls[0].body).toEqual({ kind: 'more_like_this' })
    expect(turn).toMatchObject({ userText: 'Keep this vibe', acknowledgement: 'intent', ackLabel: 'Keeping this direction', recommendation: null })
  })

  it('refines one dimension and keeps the rest of the context; the song plays on', async () => {
    const context = await focusing()

    const turn = turnOf(await service.respond(context, { kind: 'refine', dimension: 'genre', valueId: 'genre:Jazz' }))

    expect(backend.calls[0].body).toEqual({
      kind: 'refine',
      context: { ...EMPTY_CONTEXT, temporary_moods: ['Focused'], target_energy: 0.5, temporary_genres: ['Jazz'] },
    })
    expect(turn.recommendation).toBeNull() // the hero is still the one playing
    expect(turn.refineTab).toBe('genre') // Tune stays open on the dimension just tuned
  })

  it('sends Next and the end of a song with the player facts', async () => {
    const context = await focusing({
      'POST /api/v1/sessions/backend-1/playback-events': () => ({ status: 201, body: { event: {}, state: state({}, occurrence('q1', 'playing', 'Blue'), []) } }),
    })

    await service.respond(context, { kind: 'next', playback: { playedSeconds: 30, durationSeconds: 200 } })
    await service.respond(context, { kind: 'track_ended', playback: { playedSeconds: 200, durationSeconds: 200 } })

    expect(backend.calls.map((call) => [call.path, call.body])).toEqual([
      ['/api/v1/sessions/backend-1/turns', { kind: 'next', occurrence_id: 'q0', playback: { played_seconds: 30, duration_seconds: 200 } }],
      ['/api/v1/sessions/backend-1/playback-events', { occurrence_id: 'q0', event_type: 'complete', played_seconds: 200, duration_seconds: 200 }],
    ])
  })

  it('records likes and unlikes, and replays a past song by its reference', async () => {
    const context = await focusing({
      'POST /api/v1/sessions/backend-1/recommendations/[^/]+/reactions': () => ({ status: 201, body: { event: {}, state: playingState } }),
    })

    const liked = await service.react(context, 'like')
    await service.react(context, 'unlike')
    await service.respond(context, { kind: 'replay', songId: 'track-Old', ref: 'old-1' })

    expect(backend.calls.map((call) => [call.path, call.body])).toEqual([
      ['/api/v1/sessions/backend-1/recommendations/q0/reactions', { reaction: 'like' }],
      ['/api/v1/sessions/backend-1/recommendations/q0/reactions', { reaction: 'unlike' }],
      ['/api/v1/sessions/backend-1/recommendations/old-1/reactions', { reaction: 'replay' }],
    ])
    expect(liked.upNext).toMatchObject({ ref: 'q1' })
  })

  it('saves to playlists as feedback on the recommendation, and removes when unticked', async () => {
    const context = await focusing({
      'POST /api/v1/playlists/[^/]+/items': (_body, path) =>
        path.includes('p-2') ? { status: 409, body: { error: { code: 'CONFLICT', message: 'Already', details: {}, request_id: 'r' } } } : { status: 201, body: {} },
      'DELETE /api/v1/playlists/[^/]+/items/[^/]+': () => ({ status: 204 }),
    })

    await service.savePlaylists(context, { added: ['p-1', 'p-2'], removed: ['p-3'] })

    expect(backend.calls.map((call) => [call.method, call.path, call.body])).toEqual([
      ['POST', '/api/v1/playlists/p-1/items', { track_id: 'track-Drift', session_id: 'backend-1', occurrence_id: 'q0' }],
      ['POST', '/api/v1/playlists/p-2/items', { track_id: 'track-Drift', session_id: 'backend-1', occurrence_id: 'q0' }],
      ['DELETE', '/api/v1/playlists/p-3/items/track-Drift', undefined],
    ])
  })

  it('creates playlists on the backend', async () => {
    await open({ 'POST /api/v1/playlists': () => ({ status: 201, body: { playlist_id: 'p-9', name: 'Focused', track_count: 0 } }) })

    expect(await service.createPlaylist('Focused')).toEqual({ id: 'p-9', name: 'Focused', tone: expect.any(String) })
  })

  it('continues a past session as a new backend session with its last context', async () => {
    const past = {
      ...state({ temporary_genres: ['Jazz'] }, null, [], 'ended'),
      turns: [{ turn_id: 't1', sequence: 1, kind: 'initial_intent', context: { ...EMPTY_CONTEXT, temporary_genres: ['Jazz'] }, occurrence_id: null, created_at: '2026-10-20T09:00:00Z' }],
      occurrences: [occurrence('old-1', 'played', 'Old')],
      feedback_events: [{ event_id: 'f1', occurrence_id: 'old-1', event_type: 'like', occurred_at: '2026-10-20T09:01:00Z', played_seconds: null, duration_seconds: null }],
    }
    past.session.session_id = 'past-1'
    const seed = await open({
      'GET /api/v1/sessions': () => ({ body: { items: [{ session_id: 'past-1' }], total: 1, limit: 20, offset: 0 } }),
      'GET /api/v1/sessions/past-1': () => ({ body: past }),
      'POST /api/v1/sessions': () => ({ status: 201, body: state({ temporary_genres: ['Jazz'] }, null, queued) }),
      'POST /api/v1/sessions/backend-1/turns': (body) => ({ body: { turn: null, state: (body as { kind: string }).kind === 'next' ? state({ temporary_genres: ['Jazz'] }, occurrence('q1', 'playing', 'Blue'), []) : state({ temporary_genres: ['Jazz'] }, null, queued) } }),
    })
    const [session] = seed.sessions
    expect(session).toMatchObject({ id: 'past-1', title: 'Jazz', currentRecommendationId: 'old-1' })
    expect(session.recommendations['old-1']).toMatchObject({ liked: true, ref: 'old-1' })
    expect(session.events.map((event) => event.kind)).toEqual(['intent_set', 'recommendation'])
    backend.calls.length = 0

    const context: TurnContext = { ...fresh, sessionId: 'past-1', intent: session.intent, currentSongId: 'track-Old', currentRef: 'old-1' }
    const turn = turnOf(await service.respond(context, { kind: 'control', control: 'surprise_me', label: 'Surprise me' }))

    expect(backend.calls.map((call) => [call.path, call.body])).toEqual([
      ['/api/v1/sessions', { context: { ...EMPTY_CONTEXT, temporary_genres: ['Jazz'] } }],
      ['/api/v1/sessions/backend-1/turns', { kind: 'surprise_me' }],
      ['/api/v1/sessions/backend-1/turns', { kind: 'next' }],
    ])
    expect(turn.recommendation).toMatchObject({ ref: 'q1' })
    await expect(service.react(context, 'like')).rejects.toThrow() // the old song is not in the new session
  })
})
