import styles from './PlaylistSwatch.module.css'

/** The fixed set of swatch tints a playlist can carry. */
export type PlaylistTone = 'violet' | 'indigo' | 'ember' | 'dusk' | 'lavender'

type PlaylistSwatchProps = {
  tone?: PlaylistTone
  className?: string
}

// Decorative colour tile that identifies a playlist. The caller sets the size.
function PlaylistSwatch({ tone = 'lavender', className }: PlaylistSwatchProps) {
  return (
    <span
      className={className ? `${styles.swatch} ${className}` : styles.swatch}
      data-tone={tone}
      aria-hidden="true"
    />
  )
}

export default PlaylistSwatch
