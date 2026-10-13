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
  onClose?: () => void
  onNewSession?: () => void
  onSelectSession?: (id: string) => void
  onSelectPlaylist?: (id: string) => void
}

// Slide-over navigation for listening sessions. Expects a positioned ancestor.
function SessionDrawer({
  sessions,
  playlists,
  onClose,
  onNewSession,
  onSelectSession,
  onSelectPlaylist,
}: SessionDrawerProps) {
  return (
    <div className={styles.layer}>
      <button
        type="button"
        className={styles.scrim}
        aria-label="Close menu"
        tabIndex={-1}
        onClick={onClose}
      />
      <nav
        className={styles.drawer}
        aria-label="Listening sessions and playlists"
      >
        <div className={styles.head}>
          <span className={styles.brand}>
            <WaveformIcon className={styles.brandGlyph} size={22} strokeWidth="2" />
            <span className={styles.wordmark}>intentune</span>
          </span>
          <button
            type="button"
            className={styles.close}
            aria-label="Close menu"
            onClick={onClose}
          >
            <CloseIcon size={18} />
          </button>
        </div>

        <button
          type="button"
          className={styles.newSession}
          onClick={onNewSession}
        >
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
                <span className={styles.sessionSubtitle}>
                  {session.subtitle}
                </span>
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
    </div>
  )
}

export default SessionDrawer
