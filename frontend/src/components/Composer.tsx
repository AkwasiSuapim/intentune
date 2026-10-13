import { useId } from 'react'
import type { FormEvent } from 'react'
import Artwork from './Artwork.tsx'
import { ArrowUpIcon, WaveformIcon } from './icons.tsx'
import styles from './Composer.module.css'

export type ComposerNowPlaying = {
  title: string
  artworkUrl?: string | null
  playing: boolean
}

type ComposerProps = {
  value: string
  placeholder: string
  onValueChange?: (value: string) => void
  onSubmit?: () => void
  /** Shown in the leading slot once the hero recommendation is out of view. */
  nowPlaying?: ComposerNowPlaying
  onTogglePlay?: () => void
}

function Composer({
  value,
  placeholder,
  onValueChange,
  onSubmit,
  nowPlaying,
  onTogglePlay,
}: ComposerProps) {
  const inputId = useId()

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    onSubmit?.()
  }

  return (
    <form className={styles.composer} onSubmit={handleSubmit}>
      <span className={styles.lead} data-mode={nowPlaying ? 'playing' : 'idle'}>
        <span className={styles.glyph} aria-hidden="true">
          <WaveformIcon size={22} />
        </span>
        {nowPlaying && (
          <button
            type="button"
            className={styles.mini}
            aria-label={`${nowPlaying.playing ? 'Pause' : 'Play'} ${nowPlaying.title}`}
            onClick={onTogglePlay}
          >
            <Artwork src={nowPlaying.artworkUrl} className={styles.miniArt} />
            <span
              className={styles.equalizer}
              data-playing={nowPlaying.playing ? '' : undefined}
              aria-hidden="true"
            >
              <span />
              <span />
              <span />
            </span>
          </button>
        )}
      </span>
      <label className={styles.label} htmlFor={inputId}>
        Tell Intentune what you want
      </label>
      <input
        id={inputId}
        className={styles.input}
        type="text"
        autoComplete="off"
        enterKeyHint="send"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onValueChange?.(event.target.value)}
      />
      <button
        type="submit"
        className={styles.send}
        data-ready={value.trim() ? '' : undefined}
        aria-label="Send to Intentune"
      >
        <ArrowUpIcon size={20} />
      </button>
    </form>
  )
}

export default Composer
