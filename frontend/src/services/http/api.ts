// The backend's HTTP bodies, as docs/design/api-design.md defines them (B8, B9).
// Only the fields this client reads or sends are listed. Enumerations travel
// in lowercase.

export type ContextBody = {
  current_mood: string | null
  desired_mood: string | null
  listening_goal: string | null
  activity: string | null
  temporary_genres: string[]
  temporary_moods: string[]
  target_energy: number | null
  target_danceability: number | null
  target_valence: number | null
  target_acousticness: number | null
  target_tempo_bpm: number | null
}

/** A context to send: only the fields that are set. */
export type ContextIn = Partial<ContextBody>

export type TrackBody = {
  track_id: string
  title: string | null
  file_name: string
  artist: string | null
  album: string | null
  duration_seconds: number | null
  status: string
  playable: boolean
  genres: string[]
  moods: string[]
  audio_url: string
}

export type OccurrenceBody = {
  occurrence_id: string
  track: TrackBody
  status: 'queued' | 'playing' | 'played' | 'replaced' | 'discarded'
  rank: number
  score: number | null
  algorithm: string
  is_exploration: boolean
  surfaced_position: number
  queue_position: number | null
  surfaced_at: string
  started_at: string | null
  finished_at: string | null
}

export type SessionBody = {
  session_id: string
  status: 'active' | 'ended'
  context: ContextBody
  started_at: string
  updated_at: string
  ended_at: string | null
  end_reason: string | null
}

export type SessionStateBody = {
  session: SessionBody
  playing: OccurrenceBody | null
  queue: OccurrenceBody[]
}

export type TurnBody = {
  turn_id: string
  sequence: number
  kind: string
  context: ContextBody
  occurrence_id: string | null
  created_at: string
}

export type FeedbackEventBody = {
  event_id: string
  occurrence_id: string
  event_type: string
  occurred_at: string
  played_seconds: number | null
  duration_seconds: number | null
}

export type MeaningBody = {
  kind: 'refine' | 'turn' | 'reaction' | 'save_requested'
  turn: string | null
  reaction: string | null
}

export type SessionStartBody = SessionStateBody & {
  meaning?: MeaningBody | null
  turn?: TurnBody | null
}

export type TurnResultBody = {
  meaning?: MeaningBody | null
  turn: TurnBody | null
  feedback?: { event: FeedbackEventBody } | null
  state: SessionStateBody
}

export type FeedbackBody = {
  event: FeedbackEventBody
  state: SessionStateBody
}

export type SessionDetailBody = SessionStateBody & {
  turns: TurnBody[]
  occurrences: OccurrenceBody[]
  feedback_events: FeedbackEventBody[]
}

export type PageBody<T> = { items: T[]; total: number; limit: number; offset: number }

export type PlaylistSummaryBody = { playlist_id: string; name: string; track_count: number }

export type VocabularyBody = {
  genres: string[]
  moods: string[]
  energy: { id: string; label: string; target_energy: number }[]
  /** Whether anything can be recommended: with no playable tracks, the library is not ready (music must be imported). */
  library: { ready: boolean; playable_tracks: number }
  /** What each dimension's data allows now. Only Tune's three are offered in the UI. */
  dimensions: Record<CapabilityDimension, DimensionState>
  /** Tune's moods that some playable track declares; choosing another changes nothing. */
  usable_moods: string[]
  /** Context fields the backend stores but has not mapped into ranking yet. */
  unmapped_fields: string[]
}

/** usable: some playable track has usable data. no_data: none has, yet. library_not_ready: nothing is playable. */
export type DimensionState = 'usable' | 'no_data' | 'library_not_ready'

export type CapabilityDimension = 'mood' | 'genre' | 'energy' | 'danceability' | 'tempo' | 'valence' | 'acousticness'

export type ErrorBody = {
  error: {
    code: string
    message: string
    details: Record<string, unknown>
    request_id: string
  }
}
