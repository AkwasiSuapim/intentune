// Representative fixture props for the demo compositions. Static display data
// only: nothing here selects, scores or ranks music.
import type { IntentChange } from '../components/Ack.tsx'
import type { StarterIntent } from '../components/DiscoveryPrompt.tsx'
import type { IntentChip } from '../components/IntentSummary.tsx'
import type { PlaylistOption } from '../components/PlaylistPicker.tsx'
import type { QuickAction } from '../components/QuickActions.tsx'
import type { RefineOption } from '../components/RefineControl.tsx'
import type { DrawerSession } from '../components/SessionDrawer.tsx'
import calmDownArt from './artwork/calm-down.svg'
import essenceArt from './artwork/essence.svg'
import lastLastArt from './artwork/last-last.svg'
import loveNwantitiArt from './artwork/love-nwantiti.svg'
import mnikeArt from './artwork/mnike.svg'
import monalisaArt from './artwork/monalisa.svg'
import peruArt from './artwork/peru.svg'
import rushArt from './artwork/rush.svg'
import sosoArt from './artwork/soso.svg'

type SongFixture = {
  title: string
  artist: string
  descriptors: string[]
  artworkUrl: string | null
  durationSeconds: number
}

export const songs = {
  calmDown: {
    title: 'Calm Down',
    artist: 'Rema',
    descriptors: ['Afrobeats', 'Emotional', 'Gentle'],
    artworkUrl: calmDownArt,
    durationSeconds: 239,
  },
  lastLast: {
    title: 'Last Last',
    artist: 'Burna Boy',
    descriptors: ['Afrobeats', 'Bittersweet', 'Steady groove'],
    artworkUrl: lastLastArt,
    durationSeconds: 172,
  },
  rush: {
    title: 'Rush',
    artist: 'Ayra Starr',
    descriptors: ['Afrobeats', 'Bright', 'Mid-tempo'],
    artworkUrl: rushArt,
    durationSeconds: 185,
  },
  loveNwantiti: {
    title: 'Love Nwantiti',
    artist: 'CKay',
    descriptors: ['Afro-pop', 'Romantic', 'Swaying'],
    artworkUrl: loveNwantitiArt,
    durationSeconds: 145,
  },
  essence: {
    title: 'Essence',
    artist: 'Wizkid ft. Tems',
    descriptors: ['Afrobeats', 'Warm', 'Slow groove'],
    artworkUrl: essenceArt,
    durationSeconds: 248,
  },
  soso: {
    title: 'Soso',
    artist: 'Omah Lay',
    descriptors: ['Afrobeats', 'Mellow', 'Tender'],
    artworkUrl: sosoArt,
    durationSeconds: 190,
  },
  monalisa: {
    title: 'Monalisa',
    artist: 'Lojay & Sarz',
    descriptors: ['Afrobeats', 'Smooth', 'Steady pulse'],
    artworkUrl: monalisaArt,
    durationSeconds: 177,
  },
  // Bright, low-contrast artwork: exercises the text contrast treatment.
  peru: {
    title: 'Peru',
    artist: 'Fireboy DML',
    descriptors: ['Afrobeats', 'Playful', 'Upbeat'],
    artworkUrl: peruArt,
    durationSeconds: 187,
  },
  // No artwork and a long title: exercises the fallback and clamping.
  kuLoSa: {
    title: 'Ku Lo Sa – A COLORS SHOW',
    artist: 'Oxlade',
    descriptors: ['Afro-soul', 'Intimate', 'Hushed'],
    artworkUrl: null,
    durationSeconds: 151,
  },
} satisfies Record<string, SongFixture>

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
  energyLevels: [
    { id: 'very-low', label: 'Very low' },
    { id: 'low', label: 'Low' },
    { id: 'medium', label: 'Medium' },
    { id: 'high', label: 'High' },
    { id: 'very-high', label: 'Very high' },
  ],
  moods: [
    { id: 'emotional', label: 'Emotional' },
    { id: 'focused', label: 'Focused' },
    { id: 'calm', label: 'Calm' },
    { id: 'joyful', label: 'Joyful' },
    { id: 'driven', label: 'Driven' },
  ],
  genres: [
    { id: 'afrobeats', label: 'Afrobeats' },
    { id: 'amapiano', label: 'Amapiano' },
    { id: 'alte', label: 'Alté' },
    { id: 'any', label: 'Any genre' },
  ],
} satisfies Record<string, RefineOption[]>

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

export const starters: StarterIntent[] = [
  {
    id: 'focus',
    label: 'Focus',
    phrase: 'Help me focus',
    artworkUrl: monalisaArt,
  },
  {
    id: 'unwind',
    label: 'Unwind',
    phrase: 'Something to unwind to',
    artworkUrl: essenceArt,
  },
  { id: 'move', label: 'Move', phrase: 'Get me moving', artworkUrl: mnikeArt },
  {
    id: 'discover',
    label: 'Discover',
    phrase: 'Surprise me',
    artworkUrl: rushArt,
  },
]

export const composerPlaceholders = {
  firstTurn: 'Tell Intentune what you want…',
  nextTurn: 'Tell Intentune what you want next…',
}
