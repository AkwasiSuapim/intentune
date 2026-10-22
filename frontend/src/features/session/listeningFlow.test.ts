// The mock listening flow end to end: user commands, the mock service and the
// reducers together, checked through what the session view would compose.
import { describe, expect, it } from 'vitest'
import { mockSessionService } from '../../mocks/mockSessionService.ts'
import { mockEnvironment } from '../../mocks/environment.ts'
import { mockSessions } from '../../mocks/sessions.ts'
import { ask, planCommand } from './commands.ts'
import type { SessionCommand } from './commands.ts'
import { composeSession } from './composeSession.ts'
import {
  activeSession,
  createWorkspace,
  selectEnvironment,
  workspaceReducer,
} from './workspaceReducer.ts'
import type { WorkspaceState } from './workspaceReducer.ts'

const service = mockSessionService

const open = async () => createWorkspace(await service.loadWorkspace())

/** Runs commands as the app does: the changes made at once, then the service's answer. */
async function act(workspace: WorkspaceState, ...commands: SessionCommand[]) {
  let current = workspace
  for (const command of commands) {
    const { actions, question } = planCommand(current, command)
    current = actions.reduce(workspaceReducer, current)
    if (question) {
      current = workspaceReducer(current, await ask(service, question))
    }
  }
  return current
}

const view = (workspace: WorkspaceState) =>
  composeSession(activeSession(workspace), selectEnvironment(workspace))

const hero = (workspace: WorkspaceState) =>
  view(workspace).content.find(
    (block) => block.type === 'recommendation' && block.variant === 'hero',
  )

const heroTitle = (workspace: WorkspaceState) => {
  const block = hero(workspace)
  return block?.type === 'recommendation' ? block.title : null
}

const actionLabels = (workspace: WorkspaceState) => {
  const control = view(workspace).contextualControl
  return control?.type === 'quick_actions'
    ? control.actions.map((action) => action.label)
    : null
}

const types = (workspace: WorkspaceState) =>
  view(workspace).content.map((block) => block.type)

/** Opens the seeded "Emotional Afrobeats" session. */
const inEmotionalAfrobeats = async () =>
  act(await open(), { type: 'open_session', sessionId: 'emotional-afrobeats' })

describe('starting a session', () => {
  it('opens on Tune in, with the existing sessions one tap away', async () => {
    const workspace = await open()

    expect(view(workspace).layout).toBe('prompt')
    expect(view(workspace).title).toBe('New session')
    expect(
      view(await act(workspace, { type: 'open_drawer' })).navigation.sessions.map(
        (session) => session.title,
      ),
    ).toEqual([
      'New session',
      'Emotional Afrobeats',
      'Late Night Study',
      'Gym Energy',
      'Coding',
      'Morning Focus',
    ])
  })

  it('turns a starter into a first message, an acknowledgement and a recommendation', async () => {
    const workspace = await act(await open(), { type: 'select_starter', starterId: 'focus' })
    const [message, ack] = view(workspace).content

    expect(types(workspace)).toEqual(['user_message', 'ack', 'recommendation'])
    expect(message).toMatchObject({ text: 'Help me focus' })
    expect(ack).toMatchObject({
      label: 'Intent set',
      detail: 'Focused · Any genre · Medium energy',
    })
    expect(view(workspace).title).toBe('Focus')
    expect(view(workspace).accent).toBe('focused')
    expect(heroTitle(workspace)).toBe('Last Last')
  })

  it('treats a typed request exactly like the starter with the same words', async () => {
    const typed = await act(await open(), { type: 'send_message', text: '  Help me focus  ' })
    const tapped = await act(await open(), { type: 'select_starter', starterId: 'focus' })

    expect(activeSession(typed)).toEqual(activeSession(tapped))
  })

  it('ignores an empty message', async () => {
    const workspace = await open()

    expect(await act(workspace, { type: 'send_message', text: '   ' })).toBe(workspace)
  })
})

describe('steering with words', () => {
  it('reproduces the approved "intent changed" scene from the first one', async () => {
    const workspace = await act(
      await inEmotionalAfrobeats(),
      { type: 'toggle_like' },
      { type: 'send_message', text: 'Make it more energetic.' },
    )
    const approved = composeSession(mockSessions.change, mockEnvironment)
    const result = view(workspace)
    // Ids, the playback position and the "picking up" summary differ; the rest must not.
    const essentials = (composition: typeof result) =>
      composition.content
        .filter((block) => block.type !== 'session_summary')
        .map((block) =>
          block.type === 'recommendation'
            ? [block.variant, block.title, 'whyReasons' in block && block.whyReasons]
            : block.type === 'ack'
              ? [block.label, block.detail, block.changes]
              : block.type === 'user_message'
                ? block.text
                : block.type,
        )

    expect(essentials(result)).toEqual(essentials(approved))
    expect(result.intentSummary).toEqual(approved.intentSummary)
    expect(actionLabels(workspace)).toEqual(['Keep this energy', 'More energetic'])
  })

  it('sends a quick action as the words on it', async () => {
    const before = await inEmotionalAfrobeats()
    const workspace = await act(before, {
      type: 'select_quick_action',
      actionId: 'a-bit-calmer',
    })
    const [message, ack] = view(workspace).content.slice(-3)

    expect(message).toMatchObject({ type: 'user_message', text: 'A bit calmer' })
    expect(ack).toMatchObject({
      label: 'Intent updated',
      changes: [{ dimension: 'Energy', from: 'Low', to: 'Very low' }],
    })
    expect(heroTitle(workspace)).not.toBe(heroTitle(before))
  })

  it('keeps the intent and says so when asked for more of the same', async () => {
    const workspace = await act(await inEmotionalAfrobeats(), {
      type: 'select_quick_action',
      actionId: 'more-like-this',
    })

    expect(view(workspace).content.at(-2)).toMatchObject({
      label: 'Keeping this direction',
      detail: 'Emotional · Afrobeats · Low energy',
    })
    expect(view(workspace).intentSummary?.chips.some((chip) => chip.changed)).toBe(
      false,
    )
  })

  it('ignores a quick action that is not on offer', async () => {
    const workspace = await inEmotionalAfrobeats()

    expect(
      await act(workspace, { type: 'select_quick_action', actionId: 'push-it-harder' }),
    ).toBe(workspace)
  })

  it('understands a request to save or a declaration of liking as a reaction, not a new direction', async () => {
    const base = await inEmotionalAfrobeats()
    const saving = await act(base, { type: 'send_message', text: 'Save this.' })
    const liking = await act(base, { type: 'send_message', text: 'I love this one' })

    expect(view(saving).overlay).toMatchObject({ type: 'playlist_picker', selectedIds: [] })
    expect(heroTitle(saving)).toBe(heroTitle(base))
    expect(hero(liking)).toMatchObject({ liked: true, echo: 'I love this one' })
    expect(types(liking)).toEqual(types(base))
  })
})

describe('starters the library cannot act on', () => {
  const limitedStarters = async () => {
    const base = await service.loadWorkspace()
    return createWorkspace({
      ...base,
      starters: base.starters.map((starter) =>
        starter.id === 'discover'
          ? starter
          : { ...starter, unavailableReason: 'Your music has no mood or energy information for this yet.' },
      ),
    })
  }

  it('sends nothing for an unavailable starter', async () => {
    const workspace = await limitedStarters()

    for (const starterId of ['focus', 'unwind', 'move']) {
      expect(planCommand(workspace, { type: 'select_starter', starterId })).toEqual({ actions: [] })
    }
  })

  it('keeps Discover usable, since it is an exploration control and needs no mood or energy', async () => {
    const workspace = await limitedStarters()

    const discovering = await act(workspace, { type: 'select_starter', starterId: 'discover' })

    expect(planCommand(workspace, { type: 'select_starter', starterId: 'discover' }).question).toBeDefined()
    expect(hero(discovering)).toBeDefined()
  })

  it('sends nothing for any starter, Discover included, while the library is not ready', async () => {
    const base = await service.loadWorkspace()
    const notReady = createWorkspace({
      ...base,
      libraryReady: false,
      unavailableDimensions: ['mood', 'genre', 'energy'],
      starters: base.starters.map((starter) => ({
        ...starter,
        unavailableReason: 'Your library has no playable music yet. Import music to start listening.',
      })),
    })

    for (const starterId of ['focus', 'unwind', 'move', 'discover']) {
      expect(planCommand(notReady, { type: 'select_starter', starterId })).toEqual({ actions: [] })
    }
    expect(selectEnvironment(notReady).libraryReady).toBe(false)
  })

  it('is never the mock: it reports full capability, so the design can show every starter', async () => {
    const seed = await service.loadWorkspace()

    expect(seed.starters.map((starter) => [starter.id, starter.unavailableReason])).toEqual([
      ['focus', undefined],
      ['unwind', undefined],
      ['move', undefined],
      ['discover', undefined],
    ])
    expect(seed.unavailableDimensions ?? []).toEqual([])
    expect(createWorkspace(seed).libraryReady).toBe(true)
    expect(Object.values(seed.refineOptions).flat().some((value) => value.unavailable)).toBe(false)
    for (const starterId of ['focus', 'unwind', 'move', 'discover']) {
      expect(planCommand(createWorkspace(seed), { type: 'select_starter', starterId }).question).toBeDefined()
    }
  })
})

describe('tuning', () => {
  it('opens from Tune, changes the energy and stays open on the same tab', async () => {
    const tuning = await act(await inEmotionalAfrobeats(), { type: 'open_refine' })
    const changed = await act(tuning, {
      type: 'refine',
      dimension: 'energy',
      valueId: 'high',
    })

    expect(view(tuning).contextualControl).toMatchObject({
      type: 'refine_control',
      activeTab: 'energy',
      energyId: 'low',
    })
    expect(view(changed).contextualControl).toMatchObject({
      type: 'refine_control',
      activeTab: 'energy',
      energyId: 'high',
    })
    expect(view(changed).content.at(-2)).toMatchObject({
      label: 'Energy adjusted',
      changes: [{ dimension: 'Energy', from: 'Low', to: 'High' }],
    })
    expect(view(changed).intentSummary?.chips.at(-1)).toMatchObject({
      label: 'High energy',
      changed: true,
      expanded: true,
    })
    expect(heroTitle(changed)).toBe('Peru')
  })

  it('changes mood and genre the same way', async () => {
    const workspace = await act(
      await inEmotionalAfrobeats(),
      { type: 'toggle_refine_tab', tab: 'mood' },
      { type: 'refine', dimension: 'mood', valueId: 'driven' },
      { type: 'change_refine_tab', tab: 'genre' },
      { type: 'refine', dimension: 'genre', valueId: 'amapiano' },
    )

    expect(view(workspace).intentSummary?.chips.map((chip) => chip.label)).toEqual([
      'Driven',
      'Amapiano',
      'Low energy',
    ])
    expect(view(workspace).accent).toBe('driven')
    expect(view(workspace).content.at(-2)).toMatchObject({ label: 'Genre switched' })
    expect(hero(workspace)).toMatchObject({ title: 'Water' })
  })

  it('does nothing when the value chosen is already the current one', async () => {
    const tuning = await act(await inEmotionalAfrobeats(), { type: 'open_refine' })

    expect(
      await act(tuning, { type: 'refine', dimension: 'energy', valueId: 'low' }),
    ).toBe(tuning)
  })

  it('marks what the library cannot use, sends nothing for it, and still tunes the rest', async () => {
    const limited = await act(
      createWorkspace({
        ...(await service.loadWorkspace()),
        unavailableDimensions: ['mood', 'energy'],
      }),
      { type: 'open_session', sessionId: 'emotional-afrobeats' },
      { type: 'open_refine' },
    )

    expect(view(limited).contextualControl).toMatchObject({
      type: 'refine_control',
      unavailable: ['mood', 'energy'],
    })
    expect(planCommand(limited, { type: 'refine', dimension: 'energy', valueId: 'high' })).toEqual({
      actions: [],
    })
    expect(planCommand(limited, { type: 'refine', dimension: 'mood', valueId: 'driven' })).toEqual({
      actions: [],
    })
    const switched = await act(limited, { type: 'refine', dimension: 'genre', valueId: 'amapiano' })
    expect(view(switched).content.at(-2)).toMatchObject({ label: 'Genre switched' })
  })

  it('sends nothing for a mood value the library cannot use, and still sends the others', async () => {
    const base = await service.loadWorkspace()
    const limited = await act(
      createWorkspace({
        ...base,
        refineOptions: {
          ...base.refineOptions,
          mood: base.refineOptions.mood.map((value) => (value.id === 'calm' ? { ...value, unavailable: true } : value)),
        },
      }),
      { type: 'open_session', sessionId: 'emotional-afrobeats' },
      { type: 'toggle_refine_tab', tab: 'mood' },
    )

    expect(planCommand(limited, { type: 'refine', dimension: 'mood', valueId: 'calm' })).toEqual({ actions: [] })
    expect(planCommand(limited, { type: 'refine', dimension: 'mood', valueId: 'driven' }).question).toBeDefined()
  })

  it('marks nothing unavailable when the library supports every dimension', async () => {
    expect(view(await inEmotionalAfrobeats()).contextualControl).not.toHaveProperty('unavailable')
    expect(
      view(await act(await inEmotionalAfrobeats(), { type: 'open_refine' })).contextualControl,
    ).toMatchObject({ type: 'refine_control', unavailable: [] })
  })

  it('opens from an intent chip and closes when the same chip is tapped again', async () => {
    const opened = await act(await inEmotionalAfrobeats(), {
      type: 'toggle_refine_tab',
      tab: 'genre',
    })
    const closed = await act(opened, { type: 'toggle_refine_tab', tab: 'genre' })

    expect(view(opened).contextualControl).toMatchObject({ activeTab: 'genre' })
    expect(view(closed).contextualControl?.type).toBe('quick_actions')
    expect(
      view(await act(opened, { type: 'close_refine' })).contextualControl?.type,
    ).toBe('quick_actions')
  })
})

describe('reacting to the current song', () => {
  it('likes without changing the song, the stream or the intent', async () => {
    const before = await inEmotionalAfrobeats()
    const liked = await act(before, { type: 'toggle_like' })

    expect(hero(liked)).toMatchObject({ liked: true })
    expect(heroTitle(liked)).toBe(heroTitle(before))
    expect(types(liked)).toEqual(types(before))
    expect(view(liked).intentSummary).toEqual(view(before).intentSummary)
    expect(actionLabels(liked)).toEqual(['More like this', 'Save this'])
    expect(hero(await act(liked, { type: 'toggle_like' }))).toMatchObject({ liked: false })
  })

  it('moves on from a song that is not for me and leaves the intent as it was', async () => {
    const before = await inEmotionalAfrobeats()
    const after = await act(before, { type: 'not_for_me' })
    const skipped = view(after).content.find(
      (block) => block.type === 'recommendation' && block.variant === 'compact',
    )
    const [ack, current] = view(after).content.slice(-2)

    expect(skipped).toMatchObject({ title: heroTitle(before), outcome: 'skipped' })
    expect(ack).toMatchObject({ label: 'Not for me', detail: 'Intent unchanged' })
    expect(current).toMatchObject({ variant: 'hero' })
    expect(view(after).intentSummary).toEqual(view(before).intentSummary)
    expect(heroTitle(after)).not.toBe(heroTitle(before))
    expect(actionLabels(after)).toEqual(['Different artist', 'Keep this mood'])
  })

  it('saves only to the playlists the user picks', async () => {
    const picking = await act(await inEmotionalAfrobeats(), { type: 'open_playlist_picker' })
    const unconfirmed = await act(picking, { type: 'confirm_playlists' })
    const saved = await act(
      picking,
      { type: 'toggle_playlist', playlistId: 'favorites' },
      { type: 'confirm_playlists' },
    )

    // Afrobeats is hinted for this session, yet nothing starts selected.
    expect(view(picking).overlay).toMatchObject({ selectedIds: [] })
    expect(
      view(picking).overlay?.playlists.filter((playlist) => playlist.fitsSession),
    ).toMatchObject([{ name: 'Afrobeats' }])
    expect(unconfirmed).toBe(picking)
    expect(view(saved).overlay).toBeNull()
    expect(hero(saved)).toMatchObject({ savedTo: ['Favorites'] })
    expect(actionLabels(saved)).toEqual(['More like this', 'Keep this energy'])
  })

  it('creates a playlist named after the session and selects it', async () => {
    const created = await act(
      await inEmotionalAfrobeats(),
      { type: 'open_playlist_picker' },
      { type: 'create_playlist' },
      { type: 'create_playlist' },
    )
    const names = view(created).overlay?.playlists.map((playlist) => playlist.name)
    const saved = await act(created, { type: 'confirm_playlists' })

    expect(names?.slice(-2)).toEqual(['Emotional Afrobeats', 'Emotional Afrobeats 2'])
    expect(view(created).overlay?.selectedIds).toHaveLength(2)
    expect(hero(saved)).toMatchObject({
      savedTo: ['Emotional Afrobeats', 'Emotional Afrobeats 2'],
    })
  })

  it('closes the picker without saving', async () => {
    const closed = await act(
      await inEmotionalAfrobeats(),
      { type: 'open_playlist_picker' },
      { type: 'toggle_playlist', playlistId: 'study' },
      { type: 'close_playlist_picker' },
    )

    expect(view(closed).overlay).toBeNull()
    expect(hero(closed)).toMatchObject({ savedTo: [] })
  })
})

describe('moving through songs', () => {
  it('goes to the next song without an acknowledgement', async () => {
    const before = await inEmotionalAfrobeats()
    const after = await act(before, { type: 'next' })
    const count = (workspace: WorkspaceState, type: string) =>
      types(workspace).filter((candidate) => candidate === type).length

    expect(count(after, 'ack')).toBe(count(before, 'ack'))
    expect(count(after, 'recommendation')).toBe(count(before, 'recommendation') + 1)
    expect(heroTitle(after)).not.toBe(heroTitle(before))
  })

  it('peeks at what is next after a few songs, then plays exactly that', async () => {
    const second = await act(await inEmotionalAfrobeats(), { type: 'next' })
    const third = await act(second, { type: 'next' })
    const peek = view(third).content.at(-1)
    const fourth = await act(third, { type: 'next' })

    expect(types(second)).not.toContain('up_next')
    expect(peek?.type).toBe('up_next')
    expect(heroTitle(fourth)).toBe(peek?.type === 'up_next' ? peek.title : null)
  })

  it('hides the peek while tuning and drops it when the direction changes', async () => {
    const peeking = await act(await inEmotionalAfrobeats(), { type: 'next' }, { type: 'next' })

    expect(types(await act(peeking, { type: 'open_refine' }))).not.toContain('up_next')
    expect(
      types(await act(peeking, { type: 'send_message', text: 'Make it more energetic.' })),
    ).not.toContain('up_next')
  })

  it('plays a song from the history again', async () => {
    const moved = await act(await inEmotionalAfrobeats(), { type: 'next' })
    const first = view(moved).content.find(
      (block) => block.type === 'recommendation' && block.variant === 'compact',
    )
    const replayed = await act(moved, {
      type: 'replay',
      recommendationId:
        first?.type === 'recommendation' ? first.recommendationId : '',
    })

    expect(heroTitle(replayed)).toBe('Calm Down')
    expect(
      view(replayed).content.filter(
        (block) => block.type === 'recommendation' && block.variant === 'hero',
      ),
    ).toHaveLength(1)
  })

  it('never recommends the same song twice until the mock catalogue runs out', async () => {
    let workspace = await inEmotionalAfrobeats()
    const titles = [heroTitle(workspace)]
    for (let step = 0; step < 12; step++) {
      workspace = await act(workspace, { type: 'next' })
      titles.push(heroTitle(workspace))
    }

    expect(new Set(titles).size).toBe(13)
    expect(heroTitle(await act(workspace, { type: 'next' }))).not.toBe(titles.at(-1))
  })
})

describe('the playback clock', () => {
  it('advances a playing song one second per tick', async () => {
    const before = await inEmotionalAfrobeats()
    const after = await act(before, { type: 'tick' }, { type: 'tick' })

    expect(hero(after)).toMatchObject({ positionSeconds: 74 })
  })

  it('stands still while paused or covered by a sheet or the drawer', async () => {
    const base = await inEmotionalAfrobeats()
    const paused = await act(base, { type: 'toggle_play' })
    const picking = await act(base, { type: 'open_playlist_picker' })
    const browsing = await act(base, { type: 'open_drawer' })

    expect(await act(paused, { type: 'tick' })).toBe(paused)
    expect(await act(picking, { type: 'tick' })).toBe(picking)
    expect(await act(browsing, { type: 'tick' })).toBe(browsing)
  })

  it('moves to the next song when the current one ends', async () => {
    let workspace = await inEmotionalAfrobeats()
    const first = heroTitle(workspace)
    for (let second = 72; second < 239; second++) {
      workspace = await act(workspace, { type: 'tick' })
    }

    expect(heroTitle(workspace)).not.toBe(first)
    expect(hero(workspace)).toMatchObject({ positionSeconds: 0, playing: true })
  })
})

describe('moving between sessions', () => {
  it('opens another session and picks up where it left off', async () => {
    const workspace = await act(
      await open(),
      { type: 'open_drawer' },
      { type: 'open_session', sessionId: 'gym-energy' },
    )

    expect(view(workspace).title).toBe('Gym Energy')
    expect(view(workspace).drawerOpen).toBe(false)
    expect(view(workspace).content.at(-2)).toMatchObject({
      type: 'session_summary',
      label: 'Picking up where you left off',
      detail: 'Driven · Amapiano · High energy',
    })
    expect(heroTitle(workspace)).toBe('Mnike')
  })

  it('drops a new session that was never used', async () => {
    const workspace = await act(
      await open(),
      { type: 'open_session', sessionId: 'coding' },
      { type: 'open_drawer' },
    )

    expect(view(workspace).navigation.sessions.map((session) => session.title)).toEqual(
      ['Emotional Afrobeats', 'Late Night Study', 'Gym Energy', 'Coding', 'Morning Focus'],
    )
  })

  it('keeps each session’s own state while the user is elsewhere', async () => {
    const tuned = await act(
      await inEmotionalAfrobeats(),
      { type: 'toggle_like' },
      { type: 'send_message', text: 'Make it more energetic.' },
    )
    const away = await act(tuned, { type: 'open_session', sessionId: 'coding' })
    const back = await act(away, { type: 'open_session', sessionId: 'emotional-afrobeats' })

    expect(view(away).title).toBe('Coding')
    expect(heroTitle(back)).toBe(heroTitle(tuned))
    expect(view(back).intentSummary?.chips.map((chip) => chip.label)).toEqual([
      'Emotional',
      'Afrobeats',
      'Medium energy',
    ])
    expect(
      view(await act(away, { type: 'open_drawer' })).navigation.sessions.find(
        (session) => session.title === 'Emotional Afrobeats',
      )?.subtitle,
    ).toBe('Emotional · Afrobeats · Medium energy')
  })

  it('creates a new session at the top of the drawer', async () => {
    const workspace = await act(
      await inEmotionalAfrobeats(),
      { type: 'new_session' },
      { type: 'select_starter', starterId: 'move' },
      { type: 'open_drawer' },
    )
    const [first] = view(workspace).navigation.sessions

    expect(first).toMatchObject({
      title: 'Move',
      subtitle: 'Driven · Any genre · High energy',
      active: true,
    })
    expect(view(workspace).navigation.sessions).toHaveLength(6)
  })

  it('only closes the drawer when the open session is chosen again, or a new one is already open', async () => {
    const browsing = await act(await inEmotionalAfrobeats(), { type: 'open_drawer' })
    const same = await act(browsing, {
      type: 'open_session',
      sessionId: 'emotional-afrobeats',
    })
    const fresh = await act(await open(), { type: 'open_drawer' }, { type: 'new_session' })

    expect(view(browsing).drawerOpen).toBe(true)
    expect(view(same).drawerOpen).toBe(false)
    expect(types(same)).toEqual(types(await inEmotionalAfrobeats()))
    expect(view(fresh).drawerOpen).toBe(false)
    expect(view(fresh).layout).toBe('prompt')
  })
})

describe('across a long session', () => {
  const script: SessionCommand[] = [
    { type: 'select_starter', starterId: 'unwind' },
    { type: 'toggle_like' },
    { type: 'select_quick_action', actionId: 'more-like-this' },
    { type: 'not_for_me' },
    { type: 'send_message', text: 'Something for the gym, amapiano' },
    { type: 'open_refine' },
    { type: 'refine', dimension: 'energy', valueId: 'very-high' },
    { type: 'refine', dimension: 'mood', valueId: 'joyful' },
    { type: 'close_refine' },
    { type: 'next' },
    { type: 'next' },
    { type: 'open_playlist_picker' },
    { type: 'toggle_playlist', playlistId: 'workout' },
    { type: 'confirm_playlists' },
    { type: 'send_message', text: 'I’m getting sleepy but still need to study' },
    { type: 'select_quick_action', actionId: 'keep-this-energy' },
    { type: 'next' },
    { type: 'send_message', text: 'skip' },
    { type: 'send_message', text: 'surprise me' },
  ]

  it('always shows one hero, at most two quick actions, and an acknowledgement that matches the intent', async () => {
    let workspace = await open()

    for (const command of script) {
      workspace = await act(workspace, command)
      const session = activeSession(workspace)
      const composed = view(workspace)
      const heroes = composed.content.filter(
        (block) => block.type === 'recommendation' && block.variant === 'hero',
      )
      const latest = session.events.findLast(
        (event) =>
          event.kind === 'intent_set' ||
          event.kind === 'intent_updated' ||
          event.kind === 'intent_kept',
      )

      expect(heroes).toHaveLength(1)
      expect(session.quickActions.length).toBeLessThanOrEqual(2)
      if (latest?.kind === 'intent_set' || latest?.kind === 'intent_kept') {
        expect(latest.intent).toEqual(session.intent)
      }
      if (latest?.kind === 'intent_updated') {
        for (const change of latest.changes) {
          expect(session.intent?.[change.dimension]).toEqual(change.to)
        }
      }
    }
  })

  it('is deterministic: the same commands give the same session', async () => {
    expect(await act(await open(), ...script)).toEqual(await act(await open(), ...script))
  })
})
