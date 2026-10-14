import { useEffect, useEffectEvent, useRef } from 'react'
import type { ReactNode } from 'react'
import styles from './SessionTimeline.module.css'

type SessionTimelineProps = {
  children: ReactNode
  /** Changes when something is added; the stream then returns to the newest content. */
  newestKey?: string
  /** Changes when the now-playing card does, so its controls are watched afresh. */
  nowPlayingKey?: string | null
  /** Reports when the now-playing card's playback controls scroll out of view. */
  onNowPlayingHiddenChange?: (hidden: boolean) => void
}

// Layout for the chronological session stream: oldest at the top, newest
// anchored to the bottom, scrolling when the history outgrows the screen.
function SessionTimeline({
  children,
  newestKey,
  nowPlayingKey,
  onNowPlayingHiddenChange,
}: SessionTimelineProps) {
  const scroller = useRef<HTMLDivElement>(null)
  const reportHidden = useEffectEvent((hidden: boolean) =>
    onNowPlayingHiddenChange?.(hidden),
  )

  useEffect(() => {
    // In a column-reverse scroller, the top of the scroll range is the newest end.
    scroller.current?.scrollTo({ top: 0 })
  }, [newestKey])

  useEffect(() => {
    const root = scroller.current
    const controls = root?.querySelector('[data-now-playing-controls]')
    if (!root || !controls) return

    const observer = new IntersectionObserver(
      ([entry]) => reportHidden(!entry.isIntersecting),
      { root },
    )
    observer.observe(controls)
    return () => {
      observer.disconnect()
      reportHidden(false)
    }
  }, [nowPlayingKey])

  return (
    <div ref={scroller} className={styles.scroller}>
      <div className={styles.stack}>{children}</div>
    </div>
  )
}

type TimelineItemProps = {
  /**
   * How the item arrives: `rise` for messages and acknowledgements, `reveal`
   * for a new recommendation, `settle` for a hero collapsing into history.
   * Left out for content that was already there.
   */
  enter?: 'rise' | 'reveal' | 'settle'
  children: ReactNode
}

export function TimelineItem({ enter, children }: TimelineItemProps) {
  return (
    <div className={styles.item} data-enter={enter}>
      {children}
    </div>
  )
}

export default SessionTimeline
