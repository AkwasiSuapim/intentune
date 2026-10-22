import { chooseService } from './chooseService.ts'
import Demo from './demo/Demo.tsx'
import ListeningSessions from './features/session/ListeningSessions.tsx'

const service = chooseService(import.meta.env)

function App() {
  // `?demo=…` opens the development demo instead of the app.
  const demo = new URLSearchParams(window.location.search).get('demo')

  if (demo !== null) {
    return <Demo view={demo} />
  }
  // The service is chosen in chooseService.ts; the session feature never imports one.
  return <ListeningSessions service={service} />
}

export default App
