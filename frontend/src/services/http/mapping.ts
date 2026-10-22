// Backend bodies <-> the session feature's typed state. Pure translation:
// nothing here interprets language, scores, or ranks. Wording (titles,
// acknowledgements, quick-action labels) is presentation, chosen from
// structured facts the backend gave.
import type { PlaylistTone } from '../../components/PlaylistSwatch.tsx'
import type { RecommendedSong, SteeringControl } from '../../features/session/sessionService.ts'
import type {
  Intent,
  IntentChange,
  IntentDimension,
  IntentValue,
  Playlist,
  QuickAction,
  Recommendation,
  SessionEnvironment,
  SessionEvent,
  SessionState,
} from '../../features/session/types.ts'
import { INTENT_DIMENSIONS } from '../../features/session/types.ts'
import type {
  ContextBody,
  FeedbackEventBody,
  OccurrenceBody,
  SessionDetailBody,
  VocabularyBody,
} from './api.ts'

// The values that mean "nothing chosen" on each dimension. Only Any genre is a tuning option.
export const ANY_GENRE: IntentValue = { id: 'any-genre', label: 'Any genre' }
export const OPEN_MOOD: IntentValue = { id: 'open-mood', label: 'Open mood' }
export const ANY_ENERGY: IntentValue = { id: 'any-energy', label: 'Any energy' }

// Prefixed, so a label can never collide with the values above.
const genreId = (label: string) => `genre:${label}`
const moodId = (label: string) => `mood:${label}`

export const EMPTY_CONTEXT: ContextBody = {
  current_mood: null,
  desired_mood: null,
  listening_goal: null,
  activity: null,
  temporary_genres: [],
  temporary_moods: [],
  target_energy: null,
  target_danceability: null,
  target_valence: null,
  target_acousticness: null,
  target_tempo_bpm: null,
}

// --- Intent ------------------------------------------------------------------------

/** The Tune dimensions the library cannot use now, as the backend reports them. */
export function unavailableFrom({ dimensions }: VocabularyBody): IntentDimension[] {
  return INTENT_DIMENSIONS.filter((dimension) => dimensions[dimension] !== 'usable')
}

/** Why no starter can be used while the library has nothing playable: one reason, about the library. */
export const LIBRARY_NOT_READY_REASON = 'Your library has no playable music yet. Import music to start listening.'

/**
 * Why a starter cannot be used now, from what the backend reports about the
 * library: nothing is usable while nothing is playable; otherwise its mood
 * must be one a track declares, and its energy needs energy data. A starter is
 * never sent with part of its meaning missing.
 */
export function unavailableStarterReason(
  intent: { mood?: string; energy?: string },
  { library, usable_moods, dimensions }: VocabularyBody,
): string | undefined {
  if (!library.ready) return LIBRARY_NOT_READY_REASON
  const moodMissing = intent.mood !== undefined && !usable_moods.includes(intent.mood)
  const energyMissing = intent.energy !== undefined && dimensions.energy !== 'usable'
  if (moodMissing && energyMissing) return 'Your music has no mood or energy information for this yet.'
  if (moodMissing) return `None of your music is tagged ${intent.mood} yet.`
  if (energyMissing) return 'Your music has no energy information for this yet.'
  return undefined
}

export function refineOptionsFrom(vocabulary: VocabularyBody): SessionEnvironment['refineOptions'] {
  return {
    // A mood no track declares is offered, as the approved design does, but marked.
    mood: vocabulary.moods.map((label) =>
      vocabulary.usable_moods.includes(label)
        ? { id: moodId(label), label }
        : { id: moodId(label), label, unavailable: true },
    ),
    genre: [...vocabulary.genres.map((label) => ({ id: genreId(label), label })), ANY_GENRE],
    energy: vocabulary.energy.map(({ id, label }) => ({ id, label })),
  }
}

function energyValue(target: number | null, vocabulary: VocabularyBody): IntentValue {
  if (target === null || vocabulary.energy.length === 0) return ANY_ENERGY
  // The nearest level; halfway, the lower one (as the backend reads it).
  const nearest = vocabulary.energy.reduce((best, level) => {
    const distance = Math.round(Math.abs(level.target_energy - target) * 1e9)
    const bestDistance = Math.round(Math.abs(best.target_energy - target) * 1e9)
    return distance < bestDistance ? level : best
  })
  return { id: nearest.id, label: nearest.label }
}

/** The intent a context expresses, in the feature's three dimensions. */
export function intentFrom(context: ContextBody, vocabulary: VocabularyBody): Intent {
  const moods = context.temporary_moods.length
    ? context.temporary_moods
    : context.desired_mood
      ? [context.desired_mood]
      : []
  const genres = context.temporary_genres
  return {
    mood: moods.length ? { id: moodId(moods.join(' + ')), label: moods.join(' + ') } : OPEN_MOOD,
    genre: genres.length ? { id: genreId(genres.join(' + ')), label: genres.join(' + ') } : ANY_GENRE,
    energy: energyValue(context.target_energy, vocabulary),
  }
}

/** The context with one dimension set to a tuning value, everything else kept. */
export function contextWith(
  context: ContextBody,
  dimension: IntentDimension,
  valueId: string,
  vocabulary: VocabularyBody,
): ContextBody {
  switch (dimension) {
    case 'genre':
      return {
        ...context,
        temporary_genres: valueId === ANY_GENRE.id ? [] : [labelOf(valueId, 'genre:')],
      }
    case 'mood':
      return valueId === OPEN_MOOD.id
        ? { ...context, temporary_moods: [], desired_mood: null }
        : { ...context, temporary_moods: [labelOf(valueId, 'mood:')] }
    case 'energy': {
      if (valueId === ANY_ENERGY.id) return { ...context, target_energy: null }
      const level = vocabulary.energy.find((candidate) => candidate.id === valueId)
      if (!level) throw new Error(`Unknown energy level: ${valueId}`)
      return { ...context, target_energy: level.target_energy }
    }
  }
}

function labelOf(valueId: string, prefix: string): string {
  if (!valueId.startsWith(prefix)) throw new Error(`Unknown tuning value: ${valueId}`)
  return valueId.slice(prefix.length)
}

/** A session's title, worded from its intent: "Calm Jazz", "Jazz", "Calm", or "Discovery". */
export function titleFor(intent: Intent): string {
  const mood = intent.mood.id === OPEN_MOOD.id ? null : intent.mood.label
  const genre = intent.genre.id === ANY_GENRE.id ? null : intent.genre.label
  if (mood && genre) return `${mood} ${genre}`
  return genre ?? mood ?? 'Discovery'
}

// --- Recommendations ---------------------------------------------------------------

export function songFrom(occurrence: OccurrenceBody, audioUrl: (path: string) => string): RecommendedSong {
  const { track } = occurrence
  return {
    songId: track.track_id,
    title: track.title ?? track.file_name,
    artist: track.artist ?? 'Unknown artist',
    descriptors: [...track.genres, ...track.moods],
    // Imported music carries no artwork yet; the Intentune fallback shows.
    artworkUrl: null,
    durationSeconds: track.duration_seconds ?? 0,
    ref: occurrence.occurrence_id,
    audioUrl: audioUrl(track.audio_url),
  }
}

const CONTROL_LABEL: Record<SteeringControl, string> = {
  more_like_this: 'More like this',
  surprise_me: 'Surprise me',
  more_familiar: 'More familiar',
  try_something_different: 'Try something different',
}

/** How a steering control is acknowledged once the backend has applied it. */
export const CONTROL_ACK: Record<SteeringControl, string> = {
  more_like_this: 'Keeping this direction',
  surprise_me: 'Surprising you next',
  more_familiar: 'Keeping it familiar',
  try_something_different: 'Trying something different next',
}

export function controlAction(control: SteeringControl): QuickAction {
  const label = CONTROL_LABEL[control]
  return { id: control.replaceAll('_', '-'), label, request: { kind: 'control', control, label } }
}

/**
 * The quick actions for the song in view (D36): More like this, and Try
 * something different, or More familiar after an exploration pick.
 */
export function quickActionsFor(hero: OccurrenceBody | null): QuickAction[] {
  if (!hero) return []
  return [
    controlAction('more_like_this'),
    controlAction(hero.is_exploration ? 'more_familiar' : 'try_something_different'),
  ]
}

// --- Playlists -----------------------------------------------------------------------

const TONES: PlaylistTone[] = ['violet', 'indigo', 'ember', 'dusk', 'lavender']

/** A playlist's swatch tint, the same every time for the same playlist. Presentation only (D32). */
export function toneFor(playlistId: string): PlaylistTone {
  let hash = 0
  for (const character of playlistId) hash = (hash * 31 + character.charCodeAt(0)) >>> 0
  return TONES[hash % TONES.length]
}

export function playlistFrom(body: { playlist_id: string; name: string }): Playlist {
  return { id: body.playlist_id, name: body.name, tone: toneFor(body.playlist_id) }
}

// --- A past session, from its history ----------------------------------------------------

/** A session event before it gets its id. */
type NewEvent = SessionEvent extends infer Event
  ? Event extends SessionEvent
    ? Omit<Event, 'id'>
    : never
  : never

function changesBetween(before: Intent, after: Intent): IntentChange[] {
  return INTENT_DIMENSIONS.filter((dimension) => before[dimension].id !== after[dimension].id).map(
    (dimension) => ({ dimension, from: before[dimension], to: after[dimension] }),
  )
}

function likedBy(events: FeedbackEventBody[], occurrenceId: string): boolean {
  let liked = false
  for (const event of events) {
    if (event.occurrence_id !== occurrenceId) continue
    if (event.event_type === 'like') liked = true
    if (event.event_type === 'unlike') liked = false
  }
  return liked
}

/**
 * A session as its history tells it: the intent it started with and each
 * refinement, and every track that played, in order. It opens paused.
 */
export function sessionStateFrom(
  detail: SessionDetailBody,
  vocabulary: VocabularyBody,
  audioUrl: (path: string) => string,
): SessionState {
  type Moment = { at: string; event: NewEvent }
  const moments: Moment[] = []
  const recommendations: Record<string, Recommendation> = {}

  let intent: Intent | null = null
  for (const turn of detail.turns) {
    const after = intentFrom(turn.context, vocabulary)
    if (turn.kind === 'initial_intent') {
      moments.push({ at: turn.created_at, event: { kind: 'intent_set', intent: after } })
    } else if (turn.kind === 'refine' && intent) {
      const changes = changesBetween(intent, after)
      if (changes.length) moments.push({ at: turn.created_at, event: { kind: 'intent_updated', changes } })
    }
    intent = turn.kind === 'initial_intent' || turn.kind === 'refine' ? after : intent
  }

  const played = detail.occurrences.filter((occurrence) => occurrence.started_at !== null)
  for (const occurrence of played) {
    const id = occurrence.occurrence_id
    recommendations[id] = {
      ...songFrom(occurrence, audioUrl),
      id,
      liked: likedBy(detail.feedback_events, id),
      skipped: detail.feedback_events.some((event) => event.occurrence_id === id && event.event_type === 'not_for_me'),
      savedToPlaylistIds: [],
    }
    moments.push({ at: occurrence.started_at!, event: { kind: 'recommendation', recommendationId: id } })
  }

  moments.sort((first, second) => first.at.localeCompare(second.at))
  const events = moments.map((moment, index) => ({ ...moment.event, id: `e${index + 1}` }) as SessionEvent)
  const current = intentFrom(detail.session.context, vocabulary)

  return {
    id: detail.session.session_id,
    title: titleFor(current),
    intent: current,
    changedDimensions: [],
    events,
    recommendations,
    currentRecommendationId: played.at(-1)?.occurrence_id ?? null,
    playback: { playing: false, positionSeconds: 0 },
    whyExpanded: false,
    quickActions: [],
    upNextRecommendationId: null,
    refine: null,
    overlay: null,
    openRequest: null,
  }
}
