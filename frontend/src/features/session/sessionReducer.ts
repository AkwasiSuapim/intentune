// Deterministic state transitions for one listening session. Pure: the same
// state and action always give the same next state. Anything a backend would
// decide arrives here already decided, inside the action.
import type { RecommendedSong, SessionTurn } from './sessionService.ts'
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
  | { type: 'turn_applied'; turn: SessionTurn }
  | { type: 'play_toggled' }
  | { type: 'playback_ticked'; seconds: number }
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
  | { type: 'playlists_saved'; quickActions: SessionState['quickActions'] }
  | { type: 'recommendation_replayed'; recommendationId: string }
  | { type: 'drawer_opened' }
  | { type: 'drawer_closed' }
  | { type: 'session_resumed' }

const SESSION_ACTION_TYPES = new Set<string>([
  'turn_applied',
  'play_toggled',
  'playback_ticked',
  'why_toggled',
  'liked_set',
  'refine_opened',
  'refine_closed',
  'playlist_picker_opened',
  'playlist_toggled',
  'playlist_picker_closed',
  'playlists_saved',
  'recommendation_replayed',
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
  }
}

type NewEvent = SessionEvent extends infer Event
  ? Event extends SessionEvent
    ? Omit<Event, 'id'>
    : never
  : never

function append(events: SessionEvent[], event: NewEvent) {
  events.push({ ...event, id: `e${events.length + 1}` } as SessionEvent)
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
      : state.playback,
    whyExpanded: false,
    quickActions: turn.quickActions,
    upNextRecommendationId: turn.upNext ? UP_NEXT_ID : null,
    refine: turn.refineTab && intent ? { tab: turn.refineTab } : null,
    overlay: null,
  }
}

function replay(state: SessionState, recommendationId: string): SessionState {
  const source = state.recommendations[recommendationId]
  if (!source || recommendationId === state.currentRecommendationId) {
    return state
  }

  // Playing a past song again is a fresh recommendation of the same song:
  // the earlier entry stays in the history with its own outcome.
  const events = [...state.events]
  const id = `rec-${events.length + 1}`
  append(events, { kind: 'recommendation', recommendationId: id })

  return {
    ...state,
    changedDimensions: [],
    events,
    recommendations: {
      ...state.recommendations,
      [id]: { ...record(id, source), echo: undefined },
    },
    currentRecommendationId: id,
    playback: { playing: true, positionSeconds: 0 },
    whyExpanded: false,
  }
}

export function sessionReducer(
  state: SessionState,
  action: SessionAction,
): SessionState {
  const current = currentOf(state)

  switch (action.type) {
    case 'turn_applied':
      return applyTurn(state, action.turn)

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
        quickActions: action.quickActions,
        overlay: null,
      }
    }

    case 'recommendation_replayed':
      return replay(state, action.recommendationId)

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
