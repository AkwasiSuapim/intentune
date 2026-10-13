import { MenuIcon, PlusIcon } from '../components/icons.tsx'
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
        <MenuIcon size={22} />
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
        <PlusIcon size={22} strokeWidth="1.8" />
      </button>
    </header>
  )
}

export default MobileHeader
