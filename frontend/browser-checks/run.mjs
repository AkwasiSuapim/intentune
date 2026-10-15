// Runs every browser check in turn against the existing production build and
// reports which passed. Each check starts its own browser. Exit code 1 if any failed.
// Usage: node browser-checks/run.mjs [walkthrough|quality|accessibility|design-compare ...]
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const ALL = ['walkthrough', 'quality', 'accessibility', 'design-compare']
const chosen = process.argv.slice(2).length ? process.argv.slice(2) : ALL

const outcomes = []
for (const name of chosen) {
  if (!ALL.includes(name)) throw new Error(`Unknown check "${name}". Choose from: ${ALL.join(', ')}`)
  console.log(`\n=== ${name} ===`)
  const started = Date.now()
  const result = spawnSync(process.execPath, [fileURLToPath(new URL(`./${name}.mjs`, import.meta.url))], { stdio: 'inherit' })
  outcomes.push({ name, passed: result.status === 0, seconds: Math.round((Date.now() - started) / 1000) })
}

console.log('\n=== Summary ===')
for (const { name, passed, seconds } of outcomes) console.log(`${passed ? 'passed' : 'FAILED'}  ${name} (${seconds}s)`)
console.log('Screenshots and results: browser-checks/output/')
process.exitCode = outcomes.every((outcome) => outcome.passed) ? 0 : 1
