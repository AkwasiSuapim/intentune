import { WaveformIcon } from '../components/icons.tsx'
import styles from './WorkspaceStatus.module.css'

type WorkspaceStatusProps = {
  /**
   * `loading` on first opening, `retrying` after a failed load, and
   * `failed` when the listening sessions could not be loaded.
   */
  status: 'loading' | 'retrying' | 'failed'
  onRetry?: () => void
}

const MESSAGES = {
  loading: 'Loading your sessions…',
  retrying: 'Loading your sessions…',
  failed: 'Couldn’t load your sessions.',
}

// What the app shows before there is a session to show: while the listening
// sessions load, and if they cannot be loaded.
function WorkspaceStatus({ status, onRetry }: WorkspaceStatusProps) {
  const failed = status === 'failed'

  return (
    <main className={styles.screen} aria-busy={!failed} data-status={status}>
      <h1 className={styles.brand}>
        <WaveformIcon className={styles.brandGlyph} size={22} strokeWidth="2" />
        <span className={styles.wordmark}>intentune</span>
      </h1>
      {/* One live region for every state, so each change is read out. */}
      <p className={styles.message} role="status">
        {MESSAGES[status]}
      </p>
      {/* Stays while a retry loads, so keyboard focus is not lost. */}
      {status !== 'loading' && (
        <button
          type="button"
          className={styles.retry}
          aria-disabled={!failed || undefined}
          onClick={failed ? onRetry : undefined}
        >
          Try again
        </button>
      )}
    </main>
  )
}

export default WorkspaceStatus
