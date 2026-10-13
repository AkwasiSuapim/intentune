import styles from './ComposerPlaceholder.module.css'

// Static stand-in that reserves the composer's place and proportions.
// The real Composer replaces it in F3.
function ComposerPlaceholder() {
  return (
    <div className={styles.composer} aria-hidden="true">
      <span className={styles.lead}>
        <svg
          width="22"
          height="22"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3 12c1.5 0 1.5-3 3-3s1.5 6 3 6 1.5-9 3-9 1.5 9 3 9 1.5-6 3-6 1.5 3 3 3" />
        </svg>
      </span>
      <span className={styles.prompt}>Tell Intentune what you want…</span>
      <span className={styles.send}>
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 19V5M6 11l6-6 6 6" />
        </svg>
      </span>
    </div>
  )
}

export default ComposerPlaceholder
