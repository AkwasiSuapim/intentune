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
  'starters' | 'refineOptions'
> & {
  sessions: Record<string, SessionState>
  /** Session ids in the order the drawer lists them. */
  sessionOrder: string[]
  activeSessionId: string
  playlists: Playlist[]
  /** Sessions and playlists created so far, used to give new ones unique ids. */
  createdCount: number
}

export type WorkspaceAction =
  | SessionAction
  | { type: 'session_created' }
  | { type: 'session_opened'; sessionId: string }
  | { type: 'playlist_created' }

export function activeSession(workspace: WorkspaceState): SessionState {
  return workspace.sessions[workspace.activeSessionId]
}

/** Opens the workspace on a new session, with the seeded ones in the drawer. */
export function createWorkspace(seed: WorkspaceSeed): WorkspaceState {
  const fresh = createSession('session-1')

  return {
    starters: seed.starters,
    refineOptions: seed.refineOptions,
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
    playlists: workspace.playlists,
    sessions: workspace.sessionOrder.map((id) => {
      const { title, intent } = workspace.sessions[id]
      return { id, title, intent }
    }),
  }
}

function isUntouched(session: SessionState) {
  return session.events.length === 0 && session.intent === null
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

function createPlaylist(workspace: WorkspaceState): WorkspaceState {
  const session = activeSession(workspace)
  if (session.overlay?.type !== 'playlist_picker') return workspace

  const base =
    session.title === NEW_SESSION_TITLE ? 'New playlist' : session.title
  const taken = new Set(workspace.playlists.map((playlist) => playlist.name))
  let name = base
  for (let copy = 2; taken.has(name); copy++) name = `${base} ${copy}`

  const createdCount = workspace.createdCount + 1
  const playlist: Playlist = { id: `playlist-${createdCount}`, name }

  // Creating a playlist from the picker is itself the user choosing it.
  return {
    ...workspace,
    createdCount,
    playlists: [...workspace.playlists, playlist],
    sessions: {
      ...workspace.sessions,
      [session.id]: sessionReducer(session, {
        type: 'playlist_toggled',
        playlistId: playlist.id,
      }),
    },
  }
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
      return createPlaylist(workspace)
  }
}
