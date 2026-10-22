// The session feature against the service boundary: what it does at once,
// what it asks, and how it handles an answer that is late, fails, or arrives
// for a session the user has left.
import { describe, expect, it } from 'vitest'
import { mockSessionService } from '../../mocks/mockSessionService.ts'
import { ask, planCommand } from './commands.ts'
import type { SessionCommand } from './commands.ts'
import { composeSession } from './composeSession.ts'
import type { SessionService } from './sessionService.ts'
import {
  activeSession,
  createWorkspace,
  selectEnvironment,
  workspaceReducer,
} from './workspaceReducer.ts'
import type { WorkspaceState } from './workspaceReducer.ts'

const offline = () => Promise.reject(new Error('The service could not be reached'))

/** The mock service with some of its answers replaced. */
const serviceWith = (overrides: Partial<SessionService>): SessionService => ({
  ...mockSessionService,
  ...overrides,
})

const open = async () =>
  createWorkspace(await mockSessionService.loadWorkspace())

/** Applies what a command does at once, and returns what it asks, unanswered. */
function start(workspace: WorkspaceState, command: SessionCommand) {
  const { actions, question } = planCommand(workspace, command)
  return { workspace: actions.reduce(workspaceReducer, workspace), question }
}

/** Runs a command to the end, with the service's answer applied. */
async function act(
  workspace: WorkspaceState,
  command: SessionCommand,
  service: SessionService = mockSessionService,
) {
  const started = start(workspace, command)
  if (!started.question) return started.workspace
  return workspaceReducer(started.workspace, await ask(service, started.question))
}

const view = (workspace: WorkspaceState) =>
  composeSession(activeSession(workspace), selectEnvironment(workspace))

const types = (workspace: WorkspaceState) =>
  view(workspace).content.map((block) => block.type)

const heroTitle = (workspace: WorkspaceState) =>
  view(workspace).content.flatMap((block) =>
    block.type === 'recommendation' && block.variant === 'hero'
      ? [block.title]
      : [],
  )[0]

/** A session already playing its first song. */
const playing = async () =>
  act(await open(), { type: 'select_starter', starterId: 'focus' })

describe('a request on its way', () => {
  it('shows the words and a waiting note at once, then the answer in their place', async () => {
    const { workspace: waiting, question } = start(await open(), {
      type: 'send_message',
      text: '  Help me focus ',
    })
    const pending = view(waiting)

    expect(question).toMatchObject({
      kind: 'turn',
      request: { kind: 'message', text: 'Help me focus' },
    })
    expect(pending.layout).toBe('timeline')
    expect(pending.busy).toBe(true)
    expect(pending.content).toEqual([
      { type: 'user_message', id: 'e1', text: 'Help me focus' },
      { type: 'turn_status', id: 'turn-pending', status: 'pending' },
    ])

    const answered = workspaceReducer(
      waiting,
      await ask(mockSessionService, question!),
    )

    expect(view(answered).busy).toBe(false)
    expect(types(answered)).toEqual(['user_message', 'ack', 'recommendation'])
    // The words keep their place in the stream: same block, same id.
    expect(view(answered).content[0]).toEqual(pending.content[0])
  })

  it('sends one request at a time', async () => {
    const { workspace: waiting } = start(await playing(), { type: 'next' })

    for (const command of [
      { type: 'next' },
      { type: 'not_for_me' },
      { type: 'send_message', text: 'More energy' },
      { type: 'select_quick_action', actionId: 'a-bit-calmer' },
      { type: 'refine', dimension: 'energy', valueId: 'high' },
    ] satisfies SessionCommand[]) {
      expect(planCommand(waiting, command)).toEqual({ actions: [] })
    }
  })

  it('lets everything that stays on this device carry on meanwhile', async () => {
    const { workspace: waiting } = start(await playing(), { type: 'next' })

    for (const command of [
      { type: 'toggle_play' },
      { type: 'toggle_why' },
      { type: 'open_refine' },
      { type: 'open_drawer' },
    ] satisfies SessionCommand[]) {
      expect(planCommand(waiting, command).actions).not.toEqual([])
    }
  })

  it('stops the clock at the end of a song rather than ask twice', async () => {
    let workspace = start(await playing(), { type: 'next' }).workspace
    for (let second = 0; second < 400; second++) {
      workspace = start(workspace, { type: 'tick' }).workspace
    }

    expect(planCommand(workspace, { type: 'tick' })).toEqual({ actions: [] })
  })
})

describe('a request that fails', () => {
  it('stays in the session as a failure, with the words kept', async () => {
    const before = await playing()
    const failed = await act(
      before,
      { type: 'select_quick_action', actionId: 'a-bit-calmer' },
      serviceWith({ respond: offline }),
    )

    expect(activeSession(failed).openRequest).toEqual({
      request: { kind: 'message', text: 'A bit calmer' },
      status: 'failed',
    })
    expect(view(failed).busy).toBe(false)
    expect(view(failed).content.slice(-2)).toMatchObject([
      { type: 'user_message', text: 'A bit calmer' },
      { type: 'turn_status', status: 'failed' },
    ])
    // Nothing else moved: same song, same intent.
    expect(heroTitle(failed)).toBe(heroTitle(before))
    expect(activeSession(failed).intent).toEqual(activeSession(before).intent)
  })

  it('sends the same request again on retry', async () => {
    const failed = await act(
      await playing(),
      { type: 'not_for_me' },
      serviceWith({ respond: offline }),
    )
    const retried = start(failed, { type: 'retry' })

    expect(retried.question).toMatchObject({
      kind: 'turn',
      request: { kind: 'not_for_me' },
    })
    expect(view(retried.workspace).content.at(-1)).toMatchObject({
      type: 'turn_status',
      status: 'pending',
    })

    const answered = workspaceReducer(
      retried.workspace,
      await ask(mockSessionService, retried.question!),
    )
    expect(activeSession(answered).openRequest).toBeNull()
    expect(types(answered)).not.toContain('turn_status')
  })

  it('gives way to a different request', async () => {
    const failed = await act(
      await playing(),
      { type: 'next' },
      serviceWith({ respond: offline }),
    )
    const instead = await act(failed, {
      type: 'send_message',
      text: 'Make it more energetic.',
    })

    expect(activeSession(instead).openRequest).toBeNull()
    expect(types(instead)).not.toContain('turn_status')
  })

  it('offers no retry when nothing has failed', async () => {
    expect(planCommand(await playing(), { type: 'retry' })).toEqual({
      actions: [],
    })
  })

  it('keeps a new session that failed on its first request', async () => {
    const failed = await act(
      await open(),
      { type: 'select_starter', starterId: 'focus' },
      serviceWith({ respond: offline }),
    )
    const elsewhere = await act(failed, {
      type: 'open_session',
      sessionId: 'coding',
    })

    expect(elsewhere.sessionOrder).toContain(activeSession(failed).id)
  })
})

describe('answers that arrive after the user has moved on', () => {
  it('go to the session that asked', async () => {
    const focus = await playing()
    const { workspace: waiting, question } = start(focus, { type: 'next' })
    const elsewhere = workspaceReducer(waiting, {
      type: 'session_opened',
      sessionId: 'coding',
    })

    const answered = workspaceReducer(
      elsewhere,
      await ask(mockSessionService, question!),
    )

    expect(view(answered)).toEqual(view(elsewhere))
    const asked = answered.sessions[focus.activeSessionId]
    expect(asked.openRequest).toBeNull()
    expect(asked.currentRecommendationId).not.toBe(
      activeSession(focus).currentRecommendationId,
    )
  })

  it('leave the drawer open if it was opened while waiting', async () => {
    const { workspace: waiting, question } = start(await playing(), {
      type: 'next',
    })
    const browsing = start(waiting, { type: 'open_drawer' }).workspace
    const answered = workspaceReducer(
      browsing,
      await ask(mockSessionService, question!),
    )

    expect(view(answered).drawerOpen).toBe(true)
    expect(heroTitle(answered)).not.toBe(heroTitle(browsing))
  })

  it('close the playlist sheet, which was for the song now replaced', async () => {
    const { workspace: waiting, question } = start(await playing(), {
      type: 'next',
    })
    const picking = start(waiting, { type: 'open_playlist_picker' }).workspace
    const answered = workspaceReducer(
      picking,
      await ask(mockSessionService, question!),
    )

    expect(view(picking).overlay).not.toBeNull()
    expect(view(answered).overlay).toBeNull()
  })

  it('drop a hint about a song that is no longer current', async () => {
    const { workspace: liked, question } = start(await playing(), {
      type: 'toggle_like',
    })
    const moved = await act(liked, { type: 'next' })
    const late = workspaceReducer(
      moved,
      await ask(mockSessionService, question!),
    )

    expect(activeSession(late).quickActions).toEqual(
      activeSession(moved).quickActions,
    )
  })
})

describe('hints the service cannot give', () => {
  // The reaction itself is recorded; only the hints that may come with it are missing.
  const noHints = serviceWith({
    react: async () => ({}),
    savePlaylists: async () => ({}),
    quickActionsAfter: offline,
    suggestPlaylists: offline,
  })

  it('leave the reaction in place and change nothing else', async () => {
    const before = await playing()
    const liked = await act(before, { type: 'toggle_like' }, noHints)

    expect(view(liked).content.at(-1)).toMatchObject({ liked: true })
    expect(activeSession(liked).quickActions).toEqual(
      activeSession(before).quickActions,
    )
    expect(activeSession(liked).openRequest).toBeNull()
  })

  it('still open the playlist sheet, without suggestions', async () => {
    const picking = await act(
      await playing(),
      { type: 'open_playlist_picker' },
      noHints,
    )

    expect(view(picking).overlay?.playlists.some((p) => p.fitsSession)).toBe(false)
  })

  it('take back a like the service could not record, without failing anything else', async () => {
    const before = await playing()
    const liked = await act(before, { type: 'toggle_like' }, serviceWith({ react: offline }))

    expect(view(liked).content.at(-1)).toMatchObject({ liked: false })
    expect(activeSession(liked).quickActions).toEqual(activeSession(before).quickActions)
    expect(activeSession(liked).openRequest).toBeNull()
  })

  it('take back a save the service could not record', async () => {
    const before = await playing()
    const picking = await act(before, { type: 'open_playlist_picker' })
    const chosen = await act(picking, { type: 'toggle_playlist', playlistId: 'study' })
    const saved = await act(chosen, { type: 'confirm_playlists' }, serviceWith({ savePlaylists: offline }))

    const current = activeSession(saved)
    expect(current.recommendations[current.currentRecommendationId!].savedToPlaylistIds).toEqual([])
    expect(current.overlay).toBeNull()
  })

  it('do not fail a request that asked for them', async () => {
    const saving = await act(
      await playing(),
      { type: 'send_message', text: 'Save this' },
      noHints,
    )

    expect(activeSession(saving).openRequest).toBeNull()
    expect(view(saving).overlay).not.toBeNull()
  })
})
