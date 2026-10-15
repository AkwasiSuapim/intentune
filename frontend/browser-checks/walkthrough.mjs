// The F5 walkthrough in a real browser: drives the built app through the whole mock flow
// (Tune in, a starter, typing, a quick action, Like, Why this fits, tuning, saving, Not for me,
// Next, Up next, the playback clock, the drawer, switching sessions, replay, a new session),
// clicking and typing as a user would, and checks the screen after every step.
// Runs at 390x844 and 320x568.
import { APP, createReport, launch, outputDir } from './harness.mjs'

const outDir = outputDir('walkthrough')
const report = createReport('Walkthrough of the mock listening flow')
const b = await launch({ outDir })
const { ev, wait } = b

/** A summary of what is on screen, read in the page. */
const STATE = `(() => {
    const name = (b) => (b.getAttribute('aria-label') || b.textContent || '').replace(/\\s+/g, ' ').trim()
    window.__btn = (text) => [...document.querySelectorAll('button')].find((b) => name(b) === text) || [...document.querySelectorAll('button')].find((b) => name(b).startsWith(text))
    window.__state = () => {
      const d = document.documentElement
      const heroes = [...document.querySelectorAll('article')]
      const hero = heroes[0]
      const actions = [...document.querySelectorAll('[aria-label="Suggested refinements"] button')]
      const group = document.querySelector('[aria-label="Suggested refinements"]')
      return {
        title: document.querySelector('h1')?.textContent,
        prompt: !!document.querySelector('h2') && /What do you need/.test(document.body.textContent) && heroes.length === 0,
        heroes: heroes.length,
        hero: hero?.querySelector('h2')?.textContent ?? null,
        time: hero?.querySelector('[role=progressbar]')?.nextElementSibling?.firstElementChild?.textContent ?? null,
        playing: hero ? /^Pause/.test(name(hero.querySelector('button'))) : null,
        chips: [...document.querySelectorAll('[aria-label="Current intent"] button')].map((b) => b.textContent.trim() + (b.hasAttribute('data-changed') ? '*' : '') + (b.getAttribute('aria-expanded') === 'true' ? '^' : '')),
        acks: [...document.querySelectorAll('main [class*="_ack_"]')].map((a) => [...a.querySelectorAll('span')].filter((el) => el.children.length === 0 && el.textContent.trim()).map((el) => el.textContent.trim()).join(' ')),
        messages: [...document.querySelectorAll('main p')].map((p) => p.textContent.replace('You said: ', '')).filter((t) => !/^You said “/.test(t)),
        history: [...document.querySelectorAll('main button[aria-label$="Played"], main button[aria-label$="Liked"], main button[aria-label$="Saved"], main button[aria-label$="Skipped"]')].map((b) => b.getAttribute('aria-label').replace(/^Play (.*) by .* again\\. /, '$1 → ')),
        actions: actions.map(name),
        actionsCut: group ? group.scrollWidth > group.clientWidth + 1 : false,
        refine: !!document.querySelector('[aria-label="Tune the session"]'),
        upNext: document.querySelector('button[aria-label^="Up next"]')?.getAttribute('aria-label') ?? null,
        liked: hero ? [...hero.querySelectorAll('button')].find((b) => b.hasAttribute('aria-pressed'))?.getAttribute('aria-pressed') : null,
        save: hero ? name([...hero.querySelectorAll('button')].at(-1)) : null,
        why: hero?.querySelector('[aria-expanded][aria-controls]')?.getAttribute('aria-expanded') ?? null,
        sheet: !!document.querySelector('[role=dialog]'),
        checked: [...document.querySelectorAll('[role=checkbox][aria-checked=true]')].map((b) => b.textContent.replace('Fits this session', '').trim()),
        cta: document.querySelector('[role=dialog]') ? name([...document.querySelectorAll('[role=dialog] button')].at(-1)) + (([...document.querySelectorAll('[role=dialog] button')].at(-1)).disabled ? ' (disabled)' : '') : null,
        drawer: [...document.querySelectorAll('nav button[aria-current], nav button')].filter((b) => b.querySelector('span span')).map((b) => (b.getAttribute('aria-current') ? '>' : '') + b.querySelector('span span').textContent),
        overflowX: d.scrollWidth > innerWidth,
        placeholder: document.querySelector('input')?.placeholder,
        draft: document.querySelector('input')?.value,
      }
    }
  })()`

async function walk(W, H) {
  report.section(`${W}×${H}`)
  await b.open(APP, W, H, { settle: 300 })
  await ev(STATE)
  let step = 0
  const state = () => ev('window.__state()')
  const click = async (text) => {
    if (!(await b.click(text))) report.fail(`${W}px step ${step}: no button "${text}"`)
  }
  const type = (text) => b.type(text)
  const shot = (name) => b.shot(`${W}-${String(step).padStart(2, '0')}-${name}`)
  const check = async (name, expectations, picture = false) => {
    step++
    const s = await state()
    const problems = []
    for (const [what, test] of Object.entries(expectations)) {
      let ok = false
      try { ok = !!test(s) } catch { ok = false }
      if (!ok) problems.push(what)
    }
    if (s.overflowX) problems.push('page overflows sideways')
    if (s.heroes > 1) problems.push('more than one hero')
    if (s.actions.length > 2) problems.push('more than two quick actions')
    if (s.actionsCut) problems.push('quick actions do not fit')
    report.check(`${step}. ${name}`, problems.length === 0, problems.length ? `${problems.join('; ')} :: ${JSON.stringify(s)}` : `${s.title} | hero: ${s.hero} | chips: ${s.chips.join(', ')}`)
    if (picture) await shot(name.replace(/[^a-z0-9]+/gi, '-').toLowerCase())
    return s
  }

    // --- The walkthrough ---
    await check('opens on Tune in', { 'prompt shown': (s) => s.prompt, 'title is New session': (s) => s.title === 'New session', 'no intent strip': (s) => s.chips.length === 0, 'first-turn placeholder': (s) => s.placeholder === 'Tell Intentune what you want…' }, true)

    await click('Unwind')
    const a = await check('starter starts a session', { 'one hero': (s) => s.heroes === 1, 'title set': (s) => s.title === 'Unwind', 'message shown': (s) => s.messages.includes('Something to unwind to'), 'intent set ack': (s) => s.acks[0] === 'Intent set Calm · Any genre · Low energy', 'chips match': (s) => s.chips.join('|') === 'Calm|Any genre|Low energy', 'two actions': (s) => s.actions.length === 2, 'playing': (s) => s.playing === true, 'next-turn placeholder': (s) => s.placeholder === 'Tell Intentune what you want next…' }, true)

    const typed = await type('Make it more energetic')
    const steered = await check('typed message steers the session', { 'typing reached the field': () => typed === 'Make it more energetic', 'draft cleared': (s) => s.draft === '', 'new hero': (s) => s.hero && s.hero !== a.hero, 'old hero in history': (s) => s.history.includes(a.hero + ' → Played'), 'message shown': (s) => s.messages.includes('Make it more energetic'), 'ack names the change': (s) => s.acks.at(-1) === 'Intent updated Energy Low Medium', 'energy chip changed': (s) => s.chips.includes('Medium energy*') }, true)

    await click('Keep this energy')
    const c = await check('quick action is sent as its words', { 'message shown': (s) => s.messages.at(-1) === 'Keep this energy', 'ack says kept': (s) => /^Holding medium energy/.test(s.acks.at(-1)), 'intent unchanged': (s) => s.chips.join('|') === 'Calm|Any genre|Medium energy', 'new hero': (s) => s.hero !== steered.hero })

    await click('Like')
    await check('like is a reaction, not a new direction', { 'pressed': (s) => s.liked === 'true', 'same hero': (s) => s.hero === c.hero, 'no new ack': (s) => s.acks.length === c.acks.length, 'actions follow the like': (s) => s.actions.join('|') === 'More like this|Save this' })

    await click('Why this fits')
    await check('why this fits expands', { 'expanded': (s) => s.why === 'true' })

    await click('Tune energy, mood or genre')
    await check('Tune opens the refine control', { 'refine shown': (s) => s.refine, 'actions replaced': (s) => s.actions.length === 0, 'energy chip marked open': (s) => s.chips.some((chip) => chip.startsWith('Medium energy') && chip.endsWith('^')) }, true)

    await click('High energy')
    const d = await check('choosing an energy level', { 'chip updated': (s) => s.chips.some((chip) => chip.startsWith('High energy')), 'ack': (s) => s.acks.at(-1) === 'Energy adjusted Energy Medium High', 'still tuning': (s) => s.refine, 'new hero': (s) => s.hero !== c.hero, 'liked song kept in history': (s) => s.history.includes(c.hero + ' → Liked'), 'why collapsed again': (s) => s.why === 'false' })

    await click('Mood')
    await click('Driven')
    await click('Genre')
    await click('Amapiano')
    const e = await check('choosing mood and genre', { 'chips': (s) => s.chips.map((chip) => chip.replace(/[*^]/g, '')).join('|') === 'Driven|Amapiano|High energy', 'ack': (s) => /^Genre switched/.test(s.acks.at(-1)), 'new hero': (s) => s.hero !== d.hero }, true)

    await click('Close tuning')
    await check('closing tuning brings the quick actions back', { 'refine hidden': (s) => !s.refine, 'actions back': (s) => s.actions.length === 2 })

    await click('Save to a playlist')
    await check('Save opens an explicit choice', { 'sheet open': (s) => s.sheet, 'nothing preselected': (s) => s.checked.length === 0, 'cannot confirm yet': (s) => s.cta === 'Choose a playlist (disabled)' }, true)

    await click('Workout')
    await check('choosing a playlist', { 'one checked': (s) => s.checked.join('|') === 'Workout', 'can confirm': (s) => s.cta === 'Save to Workout' })

    await click('Save to Workout')
    await wait(450) // the sheet now animates out before it is removed
    await check('confirming saves and closes', { 'sheet closed': (s) => !s.sheet, 'saved': (s) => /^Saved to Workout/.test(s.save), 'same hero': (s) => s.hero === e.hero, 'actions follow the save': (s) => s.actions.join('|') === 'More like this|Keep this energy' }, true)

    await click('Not for me')
    const f = await check('not for me moves on', { 'skipped in history': (s) => s.history.includes(e.hero + ' → Skipped'), 'ack': (s) => s.acks.at(-1) === 'Not for me Intent unchanged', 'intent unchanged': (s) => s.chips.map((chip) => chip.replace(/[*^]/g, '')).join('|') === 'Driven|Amapiano|High energy', 'new hero': (s) => s.hero !== e.hero })

    await click('Next recommendation')
    const g = await check('next moves on quietly', { 'new hero': (s) => s.hero !== f.hero, 'no new ack': (s) => s.acks.length === f.acks.length })
    let peek = g
    for (let i = 0; i < 3 && !peek.upNext; i++) { await click('Next recommendation'); peek = await state() }
    step++; report.check(`${step}. up next appears`, !!peek.upNext, peek.upNext ?? ''); 
    await shot('up-next')
    const promised = peek.upNext?.match(/^Up next: (.*) by /)?.[1]
    await click('Up next')
    await check('up next plays the song it named', { 'hero is the promised song': (s) => s.hero === promised })

    const before = await state()
    await wait(2300)
    const ticking = await check('the clock advances while playing', { 'time moved': (s) => s.time !== before.time })
    await click('Pause')
    const paused = await state()
    await wait(1500)
    await check('the clock holds while paused', { 'paused': (s) => s.playing === false, 'time held': (s) => s.time === paused.time })
    void ticking

    await click('Open listening sessions')
    const drawer = await check('drawer lists the sessions', { 'six sessions': (s) => s.drawer.length === 6, 'this one is active and first': (s) => s.drawer[0] === '>Move' || s.drawer[0].startsWith('>'), 'seeded ones present': (s) => s.drawer.includes('Gym Energy') }, true)

    await click('Gym Energy')
    await wait(450) // the drawer animates out
    await check('switching to another session', { 'title': (s) => s.title === 'Gym Energy', 'drawer closed': (s) => s.drawer.length === 0, 'hero': (s) => s.hero === 'Mnike', 'chips': (s) => s.chips.join('|') === 'Driven|Amapiano|High energy' }, true)
    const resumed = await ev(`document.body.textContent.includes('Picking up where you left off')`)
    if (!resumed) report.fail('no "Picking up where you left off" after switching')

    await click('Open listening sessions')
    await click(drawer.drawer[0].replace(/^>/, ''))
    await wait(450)
    await check('switching back keeps that session as it was', { 'title': (s) => s.title === before.title, 'hero': (s) => s.hero === before.hero, 'history kept': (s) => s.history.length === before.history.length })

    const replayable = await ev(`document.querySelector('main button[aria-label$="Played"]')?.getAttribute('aria-label')`)
    await ev(`document.querySelector('main button[aria-label$="Played"]').click()`); await wait(120)
    await check('a history song can be played again', { 'hero is that song': (s) => replayable.startsWith('Play ' + s.hero + ' by') })

    await click('New listening session')
    await check('a new session starts clean', { 'prompt shown': (s) => s.prompt, 'title': (s) => s.title === 'New session', 'empty draft': (s) => s.draft === '' })
    await click('Open listening sessions')
    await check('the new session is in the drawer', { 'seven sessions': (s) => s.drawer.length === 7, 'new one first and active': (s) => s.drawer[0] === '>New session' })
    await click('Close menu')

    const typedSave = await type('Surprise me')
    await check('typing into the new session works too', { 'typed': () => typedSave === 'Surprise me', 'one hero': (s) => s.heroes === 1, 'title': (s) => s.title === 'Discovery' }, true)

}

try {
  await walk(390, 844)
  await walk(320, 568)
  report.check('no console errors or warnings during the walkthrough', b.consoleErrors.length === 0, b.consoleErrors.slice(0, 3).join(' | '))
} catch (error) {
  report.fail(`script error: ${error.stack ?? error}`)
} finally {
  await b.close()
}
await report.finish(outDir)
