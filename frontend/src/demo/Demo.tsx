import type { ComponentType } from 'react'
import ComponentGallery from './ComponentGallery.tsx'
import {
  DiscoveryScene,
  DrawerScene,
  InitialScene,
  IntentChangeScene,
  NewSessionScene,
  RefineScene,
  SaveScene,
} from './scenes.tsx'

// Scene ids match the `scene` options of the approved design export.
const SCENES: { id: string; label: string; Scene: ComponentType }[] = [
  { id: 'new', label: 'New session', Scene: NewSessionScene },
  { id: 'initial', label: 'First recommendation', Scene: InitialScene },
  { id: 'change', label: 'Intent changed', Scene: IntentChangeScene },
  { id: 'save', label: 'Saving to a playlist', Scene: SaveScene },
  { id: 'discovery', label: 'Longer session', Scene: DiscoveryScene },
  { id: 'refine', label: 'Tuning', Scene: RefineScene },
  { id: 'drawer', label: 'Session drawer', Scene: DrawerScene },
]

// Development entry for F3: `?demo=<scene id>` shows one static scene,
// anything else shows the component gallery.
function Demo() {
  const requested = new URLSearchParams(window.location.search).get('demo')
  const match = SCENES.find((scene) => scene.id === requested)

  if (match) {
    return <match.Scene />
  }
  return <ComponentGallery scenes={SCENES} />
}

export default Demo
