import { useEffect, useLayoutEffect, useRef } from 'react'

/** Where focus goes when nothing more specific is left. */
const LAST_RESORT = 'composer'

function findUsable(key: string): HTMLElement | null {
  const element = document.querySelector(
    `[data-focus-key="${CSS.escape(key)}"]`,
  )
  if (!(element instanceof HTMLElement)) return null
  if (element.closest('[inert], [aria-hidden="true"]')) return null
  if (element instanceof HTMLButtonElement && element.disabled) return null
  return element
}

/**
 * Keeps keyboard focus from falling to the page when the focused control is
 * replaced, as when a new recommendation replaces the hero or the refine
 * control replaces the quick actions.
 *
 * Controls carry `data-focus-key`. When the focused control disappears,
 * focus moves to the control now holding the same key, else to the first
 * successor listed for that key, else to the composer. Focus that was simply
 * moved elsewhere by the user is left alone.
 */
export function useFocusRescue(successors: Record<string, string[]>) {
  const lastFocus = useRef<{ element: Element; key: string | null } | null>(
    null,
  )

  useEffect(() => {
    function remember(event: FocusEvent) {
      if (!(event.target instanceof Element)) return
      lastFocus.current = {
        element: event.target,
        key:
          event.target.closest<HTMLElement>('[data-focus-key]')?.dataset
            .focusKey ?? null,
      }
    }
    document.addEventListener('focusin', remember)
    return () => document.removeEventListener('focusin', remember)
  }, [])

  // Runs after every render, before paint, so focus never visibly drops.
  useLayoutEffect(() => {
    const previous = lastFocus.current
    if (!previous?.key || previous.element.isConnected) return
    const active = document.activeElement
    if (active && active !== document.body) return

    const keys = [previous.key, ...(successors[previous.key] ?? []), LAST_RESORT]
    for (const key of keys) {
      const target = findUsable(key)
      if (target) {
        target.focus()
        return
      }
    }
  })
}
