// Development page: every approved component in its representative states.
import type { ReactNode } from 'react'
import Ack from '../components/Ack.tsx'
import Composer from '../components/Composer.tsx'
import DiscoveryPrompt from '../components/DiscoveryPrompt.tsx'
import IntentSummary from '../components/IntentSummary.tsx'
import PlaylistPicker from '../components/PlaylistPicker.tsx'
import QuickActions from '../components/QuickActions.tsx'
import RecommendationCardCompact from '../components/RecommendationCardCompact.tsx'
import RecommendationCardHero from '../components/RecommendationCardHero.tsx'
import RefineControl from '../components/RefineControl.tsx'
import SessionDrawer from '../components/SessionDrawer.tsx'
import SessionSummary from '../components/SessionSummary.tsx'
import TuneBar from '../components/TuneBar.tsx'
import TurnStatus from '../components/TurnStatus.tsx'
import UpNext from '../components/UpNext.tsx'
import UserMessage from '../components/UserMessage.tsx'
import WhyThisFits from '../components/WhyThisFits.tsx'
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
  testArtwork,
  whyThisFits,
} from './fixtures.ts'
import styles from './ComponentGallery.module.css'

type SceneLink = {
  id: string
  label: string
}

type ComponentGalleryProps = {
  scenes: SceneLink[]
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className={styles.section}>
      <h2 className={styles.sectionTitle}>{title}</h2>
      {children}
    </section>
  )
}

type VariantProps = {
  label: string
  /** `inset` pads like the session timeline; `edge` lets the component set its own gutters. */
  layout?: 'inset' | 'edge' | 'frame'
  children: ReactNode
}

function Variant({ label, layout = 'inset', children }: VariantProps) {
  return (
    <div className={styles.variant}>
      <p className={styles.variantLabel}>{label}</p>
      <div className={styles[layout]}>{children}</div>
    </div>
  )
}

function ComponentGallery({ scenes }: ComponentGalleryProps) {
  return (
    <div className={styles.page}>
      <div className={styles.column}>
        <header className={styles.intro}>
          <h1 className={styles.pageTitle}>Intentune components</h1>
          <p className={styles.pageNote}>
            Static fixtures only. Controls here are not wired to session
            behaviour.
          </p>
          <nav className={styles.sceneLinks} aria-label="Design scenes">
            <a className={styles.sceneLink} href="./">
              Open the app
            </a>
            {scenes.map((scene) => (
              <a
                key={scene.id}
                className={styles.sceneLink}
                href={`?demo=${scene.id}`}
              >
                {scene.label}
              </a>
            ))}
          </nav>
        </header>

        <Section title="IntentSummary">
          <Variant label="Current intent" layout="edge">
            <IntentSummary chips={intents.emotionalLow} />
          </Variant>
          <Variant label="One dimension just changed" layout="edge">
            <IntentSummary chips={intents.emotionalEnergyRaised} />
          </Variant>
          <Variant label="Refine control open on a chip" layout="edge">
            <IntentSummary chips={intents.genreOpen} />
          </Variant>
          <Variant label="More chips than fit: the strip scrolls" layout="edge">
            <IntentSummary chips={intents.manyChips} />
          </Variant>
        </Section>

        <Section title="UserMessage">
          <Variant label="Short">
            <UserMessage text="I want emotional Afrobeats." />
          </Variant>
          <Variant label="Long">
            <UserMessage text="I’m getting sleepy but still need to study, so keep it soft but give me a little more to hold on to." />
          </Variant>
        </Section>

        <Section title="Ack">
          <Variant label="Intent set">
            <Ack label="Intent set" detail="Emotional · Afrobeats · Low energy" />
          </Variant>
          <Variant label="Intent updated, two dimensions">
            <Ack label="Intent updated" changes={intentChanges.moodAndEnergy} />
          </Variant>
          <Variant label="Neutral: intent unchanged">
            <Ack label="Not for me" detail="Intent unchanged" tone="neutral" />
          </Variant>
        </Section>

        <Section title="TurnStatus">
          <Variant label="Waiting for an answer (fades in after a moment)">
            <TurnStatus status="pending" />
          </Variant>
          <Variant label="The answer never came">
            <TurnStatus status="failed" />
          </Variant>
        </Section>

        <Section title="SessionSummary">
          <Variant label="Returning to a session">
            <SessionSummary
              label="Picking up where you left off"
              detail="Emotional · Afrobeats · Low energy"
            />
          </Variant>
        </Section>

        <Section title="RecommendationCardHero">
          <Variant label="Playing, why collapsed">
            <RecommendationCardHero
              {...songs.calmDown}
              playing
              positionSeconds={72}
              whySummary={whyThisFits.calmDown.summary}
              whyReasons={whyThisFits.calmDown.reasons}
            />
          </Variant>
          <Variant label="Paused, liked, saved, why expanded, echo">
            <RecommendationCardHero
              {...songs.lastLast}
              echo="Make it more energetic."
              playing={false}
              positionSeconds={88}
              whySummary={whyThisFits.lastLastEnergyRaised.summary}
              whyReasons={whyThisFits.lastLastEnergyRaised.reasons}
              whyExpanded
              liked
              savedTo={['Afrobeats']}
            />
          </Variant>
          <Variant label="Bright artwork">
            <RecommendationCardHero
              {...songs.peru}
              playing
              positionSeconds={30}
              whySummary={whyThisFits.peru.summary}
              whyReasons={whyThisFits.peru.reasons}
            />
          </Variant>
          <Variant label="Busy artwork">
            <RecommendationCardHero
              {...songs.joha}
              playing
              positionSeconds={48}
              whySummary={whyThisFits.peru.summary}
              whyReasons={whyThisFits.peru.reasons}
            />
          </Variant>
          <Variant label="Portrait artwork, bright, two-line title">
            <RecommendationCardHero
              {...songs.kuLoSa}
              artworkUrl={testArtwork.portrait}
              playing
              positionSeconds={12}
              whySummary={whyThisFits.kuLoSa.summary}
              whyReasons={whyThisFits.kuLoSa.reasons}
            />
          </Variant>
          <Variant label="Pure white artwork, two-line title (worst case)">
            <RecommendationCardHero
              {...songs.kuLoSa}
              artworkUrl={testArtwork.white}
              playing
              positionSeconds={12}
              whySummary={whyThisFits.kuLoSa.summary}
              whyReasons={whyThisFits.kuLoSa.reasons}
            />
          </Variant>
          <Variant label="No artwork, long title, single explanation">
            <RecommendationCardHero
              {...songs.kuLoSa}
              playing
              positionSeconds={12}
              whySummary={whyThisFits.kuLoSa.summary}
              whyReasons={whyThisFits.kuLoSa.reasons}
            />
          </Variant>
        </Section>

        <Section title="RecommendationCardCompact">
          <Variant label="Played, liked, saved, skipped">
            <div className={styles.stack}>
              <RecommendationCardCompact {...songs.soso} outcome="played" />
              <RecommendationCardCompact {...songs.calmDown} outcome="liked" />
              <RecommendationCardCompact {...songs.lastLast} outcome="saved" />
              <RecommendationCardCompact {...songs.rush} outcome="skipped" />
            </div>
          </Variant>
          <Variant label="No artwork, long title">
            <RecommendationCardCompact {...songs.kuLoSa} outcome="played" />
          </Variant>
        </Section>

        <Section title="WhyThisFits">
          <Variant label="Collapsed">
            <WhyThisFits {...whyThisFits.calmDown} />
          </Variant>
          <Variant label="Expanded">
            <WhyThisFits {...whyThisFits.calmDown} expanded />
          </Variant>
          <Variant label="Single explanation, nothing to expand">
            <WhyThisFits {...whyThisFits.kuLoSa} />
          </Variant>
        </Section>

        <Section title="QuickActions">
          <Variant label="Two contextual actions">
            <QuickActions actions={quickActions.initial} />
          </Variant>
        </Section>

        <Section title="TuneBar">
          <Variant label="Two actions plus Tune" layout="edge">
            <TuneBar actions={quickActions.initial} />
          </Variant>
          <Variant label="Longer labels" layout="edge">
            <TuneBar actions={quickActions.energyRaised} />
          </Variant>
          <Variant label="Three offered, two shown" layout="edge">
            <TuneBar actions={quickActions.threeOffered} />
          </Variant>
        </Section>

        <Section title="RefineControl">
          <Variant label="Energy" layout="edge">
            <RefineControl
              activeTab="energy"
              {...refineOptions}
              energyId="medium"
              moodId="emotional"
              genreId="afrobeats"
            />
          </Variant>
          <Variant label="Mood" layout="edge">
            <RefineControl
              activeTab="mood"
              {...refineOptions}
              energyId="medium"
              moodId="emotional"
              genreId="afrobeats"
            />
          </Variant>
          <Variant label="Genre" layout="edge">
            <RefineControl
              activeTab="genre"
              {...refineOptions}
              energyId="medium"
              moodId="emotional"
              genreId="afrobeats"
            />
          </Variant>
        </Section>

        <Section title="UpNext">
          <Variant label="One peek row">
            <UpNext {...songs.monalisa} />
          </Variant>
        </Section>

        <Section title="Composer">
          <Variant label="Default input" layout="edge">
            <Composer value="" placeholder={composerPlaceholders.nextTurn} />
          </Variant>
          <Variant label="With a draft" layout="edge">
            <Composer
              value="Something a bit calmer"
              placeholder={composerPlaceholders.nextTurn}
            />
          </Variant>
          <Variant label="Compact now-playing, playing" layout="edge">
            <Composer
              value=""
              placeholder={composerPlaceholders.nextTurn}
              nowPlaying={{ ...songs.calmDown, playing: true }}
              showNowPlaying
            />
          </Variant>
          <Variant label="Compact now-playing, paused" layout="edge">
            <Composer
              value=""
              placeholder={composerPlaceholders.nextTurn}
              nowPlaying={{ ...songs.lastLast, playing: false }}
              showNowPlaying
            />
          </Variant>
          <Variant label="Compact now-playing over pure white artwork" layout="edge">
            <Composer
              value=""
              placeholder={composerPlaceholders.nextTurn}
              nowPlaying={{
                title: 'White',
                artworkUrl: testArtwork.white,
                playing: true,
              }}
              showNowPlaying
            />
          </Variant>
        </Section>

        <Section title="DiscoveryPrompt">
          <Variant label="Tune in" layout="frame">
            <DiscoveryPrompt starters={starters} />
          </Variant>
        </Section>

        <Section title="PlaylistPicker">
          <Variant label="Nothing chosen" layout="frame">
            <PlaylistPicker
              songTitle={songs.lastLast.title}
              songArtist={songs.lastLast.artist}
              artworkUrl={songs.lastLast.artworkUrl}
              playlists={playlists}
              selectedIds={[]}
            />
          </Variant>
          <Variant label="One playlist chosen" layout="frame">
            <PlaylistPicker
              songTitle={songs.lastLast.title}
              songArtist={songs.lastLast.artist}
              artworkUrl={songs.lastLast.artworkUrl}
              playlists={playlists}
              selectedIds={['afrobeats']}
            />
          </Variant>
          <Variant label="Two playlists chosen" layout="frame">
            <PlaylistPicker
              songTitle={songs.lastLast.title}
              songArtist={songs.lastLast.artist}
              artworkUrl={songs.lastLast.artworkUrl}
              playlists={playlists}
              selectedIds={['favorites', 'afrobeats']}
            />
          </Variant>
        </Section>

        <Section title="SessionDrawer">
          <Variant label="Overlay drawer: sessions and playlists" layout="frame">
            <SessionDrawer sessions={sessions} playlists={playlists} />
          </Variant>
          <Variant label="Desktop rail" layout="frame">
            <SessionDrawer
              variant="rail"
              sessions={sessions}
              playlists={playlists}
            />
          </Variant>
        </Section>
      </div>
    </div>
  )
}

export default ComponentGallery
