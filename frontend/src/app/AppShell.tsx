import type { ReactNode } from 'react'
import styles from './AppShell.module.css'

export type AccentContext = 'emotional' | 'focused' | 'calm' | 'driven'

type AppShellProps = {
  header: ReactNode
  composer: ReactNode
  children?: ReactNode
  accent?: AccentContext
}

function AppShell({
  header,
  composer,
  children,
  accent = 'emotional',
}: AppShellProps) {
  return (
    <div className={styles.shell} data-accent={accent}>
      <div className={styles.column}>
        {header}
        <main className={styles.content} aria-label="Listening session">
          {children}
        </main>
        <footer className={styles.dock}>{composer}</footer>
      </div>
    </div>
  )
}

export default AppShell
