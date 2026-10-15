import { useEffect, useRef, useState } from 'react'

/** Longest an exit may take before the content is dropped regardless. */
const EXIT_TIMEOUT_MS = 600

/**
 * Keeps showing content for a moment after it has been taken away, so it can
 * animate out. While `value` is present it is returned as is; once it becomes
 * null the last value is returned with `leaving: true` until `finish` is
 * called (normally when the exit animation ends).
 */
export function useLingering<T>(value: T | null) {
  // The value may be a fresh object on every render, so it is remembered in a
  // ref rather than compared and copied into state.
  const last = useRef(value)
  const [exited, setExited] = useState(value === null)

  useEffect(() => {
    if (value !== null) last.current = value
  })

  // Back on screen: the next removal should linger again.
  if (value !== null && exited) setExited(false)

  const leaving = value === null && !exited

  useEffect(() => {
    if (!leaving) return
    // A safety net for exits whose animation never reports back.
    const timer = window.setTimeout(() => setExited(true), EXIT_TIMEOUT_MS)
    return () => window.clearTimeout(timer)
  }, [leaving])

  return {
    shown: value ?? (leaving ? last.current : null),
    leaving,
    finish: () => setExited(true),
  }
}
