import QuickActions from './QuickActions.tsx'
import type { QuickAction } from './QuickActions.tsx'
import { TuneIcon } from './icons.tsx'
import styles from './TuneBar.module.css'

type TuneBarProps = {
  /** Contextual actions; at most two are shown. */
  actions: QuickAction[]
  onSelectAction?: (id: string) => void
  onOpenTune?: () => void
}

function TuneBar({ actions, onSelectAction, onOpenTune }: TuneBarProps) {
  return (
    <div className={styles.bar}>
      <QuickActions actions={actions} onSelect={onSelectAction} />
      <button
        type="button"
        className={styles.tune}
        aria-label="Tune energy, mood or genre"
        data-focus-key="tune"
        onClick={onOpenTune}
      >
        <TuneIcon size={17} />
        <span className={styles.tuneLabel}>Tune</span>
      </button>
    </div>
  )
}

export default TuneBar
