import { useId, useRef } from 'react'
import type { KeyboardEvent } from 'react'
import { CloseIcon } from './icons.tsx'
import styles from './RefineControl.module.css'

export type RefineTab = 'energy' | 'mood' | 'genre'

export type RefineOption = {
  id: string
  label: string
  /** A value the music library cannot act on: shown, dimmed, and not chosen when pressed. */
  unavailable?: boolean
}

const TABS: { id: RefineTab; label: string }[] = [
  { id: 'energy', label: 'Energy' },
  { id: 'mood', label: 'Mood' },
  { id: 'genre', label: 'Genre' },
]

/** Keys that move between tabs, mapped to how far they move. */
const TAB_KEYS: Record<string, (index: number) => number> = {
  ArrowRight: (index) => index + 1,
  ArrowLeft: (index) => index - 1,
  Home: () => 0,
  End: () => TABS.length - 1,
}

/** Why some values of a dimension are dimmed, in the listener's terms. */
const PARTIAL_NOTE: Record<RefineTab, string> = {
  energy: 'Dimmed levels aren’t in your music yet, so they can’t change what plays.',
  mood: 'Dimmed moods aren’t in your music yet, so they can’t change what plays.',
  genre: 'Dimmed genres aren’t in your music yet, so they can’t change what plays.',
}

/** Why nothing can be tuned while the library has no playable music. */
const LIBRARY_NOTE = 'Your library has no playable music yet, so tuning can’t change what plays. Import music to start.'

/** Why a dimension cannot be tuned, in the listener's terms. */
const UNAVAILABLE_NOTE: Record<RefineTab, string> = {
  energy: 'Your music has no energy information yet, so this can’t change what plays.',
  mood: 'None of your music is tagged with these moods yet, so this can’t change what plays.',
  genre: 'Your music has no genre tags yet, so this can’t change what plays.',
}

type RefineControlProps = {
  activeTab: RefineTab
  /** Ordered from lowest to highest. */
  energyLevels: RefineOption[]
  energyId: string | null
  moods: RefineOption[]
  moodId: string | null
  genres: RefineOption[]
  genreId: string | null
  /** Tabs the music library has no evidence for: shown, marked, and not tunable. */
  unavailable?: RefineTab[]
  /** False while nothing in the library is playable: every tab is locked, for that one reason, and none is marked. */
  libraryReady?: boolean
  onTabChange?: (tab: RefineTab) => void
  onEnergyChange?: (id: string) => void
  onMoodChange?: (id: string) => void
  onGenreChange?: (id: string) => void
  onClose?: () => void
}

// Tabs follow the ARIA tabs pattern: one Tab stop, arrow keys move and
// select. The options are plain toggle buttons rather than radios, because
// choosing one immediately retunes the session; arrow keys that selected as
// they moved would start a new turn on every keypress.
function RefineControl({
  activeTab,
  energyLevels,
  energyId,
  moods,
  moodId,
  genres,
  genreId,
  unavailable = [],
  libraryReady = true,
  onTabChange,
  onEnergyChange,
  onMoodChange,
  onGenreChange,
  onClose,
}: RefineControlProps) {
  const baseId = useId()
  const tabRefs = useRef<Partial<Record<RefineTab, HTMLButtonElement | null>>>(
    {},
  )
  const tabId = (tab: RefineTab) => `${baseId}-tab-${tab}`
  const panelId = `${baseId}-panel`
  const noteId = `${baseId}-note`
  // Not ready is about the library, not a dimension: no tab is marked for it.
  const marked = (tab: RefineTab) => libraryReady && unavailable.includes(tab)
  const locked = !libraryReady || unavailable.includes(activeTab)
  // An option the library cannot use, or of a dimension it cannot use, stays visible but does nothing.
  const choose = (onChange: ((id: string) => void) | undefined, option: RefineOption) => {
    if (!locked && !option.unavailable) onChange?.(option.id)
  }

  const energyIndex = energyLevels.findIndex((level) => level.id === energyId)
  const activeOptions =
    activeTab === 'energy' ? energyLevels : activeTab === 'mood' ? moods : genres
  const note = !libraryReady
    ? LIBRARY_NOTE
    : locked
    ? UNAVAILABLE_NOTE[activeTab]
    : activeOptions.some((option) => option.unavailable)
      ? PARTIAL_NOTE[activeTab]
      : null
  const choices =
    activeTab === 'mood'
      ? { title: 'Mood', options: moods, selectedId: moodId, onChange: onMoodChange }
      : { title: 'Genre', options: genres, selectedId: genreId, onChange: onGenreChange }

  function handleTabKeyDown(event: KeyboardEvent) {
    const move = TAB_KEYS[event.key]
    if (!move) return
    event.preventDefault()
    const index = TABS.findIndex((tab) => tab.id === activeTab)
    const next = TABS[(move(index) + TABS.length) % TABS.length]
    tabRefs.current[next.id]?.focus()
    onTabChange?.(next.id)
  }

  function handleKeyDown(event: KeyboardEvent) {
    if (event.key === 'Escape' && onClose) {
      event.stopPropagation()
      onClose()
    }
  }

  return (
    <div
      className={styles.control}
      role="group"
      aria-label="Tune the session"
      data-focus-key="refine"
      onKeyDown={handleKeyDown}
    >
      <div className={styles.head}>
        <div
          className={styles.tabs}
          role="tablist"
          aria-label="What to tune"
          onKeyDown={handleTabKeyDown}
        >
          {TABS.map((tab) => {
            const selected = tab.id === activeTab
            return (
              <button
                key={tab.id}
                ref={(element) => {
                  tabRefs.current[tab.id] = element
                }}
                id={tabId(tab.id)}
                type="button"
                role="tab"
                className={styles.tab}
                aria-selected={selected}
                aria-controls={panelId}
                tabIndex={selected ? 0 : -1}
                data-focus-key={selected ? 'refine-tab' : undefined}
                data-unavailable={marked(tab.id) ? '' : undefined}
                aria-label={marked(tab.id) ? `${tab.label}, unavailable` : undefined}
                onClick={() => onTabChange?.(tab.id)}
              >
                {tab.label}
              </button>
            )
          })}
        </div>
        <button
          type="button"
          className={styles.close}
          aria-label="Close tuning"
          data-focus-key="refine-close"
          onClick={onClose}
        >
          <CloseIcon size={16} />
        </button>
      </div>

      <div
        id={panelId}
        role="tabpanel"
        aria-labelledby={tabId(activeTab)}
        aria-describedby={note ? noteId : undefined}
      >
        {note && (
          <p id={noteId} className={styles.unavailable}>
            {note}
          </p>
        )}
        {activeTab === 'energy' ? (
          <div className={styles.energy}>
            <span className={styles.energyLabel} aria-hidden="true">
              {energyIndex >= 0
                ? `${energyLevels[energyIndex].label} energy`
                : 'Energy'}
            </span>
            <div className={styles.bars} role="group" aria-label="Energy level">
              {energyLevels.map((level, index) => (
                <button
                  key={level.id}
                  type="button"
                  className={styles.barButton}
                  aria-pressed={index === energyIndex}
                  aria-label={`${level.label} energy`}
                  aria-disabled={locked || level.unavailable || undefined}
                  data-filled={index <= energyIndex ? '' : undefined}
                  onClick={() => choose(onEnergyChange, level)}
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
          <div className={styles.choices} role="group" aria-label={choices.title}>
            {choices.options.map((option) => (
              <button
                key={option.id}
                type="button"
                className={styles.choice}
                aria-pressed={option.id === choices.selectedId}
                aria-disabled={locked || option.unavailable || undefined}
                onClick={() => choose(choices.onChange, option)}
              >
                {option.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default RefineControl
