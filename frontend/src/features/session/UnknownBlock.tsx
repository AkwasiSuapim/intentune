import styles from './UnknownBlock.module.css'

type UnknownBlockProps = {
  /** The unrecognised block type, shown as plain text. */
  type: string
  /** Visible in development so the gap is noticed; silent in production. */
  visible?: boolean
}

// Stands in for a block the registry does not know. It never renders any of
// the block's own content: only its type name, as text.
function UnknownBlock({
  type,
  visible = import.meta.env.DEV,
}: UnknownBlockProps) {
  if (!visible) return null

  return (
    <p className={styles.unknown} role="note" data-unknown-block>
      Unsupported block “{type}”
    </p>
  )
}

export default UnknownBlock
