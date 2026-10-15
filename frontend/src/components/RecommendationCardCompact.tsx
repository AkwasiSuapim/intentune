import Artwork from './Artwork.tsx'
import { CheckIcon, HeartIcon } from './icons.tsx'
import styles from './RecommendationCardCompact.module.css'

export type RecommendationOutcome = 'played' | 'liked' | 'saved' | 'skipped'

const OUTCOME_LABEL: Record<RecommendationOutcome, string> = {
  played: 'Played',
  liked: 'Liked',
  saved: 'Saved',
  skipped: 'Skipped',
}

type RecommendationCardCompactProps = {
  title: string
  artist: string
  artworkUrl?: string | null
  outcome: RecommendationOutcome
  onReplay?: () => void
}

function RecommendationCardCompact({
  title,
  artist,
  artworkUrl,
  outcome,
  onReplay,
}: RecommendationCardCompactProps) {
  const outcomeLabel = OUTCOME_LABEL[outcome]

  return (
    <button
      type="button"
      className={styles.card}
      data-outcome={outcome}
      aria-label={`Play ${title} by ${artist} again. ${outcomeLabel}`}
      data-focus-key="history"
      onClick={onReplay}
    >
      <Artwork src={artworkUrl} glyphSize={18} className={styles.art} />
      <span className={styles.text}>
        <span className={styles.title}>{title}</span>
        <span className={styles.artist}>{artist}</span>
      </span>
      <span className={styles.outcome}>
        {outcome === 'liked' && <HeartIcon size={13} filled stroke="none" />}
        {outcome === 'saved' && <CheckIcon size={13} />}
        {outcomeLabel}
      </span>
    </button>
  )
}

export default RecommendationCardCompact
