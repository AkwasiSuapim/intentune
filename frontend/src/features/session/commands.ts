// What the user can ask of a session, and how each request becomes state
// changes. `planCommand` is pure: it reads the workspace, consults the service
// where a backend would be consulted, and returns the actions to apply.
import type {
  SessionService,
  TurnContext,
  TurnRequest,
} from './sessionService.ts'
import { activeSession } from './workspaceReducer.ts'
import type { WorkspaceAction, WorkspaceState } from './workspaceReducer.ts'
import type { IntentDimension, RefineTab, SessionState } from './types.ts'

export type SessionCommand =
  // Conversation: all three reach the service as the same kind of message.
  | { type: 'send_message'; text: string }
  | { type: 'select_starter'; starterId: string }
  | { type: 'select_quick_action'; actionId: string }
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

export function planCommand(
  workspace: WorkspaceState,
  command: SessionCommand,
  service: SessionService,
): WorkspaceAction[] {
  const session = activeSession(workspace)
  const context = turnContext(session)
  const current =
    (session.currentRecommendationId &&
      session.recommendations[session.currentRecommendationId]) ||
    null

  const ask = (request: TurnRequest): WorkspaceAction[] => {
    const response = service.respond(context, request)
    switch (response.kind) {
      case 'turn':
        return [{ type: 'turn_applied', turn: response.turn }]
      case 'save_requested':
        return [
          {
            type: 'playlist_picker_opened',
            suggestedPlaylistIds: service.suggestPlaylists(
              context,
              workspace.playlists,
            ),
            echo: response.echo,
          },
        ]
      case 'liked':
        return [
          {
            type: 'liked_set',
            liked: true,
            quickActions: service.quickActionsAfter('liked'),
            echo: response.echo,
          },
        ]
    }
  }
  const say = (text: string) =>
    text.trim() ? ask({ kind: 'message', text: text.trim() }) : []

  switch (command.type) {
    case 'send_message':
      return say(command.text)

    case 'select_starter': {
      const starter = workspace.starters.find(
        (candidate) => candidate.id === command.starterId,
      )
      return starter ? say(starter.phrase) : []
    }

    case 'select_quick_action': {
      const action = session.quickActions.find(
        (candidate) => candidate.id === command.actionId,
      )
      return action ? say(action.label) : []
    }

    case 'open_refine':
      return [{ type: 'refine_opened', tab: session.refine?.tab ?? 'energy' }]

    case 'toggle_refine_tab':
      return session.refine?.tab === command.tab
        ? [{ type: 'refine_closed' }]
        : [{ type: 'refine_opened', tab: command.tab }]

    case 'change_refine_tab':
      return [{ type: 'refine_opened', tab: command.tab }]

    case 'close_refine':
      return [{ type: 'refine_closed' }]

    case 'refine': {
      const { intent } = session
      if (!intent || intent[command.dimension].id === command.valueId) return []
      return ask({
        kind: 'refine',
        dimension: command.dimension,
        valueId: command.valueId,
      })
    }

    case 'toggle_play':
      return [{ type: 'play_toggled' }]

    case 'tick': {
      if (!current || !session.playback.playing || session.overlay) return []
      // The song ran out: move on, exactly as pressing Next would.
      if (session.playback.positionSeconds + 1 >= current.durationSeconds) {
        return ask({ kind: 'next' })
      }
      return [{ type: 'playback_ticked', seconds: 1 }]
    }

    case 'next':
      return current ? ask({ kind: 'next' }) : []

    case 'toggle_why':
      return [{ type: 'why_toggled' }]

    case 'toggle_like': {
      if (!current) return []
      const liked = !current.liked
      return [
        {
          type: 'liked_set',
          liked,
          quickActions: liked ? service.quickActionsAfter('liked') : undefined,
        },
      ]
    }

    case 'not_for_me':
      return current ? ask({ kind: 'not_for_me' }) : []

    case 'replay':
      return [
        {
          type: 'recommendation_replayed',
          recommendationId: command.recommendationId,
        },
      ]

    case 'open_playlist_picker':
      if (!current) return []
      return [
        {
          type: 'playlist_picker_opened',
          suggestedPlaylistIds: service.suggestPlaylists(
            context,
            workspace.playlists,
          ),
        },
      ]

    case 'toggle_playlist':
      return [{ type: 'playlist_toggled', playlistId: command.playlistId }]

    case 'create_playlist':
      return [{ type: 'playlist_created' }]

    case 'confirm_playlists':
      return [
        {
          type: 'playlists_saved',
          quickActions: service.quickActionsAfter('saved'),
        },
      ]

    case 'close_playlist_picker':
      return [{ type: 'playlist_picker_closed' }]

    case 'open_drawer':
      return [{ type: 'drawer_opened' }]

    case 'close_drawer':
      return [{ type: 'drawer_closed' }]

    case 'new_session':
      return [{ type: 'session_created' }]

    case 'open_session':
      return [{ type: 'session_opened', sessionId: command.sessionId }]
  }
}
