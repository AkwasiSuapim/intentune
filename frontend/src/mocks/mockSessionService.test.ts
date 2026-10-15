import { describe, expect, it } from 'vitest'
import type {
  SessionTurn,
  TurnContext,
  TurnRequest,
} from '../features/session/sessionService.ts'
import { mockEnvironment, mockIntent } from './environment.ts'
import { mockSessionService as service } from './mockSessionService.ts'

const fresh: TurnContext = {
  intent: null,
  currentSongId: null,
  playedSongIds: [],
  recommendationsSinceIntentChange: 0,
}

const playing: TurnContext = {
  intent: mockIntent('emotional', 'afrobeats', 'low'),
  currentSongId: 'calmDown',
  playedSongIds: ['calmDown'],
  recommendationsSinceIntentChange: 1,
}

async function turn(
  context: TurnContext,
  request: TurnRequest,
): Promise<SessionTurn> {
  const response = await service.respond(context, request)
  if (response.kind !== 'turn') throw new Error(`Expected a turn, got ${response.kind}`)
  return response.turn
}

const say = (context: TurnContext, text: string) =>
  turn(context, { kind: 'message', text })

const describeIntent = ({ intent }: SessionTurn) =>
  [intent.mood.label, intent.genre.label, intent.energy.label].join(' / ')

describe('answering through the service interface', () => {
  it('answers asynchronously, as a backend would', () => {
    expect(service.respond(playing, { kind: 'next' })).toBeInstanceOf(Promise)
    expect(service.loadWorkspace()).toBeInstanceOf(Promise)
  })

  it('rejects a request it cannot answer, rather than throwing', async () => {
    const answer = service.respond(fresh, {
      kind: 'refine',
      dimension: 'energy',
      valueId: 'high',
    })

    await expect(answer).rejects.toThrow('Cannot refine before an intent')
  })
})

describe('reading a first request', () => {
  it.each([
    ['Help me focus', 'Focused / Any genre / Medium', 'Focus'],
    ['Something to unwind to', 'Calm / Any genre / Low', 'Unwind'],
    ['Get me moving', 'Driven / Any genre / High', 'Move'],
    ['Surprise me', 'Open mood / Any genre / Medium', 'Discovery'],
    ['I want emotional Afrobeats.', 'Emotional / Afrobeats / Low', 'Emotional Afrobeats'],
    ['Hard-hitting Amapiano for the gym.', 'Driven / Amapiano / High', 'High-energy Amapiano'],
    ['play anything', 'Open mood / Any genre / Medium', 'Discovery'],
  ])('reads "%s" as %s', async (text, intent, title) => {
    const result = await say(fresh, text)

    expect(describeIntent(result)).toBe(intent)
    expect(result.title).toBe(title)
    expect(result.userText).toBe(text)
    expect(result.acknowledgement).toBe('intent')
    expect(result.recommendation).not.toBeNull()
  })
})

describe('reading a follow-up', () => {
  it.each([
    ['Make it more energetic.', 'Emotional / Afrobeats / Medium'],
    ['A bit calmer', 'Emotional / Afrobeats / Very low'],
    ['Switch genre', 'Emotional / Amapiano / Low'],
    ['Something to study to', 'Focused / Afrobeats / Low'],
    ['More like this', 'Emotional / Afrobeats / Low'],
  ])('reads "%s" as %s', async (text, intent) => {
    expect(describeIntent(await say(playing, text))).toBe(intent)
  })

  it('names what it is holding when asked to keep something', async () => {
    expect((await say(playing, 'Keep this energy')).ackLabel).toBe('Holding low energy')
    expect((await say(playing, 'Keep this mood')).ackLabel).toBe('Holding the emotional mood')
    expect((await say(playing, 'Different artist')).ackLabel).toBe('Trying a different artist')
  })

  it('stops at the ends of the energy range', async () => {
    const top = { ...playing, intent: mockIntent('driven', 'afrobeats', 'very-high') }
    const bottom = { ...playing, intent: mockIntent('calm', 'afrobeats', 'very-low') }

    expect((await say(top, 'Push it harder')).intent.energy.id).toBe('very-high')
    expect((await say(bottom, 'Even calmer')).intent.energy.id).toBe('very-low')
  })

  it('opens tuning on energy when the listener is flagging', async () => {
    const result = await say(playing, 'I’m getting sleepy but still need to study.')

    expect(describeIntent(result)).toBe('Focused / Afrobeats / Medium')
    expect(result.refineTab).toBe('energy')
  })

  it('treats saving, liking and rejecting as reactions to the current song', async () => {
    expect(await service.respond(playing, { kind: 'message', text: 'Save this' })).toEqual({
      kind: 'save_requested',
      echo: 'Save this',
    })
    expect(await service.respond(playing, { kind: 'message', text: 'I love this' })).toEqual({
      kind: 'liked',
      echo: 'I love this',
    })
    expect(await say(playing, 'not for me')).toMatchObject({
      acknowledgement: 'not_for_me',
      userText: 'not for me',
      intent: playing.intent,
    })
  })

  it('has nothing to react to before a song is playing', async () => {
    expect((await service.respond(fresh, { kind: 'message', text: 'Save this' })).kind).toBe('turn')
  })
})

describe('choosing what plays next', () => {
  it('is deterministic', async () => {
    expect(await say(playing, 'More like this')).toEqual(await say(playing, 'More like this'))
  })

  it('reads the next song from the fixed list for the genre and energy', async () => {
    expect((await say(fresh, 'I want emotional Afrobeats.')).recommendation?.title).toBe('Calm Down')
    expect((await say(playing, 'More like this')).recommendation?.title).toBe('Essence')
    expect((await say(playing, 'Make it more energetic.')).recommendation?.title).toBe('Last Last')
  })

  it('never repeats the current song, even when everything has been played', async () => {
    const exhausted: TurnContext = {
      ...playing,
      currentSongId: 'peru',
      playedSongIds: [
        'calmDown', 'essence', 'soso', 'kuLoSa', 'lastLast', 'rush', 'loveNwantiti',
        'monalisa', 'peru', 'joha', 'water', 'mnike', 'freeMind',
      ],
    }

    const next = (await turn(exhausted, { kind: 'next' })).recommendation

    expect(next).not.toBeNull()
    expect(next?.songId).not.toBe('peru')
  })

  it('says so when it has to leave the requested genre', async () => {
    const outOfAlte: TurnContext = {
      intent: mockIntent('focused', 'alte', 'low'),
      currentSongId: 'freeMind',
      playedSongIds: ['freeMind'],
      recommendationsSinceIntentChange: 1,
    }

    expect((await turn(outOfAlte, { kind: 'next' })).recommendation?.why.summary).toBe(
      'The closest match while Alté picks run thin.',
    )
  })

  it('explains a recommendation in terms of the intent it answers', async () => {
    expect((await say(playing, 'Make it more energetic.')).recommendation?.why).toEqual({
      summary:
        'Keeps the emotional Afrobeats feel with enough lift to keep things moving.',
      reasons: [
        'Bittersweet, steady groove — keeps the emotional tone you asked for.',
        'Raises the energy without losing the feel.',
      ],
    })
  })

  it('offers a peek only after a few songs in the same direction', async () => {
    const settled = { ...playing, recommendationsSinceIntentChange: 2 }

    expect((await turn(playing, { kind: 'next' })).upNext).toBeNull()
    expect((await turn(settled, { kind: 'next' })).upNext).not.toBeNull()
    expect((await say(settled, 'Make it more energetic.')).upNext).toBeNull()
  })
})

describe('tuning requests', () => {
  it.each([
    ['energy', 'high', 'Energy adjusted'],
    ['mood', 'calm', 'Mood adjusted'],
    ['genre', 'amapiano', 'Genre switched'],
  ] as const)('sets %s to %s and keeps tuning open there', async (dimension, valueId, label) => {
    const result = await turn(playing, { kind: 'refine', dimension, valueId })

    expect(result.intent[dimension].id).toBe(valueId)
    expect(result.ackLabel).toBe(label)
    expect(result.refineTab).toBe(dimension)
  })
})

describe('quick actions', () => {
  const contexts = [fresh, playing, { ...playing, recommendationsSinceIntentChange: 4 }]
  const messages = [
    'Help me focus', 'Something to unwind to', 'Get me moving', 'Surprise me',
    'Make it more energetic.', 'A bit calmer', 'More like this', 'Switch genre',
  ]

  it('never offers more than two', async () => {
    for (const context of contexts) {
      for (const text of messages) {
        expect((await say(context, text)).quickActions.length).toBeLessThanOrEqual(2)
      }
    }
    expect((await turn(playing, { kind: 'not_for_me' })).quickActions).toHaveLength(2)
    expect((await turn(playing, { kind: 'next' })).quickActions).toHaveLength(2)
    expect(await service.quickActionsAfter('liked')).toHaveLength(2)
    expect(await service.quickActionsAfter('saved')).toHaveLength(2)
  })

  it('offers only actions the mock itself understands', async () => {
    const offered = new Set<string>()
    for (const context of contexts) {
      for (const text of messages) {
        for (const action of (await say(context, text)).quickActions) {
          offered.add(action.label)
        }
      }
    }

    for (const label of offered) {
      const response = await service.respond(playing, { kind: 'message', text: label })
      // Understood means: a reaction, a changed intent, or a named acknowledgement.
      const understood =
        response.kind !== 'turn' ||
        response.turn.ackLabel !== undefined ||
        describeIntent(response.turn) !== 'Emotional / Afrobeats / Low'

      expect(understood, label).toBe(true)
    }
  })
})

describe('playlist hints', () => {
  it('hints at the playlist matching the genre and selects nothing', async () => {
    expect(await service.suggestPlaylists(playing, mockEnvironment.playlists)).toEqual([
      'afrobeats',
    ])
    expect(
      await service.suggestPlaylists(
        { ...playing, intent: mockIntent('driven', 'amapiano', 'high') },
        mockEnvironment.playlists,
      ),
    ).toEqual([])
  })
})

describe('the seeded workspace', () => {
  it('seeds sessions that each already have one current recommendation', async () => {
    const { sessions } = await service.loadWorkspace()

    expect(sessions.map((session) => session.title)).toEqual([
      'Emotional Afrobeats',
      'Late Night Study',
      'Gym Energy',
      'Coding',
      'Morning Focus',
    ])
    for (const session of sessions) {
      expect(session.recommendations[session.currentRecommendationId ?? '']).toBeDefined()
      expect(session.overlay).toBeNull()
      expect(session.refine).toBeNull()
      expect(session.openRequest).toBeNull()
    }
  })
})
