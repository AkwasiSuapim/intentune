// @vitest-environment jsdom
// The interactive app in a DOM: what a user can see, press and hear, by
// pointer and by keyboard, including the behaviour that lives in effects.
import { screen, within } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import {
  advance,
  renderApp,
  setObservedVisible,
  useWideScreen,
} from '../../test/dom.tsx'

const button = (name: string | RegExp) => screen.getByRole('button', { name })
const announcer = () => screen.getByRole('status')
const heroes = () => screen.queryAllByRole('article')
const hero = () => {
  const [article] = heroes()
  return within(article)
}
const intent = () =>
  within(screen.getByRole('group', { name: 'Current intent' }))
    .getAllByRole('button')
    .map((chip) => chip.textContent)

/** Starts a session from the Focus starter. */
async function startFocus(user: UserEvent) {
  await user.click(button('Focus: Help me focus'))
}

/**
 * jsdom runs no animations, so an exit that would end with `animationend` in a
 * browser ends here on the fallback timer instead. (The real exit path is
 * checked in a browser; React also listens for a vendor-prefixed event name
 * in jsdom, so a synthetic `animationend` would not reach it.)
 */
const finishExit = () => advance(700)

/** Moves the clock on one second at a time, rendering between ticks as a browser would. */
function play(seconds: number) {
  for (let second = 0; second < seconds; second++) advance(1000)
}

/** Opens one of the seeded sessions through the drawer and lets it close. */
async function openSession(user: UserEvent, title: string) {
  await user.click(button('Open listening sessions'))
  await user.click(button(new RegExp(`^${title}`)))
  finishExit()
}

describe('starting a session', () => {
  it('opens on Tune in, with four starters and the composer ready', () => {
    renderApp()

    expect(
      screen.getByRole('heading', {
        name: 'What do you need from your music right now?',
      }),
    ).toBeTruthy()
    expect(
      screen.getAllByRole('button', { name: /^(Focus|Unwind|Move|Discover): / }),
    ).toHaveLength(4)
    expect(
      screen.getByRole('textbox', { name: 'Tell Intentune what you want' }),
    ).toBeTruthy()
    expect(screen.queryByRole('group', { name: 'Current intent' })).toBeNull()
    expect(heroes()).toHaveLength(0)
  })

  it('turns a starter into the first turn, announces it, and keeps focus on the new song', async () => {
    const { user } = renderApp()
    await startFocus(user)

    expect(screen.getByRole('heading', { level: 1, name: 'Focus' })).toBeTruthy()
    expect(screen.getByText('Help me focus')).toBeTruthy()
    expect(screen.getByText('Intent set')).toBeTruthy()
    expect(intent()).toEqual(['Focused', 'Any genre', 'Medium energy'])
    expect(heroes()).toHaveLength(1)
    expect(heroes()[0].getAttribute('aria-label')).toBe(
      'Now playing: Last Last by Burna Boy',
    )
    expect(announcer().textContent).toBe(
      'Intent set, Focused, Any genre, Medium energy. Now playing Last Last by Burna Boy.',
    )
    // The starter is gone; focus moved to the new song rather than the page.
    expect(document.activeElement).toBe(button('Pause Last Last'))
  })

  it('sends a typed request on Enter, clears the field and keeps focus in it', async () => {
    const { user } = renderApp()
    await startFocus(user)
    const field = screen.getByRole('textbox', { name: 'Tell Intentune what you want' })

    await user.type(field, 'Make it more energetic{Enter}')

    expect(screen.getByText('Make it more energetic')).toBeTruthy()
    expect((field as HTMLInputElement).value).toBe('')
    expect(document.activeElement).toBe(field)
    expect(intent()).toEqual(['Focused', 'Any genre', 'High energy'])
    expect(announcer().textContent).toBe(
      'Intent updated, Energy Medium to High. Now playing Peru by Fireboy DML.',
    )
  })

  it('does not send an empty request', async () => {
    const { user } = renderApp()
    await user.type(
      screen.getByRole('textbox', { name: 'Tell Intentune what you want' }),
      '   {Enter}',
    )

    expect(heroes()).toHaveLength(0)
  })
})

describe('steering and reacting', () => {
  it('sends a quick action as its words and moves the hero into the history', async () => {
    const { user } = renderApp()
    await startFocus(user)

    await user.click(button('A bit calmer'))

    expect(screen.getByText('A bit calmer', { selector: 'p' })).toBeTruthy()
    expect(button('Play Last Last by Burna Boy again. Played')).toBeTruthy()
    expect(heroes()).toHaveLength(1)
    // The pressed action was replaced; focus stays in the same place in the row.
    expect(
      within(screen.getByRole('group', { name: 'Suggested refinements' }))
        .getAllByRole('button')
        .indexOf(document.activeElement as HTMLElement),
    ).toBe(1)
  })

  it('likes a song without moving on', async () => {
    const { user } = renderApp()
    await startFocus(user)

    await user.click(hero().getByRole('button', { name: 'Like' }))

    expect(
      hero().getByRole('button', { name: 'Liked' }).getAttribute('aria-pressed'),
    ).toBe('true')
    expect(heroes()[0].getAttribute('aria-label')).toBe(
      'Now playing: Last Last by Burna Boy',
    )
    expect(
      within(screen.getByRole('group', { name: 'Suggested refinements' }))
        .getAllByRole('button')
        .map((action) => action.textContent),
    ).toEqual(['More like this', 'Save this'])
  })

  it('moves on from a song that is not for me, keeping the intent and keyboard focus', async () => {
    const { user } = renderApp()
    await startFocus(user)
    const before = intent()

    hero().getByRole('button', { name: 'Not for me' }).focus()
    await user.keyboard('{Enter}')

    expect(button('Play Last Last by Burna Boy again. Skipped')).toBeTruthy()
    expect(intent()).toEqual(before)
    expect(announcer().textContent).toBe(
      'Not for me, Intent unchanged. Now playing Rush by Ayra Starr.',
    )
    expect(document.activeElement).toBe(
      hero().getByRole('button', { name: 'Not for me' }),
    )
  })

  it('goes to the next song quietly, keeping focus on Next', async () => {
    const { user } = renderApp()
    await startFocus(user)

    hero().getByRole('button', { name: 'Next recommendation' }).focus()
    await user.keyboard('{Enter}')

    expect(screen.getAllByText('Intent set')).toHaveLength(1)
    expect(screen.queryByText('Not for me', { selector: 'span' })).toBeNull()
    expect(announcer().textContent).toBe('Now playing Rush by Ayra Starr.')
    expect(document.activeElement).toBe(
      hero().getByRole('button', { name: 'Next recommendation' }),
    )
  })

  it('expands and collapses why the song fits', async () => {
    const { user } = renderApp()
    await startFocus(user)
    const why = hero().getByRole('button', { name: /^Why this fits/ })

    await user.click(why)
    expect(why.getAttribute('aria-expanded')).toBe('true')
    expect(hero().getAllByRole('listitem').length).toBeGreaterThan(0)

    await user.click(why)
    expect(why.getAttribute('aria-expanded')).toBe('false')
    expect(hero().queryAllByRole('listitem')).toHaveLength(0)
  })

  it('plays a song from the history again', async () => {
    const { user } = renderApp()
    await startFocus(user)
    await user.click(hero().getByRole('button', { name: 'Next recommendation' }))

    const history = button('Play Last Last by Burna Boy again. Played')
    await user.click(history)

    expect(heroes()[0].getAttribute('aria-label')).toBe(
      'Now playing: Last Last by Burna Boy',
    )
    // The history entry stays where it was, and so does focus.
    expect(document.activeElement).toBe(history)
  })
})

describe('saving to a playlist', () => {
  it('asks for an explicit choice, saves it, and hands focus back', async () => {
    const { user, container } = renderApp()
    await startFocus(user)
    await user.click(button('Save to a playlist'))

    const sheet = screen.getByRole('dialog', { name: 'Add to playlist' })
    expect(sheet.contains(document.activeElement)).toBe(true)
    expect(container.querySelector('main')?.closest('[inert]')).not.toBeNull()
    expect(
      within(sheet)
        .getAllByRole('checkbox')
        .filter((box) => box.getAttribute('aria-checked') === 'true'),
    ).toHaveLength(0)
    expect(
      (within(sheet).getByRole('button', { name: 'Choose a playlist' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true)

    await user.click(within(sheet).getByRole('checkbox', { name: /Workout/ }))
    await user.click(within(sheet).getByRole('button', { name: 'Save to Workout' }))

    // The rest of the screen is usable again at once; the sheet then leaves.
    expect(container.querySelector('main')?.closest('[inert]')).toBeNull()
    finishExit()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(document.activeElement).toBe(
      button('Saved to Workout. Change playlists'),
    )
  })

  it('closes on Escape without saving', async () => {
    const { user } = renderApp()
    await startFocus(user)
    await user.click(button('Save to a playlist'))
    await user.click(screen.getByRole('checkbox', { name: /Study/ }))

    await user.keyboard('{Escape}')
    finishExit()

    expect(screen.queryByRole('dialog')).toBeNull()
    expect(document.activeElement).toBe(button('Save to a playlist'))
  })

  it('hints at a playlist that fits the session without ticking it', async () => {
    const { user } = renderApp()
    await openSession(user, 'Emotional Afrobeats')
    await user.click(button('Save to a playlist'))

    const afrobeats = screen.getByRole('checkbox', { name: /^Afrobeats/ })
    expect(afrobeats.textContent).toContain('Fits this session')
    expect(afrobeats.getAttribute('aria-checked')).toBe('false')
  })
})

describe('tuning', () => {
  it('opens on the energy tab with focus on it, and arrow keys move between tabs', async () => {
    const { user } = renderApp()
    await startFocus(user)

    await user.click(button('Tune energy, mood or genre'))

    const tabs = screen.getAllByRole('tab')
    const selected = () => tabs.filter((tab) => tab.getAttribute('aria-selected') === 'true')
    expect(tabs.map((tab) => tab.textContent)).toEqual(['Energy', 'Mood', 'Genre'])
    expect(document.activeElement).toBe(screen.getByRole('tab', { name: 'Energy' }))
    // One Tab stop for the whole tab list.
    expect(tabs.map((tab) => tab.tabIndex)).toEqual([0, -1, -1])

    await user.keyboard('{ArrowRight}')
    expect(selected().map((tab) => tab.textContent)).toEqual(['Mood'])
    expect(document.activeElement).toBe(screen.getByRole('tab', { name: 'Mood' }))
    await user.keyboard('{End}')
    expect(document.activeElement).toBe(screen.getByRole('tab', { name: 'Genre' }))
    await user.keyboard('{ArrowRight}')
    expect(document.activeElement).toBe(screen.getByRole('tab', { name: 'Energy' }))
    await user.keyboard('{ArrowLeft}')
    expect(document.activeElement).toBe(screen.getByRole('tab', { name: 'Genre' }))
    await user.keyboard('{Home}')
    expect(selected().map((tab) => tab.textContent)).toEqual(['Energy'])

    const panel = screen.getByRole('tabpanel')
    expect(panel.getAttribute('aria-labelledby')).toBe(
      screen.getByRole('tab', { name: 'Energy' }).id,
    )
  })

  it('offers the values as pressed buttons and applies one when chosen', async () => {
    const { user } = renderApp()
    await startFocus(user)
    await user.click(button('Tune energy, mood or genre'))

    const levels = within(screen.getByRole('group', { name: 'Energy level' }))
    expect(
      levels
        .getAllByRole('button')
        .filter((level) => level.getAttribute('aria-pressed') === 'true')
        .map((level) => level.getAttribute('aria-label')),
    ).toEqual(['Medium energy'])
    expect(screen.queryAllByRole('radio')).toHaveLength(0)

    await user.click(levels.getByRole('button', { name: 'High energy' }))

    expect(intent()).toEqual(['Focused', 'Any genre', 'High energy'])
    expect(screen.getByRole('tab', { name: 'Energy' })).toBeTruthy()
    expect(
      levels.getByRole('button', { name: 'High energy' }).getAttribute('aria-pressed'),
    ).toBe('true')
    expect(announcer().textContent).toBe(
      'Energy adjusted, Energy Medium to High. Now playing Peru by Fireboy DML.',
    )
  })

  it('closes on Escape and returns focus to Tune', async () => {
    const { user } = renderApp()
    await startFocus(user)
    await user.click(button('Tune energy, mood or genre'))

    await user.keyboard('{Escape}')

    expect(screen.queryByRole('tablist')).toBeNull()
    expect(document.activeElement).toBe(button('Tune energy, mood or genre'))
  })

  it('closes from its close button and returns focus to Tune', async () => {
    const { user } = renderApp()
    await startFocus(user)
    await user.click(button('Tune energy, mood or genre'))

    await user.click(button('Close tuning'))

    expect(document.activeElement).toBe(button('Tune energy, mood or genre'))
  })

  it('opens from an intent chip on that dimension, and the chip closes it again', async () => {
    const { user } = renderApp()
    await startFocus(user)
    const genre = button('Tune Any genre')

    await user.click(genre)
    expect(genre.getAttribute('aria-expanded')).toBe('true')
    expect(
      screen.getByRole('tab', { name: 'Genre' }).getAttribute('aria-selected'),
    ).toBe('true')

    await user.click(genre)
    expect(genre.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('tablist')).toBeNull()
  })
})

describe('moving between sessions', () => {
  it('opens the drawer as a modal, switches session, announces it and returns focus', async () => {
    const { user, container } = renderApp()

    await user.click(button('Open listening sessions'))
    const drawer = screen.getByRole('navigation', {
      name: 'Listening sessions and playlists',
    })
    expect(drawer.contains(document.activeElement)).toBe(true)
    expect(container.querySelector('main')?.closest('[inert]')).not.toBeNull()

    await user.click(within(drawer).getByRole('button', { name: /^Gym Energy/ }))

    expect(screen.getByRole('heading', { level: 1, name: 'Gym Energy' })).toBeTruthy()
    expect(announcer().textContent).toBe('Opened Gym Energy.')
    expect(screen.getByText('Picking up where you left off')).toBeTruthy()
    finishExit()
    expect(screen.queryByRole('navigation')).toBeNull()
    expect(document.activeElement).toBe(button('Open listening sessions'))
  })

  it('keeps each session as it was left', async () => {
    const { user } = renderApp()
    await startFocus(user)
    await user.click(hero().getByRole('button', { name: 'Like' }))

    await openSession(user, 'Coding')
    expect(heroes()[0].getAttribute('aria-label')).toBe('Now playing: Free Mind by Tems')
    await openSession(user, 'Focus')

    expect(screen.getByRole('heading', { level: 1, name: 'Focus' })).toBeTruthy()
    expect(hero().getByRole('button', { name: 'Liked' })).toBeTruthy()
  })

  it('shows the sessions as a standing rail on a wide screen', async () => {
    useWideScreen(true)
    const { user } = renderApp()

    const rail = screen.getByRole('navigation', { name: 'Listening sessions and playlists' })
    expect(screen.queryByRole('button', { name: 'Open listening sessions' })).toBeNull()
    expect(within(rail).queryByRole('button', { name: 'Close menu' })).toBeNull()

    await user.click(within(rail).getByRole('button', { name: /^Coding/ }))

    expect(screen.getByRole('heading', { level: 1, name: 'Coding' })).toBeTruthy()
    expect(
      within(rail).getByRole('button', { name: /^Coding/ }).getAttribute('aria-current'),
    ).toBe('page')
  })
})

describe('playback', () => {
  const elapsed = () =>
    screen.getByRole('progressbar', { name: 'Playback position' }).getAttribute('aria-valuetext')

  it('advances while playing, holds while paused, and moves on when the song ends', async () => {
    const { user } = renderApp()
    await startFocus(user)

    play(3)
    expect(elapsed()).toBe('0:03 of 2:52')

    await user.click(button('Pause Last Last'))
    play(3)
    expect(elapsed()).toBe('0:03 of 2:52')

    await user.click(button('Play Last Last'))
    play(169)
    expect(heroes()[0].getAttribute('aria-label')).toBe('Now playing: Rush by Ayra Starr')
    expect(announcer().textContent).toBe('Now playing Rush by Ayra Starr.')
  })

  it('stands still while the playlist sheet is open', async () => {
    const { user } = renderApp()
    await startFocus(user)
    await user.click(button('Save to a playlist'))

    play(5)

    expect(elapsed()).toBe('0:00 of 2:52')
  })

  it('offers compact now-playing in the composer once the hero scrolls away', async () => {
    const { user } = renderApp()
    await startFocus(user)
    const mini = () =>
      screen.getByRole('textbox').closest('form')!.querySelector('button[aria-label]')!

    expect(mini().getAttribute('aria-hidden')).toBe('true')
    expect((mini() as HTMLButtonElement).tabIndex).toBe(-1)

    setObservedVisible(false)
    expect(mini().getAttribute('aria-hidden')).toBe('false')
    expect((mini() as HTMLButtonElement).tabIndex).toBe(0)

    await user.click(mini())
    expect(mini().getAttribute('aria-label')).toBe('Play Last Last')
    expect(hero().getByRole('button', { name: 'Play Last Last' })).toBeTruthy()

    setObservedVisible(true)
    expect(mini().getAttribute('aria-hidden')).toBe('true')
  })
})
