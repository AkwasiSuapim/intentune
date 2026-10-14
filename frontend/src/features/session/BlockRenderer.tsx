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
import type { SessionCommand } from './commands.ts'
import type { IntentDimension } from './types.ts'
import UnknownBlock from './UnknownBlock.tsx'

type CommandHandler = (command: SessionCommand) => void

/** Lets a block that has been taken away play its exit before it is removed. */
export type BlockPresence = {
  leaving: boolean
  onExited: () => void
}

type BlockProps<T extends SessionBlockType> = {
  block: BlockOf<T>
  /** Reports what the user did. Blocks never change state themselves. */
  onCommand: CommandHandler
  presence?: BlockPresence
}

function IntentSummaryBlock({
  block,
  onCommand,
}: BlockProps<'intent_summary'>) {
  return (
    <IntentSummary
      chips={block.chips}
      onSelectChip={(id) =>
        // Chip ids are the intent dimensions they show.
        onCommand({ type: 'toggle_refine_tab', tab: id as IntentDimension })
      }
    />
  )
}

function DiscoveryPromptBlock({
  block,
  onCommand,
}: BlockProps<'discovery_prompt'>) {
  return (
    <DiscoveryPrompt
      starters={block.starters}
      onStart={(starterId) => onCommand({ type: 'select_starter', starterId })}
    />
  )
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

function RecommendationBlock({
  block,
  onCommand,
}: BlockProps<'recommendation'>) {
  if (block.variant === 'compact') {
    return (
      <RecommendationCardCompact
        title={block.title}
        artist={block.artist}
        artworkUrl={block.artworkUrl}
        outcome={block.outcome}
        onReplay={() =>
          onCommand({
            type: 'replay',
            recommendationId: block.recommendationId,
          })
        }
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
      onTogglePlay={() => onCommand({ type: 'toggle_play' })}
      onNext={() => onCommand({ type: 'next' })}
      onToggleWhy={() => onCommand({ type: 'toggle_why' })}
      onLike={() => onCommand({ type: 'toggle_like' })}
      onNotForMe={() => onCommand({ type: 'not_for_me' })}
      onSave={() => onCommand({ type: 'open_playlist_picker' })}
    />
  )
}

function UpNextBlock({ block, onCommand }: BlockProps<'up_next'>) {
  return (
    <UpNext
      title={block.title}
      artist={block.artist}
      artworkUrl={block.artworkUrl}
      onPlay={() => onCommand({ type: 'next' })}
    />
  )
}

function QuickActionsBlock({ block, onCommand }: BlockProps<'quick_actions'>) {
  return (
    <TuneBar
      actions={block.actions}
      onSelectAction={(actionId) =>
        onCommand({ type: 'select_quick_action', actionId })
      }
      onOpenTune={() => onCommand({ type: 'open_refine' })}
    />
  )
}

function RefineControlBlock({
  block,
  onCommand,
}: BlockProps<'refine_control'>) {
  const refine = (dimension: IntentDimension) => (valueId: string) =>
    onCommand({ type: 'refine', dimension, valueId })

  return (
    <RefineControl
      activeTab={block.activeTab}
      energyLevels={block.energyLevels}
      energyId={block.energyId}
      moods={block.moods}
      moodId={block.moodId}
      genres={block.genres}
      genreId={block.genreId}
      onTabChange={(tab) => onCommand({ type: 'change_refine_tab', tab })}
      onEnergyChange={refine('energy')}
      onMoodChange={refine('mood')}
      onGenreChange={refine('genre')}
      onClose={() => onCommand({ type: 'close_refine' })}
    />
  )
}

function PlaylistPickerBlock({
  block,
  onCommand,
  presence,
}: BlockProps<'playlist_picker'>) {
  return (
    <PlaylistPicker
      songTitle={block.songTitle}
      songArtist={block.songArtist}
      artworkUrl={block.artworkUrl}
      playlists={block.playlists}
      selectedIds={block.selectedIds}
      leaving={presence?.leaving}
      onExited={presence?.onExited}
      onToggle={(playlistId) =>
        onCommand({ type: 'toggle_playlist', playlistId })
      }
      onCreate={() => onCommand({ type: 'create_playlist' })}
      onConfirm={() => onCommand({ type: 'confirm_playlists' })}
      onClose={() => onCommand({ type: 'close_playlist_picker' })}
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

function ignoreCommand() {}

type BlockRendererProps = {
  block: SessionBlock
  /** Left out for a static rendering: the block's controls then do nothing. */
  onCommand?: CommandHandler
  presence?: BlockPresence
}

// Renders one block through the registry. Data that reaches here at runtime
// may not match the types (for example a future backend response), so the
// type is checked rather than trusted: anything unrecognised falls back to
// UnknownBlock and none of its content is rendered.
function BlockRenderer({
  block,
  onCommand = ignoreCommand,
  presence,
}: BlockRendererProps) {
  const type: unknown = (block as { type?: unknown } | null | undefined)?.type

  if (!isRegistered(type)) {
    return <UnknownBlock type={typeof type === 'string' ? type : 'untyped'} />
  }
  const Component = REGISTRY[type] as ComponentType<BlockProps<SessionBlockType>>
  return <Component block={block} onCommand={onCommand} presence={presence} />
}

export default BlockRenderer
