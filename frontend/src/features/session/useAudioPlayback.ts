import { useEffect, useEffectEvent, useRef } from 'react'
import type { SessionCommand } from './commands.ts'
import type { SessionState } from './types.ts'

// Real playback for a recommendation that has audio. The audio element is the
// playback authority: its position, duration and end are reported to the
// session as commands, and the session's play/pause state is applied to it.
// A recommendation without audio (the mock's) keeps the simulated clock in
// useListeningSessions instead; the two never run together.
//
// The element is created only once a recommendation with audio appears, so a
// session without real audio never touches it.
export function useAudioPlayback(
  session: SessionState | null,
  run: (command: SessionCommand) => void,
) {
  const audio = useRef<HTMLAudioElement | null>(null)
  const current =
    (session?.currentRecommendationId &&
      session.recommendations[session.currentRecommendationId]) ||
    null
  const src = current?.audioUrl ?? null
  const heroId = src ? current?.id : null
  const playing = !!session?.playback.playing && !!src
  const restarts = session?.playback.restarts ?? 0

  const report = useEffectEvent((command: SessionCommand) => run(command))

  // A new hero loads its own audio, from the start.
  useEffect(() => {
    if (!heroId || !src) {
      audio.current?.pause()
      return
    }
    if (!audio.current) {
      const element = new Audio()
      element.preload = 'auto'
      element.addEventListener('timeupdate', () =>
        report({ type: 'playback_progressed', positionSeconds: element.currentTime }),
      )
      element.addEventListener('loadedmetadata', () =>
        report({
          type: 'playback_progressed',
          positionSeconds: element.currentTime,
          durationSeconds: Number.isFinite(element.duration) ? element.duration : undefined,
        }),
      )
      element.addEventListener('ended', () => report({ type: 'track_ended' }))
      audio.current = element
    }
    audio.current.src = src
  }, [heroId, src])

  // Play and pause follow the session. A browser that refuses to start
  // playing leaves the session paused, so the listener can press play.
  useEffect(() => {
    const element = audio.current
    if (!element || !heroId) return
    if (!playing) {
      element.pause()
      return
    }
    void element.play()?.catch(() => report({ type: 'playback_refused' }))
  }, [playing, heroId])

  // Replaying the hero starts it again from the beginning.
  useEffect(() => {
    if (audio.current && restarts > 0) audio.current.currentTime = 0
  }, [restarts])

  useEffect(
    () => () => {
      audio.current?.pause()
      audio.current = null
    },
    [],
  )
}
