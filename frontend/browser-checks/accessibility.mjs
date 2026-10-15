// Accessibility checks in a real browser:
//   - axe-core over every design scene and long-content scene, and with each overlay open;
//   - a keyboard-only probe of where focus lands after each main action, and the Tab order;
//   - text scaled to 200%: no sideways overflow, no cut-off control labels, song title kept in its card.
// Usage: node browser-checks/accessibility.mjs [all|axe|keys|text]
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { APP, createReport, launch, outputDir } from './harness.mjs'

const mode = process.argv[2] ?? 'all'
const outDir = outputDir('accessibility')
const axeSource = await readFile(createRequire(import.meta.url).resolve('axe-core/axe.min.js'), 'utf8')
const report = createReport('Accessibility')
const { check } = report
const b = await launch({ outDir })

async function axe(label) {
  await b.ev(`${axeSource};0`)
  // No preload: axe would re-fetch every stylesheet, including the cross-origin Google Fonts
  // one, which makes the audit depend on the network. Only the css-orientation-lock rule
  // needs it, and the app never locks orientation.
  const violations = await b.ev(`axe.run(document, { resultTypes: ['violations'], preload: false }).then((r) => r.violations.map((v) => ({
    id: v.id, impact: v.impact, help: v.help,
    nodes: v.nodes.slice(0, 4).map((n) => n.target.join(' ') + ' :: ' + (n.failureSummary || '').split('\\n').slice(1, 2).join('').trim()),
  })))`)
  check(`axe: ${label}`, violations.length === 0, violations.map((v) => `${v.impact} ${v.id} (${v.help}) ${v.nodes.join(' | ')}`).join(' || '))
}

/** Where focus is, named the way a screen reader would announce it. */
const FOCUS = `(() => {
  const el = document.activeElement
  if (!el || el === document.body) return 'BODY (focus lost)'
  return (el.getAttribute('role') || el.tagName.toLowerCase()) + ' "' + (el.getAttribute('aria-label') || el.innerText || el.placeholder || '').replace(/\\s+/g, ' ').trim().slice(0, 40) + '"'
})()`

const SCENES = ['new', 'initial', 'change', 'save', 'discovery', 'refine', 'drawer', 'stress', 'stress-tune']

try {
  if (mode === 'all' || mode === 'axe') {
    report.section('axe-core: scenes at phone and desktop width')
    for (const [width, height] of [[390, 844], [1280, 800]]) {
      for (const scene of SCENES) {
        await b.open(`${APP}?demo=${scene}`, width, height, { mobile: width < 700, scale: 1, settle: 700 })
        await axe(`${scene} @${width}`)
      }
    }
    report.section('axe-core: interactive states')
    await b.open(APP, 390, 844, { settle: 500 })
    await b.click('Focus', 400)
    await axe('first recommendation')
    await b.click('Tune energy, mood or genre', 300)
    await axe('tuning open')
    await b.click('Close tuning', 200)
    await b.click('Save to a playlist', 500)
    await axe('playlist sheet open')
    await b.key('Escape', 'Escape', 27)
    await b.wait(500)
    await b.click('Open listening sessions', 500)
    await axe('drawer open')
  }

  if (mode === 'all' || mode === 'keys') {
    report.section('Keyboard only: where focus lands after each action')
    await b.open(APP, 390, 844, { settle: 500 })
    const focusOn = (text) => b.ev(`window.__btn(${JSON.stringify(text)}).focus()`)
    const press = async (key, code, keyCode, pause = 120) => { await b.key(key, code, keyCode); await b.wait(pause) }
    const focusAfter = async (action) => {
      const where = await b.ev(FOCUS)
      report.note(`after ${action}: ${where}`)
      return where
    }

    await focusOn('Focus')
    await press('Enter', 'Enter', 13, 400)
    check('starting a session keeps focus in the app', /Pause Last Last/.test(await focusAfter('choosing a starter with Enter')))
    await focusOn('Tune energy, mood or genre')
    await press('Enter', 'Enter', 13)
    check('opening Tune moves focus to the selected tab', /tab "Energy"/.test(await focusAfter('opening Tune')))
    await press('ArrowRight', 'ArrowRight', 39)
    check('ArrowRight moves to and selects the next tab', /tab "Mood"/.test(await focusAfter('ArrowRight on the tabs')))
    await focusOn('Close tuning')
    await press('Enter', 'Enter', 13)
    check('closing Tune returns focus to Tune', /Tune energy/.test(await focusAfter('closing Tune')))
    await focusOn('A bit calmer')
    await press('Enter', 'Enter', 13, 400)
    check('a quick action keeps focus in the same place among the new quick actions', /button "Even calmer"/.test(await focusAfter('a quick action')))
    await focusOn('Not for me')
    await press('Enter', 'Enter', 13, 400)
    check('"Not for me" keeps focus on the new song\'s "Not for me"', /Not for me/.test(await focusAfter('"Not for me"')))
    await focusOn('Next recommendation')
    await press('Enter', 'Enter', 13, 400)
    check('Next keeps focus on Next', /Next recommendation/.test(await focusAfter('Next')))
    await focusOn('Like')
    await press('Enter', 'Enter', 13)
    check('Like keeps focus on the pressed Like', /Liked/.test(await focusAfter('Like')))

    report.section('Keyboard only: Tab order while tuning')
    await b.open(`${APP}?demo=refine`, 390, 844, { settle: 500 })
    await b.ev('document.activeElement?.blur()')
    const order = []
    for (let i = 0; i < 40; i++) {
      await press('Tab', 'Tab', 9, 60)
      const where = await b.ev(FOCUS)
      if (order.length && where === order[0]) break
      order.push(where)
    }
    report.note(order.join('\n     '))
    check('the tab list is a single Tab stop', order.filter((entry) => entry.startsWith('tab ')).length === 1)
    check('every control in the session is reachable by Tab', ['Open listening sessions', 'Pause Monalisa', 'Save to a playlist', 'Close tuning', 'High energy', 'Send to Intentune'].every((name) => order.some((entry) => entry.includes(name))))
  }

  if (mode === 'all' || mode === 'text') {
    report.section('Text at 200%')
    for (const scene of ['new', 'initial', 'refine', 'save', 'drawer', 'stress']) {
      for (const [width, height] of [[390, 844], [1280, 800]]) {
        await b.open(`${APP}?demo=${scene}`, width, height, { mobile: width < 700, scale: 1, settle: 500 })
        await b.ev(`document.documentElement.style.fontSize = '200%'`)
        await b.wait(400)
        const result = await b.ev(`(() => {
          const visible = (el) => el.getClientRects().length && !el.closest('[aria-hidden="true"]')
          // Control labels that are cut off sideways (rows that scroll, by design, are not controls).
          const cut = [...document.querySelectorAll('button, [role=tab]')].filter((el) => visible(el) && el.textContent.trim() && el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).textOverflow !== 'ellipsis').map((el) => window.__name(el).slice(0, 30))
          const card = document.querySelector('article')
          const title = card?.querySelector('h2')
          const titleInCard = !card || title.getBoundingClientRect().top >= card.getBoundingClientRect().top - 1
          return { overflowX: document.documentElement.scrollWidth > innerWidth, cut, titleInCard }
        })()`)
        check(`${scene} @${width}: no sideways overflow, no cut-off labels, song title within its card`, !result.overflowX && result.cut.length === 0 && result.titleInCard, JSON.stringify(result))
        if (width === 390) await b.shot(`text-200-${scene}`)
      }
    }
  }

  check('no console errors or warnings during the checks', b.consoleErrors.length === 0, b.consoleErrors.slice(0, 3).join(' | '))
} catch (error) {
  report.fail(`script error: ${error.stack ?? error}`)
} finally {
  await b.close()
}
await report.finish(outDir)
