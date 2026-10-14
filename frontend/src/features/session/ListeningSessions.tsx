import type { SessionService } from './sessionService.ts'
import SessionView from './SessionView.tsx'
import { useListeningSessions } from './useListeningSessions.ts'

type ListeningSessionsProps = {
  /** Answers the session's requests: a mock now, the backend later. */
  service: SessionService
}

// The interactive app: the open listening session, driven by user commands.
function ListeningSessions({ service }: ListeningSessionsProps) {
  const { session, environment, run } = useListeningSessions(service)

  return (
    <SessionView state={session} environment={environment} onCommand={run} />
  )
}

export default ListeningSessions
