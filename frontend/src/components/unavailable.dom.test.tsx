// @vitest-environment jsdom
// What the music library cannot act on, at the component level: a marked
// starter or Tune value does nothing when pressed, on its own, whatever the
// feature around it would also refuse.
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DiscoveryPrompt from './DiscoveryPrompt.tsx'
import RefineControl from './RefineControl.tsx'

afterEach(cleanup)

describe('an unavailable starter', () => {
  it('does nothing when pressed, while the others start', async () => {
    const onStart = vi.fn()
    render(
      <DiscoveryPrompt
        starters={[
          { id: 'focus', label: 'Focus', phrase: 'Help me focus', unavailableReason: 'Your music has no energy information for this yet.' },
          { id: 'discover', label: 'Discover', phrase: 'Surprise me' },
        ]}
        onStart={onStart}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Focus: Help me focus, unavailable' }))
    expect(onStart).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: 'Discover: Surprise me' }))
    expect(onStart).toHaveBeenCalledWith('discover')
  })
})

describe('Tune while the library is not ready', () => {
  it('locks every tab for that one reason, without marking any dimension unavailable', async () => {
    const onEnergyChange = vi.fn()
    render(
      <RefineControl
        activeTab="energy"
        energyLevels={[{ id: 'high', label: 'High' }]}
        energyId={null}
        moods={[]}
        moodId={null}
        genres={[]}
        genreId={null}
        unavailable={['mood', 'genre', 'energy']}
        libraryReady={false}
        onEnergyChange={onEnergyChange}
      />,
    )

    expect(screen.getAllByRole('tab').map((tab) => tab.getAttribute('aria-label') ?? tab.textContent)).toEqual(['Energy', 'Mood', 'Genre'])
    const panel = screen.getByRole('tabpanel')
    expect(document.getElementById(panel.getAttribute('aria-describedby') ?? '')?.textContent).toBe(
      'Your library has no playable music yet, so tuning can’t change what plays. Import music to start.',
    )
    const high = screen.getByRole('button', { name: 'High energy' })
    expect(high.getAttribute('aria-disabled')).toBe('true')
    await userEvent.click(high)
    expect(onEnergyChange).not.toHaveBeenCalled()
  })
})

describe('an unavailable Tune value', () => {
  it('does nothing when pressed, while the others are chosen', async () => {
    const onMoodChange = vi.fn()
    render(
      <RefineControl
        activeTab="mood"
        energyLevels={[]}
        energyId={null}
        moods={[
          { id: 'calm', label: 'Calm', unavailable: true },
          { id: 'driven', label: 'Driven' },
        ]}
        moodId={null}
        genres={[]}
        genreId={null}
        onMoodChange={onMoodChange}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Calm' }))
    expect(onMoodChange).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: 'Driven' }))
    expect(onMoodChange).toHaveBeenCalledWith('driven')
  })
})
