// Wording for the screen-reader announcer: what changed when new blocks
// arrived in the stream. Short sentences, no visual separators.
import type { SessionBlock } from './blocks.ts'

/** Turns "Emotional · Afrobeats · Low energy" into a list that reads aloud. */
const spoken = (text: string) => text.replaceAll(' · ', ', ')

function sentence(block: SessionBlock): string | null {
  switch (block.type) {
    case 'ack': {
      const parts = [
        block.label,
        block.detail && spoken(block.detail),
        ...(block.changes ?? []).map(
          (change) => `${change.dimension} ${change.from} to ${change.to}`,
        ),
      ].filter(Boolean)
      return `${parts.join(', ')}.`
    }
    case 'recommendation':
      return block.variant === 'hero'
        ? `Now playing ${block.title} by ${block.artist}.`
        : null
    case 'session_summary':
      return `${block.label}: ${spoken(block.detail)}.`
    case 'turn_status':
      // Waiting is not news; a request that failed is.
      return block.status === 'failed'
        ? 'That didn’t go through. You can try again.'
        : null
    default:
      // The user's own message, and anything else, needs no announcing.
      return null
  }
}

/** What a screen reader should hear about blocks that just arrived. */
export function announceBlocks(blocks: SessionBlock[]): string {
  return blocks
    .map(sentence)
    .filter((text) => text !== null)
    .join(' ')
}
