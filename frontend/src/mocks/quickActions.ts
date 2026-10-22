// The mock's quick actions. Each says what it does: a steering control when it
// is one (D36), or else the phrase the mock's own reader understands. Only the
// mock reads that phrase; the session feature only sends the request.
import type { SteeringControl } from '../features/session/sessionService.ts'
import type { QuickAction } from '../features/session/types.ts'

const CONTROLS: Partial<Record<string, SteeringControl>> = {
  'More like this': 'more_like_this',
}

export function mockQuickAction(
  label: string,
  id = label.toLowerCase().replaceAll(' ', '-'),
): QuickAction {
  const control = CONTROLS[label]
  return {
    id,
    label,
    request: control
      ? { kind: 'control', control, label }
      : { kind: 'message', text: label },
  }
}
