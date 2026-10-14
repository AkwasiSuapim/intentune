import type { ComponentType } from 'react'
import Ack from '../../components/Ack.tsx'
import DiscoveryPrompt from '../../components/DiscoveryPrompt.tsx'
import IntentSummary from '../../components/IntentSummary.tsx'
import PlaylistPicker from '../../components/PlaylistPicker.tsx'
import RecommendationCardCompact from '../../components/RecommendationCardCompact.tsx'
import RecommendationCardHero from '../../components/RecommendationCardHero.tsx'
import RefineControl from '../../components/RefineControl.tsx'
import SessionSummary from '../../components/SessionSummary.tsx'
import TuneBar from '../../components/TuneBar.tsx'
import UpNext from '../../components/UpNext.tsx'
import UserMessage from '../../components/UserMessage.tsx'
import type { BlockOf, SessionBlock, SessionBlockType } from './blocks.ts'
import UnknownBlock from './UnknownBlock.tsx'

type BlockProps<T extends SessionBlockType> = { block: BlockOf<T> }

function IntentSummaryBlock({ block }: BlockProps<'intent_summary'>) {
  return <IntentSummary chips={block.chips} />
}

function DiscoveryPromptBlock({ block }: BlockProps<'discovery_prompt'>) {
  return <DiscoveryPrompt starters={block.starters} />
}

function UserMessageBlock({ block }: BlockProps<'user_message'>) {
  return <UserMessage text={block.text} />
}

function AckBlock({ block }: BlockProps<'ack'>) {
  return (
    <Ack
      label={block.label}
      detail={block.detail}
      changes={block.changes}
      tone={block.tone}
    />
  )
}

function SessionSummaryBlock({ block }: BlockProps<'session_summary'>) {
  return <SessionSummary label={block.label} detail={block.detail} />
}

function RecommendationBlock({ block }: BlockProps<'recommendation'>) {
  if (block.variant === 'compact') {
    return (
      <RecommendationCardCompact
        title={block.title}
        artist={block.artist}
        artworkUrl={block.artworkUrl}
        outcome={block.outcome}
      />
    )
  }
  return (
    <RecommendationCardHero
      title={block.title}
      artist={block.artist}
      descriptors={block.descriptors}
      artworkUrl={block.artworkUrl}
      echo={block.echo}
      playing={block.playing}
      positionSeconds={block.positionSeconds}
      durationSeconds={block.durationSeconds}
      whySummary={block.whySummary}
      whyReasons={block.whyReasons}
      whyExpanded={block.whyExpanded}
      liked={block.liked}
      savedTo={block.savedTo}
    />
  )
}

function UpNextBlock({ block }: BlockProps<'up_next'>) {
  return (
    <UpNext
      title={block.title}
      artist={block.artist}
      artworkUrl={block.artworkUrl}
    />
  )
}

function QuickActionsBlock({ block }: BlockProps<'quick_actions'>) {
  return <TuneBar actions={block.actions} />
}

function RefineControlBlock({ block }: BlockProps<'refine_control'>) {
  return (
    <RefineControl
      activeTab={block.activeTab}
      energyLevels={block.energyLevels}
      energyId={block.energyId}
      moods={block.moods}
      moodId={block.moodId}
      genres={block.genres}
      genreId={block.genreId}
    />
  )
}

function PlaylistPickerBlock({ block }: BlockProps<'playlist_picker'>) {
  return (
    <PlaylistPicker
      songTitle={block.songTitle}
      songArtist={block.songArtist}
      artworkUrl={block.artworkUrl}
      playlists={block.playlists}
      selectedIds={block.selectedIds}
    />
  )
}

// The registry: every approved block type maps to one local component. The
// mapped type makes a missing or misspelled entry a compile error.
const REGISTRY: { [T in SessionBlockType]: ComponentType<BlockProps<T>> } = {
  intent_summary: IntentSummaryBlock,
  discovery_prompt: DiscoveryPromptBlock,
  user_message: UserMessageBlock,
  ack: AckBlock,
  session_summary: SessionSummaryBlock,
  recommendation: RecommendationBlock,
  up_next: UpNextBlock,
  quick_actions: QuickActionsBlock,
  refine_control: RefineControlBlock,
  playlist_picker: PlaylistPickerBlock,
}

function isRegistered(type: unknown): type is SessionBlockType {
  // Own keys only, so inherited names like "constructor" never resolve.
  return typeof type === 'string' && Object.hasOwn(REGISTRY, type)
}

type BlockRendererProps = {
  block: SessionBlock
}

// Renders one block through the registry. Data that reaches here at runtime
// may not match the types (for example a future backend response), so the
// type is checked rather than trusted: anything unrecognised falls back to
// UnknownBlock and none of its content is rendered.
function BlockRenderer({ block }: BlockRendererProps) {
  const type: unknown = (block as { type?: unknown } | null | undefined)?.type

  if (!isRegistered(type)) {
    return <UnknownBlock type={typeof type === 'string' ? type : 'untyped'} />
  }
  const Component = REGISTRY[type] as ComponentType<{ block: SessionBlock }>
  return <Component block={block} />
}

export default BlockRenderer
