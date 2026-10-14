import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { mockEnvironment } from '../../mocks/environment.ts'
import { mockSessions } from '../../mocks/sessions.ts'
import BlockRenderer from './BlockRenderer.tsx'
import type { SessionBlock, SessionBlockType } from './blocks.ts'
import { composeSession } from './composeSession.ts'
import SessionView from './SessionView.tsx'
import UnknownBlock from './UnknownBlock.tsx'

const render = (block: SessionBlock) =>
  renderToStaticMarkup(<BlockRenderer block={block} />)

/** Renders data the types would reject, as a bad response might deliver it. */
const renderUntyped = (block: unknown) => render(block as SessionBlock)

const UNSUPPORTED = 'Unsupported block'

// One sample per block type (two for the recommendation variants), with text
// that only that block's component would produce.
const SAMPLES: { block: SessionBlock; shows: string[] }[] = [
  {
    block: {
      type: 'intent_summary',
      id: 'b1',
      chips: [{ id: 'mood', label: 'Emotional' }],
    },
    shows: ['aria-label="Current intent"', 'Emotional'],
  },
  {
    block: {
      type: 'discovery_prompt',
      id: 'b2',
      starters: mockEnvironment.starters,
    },
    shows: ['Tune in', 'What do you need from your music right now?', 'Unwind'],
  },
  {
    block: { type: 'user_message', id: 'b3', text: 'Make it more energetic.' },
    shows: ['Make it more energetic.'],
  },
  {
    block: {
      type: 'ack',
      id: 'b4',
      label: 'Intent updated',
      changes: [{ dimension: 'Energy', from: 'Low', to: 'Medium' }],
      tone: 'confirm',
    },
    shows: ['role="status"', 'Intent updated', 'Medium'],
  },
  {
    block: {
      type: 'session_summary',
      id: 'b5',
      label: 'Picking up where you left off',
      detail: 'Emotional · Afrobeats · Low energy',
    },
    shows: ['Picking up where you left off'],
  },
  {
    block: {
      type: 'recommendation',
      id: 'b6',
      variant: 'hero',
      title: 'Calm Down',
      artist: 'Rema',
      descriptors: ['Afrobeats', 'Emotional'],
      artworkUrl: null,
      playing: true,
      positionSeconds: 72,
      durationSeconds: 239,
      whySummary: 'Keeps the emotional Afrobeats feel while staying relaxed.',
      whyReasons: ['Keeps the energy relaxed.'],
      whyExpanded: false,
      liked: false,
      savedTo: [],
    },
    shows: ['Now playing: Calm Down by Rema', 'Why this fits', 'Not for me'],
  },
  {
    block: {
      type: 'recommendation',
      id: 'b7',
      variant: 'compact',
      title: 'Rush',
      artist: 'Ayra Starr',
      artworkUrl: null,
      outcome: 'skipped',
    },
    shows: ['Play Rush by Ayra Starr again. Skipped'],
  },
  {
    block: {
      type: 'up_next',
      id: 'b8',
      title: 'Monalisa',
      artist: 'Lojay & Sarz',
      artworkUrl: null,
    },
    shows: ['Up next', 'Monalisa'],
  },
  {
    block: {
      type: 'quick_actions',
      id: 'b9',
      actions: [{ id: 'a', label: 'More like this' }],
    },
    shows: ['More like this', 'Tune energy, mood or genre'],
  },
  {
    block: {
      type: 'refine_control',
      id: 'b10',
      activeTab: 'energy',
      energyLevels: mockEnvironment.refineOptions.energy,
      energyId: 'medium',
      moods: mockEnvironment.refineOptions.mood,
      moodId: 'focused',
      genres: mockEnvironment.refineOptions.genre,
      genreId: 'afrobeats',
    },
    shows: ['Tune the session', 'Medium energy'],
  },
  {
    block: {
      type: 'playlist_picker',
      id: 'b11',
      songTitle: 'Last Last',
      songArtist: 'Burna Boy',
      artworkUrl: null,
      playlists: [{ id: 'study', name: 'Study' }],
      selectedIds: [],
    },
    shows: ['Add to playlist', 'Choose a playlist'],
  },
]

describe('known blocks', () => {
  it.each(SAMPLES)(
    'renders $block.type ($block.id) with its approved component',
    ({ block, shows }) => {
      const markup = render(block)

      for (const text of shows) expect(markup).toContain(text)
      expect(markup).not.toContain(UNSUPPORTED)
    },
  )

  it('has a sample for every block type in the vocabulary', () => {
    // Listing the types as a record makes a new block type a compile error
    // here until it is added, which keeps the samples complete.
    const vocabulary: Record<SessionBlockType, true> = {
      intent_summary: true,
      discovery_prompt: true,
      user_message: true,
      ack: true,
      session_summary: true,
      recommendation: true,
      up_next: true,
      quick_actions: true,
      refine_control: true,
      playlist_picker: true,
    }

    expect(new Set(SAMPLES.map((sample) => sample.block.type))).toEqual(
      new Set(Object.keys(vocabulary)),
    )
  })

  it('renders the hero and compact recommendation variants differently', () => {
    const hero = render(SAMPLES[5].block)
    const compact = render(SAMPLES[6].block)

    expect(hero).toContain('<article')
    expect(compact).not.toContain('<article')
    expect(compact).not.toContain('Why this fits')
  })

  it('renders every block the mock scenes compose', () => {
    for (const state of Object.values(mockSessions)) {
      const view = composeSession(state, mockEnvironment)
      const blocks = [
        view.intentSummary,
        ...view.content,
        view.contextualControl,
        view.overlay,
      ].filter((block) => block !== null)

      for (const block of blocks) {
        expect(render(block)).not.toContain(UNSUPPORTED)
      }
    }
  })
})

describe('unknown blocks', () => {
  it('shows a visible notice naming the type during development', () => {
    const markup = renderUntyped({ type: 'lyrics_panel', id: 'x1' })

    expect(markup).toContain(UNSUPPORTED)
    expect(markup).toContain('lyrics_panel')
  })

  it('renders none of the unknown block’s own content', () => {
    const markup = renderUntyped({
      type: 'html',
      id: 'x2',
      html: '<img src=x onerror="alert(1)">',
      text: 'smuggled text',
      children: [{ type: 'user_message', id: 'x3', text: 'nested message' }],
    })

    expect(markup).toContain(UNSUPPORTED)
    expect(markup).not.toContain('onerror')
    expect(markup).not.toContain('smuggled text')
    expect(markup).not.toContain('nested message')
  })

  it('escapes the type name instead of treating it as markup', () => {
    const markup = renderUntyped({ type: '<script>alert(1)</script>', id: 'x4' })

    expect(markup).not.toContain('<script>')
    expect(markup).toContain('&lt;script&gt;')
  })

  it.each(['constructor', 'toString', '__proto__', 'hasOwnProperty'])(
    'does not resolve the inherited name "%s" as a block type',
    (type) => {
      expect(renderUntyped({ type, id: 'x5' })).toContain(UNSUPPORTED)
    },
  )

  it.each([
    ['a missing type', { id: 'x6' }],
    ['a non-string type', { type: 42, id: 'x7' }],
    ['null', null],
    ['a bare string', 'user_message'],
  ])('falls back safely for %s', (_name, value) => {
    expect(renderUntyped(value)).toContain(UNSUPPORTED)
  })

  it('is close in name to a known type but still unknown', () => {
    expect(renderUntyped({ type: 'User_Message', id: 'x8', text: 'hi' })).toContain(
      UNSUPPORTED,
    )
  })

  it('renders nothing at all outside development', () => {
    expect(
      renderToStaticMarkup(<UnknownBlock type="lyrics_panel" visible={false} />),
    ).toBe('')
  })
})

describe('session view', () => {
  it('renders a whole session from state', () => {
    const markup = renderToStaticMarkup(
      <SessionView state={mockSessions.change} environment={mockEnvironment} />,
    )

    expect(markup).toContain('Emotional Afrobeats')
    expect(markup).toContain('Medium energy')
    expect(markup).toContain('Now playing: Last Last by Burna Boy')
    expect(markup).toContain('Play Calm Down by Rema again. Liked')
    expect(markup).toContain('Keep this energy')
    expect(markup.match(/<article/g)).toHaveLength(1)
  })

  it('renders the Tune in prompt for a new session', () => {
    const markup = renderToStaticMarkup(
      <SessionView state={mockSessions.new} environment={mockEnvironment} />,
    )

    expect(markup).toContain('What do you need from your music right now?')
    expect(markup).not.toContain('<article')
    expect(markup).not.toContain('aria-label="Current intent"')
  })
})
