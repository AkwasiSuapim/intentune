// What the user can ask of a session, and how each request becomes state
// changes. `planCommand` is pure: it reads the workspace and returns the
// changes to make at once, plus anything only the service can answer. `ask`
// puts that question to the service and turns the answer into changes for the
// session that asked.
import type {
  SessionService,
  TurnContext,
  TurnRequest,
} from './sessionService.ts'
import type { SessionAction } from './sessionReducer.ts'
import { activeSession } from './workspaceReducer.ts'
import type { WorkspaceAction, WorkspaceState } from './workspaceReducer.ts'
import type {
  IntentDimension,
  Playlist,
  RefineTab,
  SessionState,
} from './types.ts'

export type SessionCommand =
  // Conversation: all three reach the service as the same kind of message.
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
  | { type: 'tick' }
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

type QuickActions = SessionState['quickActions']

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
  // Hints about the current song. Each names the recommendation it is about.
  | {
      kind: 'quick_actions_after'
      recommendationId: string
      reaction: 'liked' | 'saved'
    }
  | { kind: 'playlist_suggestions'; recommendationId: string }
)

export type CommandPlan = {
  /** Applied at once, without waiting for the service. */
  actions: WorkspaceAction[]
  /** Asked of the service. Its answer is applied when it arrives. */
  question?: ServiceQuestion
}

export function turnContext(session: SessionState): TurnContext {
  const current =
    (session.currentRecommendationId &&
      session.recommendations[session.currentRecommendationId]) ||
    null
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
    intent: session.intent,
    currentSongId: current?.songId ?? null,
    playedSongIds,
    recommendationsSinceIntentChange,
  }
}

const NOTHING: CommandPlan = { actions: [] }

const local = (...actions: WorkspaceAction[]): CommandPlan => ({ actions })

export function planCommand(
  workspace: WorkspaceState,
  command: SessionCommand,
): CommandPlan {
  const session = activeSession(workspace)
  const current =
    (session.currentRecommendationId &&
      session.recommendations[session.currentRecommendationId]) ||
    null
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
    text.trim() ? send({ kind: 'message', text: text.trim() }) : NOTHING

  switch (command.type) {
    case 'send_message':
      return say(command.text)

    case 'select_starter': {
      const starter = workspace.starters.find(
        (candidate) => candidate.id === command.starterId,
      )
      return starter ? say(starter.phrase) : NOTHING
    }

    case 'select_quick_action': {
      const action = session.quickActions.find(
        (candidate) => candidate.id === command.actionId,
      )
      return action ? say(action.label) : NOTHING
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
      return send({
        kind: 'refine',
        dimension: command.dimension,
        valueId: command.valueId,
      })
    }

    case 'toggle_play':
      return local({ type: 'play_toggled' })

    case 'tick': {
      if (!current || !session.playback.playing || session.overlay) {
        return NOTHING
      }
      // The song ran out: move on, exactly as pressing Next would.
      if (session.playback.positionSeconds + 1 >= current.durationSeconds) {
        return send({ kind: 'next' })
      }
      return local({ type: 'playback_ticked', seconds: 1 })
    }

    case 'next':
      return current ? send({ kind: 'next' }) : NOTHING

    case 'toggle_why':
      return local({ type: 'why_toggled' })

    case 'toggle_like': {
      if (!current) return NOTHING
      const liked = !current.liked
      return {
        actions: [{ type: 'liked_set', liked }],
        question: liked
          ? {
              ...asking,
              kind: 'quick_actions_after',
              recommendationId: current.id,
              reaction: 'liked',
            }
          : undefined,
      }
    }

    case 'not_for_me':
      return current ? send({ kind: 'not_for_me' }) : NOTHING

    case 'replay':
      return local({
        type: 'recommendation_replayed',
        recommendationId: command.recommendationId,
      })

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
      return local({ type: 'playlist_created' })

    case 'confirm_playlists': {
      const { overlay } = session
      if (
        overlay?.type !== 'playlist_picker' ||
        overlay.selectedPlaylistIds.length === 0 ||
        !current
      ) {
        return NOTHING
      }
      return {
        actions: [{ type: 'playlists_saved' }],
        question: {
          ...asking,
          kind: 'quick_actions_after',
          recommendationId: current.id,
          reaction: 'saved',
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
              quickActions: await hint<QuickActions | undefined>(
                service.quickActionsAfter('liked'),
                undefined,
              ),
              echo: response.echo,
            },
          ]
      }
    }

    case 'quick_actions_after':
      return [
        {
          type: 'quick_actions_offered',
          recommendationId: question.recommendationId,
          quickActions: await service.quickActionsAfter(question.reaction),
        },
      ]

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
  let actions: SessionAction[]
  try {
    actions = await answer(service, question)
  } catch {
    actions = question.kind === 'turn' ? [{ type: 'request_failed' }] : []
  }
  return { type: 'answer_received', sessionId: question.sessionId, actions }
}
