import { ArrowRightIcon, CheckIcon, CloseIcon } from './icons.tsx'
import styles from './Ack.module.css'

export type IntentChange = {
  dimension: string
  from: string
  to: string
}

type AckProps = {
  label: string
  detail?: string
  changes?: IntentChange[]
  /** `neutral` acknowledges something that left the intent as it was. */
  tone?: 'confirm' | 'neutral'
}

function Ack({ label, detail, changes = [], tone = 'confirm' }: AckProps) {
  return (
    <div className={styles.ack}>
      <span className={styles.icon} data-tone={tone} aria-hidden="true">
        {tone === 'confirm' ? (
          <CheckIcon size={12} strokeWidth="2.8" />
        ) : (
          <CloseIcon size={10} strokeWidth="2.8" />
        )}
      </span>
      <div className={styles.body}>
        <span className={styles.label}>{label}</span>
        {detail && <span className={styles.detail}>{detail}</span>}
        {changes.map((change) => (
          <span key={change.dimension} className={styles.change}>
            <span>{change.dimension}</span>
            <span>{change.from}</span>
            <ArrowRightIcon
              size={12}
              role="img"
              aria-hidden={undefined}
              aria-label="to"
            />
            <span className={styles.to}>{change.to}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

export default Ack
