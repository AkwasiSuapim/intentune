// Deterministic state transitions for one listening session. Pure: the same
// state and action always give the same next state. Anything a backend would
// decide arrives here already decided, inside the action.
import type {
  RecommendedSong,
  SessionTurn,
  TurnRequest,
} from './sessionService.ts'
import { INTENT_DIMENSIONS } from './types.ts'
import type {
  Intent,
  IntentChange,
  Recommendation,
  RefineTab,
  SessionEvent,
  SessionState,
} from './types.ts'

export type SessionAction =
  | { type: 'request_sent'; request: TurnRequest }
  | { type: 'request_answered' }
  | { type: 'request_failed' }
  | { type: 'turn_applied'; turn: SessionTurn }
  /** The service could not act on what the listener typed. */
  | {
      type: 'turn_not_understood'
      echo: string
      message: string
      refineTab?: RefineTab
    }
  /** The service understood, but the music library cannot act on what was asked. */
  | {
      type: 'turn_unavailable'
      echo?: string
      message: string
      refineTab?: RefineTab
    }
  /** The music library has nothing playable yet. */
  | { type: 'turn_library_not_ready'; echo?: string; message: string }
  | { type: 'play_toggled' }
  | { type: 'playback_ticked'; seconds: number }
  /** The audio player's own position, and its duration once known. */
  | { type: 'playback_progressed'; positionSeconds: number; durationSeconds?: number }
  | { type: 'why_toggled' }
  | {
      type: 'liked_set'
      liked: boolean
      quickActions?: SessionState['quickActions']
      echo?: string
    }
  | { type: 'refine_opened'; tab: RefineTab }
  | { type: 'refine_closed' }
  | {
      type: 'playlist_picker_opened'
      suggestedPlaylistIds: string[]
      echo?: string
    }
  | { type: 'playlist_toggled'; playlistId: string }
  | { type: 'playlist_picker_closed' }
  | { type: 'playlists_saved'; quickActions?: SessionState['quickActions'] }
  // Hints that arrive after the change they follow. Each names the
  // recommendation it was asked about and is dropped once that has moved on.
  | {
      type: 'quick_actions_offered'
      recommendationId: string
      quickActions: SessionState['quickActions']
    }
  | {
      type: 'playlists_suggested'
      recommendationId: string
      suggestedPlaylistIds: string[]
    }
  | {
      type: 'up_next_offered'
      recommendationId: string
      upNext: RecommendedSong | null
    }
  // A reaction or save the service did not take: the card goes back to what is true.
  | { type: 'like_reverted'; recommendationId: string; liked: boolean }
  | {
      type: 'playlists_save_reverted'
      recommendationId: string
      savedToPlaylistIds: string[]
    }
  | { type: 'drawer_opened' }
  | { type: 'drawer_closed' }
  | { type: 'session_resumed' }

/** The event each refusal leaves in the session. */
const REFUSAL_EVENT = {
  turn_not_understood: 'not_understood',
  turn_unavailable: 'unavailable',
  turn_library_not_ready: 'library_not_ready',
} as const

const SESSION_ACTION_TYPES = new Set<string>([
  'request_sent',
  'request_answered',
  'request_failed',
  'turn_applied',
  'turn_not_understood',
  'turn_unavailable',
  'turn_library_not_ready',
  'play_toggled',
  'playback_ticked',
  'playback_progressed',
  'why_toggled',
  'liked_set',
  'refine_opened',
  'refine_closed',
  'playlist_picker_opened',
  'playlist_toggled',
  'playlist_picker_closed',
  'playlists_saved',
  'quick_actions_offered',
  'playlists_suggested',
  'up_next_offered',
  'like_reverted',
  'playlists_save_reverted',
  'drawer_opened',
  'drawer_closed',
  'session_resumed',
] satisfies SessionAction['type'][])

export function isSessionAction(action: {
  type: string
}): action is SessionAction {
  return SESSION_ACTION_TYPES.has(action.type)
}

/** The single slot holding the peek at what follows. */
const UP_NEXT_ID = 'up-next'

export const NEW_SESSION_TITLE = 'New session'

export function createSession(id: string): SessionState {
  return {
    id,
    title: NEW_SESSION_TITLE,
    intent: null,
    changedDimensions: [],
    events: [],
    recommendations: {},
    currentRecommendationId: null,
    playback: { playing: false, positionSeconds: 0 },
    whyExpanded: false,
    quickActions: [],
    upNextRecommendationId: null,
    refine: null,
    overlay: null,
    openRequest: null,
  }
}

type NewEvent = SessionEvent extends infer Event
  ? Event extends SessionEvent
    ? Omit<Event, 'id'>
    : never
  : never

const eventId = (position: number) => `e${position}`

/** The id the next event added to this session will have. */
export function nextEventId(state: SessionState) {
  return eventId(state.events.length + 1)
}

function append(events: SessionEvent[], event: NewEvent) {
  events.push({ ...event, id: eventId(events.length + 1) } as SessionEvent)
}

function diffIntent(before: Intent, after: Intent): IntentChange[] {
  return INTENT_DIMENSIONS.filter(
    (dimension) => before[dimension].id !== after[dimension].id,
  ).map((dimension) => ({
    dimension,
    from: before[dimension],
    to: after[dimension],
  }))
}

function record(id: string, song: RecommendedSong): Recommendation {
  return { ...song, id, liked: false, skipped: false, savedToPlaylistIds: [] }
}

function currentOf(state: SessionState) {
  const id = state.currentRecommendationId
  return (id && state.recommendations[id]) || null
}

function updateCurrent(
  state: SessionState,
  patch: Partial<Recommendation>,
): SessionState['recommendations'] {
  const current = currentOf(state)
  if (!current) return state.recommendations
  return { ...state.recommendations, [current.id]: { ...current, ...patch } }
}

function updateRecommendation(
  state: SessionState,
  recommendationId: string,
  patch: Partial<Recommendation>,
): SessionState {
  const target = state.recommendations[recommendationId]
  if (!target) return state
  return {
    ...state,
    recommendations: { ...state.recommendations, [recommendationId]: { ...target, ...patch } },
  }
}

function withUpNext(state: SessionState, upNext: RecommendedSong | null): SessionState {
  const recommendations = { ...state.recommendations }
  delete recommendations[UP_NEXT_ID]
  if (upNext) recommendations[UP_NEXT_ID] = record(UP_NEXT_ID, upNext)
  return {
    ...state,
    recommendations,
    upNextRecommendationId: upNext ? UP_NEXT_ID : null,
  }
}

function applyTurn(state: SessionState, turn: SessionTurn): SessionState {
  const events = [...state.events]
  const recommendations = { ...state.recommendations }
  delete recommendations[UP_NEXT_ID]

  const current = currentOf(state)
  if (turn.acknowledgement === 'not_for_me' && current) {
    recommendations[current.id] = { ...current, skipped: true }
  }
  if (turn.userText) {
    append(events, { kind: 'user_message', text: turn.userText })
  }

  // The acknowledgement is derived here from the very intent being stored,
  // so the stream and the intent summary cannot disagree.
  let intent = state.intent
  let changes: IntentChange[] = []
  if (turn.acknowledgement === 'intent') {
    if (!intent) {
      append(events, { kind: 'intent_set', intent: turn.intent })
    } else {
      changes = diffIntent(intent, turn.intent)
      if (changes.length > 0) {
        append(events, {
          kind: 'intent_updated',
          changes,
          label: turn.ackLabel,
        })
      } else {
        append(events, {
          kind: 'intent_kept',
          intent: turn.intent,
          label: turn.ackLabel ?? 'Kept current intent',
        })
      }
    }
    intent = turn.intent
  } else if (turn.acknowledgement === 'not_for_me') {
    append(events, { kind: 'intent_unchanged', cause: 'not_for_me' })
  }

  // Appending the new recommendation is all it takes to retire the old hero:
  // whichever recommendation is current renders as the hero.
  let currentRecommendationId = state.currentRecommendationId
  if (turn.recommendation) {
    const id = `rec-${events.length + 1}`
    recommendations[id] = record(id, turn.recommendation)
    append(events, { kind: 'recommendation', recommendationId: id })
    currentRecommendationId = id
  }
  if (turn.upNext) {
    recommendations[UP_NEXT_ID] = record(UP_NEXT_ID, turn.upNext)
  }

  return {
    ...state,
    title: turn.title ?? state.title,
    intent,
    changedDimensions: changes.map((change) => change.dimension),
    events,
    recommendations,
    currentRecommendationId,
    playback: turn.recommendation
      ? { playing: true, positionSeconds: 0 }
      : turn.restart
        ? {
            ...state.playback,
            playing: true,
            positionSeconds: 0,
            restarts: (state.playback.restarts ?? 0) + 1,
          }
        : state.playback,
    whyExpanded: false,
    quickActions: turn.quickActions,
    upNextRecommendationId: turn.upNext ? UP_NEXT_ID : null,
    refine: turn.refineTab && intent ? { tab: turn.refineTab } : null,
    // The playlist sheet belonged to the song this turn replaces; the
    // drawer, opened while the answer was on its way, stays open.
    overlay: state.overlay?.type === 'session_drawer' ? state.overlay : null,
  }
}

export function sessionReducer(
  state: SessionState,
  action: SessionAction,
): SessionState {
  const current = currentOf(state)

  switch (action.type) {
    case 'request_sent':
      return {
        ...state,
        openRequest: { request: action.request, status: 'pending' },
      }

    case 'request_answered':
      return state.openRequest ? { ...state, openRequest: null } : state

    case 'request_failed':
      if (state.openRequest?.status !== 'pending') return state
      return {
        ...state,
        openRequest: { ...state.openRequest, status: 'failed' },
      }

    case 'turn_applied':
      return applyTurn(state, action.turn)

    case 'turn_not_understood':
    case 'turn_unavailable':
    case 'turn_library_not_ready': {
      const events = [...state.events]
      if (action.echo !== undefined) append(events, { kind: 'user_message', text: action.echo })
      append(events, { kind: REFUSAL_EVENT[action.type], message: action.message })
      // Tune shows what can be asked instead (nothing can be, while the library is not ready).
      const refineTab = action.type === 'turn_library_not_ready' ? undefined : action.refineTab
      return {
        ...state,
        events,
        changedDimensions: [],
        refine: refineTab && state.intent ? { tab: refineTab } : state.refine,
      }
    }

    case 'play_toggled':
      if (!current) return state
      return {
        ...state,
        playback: { ...state.playback, playing: !state.playback.playing },
      }

    case 'playback_ticked':
      if (!current || !state.playback.playing) return state
      return {
        ...state,
        playback: {
          ...state.playback,
          positionSeconds: Math.min(
            current.durationSeconds,
            state.playback.positionSeconds + action.seconds,
          ),
        },
      }

    case 'playback_progressed':
      if (!current) return state
      return {
        ...state,
        playback: {
          ...state.playback,
          positionSeconds: action.positionSeconds,
          durationSeconds: action.durationSeconds ?? state.playback.durationSeconds,
        },
      }

    case 'why_toggled':
      return { ...state, whyExpanded: !state.whyExpanded }

    case 'liked_set':
      if (!current) return state
      return {
        ...state,
        recommendations: updateCurrent(state, {
          liked: action.liked,
          echo: action.echo ?? current.echo,
        }),
        quickActions: action.quickActions ?? state.quickActions,
      }

    case 'refine_opened':
      if (!state.intent) return state
      return { ...state, refine: { tab: action.tab } }

    case 'refine_closed':
      return { ...state, refine: null }

    case 'playlist_picker_opened':
      if (!current) return state
      return {
        ...state,
        recommendations: updateCurrent(state, {
          echo: action.echo ?? current.echo,
        }),
        overlay: {
          type: 'playlist_picker',
          // Starts from where the song is already saved, which is empty for
          // an unsaved song. Suggestions are hints and are never ticked.
          selectedPlaylistIds: current.savedToPlaylistIds,
          suggestedPlaylistIds: action.suggestedPlaylistIds,
        },
      }

    case 'playlist_toggled': {
      if (state.overlay?.type !== 'playlist_picker') return state
      const selected = state.overlay.selectedPlaylistIds
      return {
        ...state,
        overlay: {
          ...state.overlay,
          selectedPlaylistIds: selected.includes(action.playlistId)
            ? selected.filter((id) => id !== action.playlistId)
            : [...selected, action.playlistId],
        },
      }
    }

    case 'playlist_picker_closed':
      if (state.overlay?.type !== 'playlist_picker') return state
      return { ...state, overlay: null }

    case 'playlists_saved': {
      const { overlay } = state
      if (overlay?.type !== 'playlist_picker' || !current) return state
      if (overlay.selectedPlaylistIds.length === 0) return state
      return {
        ...state,
        recommendations: updateCurrent(state, {
          savedToPlaylistIds: overlay.selectedPlaylistIds,
          echo: undefined,
        }),
        quickActions: action.quickActions ?? state.quickActions,
        overlay: null,
      }
    }

    case 'quick_actions_offered':
      if (action.recommendationId !== state.currentRecommendationId) {
        return state
      }
      return { ...state, quickActions: action.quickActions }

    case 'playlists_suggested':
      if (
        state.overlay?.type !== 'playlist_picker' ||
        action.recommendationId !== state.currentRecommendationId
      ) {
        return state
      }
      return {
        ...state,
        overlay: {
          ...state.overlay,
          suggestedPlaylistIds: action.suggestedPlaylistIds,
        },
      }

    case 'up_next_offered':
      if (action.recommendationId !== state.currentRecommendationId) {
        return state
      }
      return withUpNext(state, action.upNext)

    case 'like_reverted':
      return updateRecommendation(state, action.recommendationId, {
        liked: action.liked,
      })

    case 'playlists_save_reverted':
      return updateRecommendation(state, action.recommendationId, {
        savedToPlaylistIds: action.savedToPlaylistIds,
      })

    case 'drawer_opened':
      return { ...state, overlay: { type: 'session_drawer' } }

    case 'drawer_closed':
      if (state.overlay?.type !== 'session_drawer') return state
      return { ...state, overlay: null }

    case 'session_resumed': {
      if (!state.intent || state.events.at(-1)?.kind === 'session_resumed') {
        return state
      }
      const events = [...state.events]
      append(events, { kind: 'session_resumed', intent: state.intent })
      return { ...state, events }
    }
  }
}
