import WorkspaceStatus from '../../app/WorkspaceStatus.tsx'
import type { SessionService } from './sessionService.ts'
import SessionView from './SessionView.tsx'
import { useListeningSessions } from './useListeningSessions.ts'

type ListeningSessionsProps = {
  /** Answers the session's requests: a mock now, the backend later. */
  service: SessionService
}

// The interactive app: the open listening session, driven by user commands.
function ListeningSessions({ service }: ListeningSessionsProps) {
  const sessions = useListeningSessions(service)

  if (sessions.status !== 'ready') {
    return (
      <WorkspaceStatus status={sessions.status} onRetry={sessions.retry} />
    )
  }
  return (
    <SessionView
      state={sessions.session}
      environment={sessions.environment}
      onCommand={sessions.run}
    />
  )
}

export default ListeningSessions
