import { RestoreIcon } from './icons.tsx'
import styles from './SessionSummary.module.css'

type SessionSummaryProps = {
  label: string
  detail: string
}

function SessionSummary({ label, detail }: SessionSummaryProps) {
  return (
    <div className={styles.summary}>
      <RestoreIcon className={styles.icon} size={18} />
      <div className={styles.body}>
        <span className={styles.label}>{label}</span>
        <span className={styles.detail}>{detail}</span>
      </div>
    </div>
  )
}

export default SessionSummary
