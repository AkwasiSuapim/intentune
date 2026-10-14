import SessionView from '../features/session/SessionView.tsx'
import type {
  SessionEnvironment,
  SessionState,
} from '../features/session/types.ts'
import { mockEnvironment } from '../mocks/environment.ts'
import { mockSessions } from '../mocks/sessions.ts'
import ComponentGallery from './ComponentGallery.tsx'
import { stressEnvironment, stressSessions } from './stress.ts'

type Scene = {
  id: string
  label: string
  state: SessionState
  environment: SessionEnvironment
}

const designScene = (
  id: keyof typeof mockSessions,
  label: string,
): Scene => ({ id, label, state: mockSessions[id], environment: mockEnvironment })

const stressScene = (
  id: keyof typeof stressSessions,
  label: string,
): Scene => ({
  id,
  label,
  state: stressSessions[id],
  environment: stressEnvironment,
})

const SCENES: Scene[] = [
  // These ids match the `scene` options of the approved design export.
  designScene('new', 'New session'),
  designScene('initial', 'First recommendation'),
  designScene('change', 'Intent changed'),
  designScene('save', 'Saving to a playlist'),
  designScene('discovery', 'Longer session'),
  designScene('refine', 'Tuning'),
  designScene('drawer', 'Session drawer'),
  // Awkward content, for checking that nothing clips or overflows.
  stressScene('stress', 'Long content'),
  stressScene('stress-tune', 'Long content, tuning'),
  stressScene('stress-save', 'Long content, saving'),
  stressScene('stress-drawer', 'Long content, drawer'),
]

type DemoProps = {
  /** A scene id, or anything else (such as `gallery`) for the gallery. */
  view: string
}

// Development demo. A scene id renders that fixed session state, with inert
// controls, for comparison with the approved design; anything else shows the
// component gallery.
function Demo({ view }: DemoProps) {
  const scene = SCENES.find((candidate) => candidate.id === view)

  if (scene) {
    return <SessionView state={scene.state} environment={scene.environment} />
  }
  return <ComponentGallery scenes={SCENES} />
}

export default Demo
