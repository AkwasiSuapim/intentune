import { useState } from 'react'
import { WaveformIcon } from './icons.tsx'
import styles from './Artwork.module.css'

type ArtworkProps = {
  src?: string | null
  /** Size of the fallback glyph in px; 0 shows the fallback surface only. */
  glyphSize?: number
  className?: string
}

// Decorative song artwork. Falls back to the Intentune surface when the
// artwork is missing or fails to load. The caller sets size and radius.
function Artwork({ src, glyphSize = 0, className }: ArtworkProps) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null)
  const showImage = Boolean(src) && src !== failedSrc

  return (
    <span
      className={className ? `${styles.artwork} ${className}` : styles.artwork}
      aria-hidden="true"
    >
      {showImage ? (
        <img
          className={styles.image}
          src={src ?? undefined}
          alt=""
          draggable={false}
          onError={() => setFailedSrc(src ?? null)}
        />
      ) : (
        glyphSize > 0 && (
          <WaveformIcon
            className={styles.glyph}
            size={glyphSize}
            strokeWidth={glyphSize >= 48 ? 1.2 : 1.8}
          />
        )
      )}
    </span>
  )
}

export default Artwork
