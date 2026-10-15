import { CloseIcon } from './icons.tsx'
import styles from './TurnStatus.module.css'

type TurnStatusProps = {
  /** `pending` while Intentune is answering; `failed` once it could not. */
  status: 'pending' | 'failed'
  onRetry?: () => void
}

// Stands where an answer will appear: a quiet note while it is on its way,
// and a way to try again if it never arrives.
function TurnStatus({ status, onRetry }: TurnStatusProps) {
  if (status === 'pending') {
    return (
      // Can hold keyboard focus while waiting, when the control used is gone.
      <div
        className={styles.status}
        data-status="pending"
        tabIndex={-1}
        data-focus-key="turn-status"
      >
        <span className={styles.icon} aria-hidden="true">
          <span className={styles.dots}>
            <span />
            <span />
            <span />
          </span>
        </span>
        <span className={styles.body}>
          <span className={styles.label}>Working on it…</span>
        </span>
      </div>
    )
  }
  return (
    <div className={styles.status} data-status="failed">
      <span className={styles.notice}>
        <span className={styles.icon} data-tone="failed" aria-hidden="true">
          <CloseIcon size={10} strokeWidth="2.8" />
        </span>
        <span className={styles.label}>That didn’t go through.</span>
      </span>
      <button
        type="button"
        className={styles.retry}
        data-focus-key="retry"
        onClick={onRetry}
      >
        Try again
      </button>
    </div>
  )
}

export default TurnStatus
