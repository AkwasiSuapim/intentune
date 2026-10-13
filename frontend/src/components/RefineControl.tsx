import { CloseIcon } from './icons.tsx'
import styles from './RefineControl.module.css'

export type RefineTab = 'energy' | 'mood' | 'genre'

export type RefineOption = {
  id: string
  label: string
}

const TABS: { id: RefineTab; label: string }[] = [
  { id: 'energy', label: 'Energy' },
  { id: 'mood', label: 'Mood' },
  { id: 'genre', label: 'Genre' },
]

type RefineControlProps = {
  activeTab: RefineTab
  /** Ordered from lowest to highest. */
  energyLevels: RefineOption[]
  energyId: string | null
  moods: RefineOption[]
  moodId: string | null
  genres: RefineOption[]
  genreId: string | null
  onTabChange?: (tab: RefineTab) => void
  onEnergyChange?: (id: string) => void
  onMoodChange?: (id: string) => void
  onGenreChange?: (id: string) => void
  onClose?: () => void
}

function RefineControl({
  activeTab,
  energyLevels,
  energyId,
  moods,
  moodId,
  genres,
  genreId,
  onTabChange,
  onEnergyChange,
  onMoodChange,
  onGenreChange,
  onClose,
}: RefineControlProps) {
  const energyIndex = energyLevels.findIndex((level) => level.id === energyId)
  const choices =
    activeTab === 'mood'
      ? { title: 'Mood', options: moods, selectedId: moodId, onChange: onMoodChange }
      : { title: 'Genre', options: genres, selectedId: genreId, onChange: onGenreChange }

  return (
    <div className={styles.control} role="group" aria-label="Tune the session">
      <div className={styles.head}>
        <div className={styles.tabs} role="tablist" aria-label="What to tune">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              className={styles.tab}
              aria-selected={tab.id === activeTab}
              onClick={() => onTabChange?.(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          className={styles.close}
          aria-label="Close tuning"
          onClick={onClose}
        >
          <CloseIcon size={16} />
        </button>
      </div>

      {activeTab === 'energy' ? (
        <div className={styles.energy}>
          <span className={styles.energyLabel}>
            {energyIndex >= 0 ? `${energyLevels[energyIndex].label} energy` : 'Energy'}
          </span>
          <div className={styles.bars} role="radiogroup" aria-label="Energy level">
            {energyLevels.map((level, index) => (
              <button
                key={level.id}
                type="button"
                role="radio"
                className={styles.barButton}
                aria-checked={index === energyIndex}
                aria-label={`${level.label} energy`}
                data-filled={index <= energyIndex ? '' : undefined}
                onClick={() => onEnergyChange?.(level.id)}
              >
                <span
                  className={styles.bar}
                  style={{ height: 14 + index * 6 }}
                />
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className={styles.choices} role="radiogroup" aria-label={choices.title}>
          {choices.options.map((option) => (
            <button
              key={option.id}
              type="button"
              role="radio"
              className={styles.choice}
              aria-checked={option.id === choices.selectedId}
              onClick={() => choices.onChange?.(option.id)}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default RefineControl
