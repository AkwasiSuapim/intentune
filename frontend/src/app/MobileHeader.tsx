import styles from './MobileHeader.module.css'

type MobileHeaderProps = {
  title: string
  onOpenSessions?: () => void
  onNewSession?: () => void
}

function MobileHeader({
  title,
  onOpenSessions,
  onNewSession,
}: MobileHeaderProps) {
  return (
    <header className={styles.header}>
      <button
        type="button"
        className={styles.iconButton}
        aria-label="Open listening sessions"
        onClick={onOpenSessions}
      >
        <svg
          aria-hidden="true"
          width="22"
          height="22"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        >
          <path d="M4 7h16M4 12h11M4 17h16" />
        </svg>
      </button>
      <div className={styles.titleSlot}>
        <h1 className={styles.title}>{title}</h1>
      </div>
      <button
        type="button"
        className={styles.iconButton}
        aria-label="New listening session"
        onClick={onNewSession}
      >
        <svg
          aria-hidden="true"
          width="22"
          height="22"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        >
          <path d="M12 5v14M5 12h14" />
        </svg>
      </button>
    </header>
  )
}

export default MobileHeader
