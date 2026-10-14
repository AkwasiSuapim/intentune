import { useState } from 'react'
import AppShell from '../../app/AppShell.tsx'
import MobileHeader from '../../app/MobileHeader.tsx'
import Composer from '../../components/Composer.tsx'
import SessionDrawer from '../../components/SessionDrawer.tsx'
import SessionTimeline from '../../components/SessionTimeline.tsx'
import BlockRenderer from './BlockRenderer.tsx'
import { composeSession } from './composeSession.ts'
import type { SessionEnvironment, SessionState } from './types.ts'

type SessionViewProps = {
  state: SessionState
  environment: SessionEnvironment
}

// Places a composed session into the stable shell. Which blocks appear is
// decided by `composeSession`; this component only lays the regions out.
function SessionView({ state, environment }: SessionViewProps) {
  const view = composeSession(state, environment)
  // The draft is plain input state for now; it joins the session state when
  // sending a message starts to mean something.
  const [draft, setDraft] = useState('')

  const content = view.content.map((block) => (
    <BlockRenderer key={block.id} block={block} />
  ))

  return (
    <AppShell
      accent={view.accent}
      header={<MobileHeader title={view.title} />}
      intentSummary={
        view.intentSummary && <BlockRenderer block={view.intentSummary} />
      }
      contextualControls={
        view.contextualControl && (
          <BlockRenderer block={view.contextualControl} />
        )
      }
      composer={
        <Composer
          value={draft}
          onValueChange={setDraft}
          placeholder={view.composerPlaceholder}
        />
      }
      overlay={
        view.drawer ? (
          <SessionDrawer
            sessions={view.drawer.sessions}
            playlists={view.drawer.playlists}
          />
        ) : (
          view.overlay && <BlockRenderer block={view.overlay} />
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
