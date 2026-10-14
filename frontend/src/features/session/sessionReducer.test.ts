import { describe, expect, it } from 'vitest'
import { mockEnvironment, mockIntent } from '../../mocks/environment.ts'
import { mockSessions } from '../../mocks/sessions.ts'
import { composeSession } from './composeSession.ts'
import { createSession, sessionReducer } from './sessionReducer.ts'
import type { SessionAction } from './sessionReducer.ts'
import type { RecommendedSong, SessionTurn } from './sessionService.ts'
import type { SessionState } from './types.ts'

const apply = (state: SessionState, ...actions: SessionAction[]) =>
  actions.reduce(sessionReducer, state)

const blocks = (state: SessionState) =>
  composeSession(state, mockEnvironment).content

const song = (songId: string, title: string): RecommendedSong => ({
  songId,
  title,
  artist: 'Artist',
  descriptors: ['Afrobeats', 'Warm', 'Steady'],
  artworkUrl: null,
  durationSeconds: 180,
  why: { summary: `Why ${title}`, reasons: [] },
})

const emotionalLow = mockIntent('emotional', 'afrobeats', 'low')
const emotionalMedium = mockIntent('emotional', 'afrobeats', 'medium')

function turn(overrides: Partial<SessionTurn> = {}): SessionTurn {
  return {
    intent: emotionalLow,
    acknowledgement: 'intent',
    recommendation: song('first', 'First Song'),
    quickActions: [{ id: 'more', label: 'More like this' }],
    upNext: null,
    ...overrides,
  }
}

const started = apply(createSession('s1'), {
  type: 'turn_applied',
  turn: turn({ userText: 'I want emotional Afrobeats.', title: 'Emotional' }),
})

describe('a turn', () => {
  it('starts a session: message, acknowledgement, recommendation, in that order', () => {
    expect(started.events.map((event) => event.kind)).toEqual([
      'user_message',
      'intent_set',
      'recommendation',
    ])
    expect(started.title).toBe('Emotional')
    expect(started.intent).toEqual(emotionalLow)
    expect(started.playback).toEqual({ playing: true, positionSeconds: 0 })
    expect(blocks(started).at(-1)).toMatchObject({
      type: 'recommendation',
      variant: 'hero',
      title: 'First Song',
    })
  })

  it('moves the previous hero into compact history when a new recommendation arrives', () => {
    const next = apply(started, {
      type: 'turn_applied',
      turn: turn({ recommendation: song('second', 'Second Song') }),
    })
    const recommendations = blocks(next).filter(
      (block) => block.type === 'recommendation',
    )

    expect(recommendations.map((block) => [block.title, block.variant])).toEqual(
      [
        ['First Song', 'compact'],
        ['Second Song', 'hero'],
      ],
    )
  })

  it('reports a changed intent as from-to changes and marks the dimension', () => {
    const next = apply(started, {
      type: 'turn_applied',
      turn: turn({ intent: emotionalMedium, userText: 'More energy.' }),
    })

    expect(next.intent).toEqual(emotionalMedium)
    expect(next.changedDimensions).toEqual(['energy'])
    expect(next.events.at(-2)).toMatchObject({
      kind: 'intent_updated',
      changes: [
        { dimension: 'energy', from: emotionalLow.energy, to: emotionalMedium.energy },
      ],
    })
  })

  it('reports an unchanged intent as kept, with the wording it was given', () => {
    const next = apply(started, {
      type: 'turn_applied',
      turn: turn({ ackLabel: 'Keeping this direction' }),
    })

    expect(next.changedDimensions).toEqual([])
    expect(next.events.at(-2)).toMatchObject({
      kind: 'intent_kept',
      label: 'Keeping this direction',
      intent: emotionalLow,
    })
  })

  it('never lets the acknowledgement disagree with the intent summary', () => {
    const next = apply(started, {
      type: 'turn_applied',
      turn: turn({ intent: mockIntent('focused', 'amapiano', 'high') }),
    })
    const view = composeSession(next, mockEnvironment)
    const chips = view.intentSummary?.chips ?? []
    const ack = view.content.findLast((block) => block.type === 'ack')

    expect(chips.map((chip) => chip.label)).toEqual([
      'Focused',
      'Amapiano',
      'High energy',
    ])
    expect(ack?.changes?.map((change) => change.to)).toEqual([
      'Focused',
      'Amapiano',
      'High',
    ])
    expect(chips.every((chip) => chip.changed)).toBe(true)
  })

  it('marks the current song skipped on "not for me" and leaves the intent alone', () => {
    const next = apply(started, {
      type: 'turn_applied',
      turn: turn({
        // Even if a turn carried a different intent, "not for me" keeps the current one.
        intent: emotionalMedium,
        acknowledgement: 'not_for_me',
        recommendation: song('second', 'Second Song'),
      }),
    })
    const [first, ack, second] = blocks(next).slice(-3)

    expect(next.intent).toEqual(emotionalLow)
    expect(first).toMatchObject({ variant: 'compact', outcome: 'skipped' })
    expect(ack).toMatchObject({ label: 'Not for me', detail: 'Intent unchanged' })
    expect(second).toMatchObject({ variant: 'hero', title: 'Second Song' })
  })

  it('adds no acknowledgement when simply moving to the next song', () => {
    const next = apply(started, {
      type: 'turn_applied',
      turn: turn({
        acknowledgement: 'none',
        recommendation: song('second', 'Second Song'),
      }),
    })

    expect(next.events.map((event) => event.kind)).toEqual([
      'user_message',
      'intent_set',
      'recommendation',
      'recommendation',
    ])
  })

  it('holds one Up next peek and replaces it each turn', () => {
    const peeking = apply(started, {
      type: 'turn_applied',
      turn: turn({
        acknowledgement: 'none',
        recommendation: song('second', 'Second Song'),
        upNext: song('third', 'Third Song'),
      }),
    })
    const after = apply(peeking, {
      type: 'turn_applied',
      turn: turn({
        acknowledgement: 'none',
        recommendation: song('third', 'Third Song'),
      }),
    })

    expect(blocks(peeking).at(-1)).toMatchObject({
      type: 'up_next',
      title: 'Third Song',
    })
    expect(blocks(after).at(-1)).toMatchObject({ variant: 'hero', title: 'Third Song' })
    expect(after.upNextRecommendationId).toBeNull()
    expect(Object.keys(after.recommendations)).toHaveLength(3)
  })

  it('closes overlays and the refine control unless the turn keeps tuning open', () => {
    const tuning = apply(started, { type: 'refine_opened', tab: 'mood' })
    const closed = apply(tuning, { type: 'turn_applied', turn: turn() })
    const kept = apply(tuning, {
      type: 'turn_applied',
      turn: turn({ refineTab: 'energy' }),
    })

    expect(closed.refine).toBeNull()
    expect(kept.refine).toEqual({ tab: 'energy' })
    expect(
      apply(started, { type: 'drawer_opened' }, { type: 'turn_applied', turn: turn() })
        .overlay,
    ).toBeNull()
  })

  it('does not mutate the state it was given', () => {
    const before = structuredClone(started)

    apply(started, { type: 'turn_applied', turn: turn({ intent: emotionalMedium }) })

    expect(started).toEqual(before)
  })
})

describe('reactions', () => {
  it('likes and unlikes the current song without touching the stream or the intent', () => {
    const liked = apply(started, {
      type: 'liked_set',
      liked: true,
      quickActions: [{ id: 'save', label: 'Save this' }],
    })
    const unliked = apply(liked, { type: 'liked_set', liked: false })

    expect(blocks(liked).at(-1)).toMatchObject({ variant: 'hero', liked: true })
    expect(liked.quickActions).toEqual([{ id: 'save', label: 'Save this' }])
    expect(liked.events).toBe(started.events)
    expect(liked.intent).toBe(started.intent)
    expect(blocks(unliked).at(-1)).toMatchObject({ variant: 'hero', liked: false })
    expect(unliked.quickActions).toEqual(liked.quickActions)
  })

  it('carries a like into the history once the song is no longer current', () => {
    const next = apply(
      started,
      { type: 'liked_set', liked: true },
      { type: 'turn_applied', turn: turn({ recommendation: song('second', 'Second') }) },
    )

    expect(blocks(next).find((block) => block.type === 'recommendation')).toMatchObject({
      variant: 'compact',
      outcome: 'liked',
    })
    expect(blocks(next).at(-1)).toMatchObject({ variant: 'hero', liked: false })
  })
})

describe('playlist picker', () => {
  const open = apply(started, {
    type: 'playlist_picker_opened',
    suggestedPlaylistIds: ['afrobeats'],
  })
  const picker = (state: SessionState) =>
    composeSession(state, mockEnvironment).overlay

  it('opens with nothing selected, however strongly a playlist is suggested', () => {
    expect(picker(open)?.selectedIds).toEqual([])
    expect(picker(open)?.playlists.find((p) => p.fitsSession)?.id).toBe('afrobeats')
  })

  it('selects only what the user toggles', () => {
    const toggled = apply(
      open,
      { type: 'playlist_toggled', playlistId: 'study' },
      { type: 'playlist_toggled', playlistId: 'favorites' },
      { type: 'playlist_toggled', playlistId: 'study' },
    )

    expect(picker(toggled)?.selectedIds).toEqual(['favorites'])
  })

  it('saves nothing until a playlist is chosen', () => {
    const confirmed = apply(open, { type: 'playlists_saved', quickActions: [] })

    expect(confirmed).toBe(open)
  })

  it('saves the chosen playlists, closes the sheet and updates the quick actions', () => {
    const saved = apply(
      open,
      { type: 'playlist_toggled', playlistId: 'study' },
      {
        type: 'playlists_saved',
        quickActions: [{ id: 'keep', label: 'Keep this energy' }],
      },
    )

    expect(saved.overlay).toBeNull()
    expect(blocks(saved).at(-1)).toMatchObject({ variant: 'hero', savedTo: ['Study'] })
    expect(saved.quickActions).toEqual([{ id: 'keep', label: 'Keep this energy' }])
  })

  it('discards the selection when closed without saving', () => {
    const closed = apply(
      open,
      { type: 'playlist_toggled', playlistId: 'study' },
      { type: 'playlist_picker_closed' },
    )

    expect(closed.overlay).toBeNull()
    expect(blocks(closed).at(-1)).toMatchObject({ variant: 'hero', savedTo: [] })
  })

  it('reopens on the playlists the song is already saved to', () => {
    const reopened = apply(
      open,
      { type: 'playlist_toggled', playlistId: 'study' },
      { type: 'playlists_saved', quickActions: [] },
      { type: 'playlist_picker_opened', suggestedPlaylistIds: [] },
    )

    expect(picker(reopened)?.selectedIds).toEqual(['study'])
  })

  it('cannot open without a current song', () => {
    const empty = createSession('s2')

    expect(
      apply(empty, { type: 'playlist_picker_opened', suggestedPlaylistIds: [] }),
    ).toBe(empty)
  })
})

describe('tuning and playback controls', () => {
  it('opens the refine control on a tab, switches tab and closes', () => {
    const open = apply(started, { type: 'refine_opened', tab: 'energy' })
    const switched = apply(open, { type: 'refine_opened', tab: 'genre' })

    expect(composeSession(open, mockEnvironment).contextualControl).toMatchObject({
      type: 'refine_control',
      activeTab: 'energy',
    })
    expect(switched.refine).toEqual({ tab: 'genre' })
    expect(apply(switched, { type: 'refine_closed' }).refine).toBeNull()
  })

  it('has nothing to refine before there is an intent', () => {
    const empty = createSession('s2')

    expect(apply(empty, { type: 'refine_opened', tab: 'energy' })).toBe(empty)
  })

  it('toggles playback and the explanation', () => {
    const paused = apply(started, { type: 'play_toggled' })

    expect(paused.playback.playing).toBe(false)
    expect(apply(paused, { type: 'play_toggled' }).playback.playing).toBe(true)
    expect(apply(started, { type: 'why_toggled' }).whyExpanded).toBe(true)
  })

  it('advances the position only while playing, and never past the end', () => {
    const ticked = apply(started, { type: 'playback_ticked', seconds: 5 })
    const paused = apply(ticked, { type: 'play_toggled' })

    expect(ticked.playback.positionSeconds).toBe(5)
    expect(apply(paused, { type: 'playback_ticked', seconds: 5 })).toBe(paused)
    expect(
      apply(ticked, { type: 'playback_ticked', seconds: 999 }).playback
        .positionSeconds,
    ).toBe(180)
  })

  it('collapses the explanation for a new recommendation', () => {
    const next = apply(
      started,
      { type: 'why_toggled' },
      { type: 'turn_applied', turn: turn({ recommendation: song('second', 'Second') }) },
    )

    expect(next.whyExpanded).toBe(false)
  })
})

describe('replaying history', () => {
  const state = mockSessions.change
  const replayed = apply(state, {
    type: 'recommendation_replayed',
    recommendationId: 'calm-down',
  })

  it('plays a past song again as a fresh hero and keeps its history entry', () => {
    const recommendations = blocks(replayed).filter(
      (block) => block.type === 'recommendation',
    )

    expect(recommendations.map((block) => [block.title, block.variant])).toEqual(
      [
        ['Calm Down', 'compact'],
        ['Last Last', 'compact'],
        ['Calm Down', 'hero'],
      ],
    )
    expect(recommendations[0]).toMatchObject({ outcome: 'liked' })
    expect(recommendations[2]).toMatchObject({ liked: false, positionSeconds: 0 })
  })

  it('ignores replaying the song that is already current', () => {
    expect(
      apply(state, {
        type: 'recommendation_replayed',
        recommendationId: 'last-last',
      }),
    ).toBe(state)
  })
})

describe('returning to a session', () => {
  it('adds one "picking up" summary, however often it is resumed', () => {
    const resumed = apply(
      mockSessions.initial,
      { type: 'session_resumed' },
      { type: 'session_resumed' },
    )

    expect(resumed.events.filter((event) => event.kind === 'session_resumed')).toHaveLength(1)
    // The summary reads just above the hero, which stays last.
    expect(blocks(resumed).at(-2)).toMatchObject({
      type: 'session_summary',
      detail: 'Emotional · Afrobeats · Low energy',
    })
    expect(blocks(resumed).at(-1)).toMatchObject({ variant: 'hero' })
  })

  it('has nothing to pick up in a session with no intent', () => {
    const empty = createSession('s2')

    expect(apply(empty, { type: 'session_resumed' })).toBe(empty)
  })
})
