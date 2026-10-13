import type { ReactNode } from 'react'
import styles from './AppShell.module.css'

export type AccentContext = 'emotional' | 'focused' | 'calm' | 'driven'

type AppShellProps = {
  header: ReactNode
  /** Stable slot under the header for the current intent. */
  intentSummary?: ReactNode
  /** The session content: a timeline, or the Tune in prompt. */
  children?: ReactNode
  /** One contextual control above the composer, e.g. the TuneBar. */
  contextualControls?: ReactNode
  composer: ReactNode
  /** A sheet or drawer layered over the whole shell. */
  overlay?: ReactNode
  accent?: AccentContext
}

function AppShell({
  header,
  intentSummary,
  children,
  contextualControls,
  composer,
  overlay,
  accent = 'emotional',
}: AppShellProps) {
  return (
    <div className={styles.shell} data-accent={accent}>
      <div className={styles.column}>
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
      {overlay}
    </div>
  )
}

export default AppShell
