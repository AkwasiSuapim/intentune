// Compares the app's static scenes (/?demo=<scene>) with the same scenes rendered from the
// approved design export, element by element, at the phone size and the design's wide size.
// Any element more than 1.5px away from the design fails, except the approved deviations below.
import { APP, DESIGN, createReport, launch, outputDir } from './harness.mjs'

const outDir = outputDir('design-compare')
const report = createReport('Design comparison')
const b = await launch({ outDir, design: true })

const SCENES = ['new', 'initial', 'change', 'save', 'discovery', 'refine', 'drawer']
const SIZES = [[390, 844], [768, 1024]]
const TOLERANCE = 1.5
/** Fewer matches than this means a scene did not render, not that it matched. */
const MIN_MATCHED = 5

/**
 * Approved during F6: at 390px a changed or tuned intent chip is scrolled fully into view,
 * so the chips in these scenes sit further left than in the design.
 */
const APPROVED = [{ width: 390, scenes: ['change', 'refine'], key: /^button "Tune / }]

const GEOMETRY = `(() => {
  const out = {}
  const seen = {}
  for (const el of document.querySelectorAll('header, h1, h2, article, form, nav, section, button, [role=status], [role=progressbar], ul')) {
    const r = el.getBoundingClientRect()
    if (r.width === 0 || r.height === 0) continue
    if (el.getAttribute('aria-hidden') === 'true' || getComputedStyle(el).opacity === '0') continue
    const name = (el.getAttribute('aria-label') || (['BUTTON', 'H1', 'H2'].includes(el.tagName) ? el.textContent : '') || '').replace(/[\\s,]+/g, ' ').replace(' just updated', '').trim().slice(0, 34)
    let key = el.tagName.toLowerCase() + (el.getAttribute('role') ? '[' + el.getAttribute('role') + ']' : '') + (name ? ' "' + name + '"' : '')
    seen[key] = (seen[key] || 0) + 1
    if (seen[key] > 1) key += ' #' + seen[key]
    out[key] = [r.x, r.y, r.width, r.height].map((n) => Math.round(n * 10) / 10)
  }
  return out
})()`

/** Text width depends on the font, so both sides need the web fonts, not a fallback. Google Fonts occasionally stalls, so a page is loaded a second time before giving up. */
async function openWithFonts(url, width, height, settle) {
  for (let attempt = 1; attempt <= 2; attempt++) {
    const { webFonts } = await b.open(url, width, height, { mobile: false, scale: 1, settle, webFonts: true })
    if (webFonts) return true
    report.note(`web fonts did not load for ${url} (attempt ${attempt})`)
  }
  return false
}

try {
  for (const [width, height] of SIZES) {
    report.section(`${width}×${height}`)
    for (const scene of SCENES) {
      const appFonts = await openWithFonts(`${APP}?demo=${scene}`, width, height, 600)
      const app = await b.ev(GEOMETRY)
      await b.shot(`app-${scene}-${width}`)
      const designFonts = await openWithFonts(`${DESIGN}scene-${scene}-${width}x${height}.html`, width, height, 1500)
      const design = await b.ev(GEOMETRY)
      if (!appFonts || !designFonts) {
        report.check(`${scene}: web fonts available for the comparison`, false, 'Bricolage Grotesque and Instrument Sans did not load from Google Fonts (offline?). This comparison needs them; the app itself works without them.')
        continue
      }
      await b.shot(`design-${scene}-${width}`)

      const approved = (key) => APPROVED.some((rule) => rule.width === width && rule.scenes.includes(scene) && rule.key.test(key))
      const differences = []
      let matched = 0
      for (const key of Object.keys(design)) {
        if (!(key in app)) continue
        matched++
        const moved = design[key].some((value, index) => Math.abs(app[key][index] - value) > TOLERANCE)
        if (moved && !approved(key)) differences.push(`${key}: design ${design[key].join(' ')} | app ${app[key].join(' ')}`)
      }
      report.check(`${scene}: ${matched} matching elements within ${TOLERANCE}px of the design`, matched >= MIN_MATCHED && differences.length === 0, differences.join(' || ') || (matched < MIN_MATCHED ? 'too few elements matched' : ''))
    }
  }
  report.check('no console errors or warnings during the checks', b.consoleErrors.length === 0, b.consoleErrors.slice(0, 3).join(' | '))
} catch (error) {
  report.fail(`script error: ${error.stack ?? error}`)
} finally {
  await b.close()
}
await report.finish(outDir)
