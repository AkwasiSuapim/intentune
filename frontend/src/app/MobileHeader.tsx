import { MenuIcon, PlusIcon } from '../components/icons.tsx'
import styles from './MobileHeader.module.css'

type MobileHeaderProps = {
  title: string
  /** Left out where the session navigation is already on screen. */
  onOpenSessions?: () => void
  onNewSession?: () => void
  /** Whether the sessions button is offered at all. */
  showSessionsButton?: boolean
}

function MobileHeader({
  title,
  onOpenSessions,
  onNewSession,
  showSessionsButton = true,
}: MobileHeaderProps) {
  return (
    <header className={styles.header}>
      {showSessionsButton ? (
        <button
          type="button"
          className={styles.iconButton}
          aria-label="Open listening sessions"
          onClick={onOpenSessions}
        >
          <MenuIcon size={22} />
        </button>
      ) : (
        // Keeps the title centred when the button is not shown.
        <span className={styles.spacer} aria-hidden="true" />
      )}
      <div className={styles.titleSlot}>
        <h1 className={styles.title}>{title}</h1>
      </div>
      <button
        type="button"
        className={styles.iconButton}
        aria-label="New listening session"
        onClick={onNewSession}
      >
        <PlusIcon size={22} strokeWidth="1.8" />
      </button>
    </header>
  )
}

export default MobileHeader
