// Mock data around a session: tuning options, playlists, other sessions and
// the starter intents of a new session.
import type {
  Intent,
  IntentDimension,
  SessionEnvironment,
} from '../features/session/types.ts'
import { songs } from './songs.ts'

const refineOptions: SessionEnvironment['refineOptions'] = {
  mood: [
    { id: 'emotional', label: 'Emotional' },
    { id: 'focused', label: 'Focused' },
    { id: 'calm', label: 'Calm' },
    { id: 'joyful', label: 'Joyful' },
    { id: 'driven', label: 'Driven' },
  ],
  genre: [
    { id: 'afrobeats', label: 'Afrobeats' },
    { id: 'amapiano', label: 'Amapiano' },
    { id: 'alte', label: 'Alté' },
    { id: 'any', label: 'Any genre' },
  ],
  energy: [
    { id: 'very-low', label: 'Very low' },
    { id: 'low', label: 'Low' },
    { id: 'medium', label: 'Medium' },
    { id: 'high', label: 'High' },
    { id: 'very-high', label: 'Very high' },
  ],
}

function option(dimension: IntentDimension, id: string) {
  const found = refineOptions[dimension].find((value) => value.id === id)
  if (!found) throw new Error(`Unknown mock ${dimension}: ${id}`)
  return found
}

/** Builds a mock intent from option ids. */
export function mockIntent(mood: string, genre: string, energy: string): Intent {
  return {
    mood: option('mood', mood),
    genre: option('genre', genre),
    energy: option('energy', energy),
  }
}

export const mockEnvironment: SessionEnvironment = {
  refineOptions,
  playlists: [
    { id: 'favorites', name: 'Favorites', tone: 'violet' },
    { id: 'study', name: 'Study', tone: 'indigo' },
    { id: 'workout', name: 'Workout', tone: 'ember' },
    { id: 'afrobeats', name: 'Afrobeats', tone: 'dusk' },
  ],
  sessions: [
    {
      id: 'emotional-afrobeats',
      title: 'Emotional Afrobeats',
      intent: mockIntent('emotional', 'afrobeats', 'low'),
    },
    {
      id: 'late-night-study',
      title: 'Late Night Study',
      intent: mockIntent('focused', 'afrobeats', 'medium'),
    },
    {
      id: 'gym-energy',
      title: 'Gym Energy',
      intent: mockIntent('driven', 'amapiano', 'high'),
    },
    {
      id: 'coding',
      title: 'Coding',
      intent: mockIntent('focused', 'alte', 'low'),
    },
    {
      id: 'morning-focus',
      title: 'Morning Focus',
      intent: mockIntent('calm', 'afrobeats', 'low'),
    },
  ],
  starters: [
    {
      id: 'focus',
      label: 'Focus',
      phrase: 'Help me focus',
      artworkUrl: songs.monalisa.artworkUrl,
    },
    {
      id: 'unwind',
      label: 'Unwind',
      phrase: 'Something to unwind to',
      artworkUrl: songs.essence.artworkUrl,
    },
    {
      id: 'move',
      label: 'Move',
      phrase: 'Get me moving',
      artworkUrl: songs.mnike.artworkUrl,
    },
    {
      id: 'discover',
      label: 'Discover',
      phrase: 'Surprise me',
      artworkUrl: songs.rush.artworkUrl,
    },
  ],
}
