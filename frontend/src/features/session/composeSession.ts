// UI composition policy: a pure function from semantic session state to the
// blocks each region of the screen shows. It decides which approved blocks
// appear and in what order. It never chooses, scores or ranks music.
import type { AccentContext } from '../../app/AppShell.tsx'
import type {
  DrawerPlaylist,
  DrawerSession,
} from '../../components/SessionDrawer.tsx'
import type { RecommendationOutcome } from '../../components/RecommendationCardCompact.tsx'
import type { BlockOf, TimelineBlock } from './blocks.ts'
import { nextEventId } from './sessionReducer.ts'
import { INTENT_DIMENSIONS } from './types.ts'
import type {
  Intent,
  IntentDimension,
  Recommendation,
  SessionEnvironment,
  SessionEvent,
  SessionState,
} from './types.ts'

export type SessionComposition = {
  title: string
  accent: AccentContext
  intentSummary: BlockOf<'intent_summary'> | null
  /** `prompt` fills the screen with the Tune in state; `timeline` scrolls. */
  layout: 'prompt' | 'timeline'
  content: BlockOf<'discovery_prompt'>[] | TimelineBlock[]
  contextualControl: BlockOf<'quick_actions' | 'refine_control'> | null
  overlay: BlockOf<'playlist_picker'> | null
  /**
   * Session navigation. It is shell navigation, not a block: a drawer on
   * small screens, opened on request, and a standing rail on wide ones.
   */
  navigation: { sessions: DrawerSession[]; playlists: DrawerPlaylist[] }
  /** Whether the user has asked for the navigation drawer. */
  drawerOpen: boolean
  /** The song now playing, for the composer's compact now-playing slot. */
  nowPlaying: { title: string; artworkUrl: string | null; playing: boolean } | null
  composerPlaceholder: string
  /** True while the service is answering: nothing new can be sent yet. */
  busy: boolean
}

const NO_INTENT_YET = 'No intent yet'

// Only the accent tokens follow the listening context; unknown moods keep the default.
const ACCENT_BY_MOOD: Record<string, AccentContext> = {
  emotional: 'emotional',
  focused: 'focused',
  calm: 'calm',
  joyful: 'calm',
  driven: 'driven',
}

/** How a value reads on its own, e.g. on a chip: "Low energy". */
function valueLabel(intent: Intent, dimension: IntentDimension) {
  const { label } = intent[dimension]
  return dimension === 'energy' ? `${label} energy` : label
}

/** The whole intent in words. Used wherever an intent is spelled out. */
export function describeIntent(intent: Intent) {
  return INTENT_DIMENSIONS.map((dimension) =>
    valueLabel(intent, dimension),
  ).join(' · ')
}

function dimensionName(dimension: IntentDimension) {
  return dimension.charAt(0).toUpperCase() + dimension.slice(1)
}

function outcomeOf(recommendation: Recommendation): RecommendationOutcome {
  if (recommendation.skipped) return 'skipped'
  if (recommendation.savedToPlaylistIds.length > 0) return 'saved'
  if (recommendation.liked) return 'liked'
  return 'played'
}

function playlistNames(ids: string[], environment: SessionEnvironment) {
  return environment.playlists
    .filter((playlist) => ids.includes(playlist.id))
    .map((playlist) => playlist.name)
}

function composeIntentSummary(
  state: SessionState,
): BlockOf<'intent_summary'> | null {
  const { intent } = state
  if (!intent) return null

  return {
    type: 'intent_summary',
    id: 'intent-summary',
    chips: INTENT_DIMENSIONS.map((dimension) => ({
      id: dimension,
      label: valueLabel(intent, dimension),
      changed: state.changedDimensions.includes(dimension),
      expanded: state.refine?.tab === dimension,
    })),
  }
}

function composeEvent(
  event: SessionEvent,
  state: SessionState,
  environment: SessionEnvironment,
): TimelineBlock | null {
  switch (event.kind) {
    case 'user_message':
      return { type: 'user_message', id: event.id, text: event.text }
    case 'intent_set':
      return {
        type: 'ack',
        id: event.id,
        label: 'Intent set',
        detail: describeIntent(event.intent),
        tone: 'confirm',
      }
    case 'intent_updated':
      return {
        type: 'ack',
        id: event.id,
        label: event.label ?? 'Intent updated',
        changes: event.changes.map((change) => ({
          dimension: dimensionName(change.dimension),
          from: change.from.label,
          to: change.to.label,
        })),
        tone: 'confirm',
      }
    case 'intent_kept':
      return {
        type: 'ack',
        id: event.id,
        label: event.label,
        detail: describeIntent(event.intent),
        tone: 'confirm',
      }
    case 'intent_unchanged':
      return {
        type: 'ack',
        id: event.id,
        label: 'Not for me',
        detail: 'Intent unchanged',
        tone: 'neutral',
      }
    case 'session_resumed':
      return {
        type: 'session_summary',
        id: event.id,
        label: 'Picking up where you left off',
        detail: describeIntent(event.intent),
      }
    case 'recommendation': {
      const recommendation = state.recommendations[event.recommendationId]
      if (!recommendation) return null

      // Exactly one hero: the current recommendation. The rest are history.
      if (recommendation.id !== state.currentRecommendationId) {
        return {
          type: 'recommendation',
          id: event.id,
          variant: 'compact',
          recommendationId: recommendation.id,
          title: recommendation.title,
          artist: recommendation.artist,
          artworkUrl: recommendation.artworkUrl,
          outcome: outcomeOf(recommendation),
        }
      }
      return {
        type: 'recommendation',
        id: event.id,
        variant: 'hero',
        recommendationId: recommendation.id,
        title: recommendation.title,
        artist: recommendation.artist,
        descriptors: recommendation.descriptors,
        artworkUrl: recommendation.artworkUrl,
        // The echo steps aside while the playlist sheet covers the card.
        echo:
          state.overlay?.type === 'playlist_picker'
            ? undefined
            : recommendation.echo,
        playing: state.playback.playing,
        positionSeconds: state.playback.positionSeconds,
        durationSeconds: recommendation.durationSeconds,
        whySummary: recommendation.why.summary,
        whyReasons: recommendation.why.reasons,
        whyExpanded: state.whyExpanded,
        liked: recommendation.liked,
        savedTo: playlistNames(recommendation.savedToPlaylistIds, environment),
      }
    }
  }
}

function composeTimeline(
  state: SessionState,
  environment: SessionEnvironment,
  current: Recommendation | null,
): TimelineBlock[] {
  const blocks: TimelineBlock[] = []
  let hero: TimelineBlock | null = null

  for (const event of state.events) {
    const block = composeEvent(event, state, environment)
    if (!block) continue
    if (block.type === 'recommendation' && block.variant === 'hero') {
      // A recommendation repeated in the stream still yields a single hero.
      hero ??= block
      continue
    }
    blocks.push(block)
  }
  // The hero always closes the stream: anything noted since it started
  // playing (such as returning to the session) reads above it.
  if (hero) blocks.push(hero)

  // Up next is one peek row, shown only while the quick actions are.
  const upNext =
    current && !state.refine && state.upNextRecommendationId
      ? state.recommendations[state.upNextRecommendationId]
      : undefined
  if (hero && upNext && upNext.id !== current?.id) {
    blocks.push({
      type: 'up_next',
      id: 'up-next',
      title: upNext.title,
      artist: upNext.artist,
      artworkUrl: upNext.artworkUrl,
    })
  }

  // An open request reads last, where its answer will appear.
  const { openRequest } = state
  if (openRequest) {
    if (openRequest.request.kind === 'message') {
      // Takes the id the message will have once answered, so it stays put.
      blocks.push({
        type: 'user_message',
        id: nextEventId(state),
        text: openRequest.request.text,
      })
    }
    blocks.push({
      type: 'turn_status',
      id: `turn-${openRequest.status}`,
      status: openRequest.status,
    })
  }
  return blocks
}

function composeContextualControl(
  state: SessionState,
  environment: SessionEnvironment,
  current: Recommendation | null,
): SessionComposition['contextualControl'] {
  const { intent, refine } = state

  if (intent && refine) {
    return {
      type: 'refine_control',
      id: 'refine-control',
      activeTab: refine.tab,
      energyLevels: environment.refineOptions.energy,
      energyId: intent.energy.id,
      moods: environment.refineOptions.mood,
      moodId: intent.mood.id,
      genres: environment.refineOptions.genre,
      genreId: intent.genre.id,
    }
  }
  if (current && state.quickActions.length > 0) {
    return {
      type: 'quick_actions',
      id: 'quick-actions',
      actions: state.quickActions,
    }
  }
  return null
}

function composeOverlay(
  state: SessionState,
  environment: SessionEnvironment,
  current: Recommendation | null,
): BlockOf<'playlist_picker'> | null {
  const { overlay } = state
  if (overlay?.type !== 'playlist_picker' || !current) return null

  return {
    type: 'playlist_picker',
    id: 'playlist-picker',
    songTitle: current.title,
    songArtist: current.artist,
    artworkUrl: current.artworkUrl,
    playlists: environment.playlists.map((playlist) => ({
      ...playlist,
      fitsSession: overlay.suggestedPlaylistIds.includes(playlist.id),
    })),
    selectedIds: overlay.selectedPlaylistIds,
  }
}

function composeNavigation(
  state: SessionState,
  environment: SessionEnvironment,
): SessionComposition['navigation'] {
  const describe = (intent: Intent | null) =>
    intent ? describeIntent(intent) : NO_INTENT_YET
  const listed = environment.sessions.some(
    (session) => session.id === state.id,
  )
  const sessions: DrawerSession[] = environment.sessions.map((session) => {
    const active = session.id === state.id
    // The open session always reads from its live state, not the list copy.
    return {
      id: session.id,
      title: active ? state.title : session.title,
      subtitle: describe(active ? state.intent : session.intent),
      active,
    }
  })
  if (!listed) {
    sessions.unshift({
      id: state.id,
      title: state.title,
      subtitle: describe(state.intent),
      active: true,
    })
  }
  return { sessions, playlists: environment.playlists }
}

export function composeSession(
  state: SessionState,
  environment: SessionEnvironment,
): SessionComposition {
  const current =
    (state.currentRecommendationId &&
      state.recommendations[state.currentRecommendationId]) ||
    null
  const isNewSession =
    state.events.length === 0 && !state.intent && !state.openRequest
  const content: Pick<SessionComposition, 'layout' | 'content'> = isNewSession
    ? {
        layout: 'prompt',
        content: [
          {
            type: 'discovery_prompt',
            id: 'discovery-prompt',
            starters: environment.starters,
          },
        ],
      }
    : {
        layout: 'timeline',
        content: composeTimeline(state, environment, current),
      }

  return {
    title: state.title,
    accent:
      (state.intent && ACCENT_BY_MOOD[state.intent.mood.id]) || 'emotional',
    intentSummary: composeIntentSummary(state),
    ...content,
    contextualControl: composeContextualControl(state, environment, current),
    overlay: composeOverlay(state, environment, current),
    navigation: composeNavigation(state, environment),
    drawerOpen: state.overlay?.type === 'session_drawer',
    nowPlaying: current && {
      title: current.title,
      artworkUrl: current.artworkUrl,
      playing: state.playback.playing,
    },
    composerPlaceholder: isNewSession
      ? 'Tell Intentune what you want…'
      : 'Tell Intentune what you want next…',
    busy: state.openRequest?.status === 'pending',
  }
}
