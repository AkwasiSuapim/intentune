// The boundary between the session feature and whatever answers it. Today
// that is a local mock; later it is the backend. The feature never interprets
// requests or chooses music itself: it asks here and applies the answer.
//
// Every method answers asynchronously, as a backend over HTTP would, and
// rejects when it cannot answer. The feature does not look inside a
// rejection: any failure means the request did not go through.
import type {
  Intent,
  IntentDimension,
  Playlist,
  Recommendation,
  RefineTab,
  SessionEnvironment,
  SessionState,
} from './types.ts'

/** A song as the service recommends it, before the session records it. */
export type RecommendedSong = Pick<
  Recommendation,
  | 'songId'
  | 'title'
  | 'artist'
  | 'descriptors'
  | 'artworkUrl'
  | 'durationSeconds'
  | 'why'
>

/** What the service needs to know about a session to answer a request. */
export type TurnContext = {
  intent: Intent | null
  currentSongId: string | null
  /** Songs already recommended in this session, oldest first. */
  playedSongIds: string[]
  /** Recommendations made since the intent last changed. */
  recommendationsSinceIntentChange: number
}

export type TurnRequest =
  | { kind: 'message'; text: string }
  | { kind: 'refine'; dimension: IntentDimension; valueId: string }
  | { kind: 'not_for_me' }
  | { kind: 'next' }

/** The service's answer to a request that moves the session forward. */
export type SessionTurn = {
  /** The user's words to show in the stream, when the turn began with some. */
  userText?: string
  /** The intent after this turn. */
  intent: Intent
  /**
   * How the turn is acknowledged: `intent` reports the intent (set, updated
   * or kept), `not_for_me` reports a rejected song, `none` says nothing.
   */
  acknowledgement: 'intent' | 'not_for_me' | 'none'
  /** Wording for the acknowledgement, when the default does not fit. */
  ackLabel?: string
  recommendation: RecommendedSong | null
  quickActions: SessionState['quickActions']
  upNext: RecommendedSong | null
  /** A title for a session that has just received its first intent. */
  title?: string
  /** Keeps the refine control open on this tab after the turn. */
  refineTab?: RefineTab
}

export type TurnResponse =
  | { kind: 'turn'; turn: SessionTurn }
  /** The message asked to save the current song. */
  | { kind: 'save_requested'; echo: string }
  /** The message said the user likes the current song. */
  | { kind: 'liked'; echo: string }

export type WorkspaceSeed = Pick<
  SessionEnvironment,
  'playlists' | 'starters' | 'refineOptions'
> & {
  /** Existing listening sessions, in the order the drawer lists them. */
  sessions: SessionState[]
}

export type SessionService = {
  /** Everything the app needs before it can open a session. */
  loadWorkspace(): Promise<WorkspaceSeed>
  respond(context: TurnContext, request: TurnRequest): Promise<TurnResponse>
  /** The quick actions to offer after a reaction to the current song. */
  quickActionsAfter(
    reaction: 'liked' | 'saved',
  ): Promise<SessionState['quickActions']>
  /** Playlists worth hinting at for the current song. Never a selection. */
  suggestPlaylists(
    context: TurnContext,
    playlists: Playlist[],
  ): Promise<string[]>
}
