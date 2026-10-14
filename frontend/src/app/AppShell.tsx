import { useEffect, useEffectEvent, useRef } from 'react'
import type { ReactNode } from 'react'
import styles from './AppShell.module.css'

export type AccentContext = 'emotional' | 'focused' | 'calm' | 'driven'

/** From this width the session navigation stays on screen as a rail. */
export const RAIL_MEDIA_QUERY = '(min-width: 1024px)'

type AppShellProps = {
  header: ReactNode
  /** Persistent session navigation, shown beside the session on wide screens. */
  navigation?: ReactNode
  /** Stable slot under the header for the current intent. */
  intentSummary?: ReactNode
  /** The session content: a timeline, or the Tune in prompt. */
  children?: ReactNode
  /** One contextual control above the composer, e.g. the TuneBar. */
  contextualControls?: ReactNode
  composer: ReactNode
  /** A sheet or drawer layered over the whole shell. */
  overlay?: ReactNode
  /**
   * True while the overlay is open and must hold the user's attention. The
   * rest of the shell is then inert, focus moves into the overlay, and
   * Escape asks to dismiss it.
   */
  overlayModal?: boolean
  onDismissOverlay?: () => void
  accent?: AccentContext
}

function AppShell({
  header,
  navigation,
  intentSummary,
  children,
  contextualControls,
  composer,
  overlay,
  overlayModal = false,
  onDismissOverlay,
  accent = 'emotional',
}: AppShellProps) {
  const overlayRef = useRef<HTMLDivElement>(null)
  const dismiss = useEffectEvent(() => onDismissOverlay?.())

  useEffect(() => {
    if (!overlayModal) return

    // Move focus into the overlay, and hand it back to where it was on close.
    const opener = document.activeElement
    overlayRef.current
      ?.querySelector<HTMLElement>('[role="dialog"], nav')
      ?.focus({ preventScroll: true })

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') dismiss()
    }
    document.addEventListener('keydown', onKeyDown)

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      if (opener instanceof HTMLElement && opener.isConnected) {
        opener.focus({ preventScroll: true })
      }
    }
  }, [overlayModal])

  return (
    <div
      className={styles.shell}
      data-accent={accent}
      data-railed={navigation ? '' : undefined}
    >
      {navigation && (
        <div className={styles.rail} inert={overlayModal}>
          {navigation}
        </div>
      )}
      <div className={styles.column} inert={overlayModal}>
        {header}
        {intentSummary}
        <main className={styles.content} aria-label="Listening session">
          {children}
        </main>
        <footer className={styles.dock}>
          {contextualControls}
          {composer}
        </footer>
      </div>
      <div ref={overlayRef} className={styles.overlay}>
        {overlay}
      </div>
    </div>
  )
}

export default AppShell
