import { describe, expect, it } from 'vitest'
import { announceBlocks } from './announce.ts'

describe('announcing new blocks', () => {
  it('reads an acknowledgement and the new song as two sentences, without visual separators', () => {
    expect(
      announceBlocks([
        { type: 'user_message', id: 'e1', text: 'I want emotional Afrobeats.' },
        {
          type: 'ack',
          id: 'e2',
          label: 'Intent set',
          detail: 'Emotional · Afrobeats · Low energy',
          tone: 'confirm',
        },
        {
          type: 'recommendation',
          id: 'e3',
          variant: 'hero',
          recommendationId: 'r',
          title: 'Calm Down',
          artist: 'Rema',
          descriptors: [],
          artworkUrl: null,
          playing: true,
          positionSeconds: 0,
          durationSeconds: 239,
          whySummary: '',
          whyReasons: [],
          whyExpanded: false,
          liked: false,
          savedTo: [],
        },
      ]),
    ).toBe(
      'Intent set, Emotional, Afrobeats, Low energy. Now playing Calm Down by Rema.',
    )
  })

  it('spells out each change in an update', () => {
    expect(
      announceBlocks([
        {
          type: 'ack',
          id: 'e5',
          label: 'Intent updated',
          changes: [
            { dimension: 'Mood', from: 'Calm', to: 'Focused' },
            { dimension: 'Energy', from: 'Low', to: 'Medium' },
          ],
          tone: 'confirm',
        },
      ]),
    ).toBe('Intent updated, Mood Calm to Focused, Energy Low to Medium.')
  })

  it('announces a return to a session, and stays quiet about history and the user’s own words', () => {
    expect(
      announceBlocks([
        {
          type: 'session_summary',
          id: 'e9',
          label: 'Picking up where you left off',
          detail: 'Driven · Amapiano · High energy',
        },
        {
          type: 'recommendation',
          id: 'e3',
          variant: 'compact',
          recommendationId: 'r',
          title: 'Calm Down',
          artist: 'Rema',
          artworkUrl: null,
          outcome: 'liked',
        },
        { type: 'user_message', id: 'e10', text: 'More like this' },
      ]),
    ).toBe('Picking up where you left off: Driven, Amapiano, High energy.')
  })

  it('says nothing when nothing worth announcing arrived', () => {
    expect(announceBlocks([])).toBe('')
  })
})
