// The boundary between the session feature and whatever answers it: the
// local mock, or the backend over HTTP (src/services/http/). The feature never
// interprets requests or chooses music itself: it asks here and applies the
// answer.
//
// Requests carry meaning, not wording. A control whose meaning the UI knows
// (a quick action, a starter, a Tune value, Next, Like) is sent as that
// meaning; only what the listener typed is sent as text, unread, for the
// service to interpret.
//
// Every method answers asynchronously, as a backend over HTTP would, and
// rejects when it cannot answer. The feature does not look inside a
// rejection: any failure means the request did not go through.
import type {
  Intent,
  IntentDimension,
  Playlist,
  QuickAction,
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
  | 'ref'
  | 'audioUrl'
>

/** What the service needs to know about a session to answer a request. */
export type TurnContext = {
  /** The session asking, as the feature knows it. */
  sessionId: string
  intent: Intent | null
  currentSongId: string | null
  /** The service's own reference for the recommendation in view, if it gave one. */
  currentRef: string | null
  /** Songs already recommended in this session, oldest first. */
  playedSongIds: string[]
  /** Recommendations made since the intent last changed. */
  recommendationsSinceIntentChange: number
}

/** The steering controls a quick action can stand for (D36). */
export type SteeringControl =
  | 'more_like_this'
  | 'surprise_me'
  | 'more_familiar'
  | 'try_something_different'

/** How far the current song got, as the player measured it. */
export type PlaybackFacts = {
  playedSeconds: number
  durationSeconds: number
}

export type TurnRequest =
  /** What the listener typed, sent unread. Only the service interprets it. */
  | { kind: 'message'; text: string; playback?: PlaybackFacts }
  /** A starter the service offered. `phrase` is shown as the listener's words. */
  | { kind: 'starter'; starterId: string; phrase: string }
  /** A quick action's steering control. `label` is shown as the listener's words. */
  | { kind: 'control'; control: SteeringControl; label: string }
  | { kind: 'refine'; dimension: IntentDimension; valueId: string }
  | { kind: 'not_for_me' }
  /** The listener moved on, with how far the song got when the player knows. */
  | { kind: 'next'; playback?: PlaybackFacts }
  /** The song played to its end. */
  | { kind: 'track_ended'; playback: PlaybackFacts }
  /** A past song played again, named by its song and the service's reference. */
  | { kind: 'replay'; songId: string; ref: string | null }

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
  /** The song that is now the hero, or null when the hero plays on. */
  recommendation: RecommendedSong | null
  quickActions: SessionState['quickActions']
  upNext: RecommendedSong | null
  /** A title for a session that has just received its first intent. */
  title?: string
  /** Keeps the refine control open on this tab after the turn. */
  refineTab?: RefineTab
  /** The hero starts again from the beginning. */
  restart?: boolean
}

export type TurnResponse =
  | { kind: 'turn'; turn: SessionTurn }
  /** The message asked to save the current song. */
  | { kind: 'save_requested'; echo: string }
  /** The message said the user likes the current song. */
  | { kind: 'liked'; echo: string }
  /**
   * The service cannot act on the message. Nothing changed. `message` says so
   * in the listener's terms; Tune opens on `refineTab` to show what can be asked.
   */
  | {
      kind: 'not_understood'
      echo: string
      message: string
      refineTab?: RefineTab
    }
  /**
   * The service understood the request, but the music library cannot act on
   * what it asks for (a mood, genre or energy no track has). Nothing changed.
   * `echo` is the listener's words, when they typed them.
   */
  | {
      kind: 'unavailable'
      echo?: string
      message: string
      refineTab?: RefineTab
    }
  /** The music library has nothing playable yet: music must be imported first. Nothing changed. */
  | {
      kind: 'library_not_ready'
      echo?: string
      message: string
    }

/** What a reaction or a save led to: hints for the song in view, when there are any. */
export type ReactionAnswer = {
  quickActions?: QuickAction[]
  /** The new peek at what follows, when the reaction changed it. */
  upNext?: RecommendedSong | null
}

export type WorkspaceSeed = Pick<
  SessionEnvironment,
  'playlists' | 'starters' | 'refineOptions' | 'unavailableDimensions' | 'libraryReady'
> & {
  /** Existing listening sessions, in the order the drawer lists them. */
  sessions: SessionState[]
}

export type SessionService = {
  /** Everything the app needs before it can open a session. */
  loadWorkspace(): Promise<WorkspaceSeed>
  respond(context: TurnContext, request: TurnRequest): Promise<TurnResponse>
  /** Records a Like, or takes one back, for the song in view. */
  react(
    context: TurnContext,
    reaction: 'like' | 'unlike',
  ): Promise<ReactionAnswer>
  /** Saves the song in view to these playlists, and removes it from those. */
  savePlaylists(
    context: TurnContext,
    change: { added: string[]; removed: string[] },
  ): Promise<ReactionAnswer>
  /** Creates a playlist with this name. */
  createPlaylist(name: string): Promise<Playlist>
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
