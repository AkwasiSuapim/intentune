// @vitest-environment jsdom
// What a user sees, hears and can do while the service is slow or fails:
// loading the sessions, waiting for an answer, and trying again.
import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { heldService, renderApp } from '../../test/dom.tsx'

const button = (name: string | RegExp) => screen.getByRole('button', { name })
const queryButton = (name: string | RegExp) =>
  screen.queryByRole('button', { name })
const announcer = () => screen.getByRole('status')
const heroLabel = () =>
  screen.queryAllByRole('article')[0]?.getAttribute('aria-label') ?? null
const composer = () =>
  screen.getByRole('textbox', { name: 'Tell Intentune what you want' })
const focused = () => document.activeElement

/** Opens the app on a held service, with its sessions already loaded. */
async function openHeld() {
  const held = heldService()
  const app = await renderApp(held.service)
  await held.answer()
  return { held, ...app }
}

describe('loading the listening sessions', () => {
  it('says it is loading, then opens on Tune in', async () => {
    const held = heldService()
    await renderApp(held.service)

    expect(screen.getByRole('heading', { level: 1, name: 'intentune' })).toBeTruthy()
    expect(announcer().textContent).toBe('Loading your sessions…')
    expect(screen.getByRole('main').getAttribute('aria-busy')).toBe('true')
    expect(queryButton('Try again')).toBeNull()

    await held.answer()

    expect(
      screen.getByRole('heading', {
        name: 'What do you need from your music right now?',
      }),
    ).toBeTruthy()
  })

  it('offers to try again when they cannot be loaded, without losing focus', async () => {
    const held = heldService()
    const { user } = await renderApp(held.service)
    await held.fail()

    expect(announcer().textContent).toBe('Couldn’t load your sessions.')
    await user.click(button('Try again'))

    // The button stays, unavailable, while the retry loads.
    expect(focused()).toBe(button('Try again'))
    expect(button('Try again').getAttribute('aria-disabled')).toBe('true')
    expect(announcer().textContent).toBe('Loading your sessions…')

    await held.fail()
    expect(focused()).toBe(button('Try again'))
    expect(button('Try again').getAttribute('aria-disabled')).toBeNull()

    await user.click(button('Try again'))
    await held.answer()
    expect(button('Focus: Help me focus')).toBeTruthy()
  })
})

describe('waiting for an answer', () => {
  it('shows the words at once and a note while waiting, then the answer', async () => {
    const { held, user } = await openHeld()

    await user.type(composer(), 'Help me focus{Enter}')

    expect(screen.getByText('Help me focus')).toBeTruthy()
    expect(screen.getByText('Working on it…')).toBeTruthy()
    expect(heroLabel()).toBeNull()
    expect((composer() as HTMLInputElement).value).toBe('')

    await held.answer()

    expect(screen.queryByText('Working on it…')).toBeNull()
    expect(screen.getAllByText('Help me focus')).toHaveLength(1)
    expect(screen.getByText('Intent set')).toBeTruthy()
    expect(heroLabel()).toBe('Now playing: Last Last by Burna Boy')
    expect(announcer().textContent).toContain('Now playing Last Last by Burna Boy.')
  })

  it('shows a starter’s phrase as the listener’s words while its answer is on the way', async () => {
    const { held, user } = await openHeld()

    await user.click(button('Unwind: Something to unwind to'))

    expect(screen.getByText('Something to unwind to')).toBeTruthy()
    expect(screen.getByText('Working on it…')).toBeTruthy()

    await held.answer()

    expect(screen.getAllByText('Something to unwind to')).toHaveLength(1)
    expect(screen.queryByText('Working on it…')).toBeNull()
  })

  it('sends one request at a time and keeps what is typed meanwhile', async () => {
    const { held, user } = await openHeld()
    await user.click(button('Focus: Help me focus'))
    await held.answer()

    await user.click(button('A bit calmer'))
    await user.click(button('Keep this energy'))
    await user.click(button('Next recommendation'))
    await user.type(composer(), 'More energy{Enter}')

    expect(held.waiting()).toBe(1)
    expect((composer() as HTMLInputElement).value).toBe('More energy')
    expect(button('Send to Intentune').getAttribute('aria-disabled')).toBe('true')

    await held.answer()
    expect(button('Send to Intentune').getAttribute('aria-disabled')).toBeNull()
    await user.keyboard('{Enter}')
    expect(held.waiting()).toBe(1)
    expect((composer() as HTMLInputElement).value).toBe('')
  })

  it('holds keyboard focus on the note, then hands it to the new song', async () => {
    const { held, user } = await openHeld()

    button('Focus: Help me focus').focus()
    await user.keyboard('{Enter}')
    expect(focused()?.textContent).toBe('Working on it…')

    await held.answer()
    expect(focused()).toBe(button('Pause Last Last'))
  })
})

describe('an answer that never comes', () => {
  it('says so, keeps the words and the song, and tries again on request', async () => {
    const { held, user } = await openHeld()
    await user.click(button('Focus: Help me focus'))
    await held.answer()

    await user.click(button('A bit calmer'))
    await held.fail()

    expect(screen.getByText('That didn’t go through.')).toBeTruthy()
    expect(announcer().textContent).toBe('That didn’t go through. You can try again.')
    expect(
      screen.getAllByText('A bit calmer').some((element) => element.closest('main')),
    ).toBe(true)
    expect(heroLabel()).toBe('Now playing: Last Last by Burna Boy')

    await user.click(button('Try again'))
    expect(screen.getByText('Working on it…')).toBeTruthy()
    await held.answer()

    expect(screen.queryByText('That didn’t go through.')).toBeNull()
    expect(heroLabel()).not.toBe('Now playing: Last Last by Burna Boy')
  })

  it('moves focus from the waiting note to Try again', async () => {
    const { held, user } = await openHeld()

    button('Focus: Help me focus').focus()
    await user.keyboard('{Enter}')
    await held.fail()

    expect(focused()).toBe(button('Try again'))
    await user.keyboard('{Enter}')
    expect(focused()?.textContent).toBe('Working on it…')
    await held.answer()
    expect(focused()).toBe(button('Pause Last Last'))
  })

  it('makes way for something else the user asks', async () => {
    const { held, user } = await openHeld()
    await user.click(button('Focus: Help me focus'))
    await held.answer()
    await user.click(button('Next recommendation'))
    await held.fail()

    await user.type(composer(), 'Make it more energetic.{Enter}')

    expect(screen.queryByText('That didn’t go through.')).toBeNull()
    expect(screen.getByText('Working on it…')).toBeTruthy()
  })

  it('takes back a like the service could not record, without a failure note', async () => {
    const { held, user } = await openHeld()
    await user.click(button('Focus: Help me focus'))
    await held.answer()

    await user.click(button('Like'))
    expect(button('Liked').getAttribute('aria-pressed')).toBe('true') // at once, while it is recorded
    await held.fail()

    expect(button('Like').getAttribute('aria-pressed')).toBe('false')
    expect(screen.queryByText('That didn’t go through.')).toBeNull()
    expect(
      within(screen.getByRole('group', { name: 'Suggested refinements' }))
        .getAllByRole('button')
        .map((action) => action.textContent),
    ).toEqual(['Keep this energy', 'A bit calmer'])
  })
})

describe('an answer for a session the user has left', () => {
  it('lands in that session, not the one now open', async () => {
    const { held, user } = await openHeld()
    await user.click(button('Focus: Help me focus'))
    await held.answer()
    await user.click(button('Next recommendation'))

    await user.click(button('Open listening sessions'))
    await user.click(button(/^Coding/))
    const coding = heroLabel()
    await held.answer()

    expect(heroLabel()).toBe(coding)
    await user.click(button('Open listening sessions'))
    await user.click(button(/^Focus/))
    expect(heroLabel()).not.toBe('Now playing: Last Last by Burna Boy')
    expect(screen.queryByText('Working on it…')).toBeNull()
  })
})
