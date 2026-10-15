// Quality checks in a real browser (the F6 behaviour):
//   - motion: entrances, the hero settling into history, reaction confirmation, no looping;
//   - overlays: focus moves in, the rest is inert, Tab stays inside, Escape and the scrim close,
//     focus returns, exit animations finish; the drawer while switching sessions;
//   - reduced motion: no running animations, overlays close without waiting;
//   - adaptive composer: compact now-playing appears when the hero's controls scroll away;
//   - intent strip: a changed chip scrolls into view; edge fades only where there is more;
//   - desktop rail from 1024px, and a drawer left open when the window grows;
//   - responsive audit: 16 sizes x 11 scenes for sideways overflow, off-screen content,
//     targets under 44px and clipped labels;
//   - text contrast over artwork, measured from rendered pixels.
import { APP, contrast, createReport, decodePng, launch, outputDir } from './harness.mjs'

const outDir = outputDir('quality')
const report = createReport('Quality: motion, overlays, composer, responsive layout, contrast')
const { check, section } = report
const b = await launch({ outDir })

try {
  // ---------------------------------------------------------------- motion
  section('Motion')
  await b.open(APP, 390, 844)
  await b.click('Open listening sessions'); await b.click('Emotional Afrobeats', 500)
  let s = await b.ev(`({ entering: document.querySelectorAll('main [data-enter]').length, items: document.querySelector('main').querySelectorAll('article, [role=status], p').length })`)
  check('content already in a session does not animate when the session opens', s.entering === 0 && s.items > 0, JSON.stringify(s))

  await b.ev(`window.__btn('More like this').click()`)
  s = await b.ev(`new Promise((r) => requestAnimationFrame(() => r({
    enters: [...document.querySelectorAll('main [data-enter]')].map((el) => el.dataset.enter),
    running: document.getAnimations().filter((a) => a.playState === 'running').map((a) => a.animationName),
  })))`)
  check('a new turn animates in: message and acknowledgement rise, the recommendation is revealed', s.enters.filter((e) => e === 'rise').length === 2 && s.enters.includes('reveal'), JSON.stringify(s.enters))
  check('the previous hero settles into history', s.enters.includes('settle'))
  check('those animations are actually running', s.running.some((n) => /rise|reveal|settle/.test(n)), s.running.join(','))
  await b.wait(600)
  s = await b.ev(`document.getAnimations().filter((a) => a.playState === 'running' && /rise|reveal|settle/.test(a.animationName)).length`)
  check('and they finish (no looping motion)', s === 0)

  await b.click('Like')
  s = await b.ev(`document.getAnimations().map((a) => a.animationName).filter(Boolean)`)
  check('a reaction confirms itself', s.some((n) => /confirm/.test(n)), s.join(','))

  // ------------------------------------------------- overlays: sheet
  section('Playlist sheet: focus, dismissal, exit')
  await b.ev(`window.__btn('Save to a playlist').focus()`)
  await b.ev(`window.__btn('Save to a playlist').click()`)
  await b.wait(60)
  s = await b.ev(`({
    dialog: !!document.querySelector('[role=dialog]'),
    focusInDialog: document.querySelector('[role=dialog]')?.contains(document.activeElement) ?? false,
    backgroundInert: [...document.querySelectorAll('[inert]')].length,
    running: document.getAnimations().map((a) => a.animationName).filter(Boolean),
  })`)
  check('opening the sheet moves focus into it', s.dialog && s.focusInDialog)
  check('the rest of the screen is inert while it is open', s.backgroundInert >= 1)
  check('the sheet and scrim animate in', s.running.some((n) => /sheet-in/.test(n)) && s.running.some((n) => /scrim-in/.test(n)), s.running.join(','))
  await b.wait(450)

  await b.key('Tab', 'Tab', 9); await b.key('Tab', 'Tab', 9); await b.key('Tab', 'Tab', 9)
  s = await b.ev(`({ inDialog: document.querySelector('[role=dialog]').contains(document.activeElement), tag: document.activeElement.tagName, outline: getComputedStyle(document.activeElement).outlineStyle })`)
  check('Tab stays inside the sheet', s.inDialog, JSON.stringify(s))
  check('the focused control shows a focus ring', s.outline !== 'none', s.outline)

  await b.key('Escape', 'Escape', 27)
  s = await b.ev(`({ leaving: !!document.querySelector('[data-leaving]'), present: !!document.querySelector('[role=dialog]'), inert: document.querySelectorAll('[inert]').length, focus: window.__name(document.activeElement) })`)
  check('Escape starts the exit and frees the screen at once', s.leaving && s.present && s.inert === 0, JSON.stringify(s))
  check('focus returns to the button that opened it', s.focus === 'Save to a playlist', s.focus)
  await b.wait(500)
  check('the sheet is gone once its exit ends', (await b.ev(`!document.querySelector('[role=dialog]')`)))

  await b.click('Save to a playlist', 450)
  await b.ev(`document.querySelector('[aria-label="Close playlist picker"]').click()`)
  await b.wait(500)
  check('tapping the scrim closes it too', await b.ev(`!document.querySelector('[role=dialog]')`))

  // ------------------------------------------------- overlays: drawer
  section('Session drawer: focus, dismissal, exit')
  await b.ev(`window.__btn('Open listening sessions').focus()`)
  await b.ev(`window.__btn('Open listening sessions').click()`)
  await b.wait(60)
  s = await b.ev(`({ nav: !!document.querySelector('nav'), focusInNav: document.querySelector('nav')?.contains(document.activeElement) ?? false, inert: document.querySelectorAll('[inert]').length, running: document.getAnimations().map((a) => a.animationName).filter(Boolean) })`)
  check('opening the drawer moves focus into it and makes the rest inert', s.nav && s.focusInNav && s.inert >= 1, JSON.stringify(s))
  check('the drawer slides in', s.running.some((n) => /drawer-in/.test(n)), s.running.join(','))
  await b.wait(450)
  await b.key('Escape', 'Escape', 27)
  s = await b.ev(`({ leaving: !!document.querySelector('[data-leaving]'), focus: window.__name(document.activeElement) })`)
  check('Escape closes it and returns focus to the menu button', s.leaving && s.focus === 'Open listening sessions', JSON.stringify(s))
  await b.wait(500)
  check('the drawer is gone once its exit ends', await b.ev(`!document.querySelector('nav')`))

  await b.ev(`window.__btn('Open listening sessions').focus()`)
  await b.ev(`window.__btn('Open listening sessions').click()`)
  await b.wait(450)
  await b.ev(`window.__btn('Coding').click()`)
  await b.wait(60)
  s = await b.ev(`({ title: document.querySelector('h1').textContent, leaving: !!document.querySelector('[data-leaving] nav'), entering: document.querySelectorAll('main [data-enter]').length })`)
  check('choosing a session shows it at once while the drawer slides away', s.title === 'Coding' && s.leaving, JSON.stringify(s))
  check('the session that opens does not replay entrances for content it already had', s.entering === 0, String(s.entering))
  await b.wait(500)
  s = await b.ev(`({ nav: !!document.querySelector('nav'), focus: window.__name(document.activeElement), draft: document.querySelector('input').value })`)
  check('then the drawer is gone and focus is back on the menu button', !s.nav && s.focus === 'Open listening sessions', JSON.stringify(s))
  await b.ev(`window.__btn('Open listening sessions').click()`); await b.wait(450)
  await b.ev(`window.__btn('Emotional Afrobeats').click()`); await b.wait(550)

  // ------------------------------------------------- reduced motion
  section('Reduced motion')
  await b.reducedMotion(true)
  await b.ev(`window.__btn('More like this').click()`)
  s = await b.ev(`new Promise((r) => setTimeout(() => r({ running: document.getAnimations().filter((a) => a.playState === 'running').length, longest: Math.max(0, ...document.getAnimations().map((a) => Number(a.effect.getComputedTiming().duration))) }), 120))`)
  check('a new turn appears with its animations cut to nothing', s.running === 0 && s.longest <= 0.01, JSON.stringify(s))
  await b.click('Save to a playlist', 60)
  s = await b.ev(`({ dialog: !!document.querySelector('[role=dialog]'), duration: getComputedStyle(document.querySelector('[role=dialog]')).animationDuration })`)
  check('the sheet opens with its animation reduced to nothing', s.dialog && parseFloat(s.duration) < 0.001, s.duration)
  await b.key('Escape', 'Escape', 27)
  await b.wait(120)
  check('and closes without waiting on an animation', await b.ev(`!document.querySelector('[role=dialog]')`))
  await b.reducedMotion(false)

  // ------------------------------------------------- adaptive composer
  section('Adaptive composer')
  for (let i = 0; i < 4; i++) await b.click('Next recommendation')
  await b.wait(500)
  const lead = `document.querySelector('form [data-mode]')`
  const mini = `document.querySelector('form [data-mode] button')`
  s = await b.ev(`({ mode: ${lead}.dataset.mode, miniTab: ${mini}?.tabIndex, miniHidden: ${mini}?.getAttribute('aria-hidden'), scrollable: (() => { const sc = document.querySelector('[class*="_scroller_"]'); return sc.scrollHeight - sc.clientHeight })() })`)
  check('with the hero in view the composer shows its glyph and the compact player is out of reach', s.mode === 'idle' && s.miniTab === -1 && s.miniHidden === 'true', JSON.stringify(s))
  check('the session is long enough to scroll', s.scrollable > 300, String(s.scrollable))

  await b.ev(`document.querySelector('[class*="_scroller_"]').scrollTo({ top: -100000 })`)
  await b.wait(450)
  s = await b.ev(`({ mode: ${lead}.dataset.mode, miniTab: ${mini}.tabIndex, label: ${mini}.getAttribute('aria-label'), opacity: getComputedStyle(${mini}).opacity, rect: (() => { const r = ${mini}.getBoundingClientRect(); return Math.round(r.width) + 'x' + Math.round(r.height) })() })`)
  check('scrolled away from the hero, the composer shows compact now-playing', s.mode === 'playing' && s.miniTab === 0 && s.opacity === '1', JSON.stringify(s))
  check('the compact player is a 44px target', s.rect === '44x44', s.rect)
  await b.shot('compact-now-playing')
  const labelBefore = s.label
  await b.ev(`${mini}.click()`); await b.wait(120)
  s = await b.ev(`${mini}.getAttribute('aria-label')`)
  check('it pauses and plays the song', /^Pause/.test(labelBefore) && /^Play/.test(s), `${labelBefore} → ${s}`)
  await b.ev(`${mini}.click()`)

  await b.type('Keep this mood')
  await b.wait(500)
  s = await b.ev(`({ top: document.querySelector('[class*="_scroller_"]').scrollTop, mode: ${lead}.dataset.mode })`)
  check('a new turn brings the stream back to the newest content', Math.abs(s.top) < 2, JSON.stringify(s))
  check('and the composer returns to its glyph', s.mode === 'idle')

  // ------------------------------------------------- intent strip on a narrow phone
  section('Intent strip')
  await b.open(APP + '?demo=change', 320, 568)
  s = await b.ev(`(() => { const strip = document.querySelector('[aria-label="Current intent"]'); const chip = strip.querySelector('[data-changed]'); const a = strip.getBoundingClientRect(), c = chip.getBoundingClientRect(); return { scrolled: strip.scrollLeft, chipRight: Math.round(c.right), stripRight: Math.round(a.right), fits: c.left >= a.left - 1 && c.right <= a.right + 1 && (!strip.hasAttribute('data-more-end') || c.right <= a.right - 40 + 1), fadeStart: strip.hasAttribute('data-more-start'), fadeEnd: strip.hasAttribute('data-more-end') } })()`)
  check('at 320px the chip that just changed is scrolled into view, clear of the edge fade', s.fits && s.scrolled > 0, JSON.stringify(s))
  check('the strip fades on the side that has more chips', s.fadeStart && !s.fadeEnd, JSON.stringify(s))
  await b.open(APP + '?demo=initial', 390, 844)
  s = await b.ev(`(() => { const strip = document.querySelector('[aria-label="Current intent"]'); return { start: strip.hasAttribute('data-more-start'), end: strip.hasAttribute('data-more-end'), scrolled: strip.scrollLeft } })()`)
  check('chips that fit show no fade at all', !s.start && !s.end && s.scrolled === 0, JSON.stringify(s))
  await b.open(APP + '?demo=stress', 320, 568)
  s = await b.ev(`(() => { const row = document.querySelector('[aria-label="Suggested refinements"]'); return { end: row.hasAttribute('data-more-end'), cut: [...row.querySelectorAll('button')].filter((x) => x.scrollWidth > x.clientWidth + 1).length } })()`)
  check('quick actions too long for the row scroll with a fade, and no label is truncated', s.end && s.cut === 0, JSON.stringify(s))
  await b.shot('intent-strip-320')

  // ------------------------------------------------- desktop rail
  section('Desktop rail')
  await b.open(APP, 1280, 800, { mobile: false, scale: 1 })
  s = await b.ev(`(() => { const nav = document.querySelector('nav'); const col = document.querySelector('main').parentElement; const n = nav?.getBoundingClientRect(), c = col.getBoundingClientRect(); return { rail: !!nav, railRect: n && [n.x, n.y, n.width, n.height].map(Math.round).join(' '), menu: !!window.__btn('Open listening sessions'), close: !!window.__btn('Close menu'), column: [c.x, c.width].map(Math.round).join(' '), sessions: [...nav.querySelectorAll('button')].length, overflow: document.documentElement.scrollWidth > innerWidth } })()`)
  check('from 1024px the session navigation stands as a rail', s.rail && s.railRect === '0 0 304 800', JSON.stringify(s))
  check('the menu button and the close button are not offered', !s.menu && !s.close)
  check('the session column is centred in the space beside the rail', s.column === '492 600', s.column)
  await b.shot('desktop-new')
  await b.click('Emotional Afrobeats', 400)
  s = await b.ev(`({ title: document.querySelector('h1').textContent, hero: document.querySelector('article h2')?.textContent, art: Math.round(document.querySelector('article > div').getBoundingClientRect().height), active: document.querySelector('nav [aria-current]')?.textContent.slice(0, 19) })`)
  check('choosing a session in the rail opens it, and the rail marks it', s.title === 'Emotional Afrobeats' && s.hero === 'Calm Down' && s.active === 'Emotional Afrobeats', JSON.stringify(s))
  check('the artwork takes the taller wide-screen height', s.art === 300, String(s.art))
  await b.click('Save to a playlist', 500)
  s = await b.ev(`(() => { const d = document.querySelector('[role=dialog]').getBoundingClientRect(); const railInert = document.querySelector('nav').parentElement.inert; return { centre: Math.round(d.x + d.width / 2), width: Math.round(d.width), railInert } })()`)
  check('the playlist sheet centres over the session, not the whole window', s.centre === 792 && s.width === 560, JSON.stringify(s))
  check('the rail is inert while the sheet is open', s.railInert === true)
  await b.shot('desktop-save')
  await b.key('Escape', 'Escape', 27); await b.wait(450)

  // A drawer left open on a phone must not strand the session when the window grows.
  await b.open(APP, 390, 844)
  await b.click('Open listening sessions'); await b.click('Gym Energy', 500)
  await b.click('Open listening sessions', 450)
  const timeBefore = await b.ev(`document.querySelector('article [role=progressbar]').nextElementSibling.firstElementChild.textContent`)
  await b.size(1280, 800, { mobile: false, scale: 1 })
  await b.wait(2400)
  s = await b.ev(`({ rail: document.querySelectorAll('nav').length, inert: document.querySelectorAll('[inert]').length, time: document.querySelector('article [role=progressbar]').nextElementSibling.firstElementChild.textContent })`)
  check('growing the window with the drawer open leaves one rail, nothing inert, and playback running', s.rail === 1 && s.inert === 0 && s.time !== timeBefore, JSON.stringify({ ...s, timeBefore }))

  // ------------------------------------------------- responsive audit
  section('Responsive audit')
  const AUDIT = `(() => {
    const d = document.documentElement
    const small = [], clipped = []
    for (const el of document.querySelectorAll('button, a, input')) {
      const r = el.getBoundingClientRect()
      if (r.width === 0 || r.height === 0) continue
      if (el.closest('[inert]') || el.getAttribute('aria-hidden') === 'true') continue
      const before = getComputedStyle(el, '::before')
      const ext = (side) => (before.content !== 'none' && before.position === 'absolute' ? Math.max(0, -parseFloat(before[side] || '0')) || 0 : 0)
      const w = r.width + ext('left') + ext('right'), h = r.height + ext('top') + ext('bottom')
      if (w < 43.5 || h < 43.5) small.push(window.__name(el).slice(0, 24) + ' ' + Math.round(w) + 'x' + Math.round(h))
    }
    // Labels that must never be cut: intent chips, quick actions, reactions, tabs and choices.
    for (const el of document.querySelectorAll('[aria-label="Current intent"] button, [aria-label="Suggested refinements"] button, article button, [role=tab], [role=radio]')) {
      if (el.textContent.trim() && el.scrollWidth > el.clientWidth + 1) clipped.push(window.__name(el).slice(0, 30))
    }
    const out = [...document.querySelectorAll('main *, [aria-label="Session controls"] *, header *, nav *, [role=dialog] *')].filter((el) => { const r = el.getBoundingClientRect(); if (!(r.width > 0 && (r.right > innerWidth + 1 || r.left < -1)) || el.closest('[aria-label="Current intent"], [aria-label="Suggested refinements"], [role=radiogroup]')) return false; for (let a = el.parentElement; a; a = a.parentElement) { const ar = a.getBoundingClientRect(); if (getComputedStyle(a).overflowX !== 'visible' && ar.right <= innerWidth + 1 && ar.left >= -1) return false } return true }).length
    return { overflowX: d.scrollWidth > innerWidth || document.body.scrollWidth > innerWidth, small: [...new Set(small)], clipped: [...new Set(clipped)], offscreen: out, railed: !!document.querySelector('nav') && !document.querySelector('nav').closest('[class*=layer]') }
  })()`
  const scenes = ['new', 'initial', 'change', 'save', 'discovery', 'refine', 'drawer', 'stress', 'stress-tune', 'stress-save', 'stress-drawer', 'turn-pending', 'turn-failed', 'loading', 'load-failed']
  // Before the sessions have loaded there is no navigation to show.
  const unrailed = ['drawer', 'stress-drawer', 'loading', 'load-failed']
  const sizes = [[320, 568], [344, 882], [360, 740], [375, 667], [390, 844], [430, 932], [600, 960], [699, 900], [700, 900], [768, 1024], [1023, 768], [1024, 768], [1280, 800], [1440, 900], [1920, 1080], [844, 390]]
  const problems = []
  let views = 0
  for (const [w, h] of sizes) {
    for (const scene of scenes) {
      await b.open(`${APP}?demo=${scene}`, w, h, { mobile: w < 700 || h < 500, scale: 1, settle: 550 })
      const a = await b.ev(AUDIT)
      views++
      if (a.overflowX) problems.push(`${scene}@${w}x${h}: page overflows sideways`)
      if (a.offscreen) problems.push(`${scene}@${w}x${h}: ${a.offscreen} elements off screen`)
      if (a.small.length) problems.push(`${scene}@${w}x${h}: small targets ${a.small.join('; ')}`)
      if (a.clipped.length) problems.push(`${scene}@${w}x${h}: clipped labels ${a.clipped.join('; ')}`)
      if ((w >= 1024) !== a.railed && !unrailed.includes(scene)) problems.push(`${scene}@${w}x${h}: rail ${a.railed ? 'shown' : 'missing'}`)
      if (['stress', 'stress-save', 'stress-drawer', 'stress-tune'].includes(scene) && [320, 390, 768, 1280].includes(w) && h > 500) await b.shot(`${scene}-${w}`)
      if (['initial', 'refine', 'save'].includes(scene) && [768, 1440].includes(w)) await b.shot(`${scene}-${w}`)
      if (w === 844 && scene === 'initial') await b.shot('initial-landscape')
    }
  }
  check(`no sideways overflow, off-screen content, small targets or clipped labels across ${views} views (${sizes.length} sizes × ${scenes.length} scenes)`, problems.length === 0, problems.slice(0, 12).join(' | '))

  // ------------------------------------------------- contrast over artwork
  section('Text contrast over artwork (measured from rendered pixels)')
  await b.open(APP + '?demo=gallery', 390, 844, { scale: 1 })
  const height = await b.ev(`document.querySelector('[class*=page]').scrollHeight`)
  await b.size(390, height, { scale: 1 }); await b.wait(700)
  // Hide the text itself so the pixels sampled are purely what sits behind it.
  await b.ev(`(() => { const st = document.createElement('style'); st.textContent = 'article h2, article h2 ~ span, article span:has(+ h2) { color: transparent !important; text-shadow: none !important }'; document.head.append(st) })()`)
  const heroes = await b.ev(`[...document.querySelectorAll('article')].map((article) => {
    const label = article.closest('[class*=variant]')?.querySelector('p')?.textContent ?? ''
    const media = article.firstElementChild
    const rect = (el) => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height } }
    const h2 = media.querySelector('h2')
    return { label, lines: [
      { name: 'descriptors', color: [233, 213, 255], min: 4.5, ...rect(h2.previousElementSibling) },
      { name: 'title', color: [248, 247, 251], min: 3, ...rect(h2) },
      { name: 'artist', color: [217, 210, 230], min: 4.5, ...rect(h2.nextElementSibling) },
    ] }
  })`)
  for (const hero of heroes) {
    const worst = []
    for (const line of hero.lines) {
      const image = decodePng(await b.png({ x: Math.floor(line.x), y: Math.floor(line.y), width: Math.ceil(line.width), height: Math.ceil(line.height) }))
      let lowest = Infinity
      for (let i = 0; i < image.data.length; i += image.channels) lowest = Math.min(lowest, contrast(line.color, [image.data[i], image.data[i + 1], image.data[i + 2]]))
      worst.push({ name: line.name, ratio: Math.round(lowest * 100) / 100, ok: lowest >= line.min, min: line.min })
    }
    check(`hero text over "${hero.label}"`, worst.every((w) => w.ok), worst.map((w) => `${w.name} ${w.ratio}:1 (needs ${w.min})`).join(', '))
  }
  // Compact now-playing: the equaliser bars over white artwork.
  const miniBox = await b.ev(`(() => { const all = [...document.querySelectorAll('form [data-mode="playing"] button')]; const el = all.at(-1); el.querySelectorAll('span span').forEach((s) => s.style.visibility = 'hidden'); const r = el.getBoundingClientRect(); return { x: r.x + 14, y: r.y + 14, width: 16, height: 18 } })()`)
  const miniImage = decodePng(await b.png(miniBox))
  let lowest = Infinity
  for (let i = 0; i < miniImage.data.length; i += miniImage.channels) lowest = Math.min(lowest, contrast([248, 247, 251], [miniImage.data[i], miniImage.data[i + 1], miniImage.data[i + 2]]))
  check('compact now-playing bars over pure white artwork', lowest >= 3, `${Math.round(lowest * 100) / 100}:1 (needs 3)`)

  check('no console errors or warnings during the checks', b.consoleErrors.length === 0, b.consoleErrors.slice(0, 3).join(' | '))
} catch (error) {
  report.fail(`script error: ${error.stack ?? error}`)
} finally {
  await b.close()
}
await report.finish(outDir)
