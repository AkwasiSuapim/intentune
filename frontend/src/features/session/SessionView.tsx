import { useState } from 'react'
import AppShell from '../../app/AppShell.tsx'
import MobileHeader from '../../app/MobileHeader.tsx'
import Composer from '../../components/Composer.tsx'
import SessionDrawer from '../../components/SessionDrawer.tsx'
import SessionTimeline from '../../components/SessionTimeline.tsx'
import BlockRenderer from './BlockRenderer.tsx'
import type { SessionCommand } from './commands.ts'
import { composeSession } from './composeSession.ts'
import type { SessionEnvironment, SessionState } from './types.ts'

type SessionViewProps = {
  state: SessionState
  environment: SessionEnvironment
  /** Left out for a static rendering: the controls then do nothing. */
  onCommand?: (command: SessionCommand) => void
}

// Places a composed session into the stable shell. Which blocks appear is
// decided by `composeSession`; this component only lays the regions out and
// reports what the user does.
function SessionView({ state, environment, onCommand }: SessionViewProps) {
  const view = composeSession(state, environment)
  // The unsent draft is input state of this view, not of the session.
  const [draft, setDraft] = useState('')

  function sendDraft() {
    if (!draft.trim()) return
    onCommand?.({ type: 'send_message', text: draft })
    setDraft('')
  }

  const content = view.content.map((block) => (
    <BlockRenderer key={block.id} block={block} onCommand={onCommand} />
  ))

  return (
    <AppShell
      accent={view.accent}
      header={
        <MobileHeader
          title={view.title}
          onOpenSessions={() => onCommand?.({ type: 'open_drawer' })}
          onNewSession={() => onCommand?.({ type: 'new_session' })}
        />
      }
      intentSummary={
        view.intentSummary && (
          <BlockRenderer block={view.intentSummary} onCommand={onCommand} />
        )
      }
      contextualControls={
        view.contextualControl && (
          <BlockRenderer block={view.contextualControl} onCommand={onCommand} />
        )
      }
      composer={
        <Composer
          value={draft}
          onValueChange={setDraft}
          onSubmit={sendDraft}
          placeholder={view.composerPlaceholder}
        />
      }
      overlay={
        view.drawer ? (
          <SessionDrawer
            sessions={view.drawer.sessions}
            playlists={view.drawer.playlists}
            onClose={() => onCommand?.({ type: 'close_drawer' })}
            onNewSession={() => onCommand?.({ type: 'new_session' })}
            onSelectSession={(sessionId) =>
              onCommand?.({ type: 'open_session', sessionId })
            }
          />
        ) : (
          view.overlay && (
            <BlockRenderer block={view.overlay} onCommand={onCommand} />
          )
        )
      }
    >
      {view.layout === 'prompt' ? (
        content
      ) : (
        <SessionTimeline>{content}</SessionTimeline>
      )}
    </AppShell>
  )
}

export default SessionView
