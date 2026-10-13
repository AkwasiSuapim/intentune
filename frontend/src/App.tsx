import AppShell from './app/AppShell.tsx'
import ComposerPlaceholder from './app/ComposerPlaceholder.tsx'
import MobileHeader from './app/MobileHeader.tsx'

function App() {
  return (
    <AppShell
      header={<MobileHeader title="New session" />}
      composer={<ComposerPlaceholder />}
    />
  )
}

export default App
