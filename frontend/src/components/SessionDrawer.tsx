import type { AnimationEvent } from 'react'
import PlaylistSwatch from './PlaylistSwatch.tsx'
import type { PlaylistTone } from './PlaylistSwatch.tsx'
import { CloseIcon, PlusIcon, WaveformIcon } from './icons.tsx'
import styles from './SessionDrawer.module.css'

export type DrawerSession = {
  id: string
  title: string
  /** The session's current intent in words, or a note that none is set yet. */
  subtitle: string
  active?: boolean
}

export type DrawerPlaylist = {
  id: string
  name: string
  tone?: PlaylistTone
}

type SessionDrawerProps = {
  sessions: DrawerSession[]
  playlists: DrawerPlaylist[]
  /**
   * `overlay` slides over the screen behind a scrim and can be closed.
   * `rail` is the same navigation standing permanently beside the session.
   */
  variant?: 'overlay' | 'rail'
  /** Plays the exit: the drawer slides away, then `onExited` is called. */
  leaving?: boolean
  onExited?: () => void
  onClose?: () => void
  onNewSession?: () => void
  onSelectSession?: (id: string) => void
  onSelectPlaylist?: (id: string) => void
}

// Navigation between listening sessions. The overlay expects a positioned ancestor.
function SessionDrawer({
  sessions,
  playlists,
  variant = 'overlay',
  leaving = false,
  onExited,
  onClose,
  onNewSession,
  onSelectSession,
  onSelectPlaylist,
}: SessionDrawerProps) {
  const overlay = variant === 'overlay'

  function handleAnimationEnd(event: AnimationEvent) {
    // Only the drawer's own exit counts, not animations inside it.
    if (leaving && event.target === event.currentTarget) onExited?.()
  }

  const navigation = (
    <nav
      className={overlay ? styles.drawer : styles.rail}
      aria-label="Listening sessions and playlists"
      tabIndex={overlay ? -1 : undefined}
      onAnimationEnd={overlay ? handleAnimationEnd : undefined}
    >
      <div className={styles.head}>
        <span className={styles.brand}>
          <WaveformIcon className={styles.brandGlyph} size={22} strokeWidth="2" />
          <span className={styles.wordmark}>intentune</span>
        </span>
        {overlay && (
          <button
            type="button"
            className={styles.close}
            aria-label="Close menu"
            onClick={onClose}
          >
            <CloseIcon size={18} />
          </button>
        )}
      </div>

      <button type="button" className={styles.newSession} onClick={onNewSession}>
        <PlusIcon size={18} />
        New session
      </button>

      <span className={styles.sectionLabel}>Listening sessions</span>
      <div className={styles.sessions}>
        {sessions.map((session) => (
          <button
            key={session.id}
            type="button"
            className={styles.session}
            aria-current={session.active ? 'page' : undefined}
            onClick={() => onSelectSession?.(session.id)}
          >
            <span className={styles.sessionText}>
              <span className={styles.sessionTitle}>{session.title}</span>
              <span className={styles.sessionSubtitle}>{session.subtitle}</span>
            </span>
            {session.active && (
              <span className={styles.playingMark} aria-hidden="true">
                <span />
                <span />
                <span />
              </span>
            )}
          </button>
        ))}
      </div>

      <span className={styles.sectionLabel}>Playlists</span>
      {playlists.map((playlist) => (
        <button
          key={playlist.id}
          type="button"
          className={styles.playlist}
          onClick={() => onSelectPlaylist?.(playlist.id)}
        >
          <PlaylistSwatch tone={playlist.tone} className={styles.swatch} />
          <span className={styles.playlistName}>{playlist.name}</span>
        </button>
      ))}
    </nav>
  )

  if (!overlay) return navigation

  return (
    <div className={styles.layer} data-leaving={leaving ? '' : undefined}>
      <button
        type="button"
        className={styles.scrim}
        aria-label="Close menu"
        tabIndex={-1}
        onClick={onClose}
      />
      {navigation}
    </div>
  )
}

export default SessionDrawer
