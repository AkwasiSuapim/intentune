// State shared across listening sessions: which sessions exist, which one is
// open, and the user's playlists. Session-level actions go to the open session.
import {
  NEW_SESSION_TITLE,
  createSession,
  isSessionAction,
  sessionReducer,
} from './sessionReducer.ts'
import type { SessionAction } from './sessionReducer.ts'
import type { WorkspaceSeed } from './sessionService.ts'
import type {
  Playlist,
  SessionEnvironment,
  SessionState,
} from './types.ts'

export type WorkspaceState = Pick<
  SessionEnvironment,
  'starters' | 'refineOptions' | 'unavailableDimensions' | 'libraryReady'
> & {
  sessions: Record<string, SessionState>
  /** Session ids in the order the drawer lists them. */
  sessionOrder: string[]
  activeSessionId: string
  playlists: Playlist[]
  /** Sessions created so far, used to give new ones unique ids. */
  createdCount: number
}

export type WorkspaceAction =
  | SessionAction
  /**
   * What the service answered, for the session that asked, even if another
   * session has been opened since.
   */
  | { type: 'answer_received'; sessionId: string; actions: SessionAction[] }
  | { type: 'session_created' }
  | { type: 'session_opened'; sessionId: string }
  /** The service created a playlist from the picker of this session. */
  | { type: 'playlist_created'; sessionId: string; playlist: Playlist }

export function activeSession(workspace: WorkspaceState): SessionState {
  return workspace.sessions[workspace.activeSessionId]
}

/** Opens the workspace on a new session, with the seeded ones in the drawer. */
export function createWorkspace(seed: WorkspaceSeed): WorkspaceState {
  const fresh = createSession('session-1')

  return {
    starters: seed.starters,
    refineOptions: seed.refineOptions,
    unavailableDimensions: seed.unavailableDimensions ?? [],
    libraryReady: seed.libraryReady ?? true,
    sessions: Object.fromEntries(
      [fresh, ...seed.sessions].map((session) => [session.id, session]),
    ),
    sessionOrder: [fresh.id, ...seed.sessions.map((session) => session.id)],
    activeSessionId: fresh.id,
    playlists: seed.playlists,
    createdCount: 1,
  }
}

/** The data around the open session that composing its view needs. */
export function selectEnvironment(
  workspace: WorkspaceState,
): SessionEnvironment {
  return {
    starters: workspace.starters,
    refineOptions: workspace.refineOptions,
    unavailableDimensions: workspace.unavailableDimensions,
    libraryReady: workspace.libraryReady,
    playlists: workspace.playlists,
    sessions: workspace.sessionOrder.map((id) => {
      const { title, intent } = workspace.sessions[id]
      return { id, title, intent }
    }),
  }
}

function isUntouched(session: SessionState) {
  return (
    session.events.length === 0 &&
    session.intent === null &&
    session.openRequest === null
  )
}

/** Leaves the open session: closes its overlay, and drops it if never used. */
function leaveActive(workspace: WorkspaceState): WorkspaceState {
  const leaving = activeSession(workspace)
  const sessions = { ...workspace.sessions }

  if (isUntouched(leaving)) {
    delete sessions[leaving.id]
    return {
      ...workspace,
      sessions,
      sessionOrder: workspace.sessionOrder.filter((id) => id !== leaving.id),
    }
  }
  sessions[leaving.id] = { ...leaving, overlay: null }
  return { ...workspace, sessions }
}

/** The name a playlist created from the open session's picker gets: the session's, made unique. */
export function newPlaylistName(workspace: WorkspaceState): string {
  const session = activeSession(workspace)
  const base =
    session.title === NEW_SESSION_TITLE ? 'New playlist' : session.title
  const taken = new Set(workspace.playlists.map((playlist) => playlist.name))
  let name = base
  for (let copy = 2; taken.has(name); copy++) name = `${base} ${copy}`
  return name
}

function addPlaylist(
  workspace: WorkspaceState,
  sessionId: string,
  playlist: Playlist,
): WorkspaceState {
  if (workspace.playlists.some((existing) => existing.id === playlist.id)) {
    return workspace
  }
  const session = workspace.sessions[sessionId]
  const sessions = { ...workspace.sessions }
  // Creating a playlist from the picker is itself the user choosing it,
  // if the picker it was created from is still open.
  if (session?.overlay?.type === 'playlist_picker') {
    sessions[session.id] = sessionReducer(session, {
      type: 'playlist_toggled',
      playlistId: playlist.id,
    })
  }
  return { ...workspace, playlists: [...workspace.playlists, playlist], sessions }
}

export function workspaceReducer(
  workspace: WorkspaceState,
  action: WorkspaceAction,
): WorkspaceState {
  if (isSessionAction(action)) {
    const session = activeSession(workspace)
    const next = sessionReducer(session, action)
    if (next === session) return workspace
    return {
      ...workspace,
      sessions: { ...workspace.sessions, [session.id]: next },
    }
  }

  switch (action.type) {
    case 'answer_received': {
      const target = workspace.sessions[action.sessionId]
      if (!target) return workspace
      const next = action.actions.reduce(sessionReducer, target)
      if (next === target) return workspace
      return {
        ...workspace,
        sessions: { ...workspace.sessions, [target.id]: next },
      }
    }

    case 'session_created': {
      // An unused new session is already what was asked for.
      if (isUntouched(activeSession(workspace))) {
        return workspaceReducer(workspace, { type: 'drawer_closed' })
      }
      const left = leaveActive(workspace)
      const createdCount = left.createdCount + 1
      const fresh = createSession(`session-${createdCount}`)
      return {
        ...left,
        createdCount,
        sessions: { ...left.sessions, [fresh.id]: fresh },
        sessionOrder: [fresh.id, ...left.sessionOrder],
        activeSessionId: fresh.id,
      }
    }

    case 'session_opened': {
      const target = workspace.sessions[action.sessionId]
      if (!target || target.id === workspace.activeSessionId) {
        return workspaceReducer(workspace, { type: 'drawer_closed' })
      }
      const left = leaveActive(workspace)
      return {
        ...left,
        activeSessionId: target.id,
        sessions: {
          ...left.sessions,
          [target.id]: sessionReducer(
            { ...target, overlay: null },
            { type: 'session_resumed' },
          ),
        },
      }
    }

    case 'playlist_created':
      return addPlaylist(workspace, action.sessionId, action.playlist)
  }
}
