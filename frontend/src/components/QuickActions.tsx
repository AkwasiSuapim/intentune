import { useRef } from 'react'
import { useScrollEdges } from './useScrollEdges.ts'
import styles from './QuickActions.module.css'

export type QuickAction = {
  id: string
  /** Written as something the user could have typed. */
  label: string
}

/** The interface never shows more than this many quick actions at once. */
const MAX_QUICK_ACTIONS = 2

type QuickActionsProps = {
  actions: QuickAction[]
  onSelect?: (id: string) => void
}

function QuickActions({ actions, onSelect }: QuickActionsProps) {
  const row = useRef<HTMLDivElement>(null)
  const shown = actions.slice(0, MAX_QUICK_ACTIONS)

  // Labels are never truncated, so a pair that is too wide scrolls instead,
  // and the row fades at an edge that has more beyond it.
  useScrollEdges(row, shown.map((action) => action.label).join('|'))

  return (
    <div
      ref={row}
      className={styles.actions}
      role="group"
      aria-label="Suggested refinements"
    >
      {shown.map((action, index) => (
        <button
          key={action.id}
          type="button"
          className={styles.action}
          data-focus-key={`quick-action-${index}`}
          onClick={() => onSelect?.(action.id)}
        >
          {action.label}
        </button>
      ))}
    </div>
  )
}

export default QuickActions
