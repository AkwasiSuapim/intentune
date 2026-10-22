// The controlled block vocabulary: the only things a session can render.
// A block is display-ready data. It carries no markup, styles or code.
import type { IntentChange as AckChange } from '../../components/Ack.tsx'
import type { StarterIntent } from '../../components/DiscoveryPrompt.tsx'
import type { IntentChip } from '../../components/IntentSummary.tsx'
import type { PlaylistOption } from '../../components/PlaylistPicker.tsx'
import type { QuickAction } from '../../components/QuickActions.tsx'
import type { RecommendationOutcome } from '../../components/RecommendationCardCompact.tsx'
import type {
  RefineOption,
  RefineTab,
} from '../../components/RefineControl.tsx'

export type SessionBlock =
  | { type: 'intent_summary'; id: string; chips: IntentChip[] }
  | { type: 'discovery_prompt'; id: string; starters: StarterIntent[] }
  | { type: 'user_message'; id: string; text: string }
  | {
      type: 'ack'
      id: string
      label: string
      detail?: string
      changes?: AckChange[]
      tone: 'confirm' | 'neutral'
    }
  | { type: 'session_summary'; id: string; label: string; detail: string }
  /** A request the service is still answering, or could not answer. */
  | { type: 'turn_status'; id: string; status: 'pending' | 'failed' }
  | {
      type: 'recommendation'
      id: string
      /** `hero` is the one current recommendation; `compact` is history. */
      variant: 'hero'
      recommendationId: string
      title: string
      artist: string
      descriptors: string[]
      artworkUrl: string | null
      echo?: string
      playing: boolean
      positionSeconds: number
      durationSeconds: number
      /** Absent when the recommendation carries no explanation. */
      whySummary?: string
      whyReasons: string[]
      whyExpanded: boolean
      liked: boolean
      savedTo: string[]
    }
  | {
      type: 'recommendation'
      id: string
      variant: 'compact'
      recommendationId: string
      title: string
      artist: string
      artworkUrl: string | null
      outcome: RecommendationOutcome
    }
  | {
      type: 'up_next'
      id: string
      title: string
      artist: string
      artworkUrl: string | null
    }
  | { type: 'quick_actions'; id: string; actions: QuickAction[] }
  | {
      type: 'refine_control'
      id: string
      activeTab: RefineTab
      energyLevels: RefineOption[]
      energyId: string | null
      moods: RefineOption[]
      moodId: string | null
      genres: RefineOption[]
      genreId: string | null
      /** Tabs the library has no evidence for: shown, marked, and not tunable. */
      unavailable: RefineTab[]
      /** False while nothing in the library is playable: nothing is tunable, for that one reason. */
      libraryReady: boolean
    }
  | {
      type: 'playlist_picker'
      id: string
      songTitle: string
      songArtist: string
      artworkUrl: string | null
      playlists: PlaylistOption[]
      selectedIds: string[]
    }

export type SessionBlockType = SessionBlock['type']

/** The block (or blocks) carrying a given type. */
export type BlockOf<T extends SessionBlockType> = Extract<
  SessionBlock,
  { type: T }
>

/** Blocks that may appear in the scrolling session stream. */
export type TimelineBlock = BlockOf<
  | 'user_message'
  | 'ack'
  | 'session_summary'
  | 'recommendation'
  | 'up_next'
  | 'turn_status'
>
