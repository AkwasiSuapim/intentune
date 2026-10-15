import Demo from './demo/Demo.tsx'
import ListeningSessions from './features/session/ListeningSessions.tsx'
import { mockSessionService } from './mocks/mockSessionService.ts'

function App() {
  // `?demo=…` opens the development demo instead of the app.
  const demo = new URLSearchParams(window.location.search).get('demo')

  if (demo !== null) {
    return <Demo view={demo} />
  }
  // The mock service is wired in here; the session feature never imports it.
  return <ListeningSessions service={mockSessionService} />
}

export default App
