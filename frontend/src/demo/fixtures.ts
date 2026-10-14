// Component-prop fixtures for the gallery. Songs, starters and tuning options
// come from the shared mocks; nothing here selects, scores or ranks music.
import type { IntentChange } from '../components/Ack.tsx'
import type { IntentChip } from '../components/IntentSummary.tsx'
import type { PlaylistOption } from '../components/PlaylistPicker.tsx'
import type { QuickAction } from '../components/QuickActions.tsx'
import type { DrawerSession } from '../components/SessionDrawer.tsx'
import { mockEnvironment } from '../mocks/environment.ts'

export { songs } from '../mocks/songs.ts'

export const intents = {
  emotionalLow: [
    { id: 'mood', label: 'Emotional' },
    { id: 'genre', label: 'Afrobeats' },
    { id: 'energy', label: 'Low energy' },
  ],
  emotionalMedium: [
    { id: 'mood', label: 'Emotional' },
    { id: 'genre', label: 'Afrobeats' },
    { id: 'energy', label: 'Medium energy' },
  ],
  emotionalEnergyRaised: [
    { id: 'mood', label: 'Emotional' },
    { id: 'genre', label: 'Afrobeats' },
    { id: 'energy', label: 'Medium energy', changed: true },
  ],
  focusedWhileTuning: [
    { id: 'mood', label: 'Focused', changed: true },
    { id: 'genre', label: 'Afrobeats' },
    { id: 'energy', label: 'Medium energy', changed: true, expanded: true },
  ],
  genreOpen: [
    { id: 'mood', label: 'Emotional' },
    { id: 'genre', label: 'Afrobeats', expanded: true },
    { id: 'energy', label: 'Low energy' },
  ],
  manyChips: [
    { id: 'mood', label: 'Emotional' },
    { id: 'genre', label: 'Afrobeats' },
    { id: 'energy', label: 'Medium energy' },
    { id: 'vocals', label: 'Fewer vocals', changed: true },
    { id: 'era', label: 'Recent releases' },
  ],
} satisfies Record<string, IntentChip[]>

export const intentChanges = {
  energyRaised: [{ dimension: 'Energy', from: 'Low', to: 'Medium' }],
  moodAndEnergy: [
    { dimension: 'Mood', from: 'Calm', to: 'Focused' },
    { dimension: 'Energy', from: 'Low', to: 'Medium' },
  ],
} satisfies Record<string, IntentChange[]>

export const whyThisFits = {
  calmDown: {
    summary: 'Keeps the emotional Afrobeats feel while staying relaxed.',
    reasons: [
      'Emotional, gentle — keeps the emotional tone you asked for.',
      'Keeps the energy relaxed.',
    ],
  },
  lastLastEnergyRaised: {
    summary:
      'Keeps the emotional Afrobeats feel with enough lift to keep things moving.',
    reasons: [
      'Bittersweet, steady groove — keeps the emotional tone you asked for.',
      'Raises the energy without losing the feel.',
    ],
  },
  lastLast: {
    summary:
      'Keeps the emotional Afrobeats feel with enough lift to keep things moving.',
    reasons: [
      'Bittersweet, steady groove — keeps the emotional tone you asked for.',
      'Medium energy, so the session keeps moving.',
    ],
  },
  loveNwantiti: {
    summary:
      'Keeps the emotional Afrobeats feel with enough lift to keep things moving.',
    reasons: [
      'Romantic, swaying — keeps the emotional tone you asked for.',
      'Medium energy, so the session keeps moving.',
    ],
  },
  monalisa: {
    summary: 'A steady Afrobeats pulse with a lift to keep you awake.',
    reasons: [
      'Smooth, steady pulse — stays steady enough to hold your focus.',
      'A step more energy, so you stay alert without losing focus.',
    ],
  },
  peru: {
    summary: 'Bright, easy Afrobeats at a strong pace.',
    reasons: [
      'Playful, upbeat — keeps things bright.',
      'High energy, matching the pace you set.',
    ],
  },
  kuLoSa: {
    summary: 'Keeps the emotional Afrobeats feel while staying relaxed.',
    reasons: [],
  },
} satisfies Record<string, { summary: string; reasons: string[] }>

export const quickActions = {
  initial: [
    { id: 'more-like-this', label: 'More like this' },
    { id: 'a-bit-calmer', label: 'A bit calmer' },
  ],
  energyRaised: [
    { id: 'keep-this-energy', label: 'Keep this energy' },
    { id: 'more-energetic', label: 'More energetic' },
  ],
  continuing: [
    { id: 'more-like-this', label: 'More like this' },
    { id: 'something-new', label: 'Something new' },
  ],
  // Three offered: the interface still shows only two.
  threeOffered: [
    { id: 'different-artist', label: 'Different artist' },
    { id: 'keep-this-mood', label: 'Keep this mood' },
    { id: 'change-genre', label: 'Change genre' },
  ],
} satisfies Record<string, QuickAction[]>

export const refineOptions = {
  energyLevels: mockEnvironment.refineOptions.energy,
  moods: mockEnvironment.refineOptions.mood,
  genres: mockEnvironment.refineOptions.genre,
}

export const playlists: PlaylistOption[] = [
  { id: 'favorites', name: 'Favorites', tone: 'violet' },
  { id: 'study', name: 'Study', tone: 'indigo' },
  { id: 'workout', name: 'Workout', tone: 'ember' },
  { id: 'afrobeats', name: 'Afrobeats', tone: 'dusk', fitsSession: true },
]

export const sessions: DrawerSession[] = [
  {
    id: 'emotional-afrobeats',
    title: 'Emotional Afrobeats',
    subtitle: 'Emotional · Afrobeats · Low energy',
    active: true,
  },
  {
    id: 'late-night-study',
    title: 'Late Night Study',
    subtitle: 'Focused · Afrobeats · Medium energy',
  },
  {
    id: 'gym-energy',
    title: 'Gym Energy',
    subtitle: 'Driven · Amapiano · High energy',
  },
  { id: 'coding', title: 'Coding', subtitle: 'Focused · Alté · Low energy' },
  {
    id: 'morning-focus',
    title: 'Morning Focus',
    subtitle: 'Calm · Afrobeats · Low energy',
  },
]

export const starters = mockEnvironment.starters

export const composerPlaceholders = {
  firstTurn: 'Tell Intentune what you want…',
  nextTurn: 'Tell Intentune what you want next…',
}
