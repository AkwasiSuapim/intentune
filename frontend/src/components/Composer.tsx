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
  /** The song that is playing, when there is one. */
  nowPlaying?: ComposerNowPlaying | null
  /**
   * Shows compact now-playing in the leading slot. Meant for when the hero
   * recommendation's own controls are out of view.
   */
  showNowPlaying?: boolean
  onTogglePlay?: () => void
}

function Composer({
  value,
  placeholder,
  onValueChange,
  onSubmit,
  nowPlaying,
  showNowPlaying = false,
  onTogglePlay,
}: ComposerProps) {
  const inputId = useId()
  const compact = showNowPlaying && !!nowPlaying

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    onSubmit?.()
  }

  return (
    <form className={styles.composer} onSubmit={handleSubmit}>
      <span className={styles.lead} data-mode={compact ? 'playing' : 'idle'}>
        <span className={styles.glyph} aria-hidden="true">
          <WaveformIcon size={22} />
        </span>
        {/* Stays mounted while there is a song, so it can fade in and out. */}
        {nowPlaying && (
          <button
            type="button"
            className={styles.mini}
            aria-label={`${nowPlaying.playing ? 'Pause' : 'Play'} ${nowPlaying.title}`}
            aria-hidden={!compact}
            tabIndex={compact ? 0 : -1}
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
        data-focus-key="composer"
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
