// Mock song display data. Static: nothing here selects, scores or ranks music.
import calmDownArt from './artwork/calm-down.svg'
import essenceArt from './artwork/essence.svg'
import lastLastArt from './artwork/last-last.svg'
import loveNwantitiArt from './artwork/love-nwantiti.svg'
import mnikeArt from './artwork/mnike.svg'
import monalisaArt from './artwork/monalisa.svg'
import peruArt from './artwork/peru.svg'
import rushArt from './artwork/rush.svg'
import sosoArt from './artwork/soso.svg'

export type MockSong = {
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
  mnike: {
    title: 'Mnike',
    artist: 'Tyler ICU & Tumela_za',
    descriptors: ['Amapiano', 'Festive', 'Log-drum heavy'],
    artworkUrl: mnikeArt,
    durationSeconds: 380,
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
} satisfies Record<string, MockSong>
