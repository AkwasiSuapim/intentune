import { describe, expect, it } from 'vitest'
import { mockEnvironment, mockIntent } from '../../mocks/environment.ts'
import { mockSessions } from '../../mocks/sessions.ts'
import type { BlockOf } from './blocks.ts'
import { composeSession, describeIntent } from './composeSession.ts'
import type { SessionState } from './types.ts'

const compose = (state: SessionState) => composeSession(state, mockEnvironment)

function heroes(state: SessionState) {
  return compose(state).content.filter(
    (block) => block.type === 'recommendation' && block.variant === 'hero',
  )
}

describe('new session', () => {
  const view = compose(mockSessions.new)

  it('shows only the Tune in prompt', () => {
    expect(view.layout).toBe('prompt')
    expect(view.content.map((block) => block.type)).toEqual([
      'discovery_prompt',
    ])
    expect(view.intentSummary).toBeNull()
    expect(view.contextualControl).toBeNull()
    expect(view.overlay).toBeNull()
  })

  it('uses the first-turn composer placeholder', () => {
    expect(view.composerPlaceholder).toBe('Tell Intentune what you want…')
    expect(compose(mockSessions.initial).composerPlaceholder).toBe(
      'Tell Intentune what you want next…',
    )
  })
})

describe('timeline', () => {
  it('keeps events in chronological order', () => {
    expect(
      compose(mockSessions.discovery).content.map((block) => block.type),
    ).toEqual([
      'user_message',
      'ack',
      'recommendation',
      'user_message',
      'ack',
      'recommendation',
      'recommendation',
      'ack',
      'recommendation',
      'up_next',
    ])
  })

  it.each(Object.entries(mockSessions))(
    'shows at most one hero in the "%s" scene',
    (_name, state) => {
      expect(heroes(state).length).toBe(state.currentRecommendationId ? 1 : 0)
    },
  )

  it('renders the current recommendation as the hero and earlier ones as compact history', () => {
    const recommendations = compose(mockSessions.discovery).content.filter(
      (block) => block.type === 'recommendation',
    )

    expect(
      recommendations.map((block) => [block.title, block.variant]),
    ).toEqual([
      ['Calm Down', 'compact'],
      ['Last Last', 'compact'],
      ['Rush', 'compact'],
      ['Love Nwantiti', 'hero'],
    ])
  })

  it('carries each reaction into the history as its outcome', () => {
    const outcomes = compose(mockSessions.discovery).content.flatMap((block) =>
      block.type === 'recommendation' && block.variant === 'compact'
        ? [block.outcome]
        : [],
    )

    expect(outcomes).toEqual(['liked', 'saved', 'skipped'])
  })

  it('moves the hero to history when another recommendation becomes current', () => {
    const state = mockSessions.change
    const before = compose({ ...state, currentRecommendationId: 'calm-down' })
    const after = compose(state)
    const variantOf = (view: typeof before, title: string) =>
      view.content.flatMap((block) =>
        block.type === 'recommendation' && block.title === title
          ? [block.variant]
          : [],
      )

    expect(variantOf(before, 'Calm Down')).toEqual(['hero'])
    expect(variantOf(after, 'Calm Down')).toEqual(['compact'])
    expect(variantOf(after, 'Last Last')).toEqual(['hero'])
  })

  it('still yields a single hero when the current recommendation repeats in the stream', () => {
    const state: SessionState = {
      ...mockSessions.initial,
      events: [
        ...mockSessions.initial.events,
        { kind: 'recommendation', id: 'again', recommendationId: 'calm-down' },
      ],
    }

    expect(heroes(state)).toHaveLength(1)
  })

  it('leaves out a recommendation event whose recommendation is missing', () => {
    const state: SessionState = {
      ...mockSessions.initial,
      events: [
        ...mockSessions.initial.events,
        { kind: 'recommendation', id: 'ghost', recommendationId: 'missing' },
      ],
    }

    expect(compose(state).content).toHaveLength(
      compose(mockSessions.initial).content.length,
    )
  })

  it('reads hero playback, explanation and reactions from state', () => {
    const [hero] = heroes({
      ...mockSessions.change,
      whyExpanded: true,
      recommendations: {
        ...mockSessions.change.recommendations,
        'last-last': {
          ...mockSessions.change.recommendations['last-last'],
          liked: true,
          savedToPlaylistIds: ['afrobeats', 'study'],
        },
      },
    }) as BlockOf<'recommendation'>[]

    expect(hero).toMatchObject({
      variant: 'hero',
      playing: true,
      positionSeconds: 41,
      durationSeconds: 172,
      whyExpanded: true,
      liked: true,
      savedTo: ['Study', 'Afrobeats'],
    })
  })
})

describe('intent', () => {
  it('derives the intent chips from the session intent', () => {
    expect(compose(mockSessions.initial).intentSummary?.chips).toEqual([
      { id: 'mood', label: 'Emotional', changed: false, expanded: false },
      { id: 'genre', label: 'Afrobeats', changed: false, expanded: false },
      { id: 'energy', label: 'Low energy', changed: false, expanded: false },
    ])
  })

  it('marks the dimensions the latest turn changed', () => {
    const chips = compose(mockSessions.change).intentSummary?.chips ?? []

    expect(chips.filter((chip) => chip.changed).map((chip) => chip.id)).toEqual(
      ['energy'],
    )
  })

  it('spells an intent the same way wherever it appears', () => {
    const intent = mockIntent('emotional', 'afrobeats', 'low')
    const view = compose(mockSessions.drawer)
    const ack = view.content.find((block) => block.type === 'ack')
    const chips = view.intentSummary?.chips ?? []

    expect(describeIntent(intent)).toBe('Emotional · Afrobeats · Low energy')
    expect(ack).toMatchObject({ label: 'Intent set', detail: describeIntent(intent) })
    expect(chips.map((chip) => chip.label).join(' · ')).toBe(
      describeIntent(intent),
    )
    expect(view.drawer?.sessions.find((session) => session.active)?.subtitle).toBe(
      describeIntent(intent),
    )
  })

  it('agrees between the latest acknowledgement and the current intent in every scene', () => {
    for (const state of Object.values(mockSessions)) {
      const chips = compose(state).intentSummary?.chips ?? []
      const latest = state.events.findLast(
        (event) => event.kind === 'intent_set' || event.kind === 'intent_updated',
      )

      if (latest?.kind === 'intent_set') {
        expect(describeIntent(latest.intent)).toBe(
          chips.map((chip) => chip.label).join(' · '),
        )
      }
      if (latest?.kind === 'intent_updated') {
        for (const change of latest.changes) {
          expect(state.intent?.[change.dimension]).toEqual(change.to)
        }
      }
    }
  })

  it('describes an intent update as from-to changes', () => {
    const acks = compose(mockSessions.refine).content.filter(
      (block) => block.type === 'ack',
    )

    expect(acks.at(-1)).toMatchObject({
      label: 'Intent updated',
      changes: [
        { dimension: 'Mood', from: 'Calm', to: 'Focused' },
        { dimension: 'Energy', from: 'Low', to: 'Medium' },
      ],
    })
  })

  it('shifts only the accent with the mood, defaulting when the mood is unknown', () => {
    expect(compose(mockSessions.initial).accent).toBe('emotional')
    expect(compose(mockSessions.refine).accent).toBe('focused')
    expect(
      compose({
        ...mockSessions.initial,
        intent: {
          ...mockIntent('emotional', 'afrobeats', 'low'),
          mood: { id: 'wistful', label: 'Wistful' },
        },
      }).accent,
    ).toBe('emotional')
  })
})

describe('contextual control', () => {
  it('offers the quick actions for the current recommendation', () => {
    expect(compose(mockSessions.initial).contextualControl).toMatchObject({
      type: 'quick_actions',
      actions: [{ label: 'More like this' }, { label: 'A bit calmer' }],
    })
  })

  it('replaces the quick actions with the refine control while tuning', () => {
    const view = compose(mockSessions.refine)

    expect(view.contextualControl).toMatchObject({
      type: 'refine_control',
      activeTab: 'energy',
      energyId: 'medium',
      moodId: 'focused',
      genreId: 'afrobeats',
    })
    expect(view.intentSummary?.chips.find((chip) => chip.expanded)?.id).toBe(
      'energy',
    )
  })

  it('hides Up next while tuning', () => {
    const tuning: SessionState = {
      ...mockSessions.discovery,
      refine: { tab: 'mood' },
    }

    expect(compose(mockSessions.discovery).content.at(-1)?.type).toBe('up_next')
    expect(compose(tuning).content.at(-1)?.type).toBe('recommendation')
  })
})

describe('overlays', () => {
  it('opens the playlist picker with nothing preselected', () => {
    const picker = compose(mockSessions.save).overlay

    expect(picker).toMatchObject({
      type: 'playlist_picker',
      songTitle: 'Last Last',
      selectedIds: [],
    })
    expect(
      picker?.playlists.filter((playlist) => playlist.fitsSession),
    ).toMatchObject([{ id: 'afrobeats' }])
  })

  it('passes on only the playlists the user chose', () => {
    const picker = compose({
      ...mockSessions.save,
      overlay: {
        type: 'playlist_picker',
        selectedPlaylistIds: ['study'],
        suggestedPlaylistIds: ['afrobeats'],
      },
    }).overlay

    expect(picker?.selectedIds).toEqual(['study'])
  })

  it('hides the echo while the playlist picker covers the hero', () => {
    const [covered] = heroes(mockSessions.save) as BlockOf<'recommendation'>[]
    const [uncovered] = heroes({
      ...mockSessions.save,
      overlay: null,
    }) as BlockOf<'recommendation'>[]

    expect(covered).toMatchObject({ variant: 'hero', echo: undefined })
    expect(uncovered).toMatchObject({ variant: 'hero', echo: 'Save this.' })
  })

  it('needs a current recommendation to show the playlist picker', () => {
    expect(
      compose({
        ...mockSessions.new,
        overlay: {
          type: 'playlist_picker',
          selectedPlaylistIds: [],
          suggestedPlaylistIds: [],
        },
      }).overlay,
    ).toBeNull()
  })

  it('lists sessions in the drawer with the open one active', () => {
    const drawer = compose(mockSessions.drawer).drawer

    expect(drawer?.sessions.map((session) => session.title)).toEqual([
      'Emotional Afrobeats',
      'Late Night Study',
      'Gym Energy',
      'Coding',
      'Morning Focus',
    ])
    expect(drawer?.sessions.filter((session) => session.active)).toHaveLength(1)
    expect(compose(mockSessions.initial).drawer).toBeNull()
  })

  it('adds an unlisted open session to the top of the drawer', () => {
    const drawer = compose({
      ...mockSessions.new,
      overlay: { type: 'session_drawer' },
    }).drawer

    expect(drawer?.sessions[0]).toEqual({
      id: 'new',
      title: 'New session',
      subtitle: 'No intent yet',
      active: true,
    })
  })
})
