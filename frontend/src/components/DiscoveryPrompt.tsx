import Artwork from './Artwork.tsx'
import styles from './DiscoveryPrompt.module.css'

export type StarterIntent = {
  id: string
  label: string
  /** The prewritten first request this starter stands for. */
  phrase: string
  artworkUrl?: string | null
}

type DiscoveryPromptProps = {
  starters: StarterIntent[]
  onStart?: (id: string) => void
}

// The "Tune in" state of a new listening session.
function DiscoveryPrompt({ starters, onStart }: DiscoveryPromptProps) {
  return (
    <div className={styles.prompt}>
      <svg
        className={styles.rings}
        aria-hidden="true"
        width="300"
        height="300"
        viewBox="0 0 300 300"
        fill="none"
      >
        <circle cx="150" cy="150" r="52" strokeOpacity="0.2" />
        <circle cx="150" cy="150" r="92" strokeOpacity="0.12" />
        <circle cx="150" cy="150" r="134" strokeOpacity="0.06" />
        <path
          d="M110 150c6 0 6-16 12-16s6 32 12 32 6-46 14-46 8 46 14 46 6-32 12-32 6 16 12 16"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>

      <div className={styles.intro}>
        <span className={styles.eyebrow}>Tune in</span>
        <h2 className={styles.heading}>
          What do you need from your music right now?
        </h2>
        <p className={styles.hint}>
          Say it however it comes to you. You can change direction anytime.
        </p>
      </div>

      <div className={styles.starters}>
        {starters.map((starter) => (
          <button
            key={starter.id}
            type="button"
            className={styles.starter}
            aria-label={`${starter.label}: ${starter.phrase}`}
            data-focus-key="starter"
            onClick={() => onStart?.(starter.id)}
          >
            <Artwork src={starter.artworkUrl} className={styles.swatch} />
            <span className={styles.starterText}>
              <span className={styles.starterLabel}>{starter.label}</span>
              <span className={styles.starterPhrase}>“{starter.phrase}”</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}

export default DiscoveryPrompt
