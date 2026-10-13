import type { ReactNode } from 'react'
import styles from './SessionTimeline.module.css'

type SessionTimelineProps = {
  children: ReactNode
}

// Layout for the chronological session stream: oldest at the top, newest
// anchored to the bottom, scrolling when the history outgrows the screen.
function SessionTimeline({ children }: SessionTimelineProps) {
  return (
    <div className={styles.scroller}>
      <div className={styles.stack}>{children}</div>
    </div>
  )
}

export default SessionTimeline
