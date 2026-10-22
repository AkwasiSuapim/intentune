// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { SessionCommand } from './commands.ts'
import { createSession } from './sessionReducer.ts'
import type { Recommendation, SessionState } from './types.ts'
import { useAudioPlayback } from './useAudioPlayback.ts'

// A stand-in for the browser's audio element: it records what it is told,
// and the test plays its events.
class FakeAudio extends EventTarget {
  static created: FakeAudio[] = []
  src = ''
  preload = ''
  currentTime = 0
  duration = Number.NaN
  paused = true
  refuse = false
  play = vi.fn(() => {
    if (this.refuse) return Promise.reject(new Error('NotAllowedError'))
    this.paused = false
    return Promise.resolve()
  })
  pause = vi.fn(() => {
    this.paused = true
  })
  constructor() {
    super()
    FakeAudio.created.push(this)
  }
}

function song(id: string, audioUrl: string | null): Recommendation {
  return {
    id,
    songId: `song-${id}`,
    title: id,
    artist: 'Artist',
    descriptors: [],
    artworkUrl: null,
    durationSeconds: 200,
    liked: false,
    skipped: false,
    savedToPlaylistIds: [],
    ref: `ref-${id}`,
    audioUrl,
  }
}

function sessionWith(hero: Recommendation | null, playing = true, restarts = 0): SessionState {
  const base = createSession('s1')
  return {
    ...base,
    recommendations: hero ? { [hero.id]: hero } : {},
    currentRecommendationId: hero?.id ?? null,
    playback: { playing, positionSeconds: 0, restarts },
  }
}

describe('real audio playback', () => {
  const commands: SessionCommand[] = []
  const run = (command: SessionCommand) => commands.push(command)

  beforeEach(() => {
    FakeAudio.created = []
    commands.length = 0
    vi.stubGlobal('Audio', FakeAudio)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('never creates an audio element for a song without audio', () => {
    renderHook(() => useAudioPlayback(sessionWith(song('mock', null)), run))

    expect(FakeAudio.created).toHaveLength(0)
  })

  it('loads the hero, plays and pauses with the session, and loads the next hero from the start', async () => {
    const { rerender } = renderHook(({ session }) => useAudioPlayback(session, run), {
      initialProps: { session: sessionWith(song('a', '/api/v1/tracks/a/audio')) },
    })
    const [audio] = FakeAudio.created

    expect(audio.src).toBe('/api/v1/tracks/a/audio')
    expect(audio.play).toHaveBeenCalledTimes(1)

    rerender({ session: sessionWith(song('a', '/api/v1/tracks/a/audio'), false) })
    expect(audio.pause).toHaveBeenCalled()

    rerender({ session: sessionWith(song('b', '/api/v1/tracks/b/audio')) })
    expect(audio.src).toBe('/api/v1/tracks/b/audio')
    expect(FakeAudio.created).toHaveLength(1) // one element, reused
  })

  it('reports the position, the duration, and the end of the song', () => {
    renderHook(() => useAudioPlayback(sessionWith(song('a', '/a.flac')), run))
    const [audio] = FakeAudio.created

    act(() => {
      audio.duration = 201.5
      audio.dispatchEvent(new Event('loadedmetadata'))
      audio.currentTime = 12.25
      audio.dispatchEvent(new Event('timeupdate'))
      audio.dispatchEvent(new Event('ended'))
    })

    expect(commands).toEqual([
      { type: 'playback_progressed', positionSeconds: 0, durationSeconds: 201.5 },
      { type: 'playback_progressed', positionSeconds: 12.25 },
      { type: 'track_ended' },
    ])
  })

  it('leaves the session paused when the browser refuses to play', async () => {
    vi.stubGlobal(
      'Audio',
      class extends FakeAudio {
        refuse = true
      },
    )
    renderHook(() => useAudioPlayback(sessionWith(song('a', '/a.flac')), run))
    await act(async () => {})

    expect(commands).toEqual([{ type: 'playback_refused' }])
  })

  it('starts the hero again from the beginning when it is replayed', () => {
    const { rerender } = renderHook(({ session }) => useAudioPlayback(session, run), {
      initialProps: { session: sessionWith(song('a', '/a.flac')) },
    })
    const [audio] = FakeAudio.created
    audio.currentTime = 90

    rerender({ session: sessionWith(song('a', '/a.flac'), true, 1) })

    expect(audio.currentTime).toBe(0)
  })

  it('stops the audio when the hero has none', () => {
    const { rerender } = renderHook(({ session }) => useAudioPlayback(session, run), {
      initialProps: { session: sessionWith(song('a', '/a.flac')) },
    })
    const [audio] = FakeAudio.created

    rerender({ session: sessionWith(null) })

    expect(audio.pause).toHaveBeenCalled()
  })
})
