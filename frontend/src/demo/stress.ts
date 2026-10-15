// Deliberately awkward content for checking the layout: long titles, long
// names, an unbroken word, and artwork that fights the text over it.
import { createSession } from '../features/session/sessionReducer.ts'
import type {
  Intent,
  SessionEnvironment,
  SessionState,
} from '../features/session/types.ts'
import { mockEnvironment } from '../mocks/environment.ts'
import whiteArt from './artwork/white.svg'

const intent: Intent = {
  mood: { id: 'bittersweet', label: 'Bittersweet and nostalgic' },
  genre: { id: 'afro-fusion', label: 'Afro-fusion and highlife' },
  energy: { id: 'very-high', label: 'Very high' },
}

const earlierIntent: Intent = {
  ...intent,
  energy: { id: 'very-low', label: 'Very low' },
}

const longSong = {
  songId: 'long',
  title: 'A Song With A Title That Keeps Going Well Past Any Sensible Length (Extended Live Version)',
  artist: 'The Orchestra of Extraordinarily Long Names featuring Several Guests',
  descriptors: ['Afro-fusion and highlife', 'Bittersweet and nostalgic', 'Unhurried and spacious'],
  artworkUrl: whiteArt,
  durationSeconds: 3725,
  why: {
    summary:
      'Keeps the bittersweet, nostalgic Afro-fusion and highlife feel you asked for, at the very high energy you set, without losing the unhurried, spacious character of the last few songs.',
    reasons: [
      'Unhurried and spacious — keeps the bittersweet tone you asked for while the energy climbs.',
      'Very high energy, matching the pace you set a moment ago.',
    ],
  },
  liked: false,
  skipped: false,
  savedToPlaylistIds: [],
}

const base: SessionState = {
  ...createSession('stress'),
  title: 'Late night bittersweet Afro-fusion for the long drive home after work',
  intent,
  changedDimensions: ['energy'],
  events: [
    {
      kind: 'user_message',
      id: 'e1',
      text: 'Something bittersweet and nostalgic, Afro-fusion or highlife, for a long drive — Supercalifragilisticexpialidocious-and-then-some-more-without-a-single-break.',
    },
    { kind: 'intent_set', id: 'e2', intent: earlierIntent },
    { kind: 'recommendation', id: 'e3', recommendationId: 'earlier' },
    {
      kind: 'intent_updated',
      id: 'e4',
      label: 'Energy adjusted after your last request',
      changes: [
        { dimension: 'energy', from: earlierIntent.energy, to: intent.energy },
      ],
    },
    { kind: 'recommendation', id: 'e5', recommendationId: 'current' },
  ],
  recommendations: {
    earlier: {
      ...longSong,
      id: 'earlier',
      artworkUrl: null,
      savedToPlaylistIds: ['long-playlist'],
    },
    current: { ...longSong, id: 'current', echo: 'Save this to my driving playlist, please.' },
    'up-next': { ...longSong, id: 'up-next', artworkUrl: null },
  },
  currentRecommendationId: 'current',
  playback: { playing: true, positionSeconds: 3601 },
  quickActions: [
    { id: 'a', label: 'Keep this exact energy going' },
    { id: 'b', label: 'Something completely different' },
  ],
  upNextRecommendationId: 'up-next',
}

export const stressEnvironment: SessionEnvironment = {
  ...mockEnvironment,
  playlists: [
    {
      id: 'long-playlist',
      name: 'Driving home late on a rainy Thursday in the middle of November',
      tone: 'dusk',
    },
    ...mockEnvironment.playlists,
  ],
  sessions: [
    { id: 'stress', title: base.title, intent },
    ...mockEnvironment.sessions,
  ],
}

export const stressSessions = {
  stress: base,
  'stress-tune': { ...base, refine: { tab: 'mood' } },
  'stress-save': {
    ...base,
    overlay: {
      type: 'playlist_picker',
      selectedPlaylistIds: ['long-playlist', 'study'],
      suggestedPlaylistIds: ['long-playlist'],
    },
  },
  'stress-drawer': { ...base, overlay: { type: 'session_drawer' } },
} satisfies Record<string, SessionState>
