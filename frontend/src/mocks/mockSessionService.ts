// A local stand-in for the backend. It answers the session's requests from
// fixed tables: a phrase list for reading requests, hand-ordered song lists
// for what plays next, and sentence templates for explanations. Nothing here
// scores or ranks songs, and none of it belongs in the session feature.
import type {
  RecommendedSong,
  SessionService,
  SessionTurn,
  SteeringControl,
  TurnContext,
  TurnRequest,
  TurnResponse,
} from '../features/session/sessionService.ts'
import type {
  Intent,
  IntentDimension,
  IntentValue,
  SessionState,
} from '../features/session/types.ts'
import { mockEnvironment } from './environment.ts'
import { mockQuickAction } from './quickActions.ts'
import { seededSessions } from './sessions.ts'
import { isMockSongId, songs } from './songs.ts'
import type { MockSongId } from './songs.ts'

type QuickActions = SessionState['quickActions']

const { refineOptions } = mockEnvironment
const ENERGY_LEVELS = refineOptions.energy

function option(dimension: IntentDimension, id: string): IntentValue {
  const found = refineOptions[dimension].find((value) => value.id === id)
  if (!found) throw new Error(`Unknown mock ${dimension}: ${id}`)
  return found
}

/** The mood of a session that has not named one. It is not a tuning option. */
const OPEN_MOOD: IntentValue = { id: 'open', label: 'Open mood' }

// --- What plays next -------------------------------------------------------
// Hand-ordered lists. The next song is the first one in the list for the
// current genre and energy that this session has not played yet.

const QUEUES: Record<string, Partial<Record<string, MockSongId[]>>> = {
  afrobeats: {
    'very-low': ['soso', 'essence', 'calmDown', 'kuLoSa'],
    low: ['calmDown', 'essence', 'soso', 'kuLoSa'],
    medium: ['lastLast', 'rush', 'loveNwantiti', 'monalisa'],
    high: ['peru', 'joha'],
    'very-high': ['joha', 'peru'],
  },
  amapiano: {
    'very-low': ['water'],
    low: ['water'],
    medium: ['water', 'mnike'],
    high: ['mnike', 'water'],
    'very-high': ['mnike'],
  },
  alte: {
    'very-low': ['freeMind'],
    low: ['freeMind'],
    medium: ['freeMind'],
    high: ['freeMind'],
    'very-high': ['freeMind'],
  },
  any: {
    'very-low': ['soso', 'freeMind', 'essence', 'calmDown'],
    low: ['calmDown', 'essence', 'soso', 'freeMind', 'kuLoSa'],
    medium: ['lastLast', 'rush', 'loveNwantiti', 'monalisa', 'water'],
    high: ['peru', 'joha', 'mnike'],
    'very-high': ['mnike', 'joha', 'peru'],
  },
}

/** Where a genre turns once its own list for the energy runs out. */
const GENRE_FALLBACK: Record<string, MockSongId[]> = {
  afrobeats: [
    'lastLast',
    'rush',
    'loveNwantiti',
    'monalisa',
    'calmDown',
    'essence',
    'soso',
    'peru',
    'joha',
    'kuLoSa',
  ],
  amapiano: ['water', 'mnike'],
  alte: ['freeMind'],
  any: [],
}

const EVERYTHING = Object.keys(songs) as MockSongId[]

function nextSong(
  intent: Intent,
  played: string[],
  current: string | null,
): MockSongId | null {
  const order = [
    ...(QUEUES[intent.genre.id]?.[intent.energy.id] ?? []),
    ...(GENRE_FALLBACK[intent.genre.id] ?? []),
    ...EVERYTHING,
  ]
  return (
    order.find((id) => !played.includes(id) && id !== current) ??
    // Everything has been played: start over, avoiding an immediate repeat.
    order.find((id) => id !== current) ??
    null
  )
}

// --- Explanations ----------------------------------------------------------

/** Each song's own genre and energy, used only to word its explanation. */
const SONG_TRAITS: Record<MockSongId, { genre: string; energy: string }> = {
  calmDown: { genre: 'afrobeats', energy: 'low' },
  essence: { genre: 'afrobeats', energy: 'low' },
  soso: { genre: 'afrobeats', energy: 'low' },
  kuLoSa: { genre: 'afrobeats', energy: 'low' },
  freeMind: { genre: 'alte', energy: 'low' },
  lastLast: { genre: 'afrobeats', energy: 'medium' },
  rush: { genre: 'afrobeats', energy: 'medium' },
  loveNwantiti: { genre: 'afrobeats', energy: 'medium' },
  monalisa: { genre: 'afrobeats', energy: 'medium' },
  water: { genre: 'amapiano', energy: 'medium' },
  peru: { genre: 'afrobeats', energy: 'high' },
  joha: { genre: 'afrobeats', energy: 'high' },
  mnike: { genre: 'amapiano', energy: 'high' },
}

const energyRank = (id: string) =>
  ENERGY_LEVELS.findIndex((level) => level.id === id)

const LEAD: Record<string, (genre: string) => string> = {
  emotional: (genre) => `Keeps the emotional ${genre && `${genre} `}feel`,
  focused: (genre) => `A steady ${genre && `${genre} `}pulse`,
  calm: (genre) => `Soft, unhurried ${genre || 'sound'}`,
  driven: (genre) => `Driving ${genre && `${genre} `}momentum`,
  joyful: (genre) => `Bright, easy ${genre || 'warmth'}`,
  open: () => 'A wide-open pick',
}

const MOOD_REASON: Record<string, string> = {
  emotional: 'keeps the emotional tone you asked for.',
  focused: 'stays steady enough to hold your focus.',
  calm: 'keeps things soft and unhurried.',
  driven: 'keeps the momentum up.',
  joyful: 'keeps things bright.',
  open: 'gives the session a fresh starting point.',
}

const ENERGY_CLAUSE: Record<string, string> = {
  'very-low': ', kept very low',
  low: ' while staying relaxed',
  medium: ' with enough lift to keep things moving',
  high: ' at a strong pace',
  'very-high': ' at full energy',
}

const ENERGY_REASON: Record<string, string> = {
  'very-low': 'Sits right at the very low energy you set.',
  low: 'Keeps the energy relaxed.',
  medium: 'Medium energy, so the session keeps moving.',
  high: 'High energy, matching the pace you set.',
  'very-high': 'Full energy, as you set it.',
}

type TurnChange = {
  /** Which way this turn moved the energy, if it did. */
  energy?: 'raised' | 'lowered'
  genre?: boolean
}

function explain(
  intent: Intent,
  songId: MockSongId,
  change: TurnChange,
): RecommendedSong['why'] {
  const traits = SONG_TRAITS[songId]
  const genre = intent.genre.id === 'any' ? '' : intent.genre.label
  const mood = intent.mood.id in LEAD ? intent.mood.id : 'open'

  if (genre && traits.genre !== intent.genre.id) {
    return {
      summary: `The closest match while ${genre} picks run thin.`,
      reasons: [
        `Few unplayed ${genre} songs fit right now.`,
        `Keeps the ${intent.mood.label.toLowerCase()} direction you set.`,
      ],
    }
  }

  let clause: string
  let energyReason: string
  if (traits.energy === intent.energy.id) {
    clause = ENERGY_CLAUSE[intent.energy.id]
    energyReason =
      change.energy === 'raised'
        ? 'Raises the energy without losing the feel.'
        : change.energy === 'lowered'
          ? 'Brings the energy down, as you asked.'
          : ENERGY_REASON[intent.energy.id]
  } else if (energyRank(traits.energy) > energyRank(intent.energy.id)) {
    clause = ', a touch livelier than you set'
    energyReason = 'Slightly livelier than your energy setting.'
  } else {
    clause = ', a touch softer than you set'
    energyReason = 'Slightly softer than your energy setting.'
  }

  const [, feel = '', texture = ''] = songs[songId].descriptors
  return {
    summary: `${LEAD[mood](genre)}${clause}.`,
    reasons: [
      change.genre
        ? `Moves into ${genre}, as you asked.`
        : `${feel}, ${texture.toLowerCase()} — ${MOOD_REASON[mood]}`,
      energyReason,
    ],
  }
}

function recommend(
  intent: Intent,
  songId: MockSongId,
  change: TurnChange = {},
): RecommendedSong {
  return { songId, ...songs[songId], why: explain(intent, songId, change) }
}

// --- Quick actions ---------------------------------------------------------
// At most two, written as things the user could type. Each carries its
// request (quickActions.ts): a steering control, or a phrase only this mock reads.

const actions = (...labels: string[]): QuickActions =>
  labels.map((label) => mockQuickAction(label))

const ACTION_SETS = {
  initial: actions('More like this', 'A bit calmer'),
  energyUp: actions('Keep this energy', 'More energetic'),
  calm: actions('Keep this mood', 'Even calmer'),
  continuing: actions('More like this', 'Something new'),
  liked: actions('More like this', 'Save this'),
  skipped: actions('Different artist', 'Keep this mood'),
  saved: actions('More like this', 'Keep this energy'),
  focus: actions('Keep this energy', 'A bit calmer'),
  gym: actions('Push it harder', 'Switch genre'),
  generic: actions('More like this', 'Something new'),
} satisfies Record<string, QuickActions>

const FIRST_ACTIONS_BY_MOOD: Record<string, QuickActions> = {
  focused: ACTION_SETS.focus,
  driven: ACTION_SETS.gym,
  calm: ACTION_SETS.calm,
}

// --- Reading a request -----------------------------------------------------

const NEXT_GENRE: Record<string, string> = {
  afrobeats: 'amapiano',
  amapiano: 'alte',
  alte: 'afrobeats',
}

const FIRST_ENERGY_BY_MOOD: Record<string, string> = {
  calm: 'low',
  emotional: 'low',
  driven: 'high',
}

/** True when the text contains any of the phrases. */
function mentions(text: string) {
  const padded = ` ${text.toLowerCase()} `
  return (...phrases: string[]) =>
    phrases.some((phrase) => padded.includes(phrase))
}

function stepEnergy(energy: IntentValue, steps: number): IntentValue {
  const rank = Math.min(
    ENERGY_LEVELS.length - 1,
    Math.max(0, energyRank(energy.id) + steps),
  )
  return ENERGY_LEVELS[rank]
}

function readMessage(
  text: string,
  before: Intent | null,
): { intent: Intent; label?: string; refineTab?: IntentDimension } {
  const said = mentions(text)
  let mood = before?.mood ?? null
  let genre = before?.genre ?? option('genre', 'any')
  let energy = before?.energy ?? option('energy', 'medium')
  let energyNamed = false
  let label: string | undefined
  let refineTab: IntentDimension | undefined

  if (said('emotional', ' sad', 'heartbreak', 'in my feelings')) {
    mood = option('mood', 'emotional')
  }
  if (said('happy', ' joy', 'sunny')) mood = option('mood', 'joyful')
  if (said('relax', 'chill', 'unwind')) mood = option('mood', 'calm')
  if (said('study', 'focus', 'coding', 'concentrate')) {
    mood = option('mood', 'focused')
  }
  if (said('workout', ' gym', 'running', 'lifting', 'moving', ' move ')) {
    mood = option('mood', 'driven')
    if (energyRank(energy.id) < energyRank('high')) {
      energy = option('energy', 'high')
      energyNamed = true
    }
  }
  if (said('discover', 'surprise me')) {
    mood = OPEN_MOOD
    genre = option('genre', 'any')
  }

  if (said('afrobeat', 'afro-beat')) genre = option('genre', 'afrobeats')
  if (said('amapiano')) genre = option('genre', 'amapiano')
  if (said('alté', ' alte ')) genre = option('genre', 'alte')
  if (
    said(
      'switch genre',
      'change genre',
      'change the genre',
      'different genre',
      'something different',
      'something new',
      'completely different',
    )
  ) {
    genre = option('genre', NEXT_GENRE[genre.id] ?? 'afrobeats')
  }

  if (said('keep this energy', 'keep the energy')) {
    label = `Holding ${energy.label.toLowerCase()} energy`
  } else if (
    said(
      'more energ',
      'energetic',
      'hype',
      'upbeat',
      'faster',
      'wake me',
      'harder',
      'push it',
    )
  ) {
    energy = stepEnergy(energy, 1)
    energyNamed = true
  } else if (said('calmer', 'slower', 'less energ', 'softer', 'quieter')) {
    energy = stepEnergy(energy, -1)
    energyNamed = true
  }

  if (said('sleepy', 'tired', 'drowsy')) {
    if (energyRank(energy.id) < energyRank('medium')) {
      energy = option('energy', 'medium')
    }
    energyNamed = true
    if (said('study', 'focus', 'work')) mood = option('mood', 'focused')
    refineTab = 'energy'
  }

  if (said('keep this mood', 'keep the mood') && mood) {
    label = `Holding the ${mood.label.toLowerCase()} mood`
  }
  if (said('more like this', 'more like that')) label = 'Keeping this direction'
  if (said('different artist')) label = 'Trying a different artist'

  if (!before) {
    mood ??= OPEN_MOOD
    if (!energyNamed) {
      energy = option('energy', FIRST_ENERGY_BY_MOOD[mood.id] ?? 'medium')
    }
  }
  return {
    intent: { mood: mood ?? OPEN_MOOD, genre, energy },
    label,
    refineTab,
  }
}

// --- Naming a session ------------------------------------------------------

const TITLE_ALONE: Record<string, string> = {
  focused: 'Focus',
  calm: 'Unwind',
  driven: 'Move',
  emotional: 'Emotional',
  joyful: 'Bright',
}

const TITLE_WITH_GENRE: Record<string, string> = {
  focused: 'Focus',
  calm: 'Calm',
  driven: 'High-energy',
  emotional: 'Emotional',
  joyful: 'Bright',
}

function titleFor(intent: Intent) {
  if (intent.genre.id === 'any') {
    return TITLE_ALONE[intent.mood.id] ?? 'Discovery'
  }
  const prefix = TITLE_WITH_GENRE[intent.mood.id]
  return prefix ? `${prefix} ${intent.genre.label}` : intent.genre.label
}

// --- Building a turn -------------------------------------------------------

/** After this many recommendations in one direction, peek at what follows. */
const UP_NEXT_AFTER = 3

function peek(
  intent: Intent,
  context: TurnContext,
  pick: MockSongId | null,
  recommendationsInDirection: number,
): RecommendedSong | null {
  if (!pick || recommendationsInDirection < UP_NEXT_AFTER) return null
  const following = nextSong(intent, [...context.playedSongIds, pick], pick)
  return following ? recommend(intent, following) : null
}

function intentTurn(
  context: TurnContext,
  intent: Intent,
  extras: Pick<SessionTurn, 'userText' | 'ackLabel' | 'refineTab'>,
): SessionTurn {
  const before = context.intent
  const energyDelta = before
    ? energyRank(intent.energy.id) - energyRank(before.energy.id)
    : 0
  const genreChanged = !!before && before.genre.id !== intent.genre.id
  const changed =
    !before ||
    energyDelta !== 0 ||
    genreChanged ||
    before.mood.id !== intent.mood.id
  const inDirection = changed ? 1 : context.recommendationsSinceIntentChange + 1

  let quickActions: QuickActions
  if (!before) {
    quickActions = FIRST_ACTIONS_BY_MOOD[intent.mood.id] ?? ACTION_SETS.initial
  } else if (energyDelta > 0) quickActions = ACTION_SETS.energyUp
  else if (energyDelta < 0) quickActions = ACTION_SETS.calm
  else if (intent.mood.id === 'focused') quickActions = ACTION_SETS.focus
  else {
    quickActions =
      inDirection >= UP_NEXT_AFTER ? ACTION_SETS.continuing : ACTION_SETS.generic
  }

  const pick = nextSong(intent, context.playedSongIds, context.currentSongId)
  return {
    ...extras,
    intent,
    acknowledgement: 'intent',
    recommendation: pick
      ? recommend(intent, pick, {
          energy:
            energyDelta > 0 ? 'raised' : energyDelta < 0 ? 'lowered' : undefined,
          genre: genreChanged,
        })
      : null,
    quickActions,
    upNext: peek(intent, context, pick, inDirection),
    title: before ? undefined : titleFor(intent),
  }
}

function moveOn(
  context: TurnContext,
  acknowledgement: 'not_for_me' | 'none',
  userText?: string,
): TurnResponse {
  const { intent } = context
  if (!intent) throw new Error('Cannot move on in a session with no intent')

  const inDirection = context.recommendationsSinceIntentChange + 1
  const pick = nextSong(intent, context.playedSongIds, context.currentSongId)
  return {
    kind: 'turn',
    turn: {
      userText,
      intent,
      acknowledgement,
      recommendation: pick ? recommend(intent, pick) : null,
      quickActions:
        acknowledgement === 'not_for_me'
          ? ACTION_SETS.skipped
          : ACTION_SETS.continuing,
      upNext: peek(intent, context, pick, inDirection),
    },
  }
}

/** The phrase this mock's reader takes a steering control as. */
const CONTROL_PHRASE: Record<SteeringControl, string> = {
  more_like_this: 'More like this',
  surprise_me: 'Surprise me',
  more_familiar: 'Keep this mood',
  try_something_different: 'Something new',
}

function replayTurn(context: TurnContext, songId: string): TurnResponse {
  const { intent } = context
  if (!intent) throw new Error('Cannot replay in a session with no intent')
  if (!isMockSongId(songId)) throw new Error(`Unknown mock song: ${songId}`)
  return {
    kind: 'turn',
    turn: {
      intent,
      acknowledgement: 'none',
      recommendation: recommend(intent, songId),
      quickActions: ACTION_SETS.continuing,
      upNext: null,
    },
  }
}

const REFINE_LABEL: Record<IntentDimension, string> = {
  energy: 'Energy adjusted',
  mood: 'Mood adjusted',
  genre: 'Genre switched',
}

function respond(context: TurnContext, request: TurnRequest): TurnResponse {
  switch (request.kind) {
    case 'starter':
      return respond(context, { kind: 'message', text: request.phrase })

    case 'control': {
      const answer = respond(context, {
        kind: 'message',
        text: CONTROL_PHRASE[request.control],
      })
      return answer.kind === 'turn'
        ? { kind: 'turn', turn: { ...answer.turn, userText: request.label } }
        : answer
    }

    case 'message': {
      const text = request.text.trim()
      const said = mentions(text)

      if (context.currentSongId) {
        if (said('save')) return { kind: 'save_requested', echo: text }
        if (
          said('not for me', 'not this song', 'skip', 'don’t like', "don't like")
        ) {
          return moveOn(context, 'not_for_me', text)
        }
        if (
          said('love this', 'i like this') &&
          !said('more like', 'not this')
        ) {
          return { kind: 'liked', echo: text }
        }
      }
      const { intent, label, refineTab } = readMessage(text, context.intent)
      return {
        kind: 'turn',
        turn: intentTurn(context, intent, {
          userText: text,
          ackLabel: label,
          refineTab,
        }),
      }
    }

    case 'refine': {
      if (!context.intent) throw new Error('Cannot refine before an intent')
      const intent: Intent = {
        ...context.intent,
        [request.dimension]: option(request.dimension, request.valueId),
      }
      return {
        kind: 'turn',
        turn: intentTurn(context, intent, {
          ackLabel: REFINE_LABEL[request.dimension],
          refineTab: request.dimension,
        }),
      }
    }

    case 'not_for_me':
      return moveOn(context, 'not_for_me')

    case 'next':
    case 'track_ended':
      return moveOn(context, 'none')

    case 'replay':
      return replayTurn(context, request.songId)
  }
}

let playlistsCreated = 0

/** Which playlists suit which genre. A hint only; nothing is selected by it. */
const PLAYLISTS_FOR_GENRE: Record<string, string[]> = {
  afrobeats: ['afrobeats'],
}

// Answers at once, but through the same asynchronous interface a backend
// client will implement, so the session feature cannot tell them apart.
export const mockSessionService: SessionService = {
  loadWorkspace: async () => ({
    sessions: seededSessions,
    playlists: mockEnvironment.playlists,
    starters: mockEnvironment.starters,
    refineOptions,
  }),
  respond: async (context, request) => respond(context, request),
  react: async (_context, reaction) =>
    reaction === 'like' ? { quickActions: ACTION_SETS.liked } : {},
  savePlaylists: async () => ({ quickActions: ACTION_SETS.saved }),
  createPlaylist: async (name) => {
    playlistsCreated++
    return { id: `created-playlist-${playlistsCreated}`, name }
  },
  quickActionsAfter: async (reaction) => ACTION_SETS[reaction],
  suggestPlaylists: async (context, playlists) => {
    const suggested = PLAYLISTS_FOR_GENRE[context.intent?.genre.id ?? ''] ?? []
    return playlists
      .filter((playlist) => suggested.includes(playlist.id))
      .map((playlist) => playlist.id)
  },
}
