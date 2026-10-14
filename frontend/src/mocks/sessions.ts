// Mock session states: one per scene of the approved design. Each is a fixed
// snapshot; nothing here computes what to play next.
import type {
  Recommendation,
  SessionEvent,
  SessionState,
} from '../features/session/types.ts'
import { mockIntent } from './environment.ts'
import { songs } from './songs.ts'
import type { MockSong } from './songs.ts'

function recommendation(
  id: string,
  song: MockSong,
  why: Recommendation['why'],
  rest: Partial<Recommendation> = {},
): Recommendation {
  return {
    id,
    ...song,
    why,
    liked: false,
    skipped: false,
    savedToPlaylistIds: [],
    ...rest,
  }
}

const EMOTIONAL_FEEL_WITH_LIFT =
  'Keeps the emotional Afrobeats feel with enough lift to keep things moving.'

const calmDown = recommendation('calm-down', songs.calmDown, {
  summary: 'Keeps the emotional Afrobeats feel while staying relaxed.',
  reasons: [
    'Emotional, gentle — keeps the emotional tone you asked for.',
    'Keeps the energy relaxed.',
  ],
})

const lastLast = recommendation('last-last', songs.lastLast, {
  summary: EMOTIONAL_FEEL_WITH_LIFT,
  reasons: [
    'Bittersweet, steady groove — keeps the emotional tone you asked for.',
    'Medium energy, so the session keeps moving.',
  ],
})

const lastLastAfterEnergyRaised: Recommendation = {
  ...lastLast,
  why: {
    summary: EMOTIONAL_FEEL_WITH_LIFT,
    reasons: [
      'Bittersweet, steady groove — keeps the emotional tone you asked for.',
      'Raises the energy without losing the feel.',
    ],
  },
}

const rush = recommendation('rush', songs.rush, {
  summary: EMOTIONAL_FEEL_WITH_LIFT,
  reasons: ['Bright, mid-tempo — keeps the emotional tone you asked for.'],
})

const loveNwantiti = recommendation('love-nwantiti', songs.loveNwantiti, {
  summary: EMOTIONAL_FEEL_WITH_LIFT,
  reasons: [
    'Romantic, swaying — keeps the emotional tone you asked for.',
    'Medium energy, so the session keeps moving.',
  ],
})

const soso = recommendation('soso', songs.soso, {
  summary: 'Soft, unhurried Afrobeats while staying relaxed.',
  reasons: ['Mellow, tender — keeps things soft and unhurried.'],
})

const essence = recommendation('essence', songs.essence, {
  summary: 'Soft, unhurried Afrobeats while staying relaxed.',
  reasons: ['Warm, slow groove — keeps things soft and unhurried.'],
})

const monalisa = recommendation('monalisa', songs.monalisa, {
  summary: 'A steady Afrobeats pulse with a lift to keep you awake.',
  reasons: [
    'Smooth, steady pulse — stays steady enough to hold your focus.',
    'A step more energy, so you stay alert without losing focus.',
  ],
})

const emotionalLow = mockIntent('emotional', 'afrobeats', 'low')
const emotionalMedium = mockIntent('emotional', 'afrobeats', 'medium')
const calmLow = mockIntent('calm', 'afrobeats', 'low')
const focusedMedium = mockIntent('focused', 'afrobeats', 'medium')

const openingTurn: SessionEvent[] = [
  { kind: 'user_message', id: 'e1', text: 'I want emotional Afrobeats.' },
  { kind: 'intent_set', id: 'e2', intent: emotionalLow },
  { kind: 'recommendation', id: 'e3', recommendationId: calmDown.id },
]

const energyRaisedTurn: SessionEvent[] = [
  { kind: 'user_message', id: 'e4', text: 'Make it more energetic.' },
  {
    kind: 'intent_updated',
    id: 'e5',
    changes: [
      {
        dimension: 'energy',
        from: emotionalLow.energy,
        to: emotionalMedium.energy,
      },
    ],
  },
  { kind: 'recommendation', id: 'e6', recommendationId: lastLast.id },
]

const blank: SessionState = {
  id: 'new',
  title: 'New session',
  intent: null,
  changedDimensions: [],
  events: [],
  recommendations: {},
  currentRecommendationId: null,
  playback: { playing: false, positionSeconds: 0 },
  whyExpanded: false,
  quickActions: [],
  upNextRecommendationId: null,
  refine: null,
  overlay: null,
}

const initial: SessionState = {
  ...blank,
  id: 'emotional-afrobeats',
  title: 'Emotional Afrobeats',
  intent: emotionalLow,
  events: openingTurn,
  recommendations: { [calmDown.id]: calmDown },
  currentRecommendationId: calmDown.id,
  playback: { playing: true, positionSeconds: 72 },
  quickActions: [
    { id: 'more-like-this', label: 'More like this' },
    { id: 'a-bit-calmer', label: 'A bit calmer' },
  ],
}

const change: SessionState = {
  ...initial,
  intent: emotionalMedium,
  changedDimensions: ['energy'],
  events: [...openingTurn, ...energyRaisedTurn],
  recommendations: {
    [calmDown.id]: { ...calmDown, liked: true },
    [lastLast.id]: lastLastAfterEnergyRaised,
  },
  currentRecommendationId: lastLast.id,
  playback: { playing: true, positionSeconds: 41 },
  quickActions: [
    { id: 'keep-this-energy', label: 'Keep this energy' },
    { id: 'more-energetic', label: 'More energetic' },
  ],
}

const save: SessionState = {
  ...change,
  changedDimensions: [],
  recommendations: {
    [calmDown.id]: { ...calmDown, liked: true },
    [lastLast.id]: { ...lastLast, echo: 'Save this.' },
  },
  playback: { playing: true, positionSeconds: 88 },
  overlay: {
    type: 'playlist_picker',
    selectedPlaylistIds: [],
    suggestedPlaylistIds: ['afrobeats'],
  },
}

const discovery: SessionState = {
  ...change,
  changedDimensions: [],
  events: [
    ...openingTurn,
    ...energyRaisedTurn,
    { kind: 'recommendation', id: 'e7', recommendationId: rush.id },
    { kind: 'intent_unchanged', id: 'e8', cause: 'not_for_me' },
    { kind: 'recommendation', id: 'e9', recommendationId: loveNwantiti.id },
  ],
  recommendations: {
    [calmDown.id]: { ...calmDown, liked: true },
    [lastLast.id]: { ...lastLast, savedToPlaylistIds: ['afrobeats'] },
    [rush.id]: { ...rush, skipped: true },
    [loveNwantiti.id]: loveNwantiti,
    [monalisa.id]: monalisa,
  },
  currentRecommendationId: loveNwantiti.id,
  playback: { playing: true, positionSeconds: 23 },
  quickActions: [
    { id: 'more-like-this', label: 'More like this' },
    { id: 'something-new', label: 'Something new' },
  ],
  upNextRecommendationId: monalisa.id,
}

const refine: SessionState = {
  ...blank,
  id: 'late-night-study',
  title: 'Late Night Study',
  intent: focusedMedium,
  changedDimensions: ['mood', 'energy'],
  events: [
    { kind: 'user_message', id: 'e1', text: 'Soft Afrobeats for studying.' },
    { kind: 'intent_set', id: 'e2', intent: calmLow },
    { kind: 'recommendation', id: 'e3', recommendationId: soso.id },
    { kind: 'recommendation', id: 'e4', recommendationId: essence.id },
    {
      kind: 'user_message',
      id: 'e5',
      text: 'I’m getting sleepy but still need to study.',
    },
    {
      kind: 'intent_updated',
      id: 'e6',
      changes: [
        { dimension: 'mood', from: calmLow.mood, to: focusedMedium.mood },
        { dimension: 'energy', from: calmLow.energy, to: focusedMedium.energy },
      ],
    },
    { kind: 'recommendation', id: 'e7', recommendationId: monalisa.id },
  ],
  recommendations: {
    [soso.id]: soso,
    [essence.id]: essence,
    [monalisa.id]: monalisa,
  },
  currentRecommendationId: monalisa.id,
  playback: { playing: true, positionSeconds: 64 },
  quickActions: [
    { id: 'fewer-vocals', label: 'Fewer vocals' },
    { id: 'keep-this-energy', label: 'Keep this energy' },
  ],
  refine: { tab: 'energy' },
}

const drawer: SessionState = {
  ...initial,
  overlay: { type: 'session_drawer' },
}

/** Keyed by the scene names of the approved design export. */
export const mockSessions = {
  new: blank,
  initial,
  change,
  save,
  discovery,
  refine,
  drawer,
} satisfies Record<string, SessionState>
