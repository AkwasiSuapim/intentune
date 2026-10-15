import { useEffect, useEffectEvent, useState } from 'react'
import AppShell, { RAIL_MEDIA_QUERY } from '../../app/AppShell.tsx'
import MobileHeader from '../../app/MobileHeader.tsx'
import { useFocusRescue } from '../../app/useFocusRescue.ts'
import { useLingering } from '../../app/useLingering.ts'
import { useMediaQuery } from '../../app/useMediaQuery.ts'
import Composer from '../../components/Composer.tsx'
import SessionDrawer from '../../components/SessionDrawer.tsx'
import SessionTimeline, {
  TimelineItem,
} from '../../components/SessionTimeline.tsx'
import { announceBlocks } from './announce.ts'
import BlockRenderer from './BlockRenderer.tsx'
import type { SessionBlock } from './blocks.ts'
import type { SessionCommand } from './commands.ts'
import { composeSession } from './composeSession.ts'
import type { SessionEnvironment, SessionState } from './types.ts'

type SessionViewProps = {
  state: SessionState
  environment: SessionEnvironment
  /** Left out for a static rendering: the controls then do nothing. */
  onCommand?: (command: SessionCommand) => void
}

/**
 * Where keyboard focus goes when the focused control is replaced and no
 * control with the same focus key takes its place.
 */
const FOCUS_SUCCESSORS: Record<string, string[]> = {
  starter: ['hero-play', 'turn-status'],
  // While an answer is on its way focus can wait on the note saying so,
  // then moves to what arrived: the new song, or the way to try again.
  'turn-status': ['retry', 'hero-play'],
  retry: ['turn-status', 'hero-play'],
  tune: ['refine-tab'],
  refine: ['tune'],
  'refine-tab': ['tune'],
  'refine-close': ['tune'],
  'quick-action-0': ['refine-tab', 'tune'],
  'quick-action-1': ['quick-action-0', 'refine-tab', 'tune'],
  history: ['hero-play'],
  'up-next': ['hero-play'],
}

/** A recommendation gets a new key when it turns from hero into history. */
function keyOf(block: SessionBlock) {
  return block.type === 'recommendation'
    ? `${block.id}:${block.variant}`
    : block.id
}

function entranceOf(block: SessionBlock) {
  if (block.type !== 'recommendation') return 'rise'
  return block.variant === 'hero' ? 'reveal' : 'settle'
}

// Places a composed session into the stable shell. Which blocks appear is
// decided by `composeSession`; this component lays the regions out, reports
// what the user does, and owns the view-only state around them.
function SessionView({ state, environment, onCommand }: SessionViewProps) {
  const view = composeSession(state, environment)
  const railed = useMediaQuery(RAIL_MEDIA_QUERY)
  useFocusRescue(FOCUS_SUCCESSORS)

  // The unsent draft is input state of this view, not of the session.
  const [draft, setDraft] = useState('')
  // Whatever is on screen when a session opens is already there; only what
  // arrives afterwards gets an entrance.
  const [presentAtOpen, setPresentAtOpen] = useState(
    () => new Set(view.content.map(keyOf)),
  )
  const [nowPlayingHidden, setNowPlayingHidden] = useState(false)
  const requestStatus = state.openRequest?.status ?? null
  // What the announcer last said, and how much of the session it had seen.
  const [news, setNews] = useState({
    sessionId: state.id,
    eventCount: state.events.length,
    requestStatus,
    text: '',
  })

  // Another session has been opened in this view: start its view state clean.
  // The view itself stays mounted so the drawer can finish sliding away.
  const [openSessionId, setOpenSessionId] = useState(state.id)
  if (openSessionId !== state.id) {
    setOpenSessionId(state.id)
    setDraft('')
    setPresentAtOpen(new Set(view.content.map(keyOf)))
    setNowPlayingHidden(false)
    setNews({
      sessionId: state.id,
      eventCount: state.events.length,
      requestStatus,
      text: `Opened ${view.title}.`,
    })
  } else if (
    news.eventCount !== state.events.length ||
    news.requestStatus !== requestStatus
  ) {
    // The stream grew, or a request failed: announce what arrived, in the
    // words shown on screen.
    const added = new Set(
      state.events.slice(news.eventCount).map((event) => event.id),
    )
    const failed = requestStatus === 'failed' && news.requestStatus !== 'failed'
    const arrived = view.content.filter(
      (block) =>
        added.has(block.id) || (failed && block.type === 'turn_status'),
    )
    // A new request clears the last news, so its answer is heard even if
    // it is worded the same.
    const sent = requestStatus === 'pending' && news.requestStatus !== 'pending'
    setNews({
      sessionId: state.id,
      eventCount: state.events.length,
      requestStatus,
      text: sent ? '' : announceBlocks(arrived) || news.text,
    })
  }

  // Overlays stay on screen long enough to animate out.
  const picker = useLingering(view.overlay)
  const drawer = useLingering(
    view.drawerOpen && !railed ? view.navigation : null,
  )
  const overlayOpen = view.overlay !== null || (view.drawerOpen && !railed)

  // Where the navigation is a standing rail there is no drawer to leave open.
  const closeStrandedDrawer = useEffectEvent(() =>
    onCommand?.({ type: 'close_drawer' }),
  )
  useEffect(() => {
    if (railed && view.drawerOpen) closeStrandedDrawer()
  }, [railed, view.drawerOpen])

  function sendDraft() {
    // While an answer is on its way the draft waits, rather than being lost.
    if (!draft.trim() || view.busy) return
    onCommand?.({ type: 'send_message', text: draft })
    setDraft('')
  }

  function dismissOverlay() {
    onCommand?.({
      type: view.overlay ? 'close_playlist_picker' : 'close_drawer',
    })
  }

  const navigationHandlers = {
    onNewSession: () => onCommand?.({ type: 'new_session' }),
    onSelectSession: (sessionId: string) =>
      onCommand?.({ type: 'open_session', sessionId }),
  }

  const content = view.content.map((block) => (
    <TimelineItem
      key={keyOf(block)}
      enter={presentAtOpen.has(keyOf(block)) ? undefined : entranceOf(block)}
    >
      <BlockRenderer block={block} onCommand={onCommand} />
    </TimelineItem>
  ))

  return (
    <AppShell
      accent={view.accent}
      announcement={news.text}
      header={
        <MobileHeader
          title={view.title}
          showSessionsButton={!railed}
          onOpenSessions={() => onCommand?.({ type: 'open_drawer' })}
          onNewSession={() => onCommand?.({ type: 'new_session' })}
        />
      }
      navigation={
        railed && (
          <SessionDrawer
            variant="rail"
            sessions={view.navigation.sessions}
            playlists={view.navigation.playlists}
            {...navigationHandlers}
          />
        )
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
          busy={view.busy}
          nowPlaying={view.nowPlaying}
          showNowPlaying={nowPlayingHidden}
          onTogglePlay={() => onCommand?.({ type: 'toggle_play' })}
        />
      }
      overlayModal={overlayOpen}
      onDismissOverlay={dismissOverlay}
      overlay={
        <>
          {picker.shown && (
            <BlockRenderer
              block={picker.shown}
              onCommand={onCommand}
              presence={{ leaving: picker.leaving, onExited: picker.finish }}
            />
          )}
          {drawer.shown && (
            <SessionDrawer
              sessions={drawer.shown.sessions}
              playlists={drawer.shown.playlists}
              leaving={drawer.leaving}
              onExited={drawer.finish}
              onClose={() => onCommand?.({ type: 'close_drawer' })}
              {...navigationHandlers}
            />
          )}
        </>
      }
    >
      {view.layout === 'prompt' ? (
        view.content.map((block) => (
          <BlockRenderer key={block.id} block={block} onCommand={onCommand} />
        ))
      ) : (
        <SessionTimeline
          key={state.id}
          newestKey={`${state.events.length}:${requestStatus ?? ''}`}
          nowPlayingKey={state.currentRecommendationId}
          onNowPlayingHiddenChange={setNowPlayingHidden}
        >
          {content}
        </SessionTimeline>
      )}
    </AppShell>
  )
}

export default SessionView
