import type { AnimationEvent } from 'react'
import Artwork from './Artwork.tsx'
import PlaylistSwatch from './PlaylistSwatch.tsx'
import type { PlaylistTone } from './PlaylistSwatch.tsx'
import { CheckIcon, PlusIcon } from './icons.tsx'
import styles from './PlaylistPicker.module.css'

export type PlaylistOption = {
  id: string
  name: string
  tone?: PlaylistTone
  /** A hint that the playlist matches the session. Never a preselection. */
  fitsSession?: boolean
}

type PlaylistPickerProps = {
  songTitle: string
  songArtist: string
  artworkUrl?: string | null
  playlists: PlaylistOption[]
  /** Only what the user has explicitly chosen. */
  selectedIds: string[]
  /** Plays the exit: the sheet slides away, then `onExited` is called. */
  leaving?: boolean
  onExited?: () => void
  onToggle?: (id: string) => void
  onCreate?: () => void
  onConfirm?: () => void
  onClose?: () => void
}

function confirmLabel(selected: PlaylistOption[]) {
  if (selected.length === 0) return 'Choose a playlist'
  if (selected.length === 1) return `Save to ${selected[0].name}`
  return `Save to ${selected.length} playlists`
}

// Bottom sheet for saving the current song. Expects a positioned ancestor.
function PlaylistPicker({
  songTitle,
  songArtist,
  artworkUrl,
  playlists,
  selectedIds,
  leaving = false,
  onExited,
  onToggle,
  onCreate,
  onConfirm,
  onClose,
}: PlaylistPickerProps) {
  const selected = playlists.filter((playlist) =>
    selectedIds.includes(playlist.id),
  )
  const nothingChosen = selected.length === 0

  function handleAnimationEnd(event: AnimationEvent) {
    // Only the sheet's own exit counts, not animations inside it.
    if (leaving && event.target === event.currentTarget) onExited?.()
  }

  return (
    <div className={styles.layer} data-leaving={leaving ? '' : undefined}>
      <button
        type="button"
        className={styles.scrim}
        aria-label="Close playlist picker"
        onClick={onClose}
      />
      <section
        className={styles.sheet}
        role="dialog"
        aria-modal="true"
        aria-label="Add to playlist"
        tabIndex={-1}
        onAnimationEnd={handleAnimationEnd}
      >
        <span className={styles.grabber} aria-hidden="true" />
        <div className={styles.head}>
          <Artwork src={artworkUrl} className={styles.art} />
          <div className={styles.headText}>
            <h2 className={styles.heading}>Add to playlist</h2>
            <span className={styles.song}>
              {songTitle} · {songArtist}
            </span>
          </div>
        </div>

        {playlists.map((playlist) => {
          const checked = selectedIds.includes(playlist.id)
          return (
            <button
              key={playlist.id}
              type="button"
              role="checkbox"
              className={styles.row}
              aria-checked={checked}
              onClick={() => onToggle?.(playlist.id)}
            >
              <PlaylistSwatch tone={playlist.tone} className={styles.swatch} />
              <span className={styles.rowText}>
                <span className={styles.name}>{playlist.name}</span>
                {playlist.fitsSession && (
                  <span className={styles.fits}>Fits this session</span>
                )}
              </span>
              <span className={styles.check} aria-hidden="true">
                {checked && <CheckIcon size={13} strokeWidth="2.8" />}
              </span>
            </button>
          )
        })}

        <button type="button" className={styles.create} onClick={onCreate}>
          <span className={styles.createIcon} aria-hidden="true">
            <PlusIcon size={16} />
          </span>
          Create playlist
        </button>

        <button
          type="button"
          className={styles.confirm}
          disabled={nothingChosen}
          onClick={onConfirm}
        >
          {confirmLabel(selected)}
        </button>
      </section>
    </div>
  )
}

export default PlaylistPicker
