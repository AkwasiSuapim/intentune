// Semantic state of a listening session. Nothing here describes layout or
// components: `composeSession` turns this state into renderable blocks.
import type { PlaylistTone } from '../../components/PlaylistSwatch.tsx'
import type { TurnRequest } from './sessionService.ts'

export type IntentDimension = 'mood' | 'genre' | 'energy'

export const INTENT_DIMENSIONS: IntentDimension[] = ['mood', 'genre', 'energy']

export type IntentValue = {
  id: string
  label: string
}

/** The interpreted listening intent: one value per dimension. */
export type Intent = Record<IntentDimension, IntentValue>

export type IntentChange = {
  dimension: IntentDimension
  from: IntentValue
  to: IntentValue
}

export type Recommendation = {
  id: string
  /** The song recommended. The same song can be recommended more than once. */
  songId: string
  title: string
  artist: string
  /** Concise music descriptors, e.g. genre and feel. */
  descriptors: string[]
  artworkUrl: string | null
  durationSeconds: number
  why: {
    summary: string
    reasons: string[]
  }
  /** The user's own words this recommendation answers, when worth echoing. */
  echo?: string
  liked: boolean
  skipped: boolean
  savedToPlaylistIds: string[]
}

/** One entry in the chronological session stream. */
export type SessionEvent =
  | { kind: 'user_message'; id: string; text: string }
  | { kind: 'intent_set'; id: string; intent: Intent }
  | {
      kind: 'intent_updated'
      id: string
      changes: IntentChange[]
      /** Wording for the acknowledgement, when the default does not fit. */
      label?: string
    }
  | { kind: 'intent_kept'; id: string; intent: Intent; label: string }
  | { kind: 'intent_unchanged'; id: string; cause: 'not_for_me' }
  | { kind: 'session_resumed'; id: string; intent: Intent }
  | { kind: 'recommendation'; id: string; recommendationId: string }

export type RefineTab = IntentDimension

export type SessionOverlay =
  | {
      type: 'playlist_picker'
      /** Only what the user has explicitly chosen. */
      selectedPlaylistIds: string[]
      /** Playlists hinted as matching the session. Never a selection. */
      suggestedPlaylistIds: string[]
    }
  | { type: 'session_drawer' }

/** A request that moves the session forward, until the service answers it. */
export type OpenRequest = {
  request: TurnRequest
  /** `pending` while the service is answering; `failed` once it could not. */
  status: 'pending' | 'failed'
}

export type SessionState = {
  id: string
  title: string
  /** The single source of truth for the current intent. */
  intent: Intent | null
  /** Dimensions changed by the latest turn, marked on the intent chips. */
  changedDimensions: IntentDimension[]
  events: SessionEvent[]
  recommendations: Record<string, Recommendation>
  /** The one recommendation shown as the hero; every other one is history. */
  currentRecommendationId: string | null
  playback: {
    playing: boolean
    positionSeconds: number
  }
  whyExpanded: boolean
  /** Contextual refinements offered for the current recommendation. */
  quickActions: { id: string; label: string }[]
  /** A single peek at what follows, when one is worth showing. */
  upNextRecommendationId: string | null
  /** The open refine mode, or null when the quick actions show instead. */
  refine: { tab: RefineTab } | null
  overlay: SessionOverlay | null
  /** At most one request is open at a time. */
  openRequest: OpenRequest | null
}

export type Playlist = {
  id: string
  name: string
  tone?: PlaylistTone
}

export type SessionListItem = {
  id: string
  title: string
  intent: Intent | null
}

export type StarterIntent = {
  id: string
  label: string
  /** The prewritten first request this starter stands for. */
  phrase: string
  artworkUrl: string | null
}

/** Data around a session that its view needs but the session does not own. */
export type SessionEnvironment = {
  playlists: Playlist[]
  sessions: SessionListItem[]
  starters: StarterIntent[]
  /** The values offered when tuning, per dimension. Energy runs low to high. */
  refineOptions: Record<IntentDimension, IntentValue[]>
}
