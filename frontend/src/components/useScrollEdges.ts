import { useEffect } from 'react'
import type { RefObject } from 'react'

/**
 * Marks a sideways-scrolling row with `data-more-start` / `data-more-end`
 * while content lies beyond that edge, so CSS can fade the edge only when
 * there is something there. `contentKey` changes when the row's content does.
 */
export function useScrollEdges(
  row: RefObject<HTMLElement | null>,
  contentKey: string,
) {
  useEffect(() => {
    const element = row.current
    if (!element) return

    function update() {
      if (!element) return
      const beyondEnd =
        element.scrollWidth - element.clientWidth - element.scrollLeft
      element.toggleAttribute('data-more-start', element.scrollLeft > 1)
      element.toggleAttribute('data-more-end', beyondEnd > 1)
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(element)
    element.addEventListener('scroll', update, { passive: true })
    return () => {
      observer.disconnect()
      element.removeEventListener('scroll', update)
    }
  }, [row, contentKey])
}
