import styles from './IntentSummary.module.css'

export type IntentChip = {
  id: string
  label: string
  /** The dimension changed in the latest turn. */
  changed?: boolean
  /** The refine control for this dimension is open. */
  expanded?: boolean
}

type IntentSummaryProps = {
  chips: IntentChip[]
  onSelectChip?: (id: string) => void
}

function IntentSummary({ chips, onSelectChip }: IntentSummaryProps) {
  return (
    <div className={styles.summary}>
      <span className={styles.label}>Intent</span>
      <div className={styles.strip} role="group" aria-label="Current intent">
        {chips.map((chip) => (
          <button
            key={chip.id}
            type="button"
            className={styles.chip}
            data-changed={chip.changed ? '' : undefined}
            aria-label={
              chip.changed
                ? `Tune ${chip.label}, just updated`
                : `Tune ${chip.label}`
            }
            aria-expanded={chip.expanded ?? false}
            onClick={() => onSelectChip?.(chip.id)}
          >
            {chip.changed && <span className={styles.dot} aria-hidden="true" />}
            {chip.label}
          </button>
        ))}
      </div>
    </div>
  )
}

export default IntentSummary
