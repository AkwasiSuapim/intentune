import Artwork from './Artwork.tsx'
import { ChevronRightIcon } from './icons.tsx'
import styles from './UpNext.module.css'

type UpNextProps = {
  title: string
  artist: string
  artworkUrl?: string | null
  onPlay?: () => void
}

// A single peek at what follows; never a queue.
function UpNext({ title, artist, artworkUrl, onPlay }: UpNextProps) {
  return (
    <button
      type="button"
      className={styles.row}
      aria-label={`Up next: ${title} by ${artist}. Play now`}
      onClick={onPlay}
    >
      <Artwork src={artworkUrl} className={styles.art} />
      <span className={styles.text}>
        <span className={styles.label}>Up next</span>
        <span className={styles.song}>
          {title} <span className={styles.artist}>· {artist}</span>
        </span>
      </span>
      <ChevronRightIcon className={styles.chevron} size={18} />
    </button>
  )
}

export default UpNext
