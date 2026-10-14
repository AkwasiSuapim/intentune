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

// Development entry: `?demo=<scene id>` renders that mock session state
// through the session view; anything else shows the component gallery.
function Demo() {
  const requested = new URLSearchParams(window.location.search).get('demo')
  const scene = SCENES.find((candidate) => candidate.id === requested)

  if (scene) {
    return (
      <SessionView state={mockSessions[scene.id]} environment={mockEnvironment} />
    )
  }
  return <ComponentGallery scenes={SCENES} />
}

export default Demo
