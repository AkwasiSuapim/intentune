// What the user can ask of a session, and how each request becomes state
// changes. `planCommand` is pure: it reads the workspace and returns the
// changes to make at once, plus anything only the service can answer. `ask`
// puts that question to the service and turns the answer into changes for the
// session that asked.
//
// Requests carry meaning: a starter, a quick action, Next or Like is sent as
// what it is, never as words for the service to read again. Only what the
// listener typed travels as text, unread.
import type {
  PlaybackFacts,
  ReactionAnswer,
  SessionService,
  TurnContext,
  TurnRequest,
} from './sessionService.ts'
import type { SessionAction } from './sessionReducer.ts'
import { activeSession, newPlaylistName } from './workspaceReducer.ts'
import type { WorkspaceAction, WorkspaceState } from './workspaceReducer.ts'
import type {
  IntentDimension,
  Playlist,
  RefineTab,
  SessionState,
} from './types.ts'

export type SessionCommand =
  // Conversation: typed words, a starter, or a quick action.
  | { type: 'send_message'; text: string }
  | { type: 'select_starter'; starterId: string }
  | { type: 'select_quick_action'; actionId: string }
  /** Sends the request that did not go through again. */
  | { type: 'retry' }
  // Tuning the session direction.
  | { type: 'open_refine' }
  | { type: 'toggle_refine_tab'; tab: RefineTab }
  | { type: 'change_refine_tab'; tab: RefineTab }
  | { type: 'close_refine' }
  | { type: 'refine'; dimension: IntentDimension; valueId: string }
  // The current song: playback and reactions.
  | { type: 'toggle_play' }
  /** The simulated clock's beat, for a song with no audio behind it. */
  | { type: 'tick' }
  /** The audio player's own position and duration. */
  | { type: 'playback_progressed'; positionSeconds: number; durationSeconds?: number }
  /** The audio player reached the end of the song. */
  | { type: 'track_ended' }
  /** The browser would not start playing the audio. */
  | { type: 'playback_refused' }
  | { type: 'next' }
  | { type: 'toggle_why' }
  | { type: 'toggle_like' }
  | { type: 'not_for_me' }
  | { type: 'replay'; recommendationId: string }
  // Saving to playlists.
  | { type: 'open_playlist_picker' }
  | { type: 'toggle_playlist'; playlistId: string }
  | { type: 'create_playlist' }
  | { type: 'confirm_playlists' }
  | { type: 'close_playlist_picker' }
  // Moving between sessions.
  | { type: 'open_drawer' }
  | { type: 'close_drawer' }
  | { type: 'new_session' }
  | { type: 'open_session'; sessionId: string }

/** Something only the service can answer, asked on behalf of one session. */
export type ServiceQuestion = {
  /** The session asking. The answer goes to it, wherever the user is by then. */
  sessionId: string
  context: TurnContext
  /** The user's playlists, for suggesting where a song might be saved. */
  playlists: Playlist[]
} & (
  /** A request that moves the session forward. */
  | { kind: 'turn'; request: TurnRequest }
  // About the current song. Each names the recommendation it is about.
  | { kind: 'playlist_suggestions'; recommendationId: string }
  | { kind: 'reaction'; recommendationId: string; reaction: 'like' | 'unlike' }
  | {
      kind: 'save_playlists'
      recommendationId: string
      added: string[]
      removed: string[]
      /** Where the song was saved before, to go back to if the save fails. */
      before: string[]
    }
  // About the workspace.
  | { kind: 'create_playlist'; name: string }
)

export type CommandPlan = {
  /** Applied at once, without waiting for the service. */
  actions: WorkspaceAction[]
  /** Asked of the service. Its answer is applied when it arrives. */
  question?: ServiceQuestion
}

function currentOf(session: SessionState) {
  return (
    (session.currentRecommendationId &&
      session.recommendations[session.currentRecommendationId]) ||
    null
  )
}

export function turnContext(session: SessionState): TurnContext {
  const current = currentOf(session)
  const playedSongIds: string[] = []
  let recommendationsSinceIntentChange = 0

  for (const event of session.events) {
    if (event.kind === 'intent_set' || event.kind === 'intent_updated') {
      recommendationsSinceIntentChange = 0
    }
    if (event.kind === 'recommendation') {
      recommendationsSinceIntentChange++
      const songId = session.recommendations[event.recommendationId]?.songId
      if (songId && !playedSongIds.includes(songId)) playedSongIds.push(songId)
    }
  }

  return {
    sessionId: session.id,
    intent: session.intent,
    currentSongId: current?.songId ?? null,
    currentRef: current?.ref ?? null,
    playedSongIds,
    recommendationsSinceIntentChange,
  }
}

/** How far the current song got, when there is one with a known length. */
function playbackFacts(session: SessionState): PlaybackFacts | undefined {
  const current = currentOf(session)
  if (!current) return undefined
  const duration = session.playback.durationSeconds ?? current.durationSeconds
  if (!(duration > 0)) return undefined
  return {
    playedSeconds: Math.min(session.playback.positionSeconds, duration),
    durationSeconds: duration,
  }
}

const NOTHING: CommandPlan = { actions: [] }

const local = (...actions: WorkspaceAction[]): CommandPlan => ({ actions })

export function planCommand(
  workspace: WorkspaceState,
  command: SessionCommand,
): CommandPlan {
  const session = activeSession(workspace)
  const current = currentOf(session)
  const asking = {
    sessionId: session.id,
    context: turnContext(session),
    playlists: workspace.playlists,
  }

  // One request at a time: while the service is answering one, nothing
  // else that would move the session forward is sent.
  const send = (request: TurnRequest): CommandPlan =>
    session.openRequest?.status === 'pending'
      ? NOTHING
      : {
          actions: [{ type: 'request_sent', request }],
          question: { ...asking, kind: 'turn', request },
        }
  const say = (text: string) =>
    text.trim()
      ? send({ kind: 'message', text: text.trim(), playback: playbackFacts(session) })
      : NOTHING

  switch (command.type) {
    case 'send_message':
      return say(command.text)

    case 'select_starter': {
      const starter = workspace.starters.find(
        (candidate) => candidate.id === command.starterId,
      )
      // A starter the library cannot act on is shown with its reason and sends nothing.
      return starter && !starter.unavailableReason
        ? send({ kind: 'starter', starterId: starter.id, phrase: starter.phrase })
        : NOTHING
    }

    case 'select_quick_action': {
      const action = session.quickActions.find(
        (candidate) => candidate.id === command.actionId,
      )
      return action ? send(action.request) : NOTHING
    }

    case 'retry':
      return session.openRequest?.status === 'failed'
        ? send(session.openRequest.request)
        : NOTHING

    case 'open_refine':
      return local({ type: 'refine_opened', tab: session.refine?.tab ?? 'energy' })

    case 'toggle_refine_tab':
      return session.refine?.tab === command.tab
        ? local({ type: 'refine_closed' })
        : local({ type: 'refine_opened', tab: command.tab })

    case 'change_refine_tab':
      return local({ type: 'refine_opened', tab: command.tab })

    case 'close_refine':
      return local({ type: 'refine_closed' })

    case 'refine': {
      const { intent } = session
      if (!intent || intent[command.dimension].id === command.valueId) {
        return NOTHING
      }
      // A dimension or value the library cannot use would change nothing: it is not sent.
      const option = workspace.refineOptions[command.dimension].find(
        (candidate) => candidate.id === command.valueId,
      )
      if (workspace.unavailableDimensions?.includes(command.dimension) || option?.unavailable) {
        return NOTHING
      }
      return send({
        kind: 'refine',
        dimension: command.dimension,
        valueId: command.valueId,
      })
    }

    case 'toggle_play':
      return local({ type: 'play_toggled' })

    case 'tick': {
      if (!current || current.audioUrl || !session.playback.playing || session.overlay) {
        return NOTHING
      }
      // The simulated song ran out: it ended, as a real one would.
      if (session.playback.positionSeconds + 1 >= current.durationSeconds) {
        return send({
          kind: 'track_ended',
          playback: {
            playedSeconds: current.durationSeconds,
            durationSeconds: current.durationSeconds,
          },
        })
      }
      return local({ type: 'playback_ticked', seconds: 1 })
    }

    case 'playback_progressed':
      return current
        ? local({
            type: 'playback_progressed',
            positionSeconds: command.positionSeconds,
            durationSeconds: command.durationSeconds,
          })
        : NOTHING

    case 'playback_refused':
      return session.playback.playing ? local({ type: 'play_toggled' }) : NOTHING

    case 'track_ended': {
      const playback = playbackFacts(session)
      if (!current || !playback) return NOTHING
      return send({
        kind: 'track_ended',
        playback: { playedSeconds: playback.durationSeconds, durationSeconds: playback.durationSeconds },
      })
    }

    case 'next':
      return current
        ? send({ kind: 'next', playback: playbackFacts(session) })
        : NOTHING

    case 'toggle_why':
      return local({ type: 'why_toggled' })

    case 'toggle_like': {
      if (!current) return NOTHING
      const liked = !current.liked
      return {
        actions: [{ type: 'liked_set', liked }],
        question: {
          ...asking,
          kind: 'reaction',
          recommendationId: current.id,
          reaction: liked ? 'like' : 'unlike',
        },
      }
    }

    case 'not_for_me':
      return current ? send({ kind: 'not_for_me' }) : NOTHING

    case 'replay': {
      const replayed = session.recommendations[command.recommendationId]
      if (!replayed || replayed.id === session.currentRecommendationId) {
        return NOTHING
      }
      return send({ kind: 'replay', songId: replayed.songId, ref: replayed.ref ?? null })
    }

    case 'open_playlist_picker':
      if (!current) return NOTHING
      // The sheet opens at once; suggestions are marked when they arrive.
      return {
        actions: [{ type: 'playlist_picker_opened', suggestedPlaylistIds: [] }],
        question: {
          ...asking,
          kind: 'playlist_suggestions',
          recommendationId: current.id,
        },
      }

    case 'toggle_playlist':
      return local({ type: 'playlist_toggled', playlistId: command.playlistId })

    case 'create_playlist':
      if (session.overlay?.type !== 'playlist_picker') return NOTHING
      return {
        actions: [],
        question: { ...asking, kind: 'create_playlist', name: newPlaylistName(workspace) },
      }

    case 'confirm_playlists': {
      const { overlay } = session
      if (
        overlay?.type !== 'playlist_picker' ||
        overlay.selectedPlaylistIds.length === 0 ||
        !current
      ) {
        return NOTHING
      }
      const before = current.savedToPlaylistIds
      const selected = overlay.selectedPlaylistIds
      return {
        actions: [{ type: 'playlists_saved' }],
        question: {
          ...asking,
          kind: 'save_playlists',
          recommendationId: current.id,
          added: selected.filter((id) => !before.includes(id)),
          removed: before.filter((id) => !selected.includes(id)),
          before,
        },
      }
    }

    case 'close_playlist_picker':
      return local({ type: 'playlist_picker_closed' })

    case 'open_drawer':
      return local({ type: 'drawer_opened' })

    case 'close_drawer':
      return local({ type: 'drawer_closed' })

    case 'new_session':
      return local({ type: 'session_created' })

    case 'open_session':
      return local({ type: 'session_opened', sessionId: command.sessionId })
  }
}

/** A hint is optional: when the service cannot give it, the session goes on without it. */
function hint<T>(answer: Promise<T>, fallback: T): Promise<T> {
  return answer.catch(() => fallback)
}

function hintsFor(recommendationId: string, answer: ReactionAnswer): SessionAction[] {
  const actions: SessionAction[] = []
  if (answer.quickActions) {
    actions.push({ type: 'quick_actions_offered', recommendationId, quickActions: answer.quickActions })
  }
  if (answer.upNext !== undefined) {
    actions.push({ type: 'up_next_offered', recommendationId, upNext: answer.upNext })
  }
  return actions
}

async function answer(
  service: SessionService,
  question: ServiceQuestion,
): Promise<SessionAction[]> {
  const { context, playlists } = question

  switch (question.kind) {
    case 'turn': {
      const response = await service.respond(context, question.request)
      switch (response.kind) {
        case 'turn':
          return [
            { type: 'request_answered' },
            { type: 'turn_applied', turn: response.turn },
          ]
        case 'save_requested':
          return [
            { type: 'request_answered' },
            {
              type: 'playlist_picker_opened',
              suggestedPlaylistIds: await hint(
                service.suggestPlaylists(context, playlists),
                [],
              ),
              echo: response.echo,
            },
          ]
        case 'liked':
          return [
            { type: 'request_answered' },
            {
              type: 'liked_set',
              liked: true,
              quickActions: await hint<SessionState['quickActions'] | undefined>(
                service.quickActionsAfter('liked'),
                undefined,
              ),
              echo: response.echo,
            },
          ]
        case 'not_understood':
          return [
            { type: 'request_answered' },
            {
              type: 'turn_not_understood',
              echo: response.echo,
              message: response.message,
              refineTab: response.refineTab,
            },
          ]
        case 'unavailable':
          return [
            { type: 'request_answered' },
            {
              type: 'turn_unavailable',
              echo: response.echo,
              message: response.message,
              refineTab: response.refineTab,
            },
          ]
        case 'library_not_ready':
          return [
            { type: 'request_answered' },
            { type: 'turn_library_not_ready', echo: response.echo, message: response.message },
          ]
      }
    }

    case 'playlist_suggestions':
      return [
        {
          type: 'playlists_suggested',
          recommendationId: question.recommendationId,
          suggestedPlaylistIds: await service.suggestPlaylists(
            context,
            playlists,
          ),
        },
      ]

    // A reaction or a save that does not go through is undone, so the card shows the truth.
    case 'reaction':
      try {
        return hintsFor(question.recommendationId, await service.react(context, question.reaction))
      } catch {
        return [{ type: 'like_reverted', recommendationId: question.recommendationId, liked: question.reaction === 'unlike' }]
      }

    case 'save_playlists':
      try {
        return hintsFor(
          question.recommendationId,
          await service.savePlaylists(context, { added: question.added, removed: question.removed }),
        )
      } catch {
        return [
          {
            type: 'playlists_save_reverted',
            recommendationId: question.recommendationId,
            savedToPlaylistIds: question.before,
          },
        ]
      }

    case 'create_playlist':
      return []
  }
}

/**
 * Puts a question to the service and returns the answer as one change for
 * the session that asked. Never rejects: a request that moves the session
 * forward and gets no answer is marked failed, so it can be tried again; a
 * hint that never comes is simply not shown.
 */
export async function ask(
  service: SessionService,
  question: ServiceQuestion,
): Promise<WorkspaceAction> {
  if (question.kind === 'create_playlist') {
    try {
      const playlist = await service.createPlaylist(question.name)
      return { type: 'playlist_created', sessionId: question.sessionId, playlist }
    } catch {
      return { type: 'answer_received', sessionId: question.sessionId, actions: [] }
    }
  }
  let actions: SessionAction[]
  try {
    actions = await answer(service, question)
  } catch {
    actions = question.kind === 'turn' ? [{ type: 'request_failed' }] : []
  }
  return { type: 'answer_received', sessionId: question.sessionId, actions }
}
