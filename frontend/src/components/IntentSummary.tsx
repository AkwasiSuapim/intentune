import { useEffect, useRef } from 'react'
import { useScrollEdges } from './useScrollEdges.ts'
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
  const strip = useRef<HTMLDivElement>(null)
  // The chip the user should be looking at: the one being tuned, else one that just changed.
  const focusId =
    chips.find((chip) => chip.expanded)?.id ??
    chips.find((chip) => chip.changed)?.id

  useScrollEdges(strip, chips.map((chip) => chip.label).join('|'))

  useEffect(() => {
    if (!focusId) return
    // On a narrow screen that chip may be scrolled out of the strip: bring it in.
    strip.current
      ?.querySelector(`[data-chip="${CSS.escape(focusId)}"]`)
      ?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [focusId])

  return (
    <div className={styles.summary}>
      <span className={styles.label}>Intent</span>
      <div
        ref={strip}
        className={styles.strip}
        role="group"
        aria-label="Current intent"
      >
        {chips.map((chip) => (
          <button
            key={chip.id}
            type="button"
            className={styles.chip}
            data-chip={chip.id}
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
