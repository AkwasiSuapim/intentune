import { useEffect, useEffectEvent, useReducer } from 'react'
import { planCommand } from './commands.ts'
import type { SessionCommand } from './commands.ts'
import type { SessionService } from './sessionService.ts'
import {
  activeSession,
  createWorkspace,
  selectEnvironment,
  workspaceReducer,
} from './workspaceReducer.ts'

const TICK_MS = 1000

// Holds the listening sessions and turns user commands into state changes.
// State resets on reload: nothing is persisted.
export function useListeningSessions(service: SessionService) {
  const [workspace, dispatch] = useReducer(workspaceReducer, service, (seeded) =>
    createWorkspace(seeded.loadWorkspace()),
  )
  const session = activeSession(workspace)

  function run(command: SessionCommand) {
    for (const action of planCommand(workspace, command, service)) {
      dispatch(action)
    }
  }

  // Simulated playback clock: there is no audio, only a position that advances.
  const ticking =
    session.playback.playing &&
    session.currentRecommendationId !== null &&
    session.overlay === null
  const onTick = useEffectEvent(() => run({ type: 'tick' }))

  useEffect(() => {
    if (!ticking) return
    const timer = window.setInterval(onTick, TICK_MS)
    return () => window.clearInterval(timer)
  }, [ticking])

  return { session, environment: selectEnvironment(workspace), run }
}
