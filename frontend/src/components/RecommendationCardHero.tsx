import Artwork from './Artwork.tsx'
import WhyThisFits from './WhyThisFits.tsx'
import {
  CheckIcon,
  CloseIcon,
  HeartIcon,
  NextIcon,
  PauseIcon,
  PlayIcon,
  PlusIcon,
} from './icons.tsx'
import styles from './RecommendationCardHero.module.css'

type RecommendationCardHeroProps = {
  title: string
  artist: string
  /** Concise music descriptors, e.g. genre and feel. */
  descriptors: string[]
  artworkUrl?: string | null
  /** The user's own words this recommendation answers, when worth echoing. */
  echo?: string
  playing: boolean
  positionSeconds: number
  durationSeconds: number
  whySummary: string
  whyReasons?: string[]
  whyExpanded?: boolean
  liked?: boolean
  /** Names of the playlists the song is saved to; empty when not saved. */
  savedTo?: string[]
  onTogglePlay?: () => void
  onNext?: () => void
  onToggleWhy?: () => void
  onLike?: () => void
  onNotForMe?: () => void
  onSave?: () => void
}

function formatTime(totalSeconds: number) {
  const seconds = Math.max(0, Math.floor(totalSeconds))
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function RecommendationCardHero({
  title,
  artist,
  descriptors,
  artworkUrl,
  echo,
  playing,
  positionSeconds,
  durationSeconds,
  whySummary,
  whyReasons,
  whyExpanded,
  liked = false,
  savedTo = [],
  onTogglePlay,
  onNext,
  onToggleWhy,
  onLike,
  onNotForMe,
  onSave,
}: RecommendationCardHeroProps) {
  const saved = savedTo.length > 0
  const progress =
    durationSeconds > 0
      ? Math.min(100, Math.max(0, (positionSeconds / durationSeconds) * 100))
      : 0

  return (
    <article
      className={styles.card}
      aria-label={`Now playing: ${title} by ${artist}`}
    >
      <div className={styles.media}>
        <Artwork src={artworkUrl} glyphSize={64} className={styles.art} />
        <div className={styles.meta}>
          <span className={styles.descriptors}>{descriptors.join(' · ')}</span>
          <h2 className={styles.title}>{title}</h2>
          <span className={styles.artist}>{artist}</span>
        </div>
      </div>

      <div className={styles.body}>
        {echo && <p className={styles.echo}>You said “{echo}”</p>}

        <div className={styles.playback} data-now-playing-controls>
          <button
            type="button"
            className={styles.play}
            aria-label={`${playing ? 'Pause' : 'Play'} ${title}`}
            data-focus-key="hero-play"
            onClick={onTogglePlay}
          >
            {playing ? <PauseIcon size={20} /> : <PlayIcon size={20} />}
          </button>
          <div className={styles.progress}>
            <div
              className={styles.track}
              role="progressbar"
              aria-label="Playback position"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(progress)}
              aria-valuetext={`${formatTime(positionSeconds)} of ${formatTime(durationSeconds)}`}
            >
              <div className={styles.fill} style={{ width: `${progress}%` }} />
            </div>
            <div className={styles.times}>
              <span>{formatTime(positionSeconds)}</span>
              <span>-{formatTime(durationSeconds - positionSeconds)}</span>
            </div>
          </div>
          <button
            type="button"
            className={styles.next}
            aria-label="Next recommendation"
            data-focus-key="hero-next"
            onClick={onNext}
          >
            <NextIcon size={22} />
          </button>
        </div>

        <WhyThisFits
          summary={whySummary}
          reasons={whyReasons}
          expanded={whyExpanded}
          onToggle={onToggleWhy}
        />

        <div className={styles.reactions}>
          <button
            type="button"
            className={styles.reaction}
            data-active={liked ? '' : undefined}
            aria-pressed={liked}
            data-focus-key="hero-like"
            onClick={onLike}
          >
            <HeartIcon size={17} filled={liked} />
            {liked ? 'Liked' : 'Like'}
          </button>
          <button
            type="button"
            className={styles.reaction}
            data-focus-key="hero-not-for-me"
            onClick={onNotForMe}
          >
            <CloseIcon size={15} />
            Not for me
          </button>
          <button
            type="button"
            className={styles.reaction}
            data-active={saved ? '' : undefined}
            aria-label={
              saved
                ? `Saved to ${savedTo.join(', ')}. Change playlists`
                : 'Save to a playlist'
            }
            data-focus-key="hero-save"
            onClick={onSave}
          >
            {saved ? <CheckIcon size={15} /> : <PlusIcon size={15} />}
            {saved ? 'Saved' : 'Save'}
          </button>
        </div>
      </div>
    </article>
  )
}

export default RecommendationCardHero
