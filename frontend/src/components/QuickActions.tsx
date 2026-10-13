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
  return (
    <div
      className={styles.actions}
      role="group"
      aria-label="Suggested refinements"
    >
      {actions.slice(0, MAX_QUICK_ACTIONS).map((action) => (
        <button
          key={action.id}
          type="button"
          className={styles.action}
          onClick={() => onSelect?.(action.id)}
        >
          {action.label}
        </button>
      ))}
    </div>
  )
}

export default QuickActions
