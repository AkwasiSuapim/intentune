// The session service over the backend's HTTP API (B9 / F9). It implements
// the same SessionService the mock does, so the session feature cannot tell
// them apart.
//
// Each request carries its meaning, and this client maps it onto the API:
// - **starter:** POST /sessions with the starter's structured context, then the
//   starter's control (Discover is SURPRISE_ME).
// - **control, refine, not for me:** POST …/turns.
// - **next:** POST …/turns, with the player's facts, which the backend records as the SKIP.
// - **track ended:** POST …/playback-events, a COMPLETE with the player's facts.
// - **replay:** POST …/reactions REPLAY.
// - **message:** the typed words, unread, as a `message` turn (or the start's
//   message). The backend interprets them and answers what they meant. Words it
//   cannot act on answer MESSAGE_NOT_UNDERSTOOD, shown as such, not as a failure.
//
// What the library can act on now is the backend's (the vocabulary's
// `library`, `dimensions`, and `usable_moods`), read when the workspace loads:
// - **Not ready** (nothing playable): no starter can be used, for that one
//   reason, and LIBRARY_NOT_READY is answered as `library_not_ready`.
// - **A dimension without data:** Tune marks it, a starter defined by it is shown
//   unavailable with its reason and never sent in part, and INTENT_UNAVAILABLE
//   (understood, but the library cannot act on it) is answered as `unavailable`.
// Neither is shown as a failure. A past session whose intent the library can no
// longer act on cannot continue, and says so. Everything becomes usable by
// itself once the backend reports the data.
//
// A new hero starts playing at once in the approved UI, so a session that has
// just started is also told to play (a `next` turn while nothing plays).
//
// Sessions:
// - **New ones:** the backend keeps one active session (D35). A new frontend
//   session becomes a backend session on its first request.
// - **Older ones:** a past session reopened from the drawer continues as a new
//   backend session with its last context, and the UI keeps showing it as one
//   session. Its old recommendations belong to the ended session, so they can
//   be saved to playlists but not liked or replayed.
//
// The browser never rebuilds history: what this client keeps per session is
// the backend session it maps to and that session's context, as the backend
// last reported it.
import type {
  PlaybackFacts,
  ReactionAnswer,
  SessionService,
  SessionTurn,
  SteeringControl,
  TurnContext,
  TurnRequest,
  TurnResponse,
} from '../../features/session/sessionService.ts'
import type { StarterIntent } from '../../features/session/types.ts'
import type {
  ContextBody,
  FeedbackBody,
  MeaningBody,
  PageBody,
  PlaylistSummaryBody,
  SessionDetailBody,
  SessionStartBody,
  SessionStateBody,
  TurnResultBody,
  VocabularyBody,
} from './api.ts'
import { ApiError } from './client.ts'
import type { ApiClient } from './client.ts'
import {
  CONTROL_ACK,
  EMPTY_CONTEXT,
  contextWith,
  controlAction,
  intentFrom,
  playlistFrom,
  quickActionsFor,
  refineOptionsFrom,
  sessionStateFrom,
  unavailableFrom,
  unavailableStarterReason,
  songFrom,
  titleFor,
} from './mapping.ts'

/** How many past sessions the drawer opens with. */
const RECENT_SESSIONS = 20

type HttpStarter = StarterIntent & {
  mood?: string
  energy?: string
  control?: SteeringControl
}

// The approved design's starters, with the meaning its design gives each.
const STARTERS: HttpStarter[] = [
  { id: 'focus', label: 'Focus', phrase: 'Help me focus', artworkUrl: null, mood: 'Focused', energy: 'medium' },
  { id: 'unwind', label: 'Unwind', phrase: 'Something to unwind to', artworkUrl: null, mood: 'Calm', energy: 'low' },
  { id: 'move', label: 'Move', phrase: 'Get me moving', artworkUrl: null, mood: 'Driven', energy: 'high' },
  { id: 'discover', label: 'Discover', phrase: 'Surprise me', artworkUrl: null, control: 'surprise_me' },
]

const NOT_UNDERSTOOD = 'MESSAGE_NOT_UNDERSTOOD'
const UNAVAILABLE = 'INTENT_UNAVAILABLE'
const NOT_READY = 'LIBRARY_NOT_READY'

/** How a refused dimension reads in a sentence. */
const ASKS_FOR: Record<string, string> = { mood: 'a mood', genre: 'a genre', energy: 'an energy level' }

/** A past session whose intent the library cannot act on any more cannot continue as it was. */
class CannotContinue extends Error {
  constructor(unavailable: unknown) {
    const asked = Array.isArray(unavailable)
      ? unavailable.map((dimension) => ASKS_FOR[String(dimension)] ?? String(dimension))
      : []
    super(
      `This session asks for ${asked.length ? asked.join(' and ') : 'something'} that your music doesn’t describe, so it can’t continue. Start a new session to keep listening.`,
    )
    this.name = 'CannotContinue'
  }
}

type Link = { backendId: string; context: ContextBody; active: boolean }

type Acknowledgement = Pick<SessionTurn, 'userText' | 'acknowledgement' | 'ackLabel' | 'restart'>

export function createHttpSessionService(client: ApiClient): SessionService {
  const links = new Map<string, Link>()
  let vocabulary: VocabularyBody = {
    genres: [],
    moods: [],
    energy: [],
    library: { ready: false, playable_tracks: 0 },
    dimensions: {
      mood: 'library_not_ready',
      genre: 'library_not_ready',
      energy: 'library_not_ready',
      danceability: 'library_not_ready',
      tempo: 'library_not_ready',
      valence: 'library_not_ready',
      acousticness: 'library_not_ready',
    },
    usable_moods: [],
    unmapped_fields: [],
  }

  const turnsOf = (link: Link) => `/api/v1/sessions/${link.backendId}/turns`
  const playback = (facts?: PlaybackFacts) =>
    facts ? { played_seconds: facts.playedSeconds, duration_seconds: facts.durationSeconds } : undefined

  /** The backend session this frontend session now is. It is the active one; any other is not. */
  function adopt(sessionId: string, state: SessionStateBody): Link {
    for (const link of links.values()) link.active = false
    const link = { backendId: state.session.session_id, context: state.session.context, active: true }
    links.set(sessionId, link)
    return link
  }

  function remember(link: Link, state: SessionStateBody) {
    link.context = state.session.context
  }

  /** A session that has just started plays its first queued track, as the UI shows it doing. */
  async function playing(link: Link, state: SessionStateBody): Promise<SessionStateBody> {
    if (state.playing || state.queue.length === 0) return state
    const result = await client.post<TurnResultBody>(turnsOf(link), { kind: 'next' })
    remember(link, result.state)
    return result.state
  }

  async function start(sessionId: string, body: object): Promise<{ link: Link; started: SessionStartBody }> {
    const started = await client.post<SessionStartBody>('/api/v1/sessions', body)
    return { link: adopt(sessionId, started), started }
  }

  /** The session's backend session, active. A past one continues as a new backend session with its context. */
  async function active(context: TurnContext): Promise<{ link: Link; continued: boolean }> {
    const link = links.get(context.sessionId)
    if (!link) throw new Error('This session has not started yet.')
    if (link.active) return { link, continued: false }
    try {
      const { link: continued } = await start(context.sessionId, { context: link.context })
      return { link: continued, continued: true }
    } catch (error) {
      // Not continued in part: the listener is told, and starts afresh.
      if (error instanceof ApiError && error.code === UNAVAILABLE) throw new CannotContinue(error.details.unavailable)
      throw error
    }
  }

  function turnFrom(context: TurnContext, state: SessionStateBody, acknowledgement: Acknowledgement): SessionTurn {
    const intent = intentFrom(state.session.context, vocabulary)
    const hero = state.playing
    return {
      ...acknowledgement,
      intent,
      recommendation: hero && hero.occurrence_id !== context.currentRef ? songFrom(hero, client.url) : null,
      quickActions: quickActionsFor(hero),
      upNext: hero && state.queue[0] ? songFrom(state.queue[0], client.url) : null,
      title: context.intent === null ? titleFor(intent) : undefined,
    }
  }

  const answer = (turn: SessionTurn): TurnResponse => ({ kind: 'turn', turn })

  /** A refusal the UI shows as such, not as a failure: words not understood, or an intent the library cannot act on. */
  function refusalOf(error: unknown, echo: string | undefined): TurnResponse | null {
    if (error instanceof CannotContinue) return { kind: 'unavailable', echo, message: error.message }
    if (!(error instanceof ApiError)) return null
    if (error.code === NOT_READY) return { kind: 'library_not_ready', echo, message: error.message }
    if (error.code === UNAVAILABLE) return { kind: 'unavailable', echo, message: error.message, refineTab: 'genre' }
    if (error.code === NOT_UNDERSTOOD && echo !== undefined) {
      return { kind: 'not_understood', echo, message: error.message, refineTab: 'genre' }
    }
    return null
  }

  function acknowledgementOf(meaning: MeaningBody | null | undefined, text: string): Acknowledgement {
    if (meaning?.kind === 'turn' && meaning.turn === 'not_for_me') {
      return { userText: text, acknowledgement: 'not_for_me' }
    }
    if (meaning?.kind === 'turn' && meaning.turn === 'next') {
      return { userText: text, acknowledgement: 'none' }
    }
    if (meaning?.kind === 'turn' && meaning.turn && meaning.turn in CONTROL_ACK) {
      return { userText: text, acknowledgement: 'intent', ackLabel: CONTROL_ACK[meaning.turn as SteeringControl] }
    }
    return { userText: text, acknowledgement: 'intent' }
  }

  async function message(context: TurnContext, text: string, facts?: PlaybackFacts): Promise<TurnResponse> {
    if (!links.has(context.sessionId)) {
      const { link, started } = await start(context.sessionId, { message: text })
      const state = await playing(link, started)
      return answer(turnFrom(context, state, acknowledgementOf(started.meaning, text)))
    }

    const { link, continued } = await active(context)
    const result = await client.post<TurnResultBody>(turnsOf(link), {
      kind: 'message',
      text,
      occurrence_id: continued ? undefined : (context.currentRef ?? undefined),
      playback: continued ? undefined : playback(facts),
    })
    remember(link, result.state)
    const { meaning } = result
    if (meaning?.kind === 'save_requested') return { kind: 'save_requested', echo: text }
    if (meaning?.kind === 'reaction' && meaning.reaction === 'like') return { kind: 'liked', echo: text }

    const state = continued ? await playing(link, result.state) : result.state
    if (meaning?.kind === 'reaction' && meaning.reaction === 'replay') {
      const sameSong = state.playing?.occurrence_id === context.currentRef
      return answer(turnFrom(context, state, { userText: text, acknowledgement: 'none', restart: sameSong }))
    }
    return answer(turnFrom(context, state, acknowledgementOf(meaning, text)))
  }

  async function respond(context: TurnContext, request: TurnRequest): Promise<TurnResponse> {
    try {
      return await answerTo(context, request)
    } catch (error) {
      const refused = refusalOf(error, request.kind === 'message' ? request.text : undefined)
      if (refused) return refused
      throw error
    }
  }

  async function answerTo(context: TurnContext, request: TurnRequest): Promise<TurnResponse> {
    switch (request.kind) {
      case 'message':
        return message(context, request.text, request.playback)

      case 'starter': {
        const starter = STARTERS.find((candidate) => candidate.id === request.starterId)
        if (!starter) throw new Error(`Unknown starter: ${request.starterId}`)
        let starting = { ...EMPTY_CONTEXT, temporary_moods: starter.mood ? [starter.mood] : [] }
        if (starter.energy) starting = contextWith(starting, 'energy', starter.energy, vocabulary)
        const { link, started } = await start(context.sessionId, { context: starting })
        let state: SessionStateBody = started
        if (starter.control) {
          state = (await client.post<TurnResultBody>(turnsOf(link), { kind: starter.control })).state
          remember(link, state)
        }
        state = await playing(link, state)
        return answer(turnFrom(context, state, { userText: starter.phrase, acknowledgement: 'intent' }))
      }

      case 'control': {
        const { link, continued } = await active(context)
        const result = await client.post<TurnResultBody>(turnsOf(link), { kind: request.control })
        remember(link, result.state)
        const state = continued ? await playing(link, result.state) : result.state
        return answer(
          turnFrom(context, state, {
            userText: request.label,
            acknowledgement: 'intent',
            ackLabel: CONTROL_ACK[request.control],
          }),
        )
      }

      case 'refine': {
        const { link, continued } = await active(context)
        const refined = contextWith(link.context, request.dimension, request.valueId, vocabulary)
        const result = await client.post<TurnResultBody>(turnsOf(link), { kind: 'refine', context: refined })
        remember(link, result.state)
        const state = continued ? await playing(link, result.state) : result.state
        // Tune stays open on the dimension just tuned, as in the approved design.
        return answer({ ...turnFrom(context, state, { acknowledgement: 'intent' }), refineTab: request.dimension })
      }

      case 'not_for_me': {
        const { link, continued } = await active(context)
        // A past session's song is not in the new backend session: refusing it moves on to new music.
        const state = continued
          ? await playing(link, await client.get<SessionStateBody>(`/api/v1/sessions/${link.backendId}`))
          : (await client.post<TurnResultBody>(turnsOf(link), {
              kind: 'not_for_me',
              occurrence_id: context.currentRef ?? undefined,
            })).state
        remember(link, state)
        return answer(turnFrom(context, state, { acknowledgement: 'not_for_me' }))
      }

      case 'next': {
        const { link, continued } = await active(context)
        const state = continued
          ? await playing(link, await client.get<SessionStateBody>(`/api/v1/sessions/${link.backendId}`))
          : (await client.post<TurnResultBody>(turnsOf(link), {
              kind: 'next',
              occurrence_id: context.currentRef ?? undefined,
              playback: playback(request.playback),
            })).state
        remember(link, state)
        return answer(turnFrom(context, state, { acknowledgement: 'none' }))
      }

      case 'track_ended': {
        const { link, continued } = await active(context)
        const state =
          continued || !context.currentRef
            ? await playing(link, await client.get<SessionStateBody>(`/api/v1/sessions/${link.backendId}`))
            : (await client.post<FeedbackBody>(`/api/v1/sessions/${link.backendId}/playback-events`, {
                occurrence_id: context.currentRef,
                event_type: 'complete',
                ...playback(request.playback),
              })).state
        remember(link, state)
        return answer(turnFrom(context, state, { acknowledgement: 'none' }))
      }

      case 'replay': {
        const link = links.get(context.sessionId)
        if (!link?.active || !request.ref) {
          throw new Error('Only a song from the session that is playing can be played again.')
        }
        const result = await client.post<FeedbackBody>(
          `/api/v1/sessions/${link.backendId}/recommendations/${request.ref}/reactions`,
          { reaction: 'replay' },
        )
        remember(link, result.state)
        return answer(turnFrom(context, result.state, { acknowledgement: 'none' }))
      }
    }
  }

  return {
    async loadWorkspace() {
      const [vocabularyBody, playlists, recent] = await Promise.all([
        client.get<VocabularyBody>('/api/v1/listening/vocabulary'),
        client.get<{ items: PlaylistSummaryBody[] }>('/api/v1/playlists'),
        client.get<PageBody<{ session_id: string }>>(`/api/v1/sessions?limit=${RECENT_SESSIONS}`),
      ])
      vocabulary = vocabularyBody
      const details = await Promise.all(
        recent.items.map((session) => client.get<SessionDetailBody>(`/api/v1/sessions/${session.session_id}`)),
      )
      for (const detail of details) {
        links.set(detail.session.session_id, {
          backendId: detail.session.session_id,
          context: detail.session.context,
          active: detail.session.status === 'active',
        })
      }
      return {
        sessions: details.map((detail) => sessionStateFrom(detail, vocabulary, client.url)),
        playlists: playlists.items.map(playlistFrom),
        starters: STARTERS.map(({ id, label, phrase, artworkUrl, mood, energy }) => {
          const unavailableReason = unavailableStarterReason({ mood, energy }, vocabulary)
          return { id, label, phrase, artworkUrl, ...(unavailableReason ? { unavailableReason } : {}) }
        }),
        refineOptions: refineOptionsFrom(vocabulary),
        unavailableDimensions: unavailableFrom(vocabulary),
        libraryReady: vocabulary.library.ready,
      }
    },

    respond,

    async react(context, reaction): Promise<ReactionAnswer> {
      const link = links.get(context.sessionId)
      if (!link?.active || !context.currentRef) {
        throw new Error('Only a song from the session that is playing can be liked.')
      }
      const result = await client.post<FeedbackBody>(
        `/api/v1/sessions/${link.backendId}/recommendations/${context.currentRef}/reactions`,
        { reaction },
      )
      remember(link, result.state)
      return {
        quickActions: quickActionsFor(result.state.playing),
        upNext: result.state.playing && result.state.queue[0] ? songFrom(result.state.queue[0], client.url) : null,
      }
    },

    async savePlaylists(context, { added, removed }): Promise<ReactionAnswer> {
      const trackId = context.currentSongId
      if (!trackId) throw new Error('There is no song to save.')
      const link = links.get(context.sessionId)
      // From the session that is playing, an add is also feedback; from a past one, a plain add.
      const recommendation =
        link?.active && context.currentRef
          ? { session_id: link.backendId, occurrence_id: context.currentRef }
          : {}
      for (const playlistId of added) {
        try {
          await client.post(`/api/v1/playlists/${playlistId}/items`, { track_id: trackId, ...recommendation })
        } catch (error) {
          // Already in that playlist is what was asked for.
          if (!(error instanceof ApiError && error.code === 'CONFLICT')) throw error
        }
      }
      for (const playlistId of removed) {
        try {
          await client.delete(`/api/v1/playlists/${playlistId}/items/${trackId}`)
        } catch (error) {
          if (!(error instanceof ApiError && error.status === 404)) throw error
        }
      }
      return { quickActions: [controlAction('more_like_this'), controlAction('try_something_different')] }
    },

    async createPlaylist(name) {
      return playlistFrom(await client.post<PlaylistSummaryBody>('/api/v1/playlists', { name }))
    },

    // No hints beyond the controls: the backend makes no playlist suggestions.
    quickActionsAfter: async () => [controlAction('more_like_this'), controlAction('try_something_different')],
    suggestPlaylists: async () => [],
  }
}
