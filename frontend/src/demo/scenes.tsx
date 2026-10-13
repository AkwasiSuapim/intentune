// Hand-composed, static reproductions of the approved design's scenes, used to
// check the component vocabulary against the design. Nothing here is session
// logic: each scene is fixed markup over fixture props.
import { useState } from 'react'
import type { ComponentProps } from 'react'
import AppShell from '../app/AppShell.tsx'
import MobileHeader from '../app/MobileHeader.tsx'
import Ack from '../components/Ack.tsx'
import Composer from '../components/Composer.tsx'
import DiscoveryPrompt from '../components/DiscoveryPrompt.tsx'
import IntentSummary from '../components/IntentSummary.tsx'
import PlaylistPicker from '../components/PlaylistPicker.tsx'
import RecommendationCardCompact from '../components/RecommendationCardCompact.tsx'
import RecommendationCardHero from '../components/RecommendationCardHero.tsx'
import RefineControl from '../components/RefineControl.tsx'
import SessionDrawer from '../components/SessionDrawer.tsx'
import SessionTimeline from '../components/SessionTimeline.tsx'
import TuneBar from '../components/TuneBar.tsx'
import UpNext from '../components/UpNext.tsx'
import UserMessage from '../components/UserMessage.tsx'
import {
  composerPlaceholders,
  intentChanges,
  intents,
  playlists,
  quickActions,
  refineOptions,
  sessions,
  songs,
  starters,
  whyThisFits,
} from './fixtures.ts'

type SceneShellProps = Omit<
  ComponentProps<typeof AppShell>,
  'header' | 'composer'
> & {
  title: string
  firstTurn?: boolean
}

// The composer keeps its own draft text so the field can be typed in.
function SceneShell({ title, firstTurn = false, ...shell }: SceneShellProps) {
  const [draft, setDraft] = useState('')

  return (
    <AppShell
      {...shell}
      header={<MobileHeader title={title} />}
      composer={
        <Composer
          value={draft}
          onValueChange={setDraft}
          placeholder={
            firstTurn
              ? composerPlaceholders.firstTurn
              : composerPlaceholders.nextTurn
          }
        />
      }
    />
  )
}

function OpeningTurn() {
  return (
    <>
      <UserMessage text="I want emotional Afrobeats." />
      <Ack label="Intent set" detail="Emotional · Afrobeats · Low energy" />
    </>
  )
}

function EnergyRaisedTurn() {
  return (
    <>
      <RecommendationCardCompact
        title={songs.calmDown.title}
        artist={songs.calmDown.artist}
        artworkUrl={songs.calmDown.artworkUrl}
        outcome="liked"
      />
      <UserMessage text="Make it more energetic." />
      <Ack label="Intent updated" changes={intentChanges.energyRaised} />
    </>
  )
}

export function NewSessionScene() {
  return (
    <SceneShell title="New session" firstTurn>
      <DiscoveryPrompt starters={starters} />
    </SceneShell>
  )
}

function InitialTimeline() {
  return (
    <SessionTimeline>
      <OpeningTurn />
      <RecommendationCardHero
        title={songs.calmDown.title}
        artist={songs.calmDown.artist}
        descriptors={songs.calmDown.descriptors}
        artworkUrl={songs.calmDown.artworkUrl}
        playing
        positionSeconds={72}
        durationSeconds={songs.calmDown.durationSeconds}
        whySummary={whyThisFits.calmDown.summary}
        whyReasons={whyThisFits.calmDown.reasons}
      />
    </SessionTimeline>
  )
}

export function InitialScene() {
  return (
    <SceneShell
      title="Emotional Afrobeats"
      intentSummary={<IntentSummary chips={intents.emotionalLow} />}
      contextualControls={<TuneBar actions={quickActions.initial} />}
    >
      <InitialTimeline />
    </SceneShell>
  )
}

export function IntentChangeScene() {
  return (
    <SceneShell
      title="Emotional Afrobeats"
      intentSummary={<IntentSummary chips={intents.emotionalEnergyRaised} />}
      contextualControls={<TuneBar actions={quickActions.energyRaised} />}
    >
      <SessionTimeline>
        <OpeningTurn />
        <EnergyRaisedTurn />
        <RecommendationCardHero
          title={songs.lastLast.title}
          artist={songs.lastLast.artist}
          descriptors={songs.lastLast.descriptors}
          artworkUrl={songs.lastLast.artworkUrl}
          playing
          positionSeconds={41}
          durationSeconds={songs.lastLast.durationSeconds}
          whySummary={whyThisFits.lastLastEnergyRaised.summary}
          whyReasons={whyThisFits.lastLastEnergyRaised.reasons}
        />
      </SessionTimeline>
    </SceneShell>
  )
}

export function SaveScene() {
  return (
    <SceneShell
      title="Emotional Afrobeats"
      intentSummary={<IntentSummary chips={intents.emotionalMedium} />}
      contextualControls={<TuneBar actions={quickActions.energyRaised} />}
      overlay={
        <PlaylistPicker
          songTitle={songs.lastLast.title}
          songArtist={songs.lastLast.artist}
          artworkUrl={songs.lastLast.artworkUrl}
          playlists={playlists}
          selectedIds={[]}
        />
      }
    >
      <SessionTimeline>
        <OpeningTurn />
        <EnergyRaisedTurn />
        <RecommendationCardHero
          title={songs.lastLast.title}
          artist={songs.lastLast.artist}
          descriptors={songs.lastLast.descriptors}
          artworkUrl={songs.lastLast.artworkUrl}
          playing
          positionSeconds={88}
          durationSeconds={songs.lastLast.durationSeconds}
          whySummary={whyThisFits.lastLast.summary}
          whyReasons={whyThisFits.lastLast.reasons}
        />
      </SessionTimeline>
    </SceneShell>
  )
}

export function DiscoveryScene() {
  return (
    <SceneShell
      title="Emotional Afrobeats"
      intentSummary={<IntentSummary chips={intents.emotionalMedium} />}
      contextualControls={<TuneBar actions={quickActions.continuing} />}
    >
      <SessionTimeline>
        <OpeningTurn />
        <EnergyRaisedTurn />
        <RecommendationCardCompact
          title={songs.lastLast.title}
          artist={songs.lastLast.artist}
          artworkUrl={songs.lastLast.artworkUrl}
          outcome="saved"
        />
        <RecommendationCardCompact
          title={songs.rush.title}
          artist={songs.rush.artist}
          artworkUrl={songs.rush.artworkUrl}
          outcome="skipped"
        />
        <Ack label="Not for me" detail="Intent unchanged" tone="neutral" />
        <RecommendationCardHero
          title={songs.loveNwantiti.title}
          artist={songs.loveNwantiti.artist}
          descriptors={songs.loveNwantiti.descriptors}
          artworkUrl={songs.loveNwantiti.artworkUrl}
          playing
          positionSeconds={23}
          durationSeconds={songs.loveNwantiti.durationSeconds}
          whySummary={whyThisFits.loveNwantiti.summary}
          whyReasons={whyThisFits.loveNwantiti.reasons}
        />
        <UpNext
          title={songs.monalisa.title}
          artist={songs.monalisa.artist}
          artworkUrl={songs.monalisa.artworkUrl}
        />
      </SessionTimeline>
    </SceneShell>
  )
}

export function RefineScene() {
  return (
    <SceneShell
      title="Late Night Study"
      accent="focused"
      intentSummary={<IntentSummary chips={intents.focusedWhileTuning} />}
      contextualControls={
        <RefineControl
          activeTab="energy"
          energyLevels={refineOptions.energyLevels}
          energyId="medium"
          moods={refineOptions.moods}
          moodId="focused"
          genres={refineOptions.genres}
          genreId="afrobeats"
        />
      }
    >
      <SessionTimeline>
        <UserMessage text="Soft Afrobeats for studying." />
        <Ack label="Intent set" detail="Calm · Afrobeats · Low energy" />
        <RecommendationCardCompact
          title={songs.soso.title}
          artist={songs.soso.artist}
          artworkUrl={songs.soso.artworkUrl}
          outcome="played"
        />
        <RecommendationCardCompact
          title={songs.essence.title}
          artist={songs.essence.artist}
          artworkUrl={songs.essence.artworkUrl}
          outcome="played"
        />
        <UserMessage text="I’m getting sleepy but still need to study." />
        <Ack label="Intent updated" changes={intentChanges.moodAndEnergy} />
        <RecommendationCardHero
          title={songs.monalisa.title}
          artist={songs.monalisa.artist}
          descriptors={songs.monalisa.descriptors}
          artworkUrl={songs.monalisa.artworkUrl}
          playing
          positionSeconds={64}
          durationSeconds={songs.monalisa.durationSeconds}
          whySummary={whyThisFits.monalisa.summary}
          whyReasons={whyThisFits.monalisa.reasons}
        />
      </SessionTimeline>
    </SceneShell>
  )
}

export function DrawerScene() {
  return (
    <SceneShell
      title="Emotional Afrobeats"
      intentSummary={<IntentSummary chips={intents.emotionalLow} />}
      contextualControls={<TuneBar actions={quickActions.initial} />}
      overlay={<SessionDrawer sessions={sessions} playlists={playlists} />}
    >
      <InitialTimeline />
    </SceneShell>
  )
}
