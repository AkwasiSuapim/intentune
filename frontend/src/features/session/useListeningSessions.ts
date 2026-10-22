import { useEffect, useEffectEvent, useReducer } from 'react'
import { ask, planCommand } from './commands.ts'
import { useAudioPlayback } from './useAudioPlayback.ts'
import type { SessionCommand } from './commands.ts'
import type { SessionService, WorkspaceSeed } from './sessionService.ts'
import {
  activeSession,
  createWorkspace,
  selectEnvironment,
  workspaceReducer,
} from './workspaceReducer.ts'
import type { WorkspaceAction, WorkspaceState } from './workspaceReducer.ts'

const TICK_MS = 1000

type Loaded =
  /** `attempt` counts tries, so trying again starts a fresh load. */
  | { status: 'loading' | 'failed'; attempt: number }
  | { status: 'ready'; workspace: WorkspaceState }

type LoadedAction =
  | { type: 'workspace_loaded'; seed: WorkspaceSeed }
  | { type: 'workspace_failed' }
  | { type: 'workspace_retried' }
  | WorkspaceAction

function loadedReducer(state: Loaded, action: LoadedAction): Loaded {
  switch (action.type) {
    case 'workspace_loaded':
      return { status: 'ready', workspace: createWorkspace(action.seed) }
    case 'workspace_failed':
      return state.status === 'loading' ? { ...state, status: 'failed' } : state
    case 'workspace_retried':
      return state.status === 'failed'
        ? { status: 'loading', attempt: state.attempt + 1 }
        : state
    default:
      if (state.status !== 'ready') return state
      return { ...state, workspace: workspaceReducer(state.workspace, action) }
  }
}

// Holds the listening sessions and turns user commands into state changes.
// The workspace arrives from the service; until it does, there is only a
// loading (or failed) state. State resets on reload: nothing is persisted.
export function useListeningSessions(service: SessionService) {
  const [loaded, dispatch] = useReducer(loadedReducer, {
    status: 'loading',
    attempt: 1,
  })
  const workspace = loaded.status === 'ready' ? loaded.workspace : null
  const session = workspace && activeSession(workspace)

  const loadingAttempt = loaded.status === 'loading' ? loaded.attempt : null
  useEffect(() => {
    if (loadingAttempt === null) return
    // An answer for a load that has since been abandoned is ignored.
    let wanted = true
    service.loadWorkspace().then(
      (seed) => wanted && dispatch({ type: 'workspace_loaded', seed }),
      () => wanted && dispatch({ type: 'workspace_failed' }),
    )
    return () => {
      wanted = false
    }
  }, [service, loadingAttempt])

  function run(command: SessionCommand) {
    if (!workspace) return
    const { actions, question } = planCommand(workspace, command)
    for (const action of actions) dispatch(action)
    if (question) void ask(service, question).then(dispatch)
  }

  // Real audio, when the recommendation has some, is the playback authority.
  useAudioPlayback(session, run)

  // Simulated playback clock, only for a recommendation with no audio behind
  // it (the mock's): a position that advances.
  const current = session?.currentRecommendationId
    ? session.recommendations[session.currentRecommendationId]
    : undefined
  const ticking =
    !!session?.playback.playing &&
    !!current &&
    !current.audioUrl &&
    session.overlay === null
  const onTick = useEffectEvent(() => run({ type: 'tick' }))

  useEffect(() => {
    if (!ticking) return
    const timer = window.setInterval(onTick, TICK_MS)
    return () => window.clearInterval(timer)
  }, [ticking])

  if (loaded.status !== 'ready' || !session) {
    const status =
      loaded.status === 'failed'
        ? 'failed'
        : loaded.status === 'loading' && loaded.attempt > 1
          ? 'retrying'
          : 'loading'
    return {
      status,
      retry: () => dispatch({ type: 'workspace_retried' }),
    } as const
  }
  return {
    status: 'ready',
    session,
    environment: selectEnvironment(loaded.workspace),
    run,
  } as const
}
