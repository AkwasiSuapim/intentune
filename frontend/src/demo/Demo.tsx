import SessionView from '../features/session/SessionView.tsx'
import { mockEnvironment } from '../mocks/environment.ts'
import { mockSessions } from '../mocks/sessions.ts'
import ComponentGallery from './ComponentGallery.tsx'

type SceneId = keyof typeof mockSessions

// Scene ids match the `scene` options of the approved design export.
const SCENES: { id: SceneId; label: string }[] = [
  { id: 'new', label: 'New session' },
  { id: 'initial', label: 'First recommendation' },
  { id: 'change', label: 'Intent changed' },
  { id: 'save', label: 'Saving to a playlist' },
  { id: 'discovery', label: 'Longer session' },
  { id: 'refine', label: 'Tuning' },
  { id: 'drawer', label: 'Session drawer' },
]

type DemoProps = {
  /** A scene id, or anything else (such as `gallery`) for the gallery. */
  view: string
}

// Development demo. A scene id renders that fixed mock session state, with
// inert controls, for comparison with the approved design; anything else
// shows the component gallery.
function Demo({ view }: DemoProps) {
  const scene = SCENES.find((candidate) => candidate.id === view)

  if (scene) {
    return (
      <SessionView state={mockSessions[scene.id]} environment={mockEnvironment} />
    )
  }
  return <ComponentGallery scenes={SCENES} />
}

export default Demo
