import { useId } from 'react'
import { ChevronRightIcon } from './icons.tsx'
import styles from './WhyThisFits.module.css'

type WhyThisFitsProps = {
  /** One concise line shown while collapsed. */
  summary: string
  /** A small number of reasons shown when expanded. Leave empty when the summary says enough. */
  reasons?: string[]
  expanded?: boolean
  onToggle?: () => void
}

function WhyThisFits({
  summary,
  reasons = [],
  expanded = false,
  onToggle,
}: WhyThisFitsProps) {
  const reasonsId = useId()

  if (reasons.length === 0) {
    return (
      <div className={styles.root}>
        <div className={styles.row}>
          <span className={styles.text}>
            <span className={styles.label}>Why this fits</span>
            <span className={styles.summary}>{summary}</span>
          </span>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.root}>
      <button
        type="button"
        className={styles.row}
        aria-expanded={expanded}
        aria-controls={reasonsId}
        onClick={onToggle}
      >
        <span className={styles.text}>
          <span className={styles.label}>Why this fits</span>
          {!expanded && <span className={styles.summary}>{summary}</span>}
        </span>
        <ChevronRightIcon className={styles.chevron} size={18} />
      </button>
      {expanded && (
        <ul id={reasonsId} className={styles.reasons}>
          {reasons.map((reason) => (
            <li key={reason} className={styles.reason}>
              <span className={styles.bullet} aria-hidden="true" />
              <span>{reason}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default WhyThisFits
