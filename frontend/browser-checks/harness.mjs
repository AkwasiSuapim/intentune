// Shared harness for the browser checks: serves the production build (and,
// when asked, the approved design export), starts headless Chrome, and drives
// one page over the Chrome DevTools Protocol. Needs Node 22+ (global
// WebSocket) and an installed Chrome, Chromium or Edge.
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { createServer } from 'node:http'
import { tmpdir } from 'node:os'
import { extname, join, normalize } from 'node:path'
import { fileURLToPath } from 'node:url'
import { inflateSync } from 'node:zlib'

export const FRONTEND = fileURLToPath(new URL('..', import.meta.url))
export const DIST = join(FRONTEND, 'dist')
export const DESIGN_EXPORT = join(FRONTEND, '..', 'docs', 'frontend', 'design', 'approved')

/** Where a check writes its screenshots and results. Ignored by git. */
export const outputDir = (name) => join(FRONTEND, 'browser-checks', 'output', name)

/** Base URLs of the served app and design export, set by `launch`. */
export let APP = ''
export let DESIGN = ''

const BROWSERS = {
  win32: [
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  ],
  darwin: [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  ],
  linux: ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser'],
}

function findBrowser() {
  const candidates = [process.env.CHROME_PATH, ...(BROWSERS[process.platform] ?? [])].filter(Boolean)
  const found = candidates.find((path) => existsSync(path))
  if (!found) throw new Error('No Chrome, Chromium or Edge found. Set CHROME_PATH to the browser executable.')
  return found
}

const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png' }

function serve(root, virtual) {
  const server = createServer(async (req, res) => {
    let path = decodeURIComponent(new URL(req.url, 'http://x').pathname)
    if (path.endsWith('/')) path += 'index.html'
    let body
    try {
      const file = normalize(join(root, path))
      if (!file.startsWith(normalize(root))) throw new Error('outside root')
      body = (virtual && (await virtual(path))) ?? (await readFile(file))
    } catch {
      res.writeHead(404).end()
      return
    }
    const type = typeof body === 'string' ? 'text/html' : (TYPES[extname(path)] ?? 'application/octet-stream')
    res.writeHead(200, { 'content-type': type }).end(body)
  })
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)))
}

/** Renders the design's Main component in one scene and size: /scene-<name>[-<w>x<h>].html */
async function designScene(path) {
  const match = /^\/scene-([a-z]+)(?:-(\d+)x(\d+))?\.html$/.exec(path)
  if (!match) return null
  const [, scene, width = '390', height = '844'] = match
  const template = await readFile(join(DESIGN_EXPORT, 'S1-NewSession.dc.html'), 'utf8')
  return template
    .replace('scene="new"', `scene="${scene}" fw="${width}" fh="${height}"`)
    .replace('width: 390px; height: 844px', `width: ${width}px; height: ${height}px`)
}

async function waitForFile(path, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      return await readFile(path, 'utf8')
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
  }
  throw new Error(`Browser did not start: ${path} never appeared`)
}

export async function launch({ outDir, design = false }) {
  if (!existsSync(join(DIST, 'index.html'))) throw new Error('No production build found. Run `npm run build` first.')
  await mkdir(outDir, { recursive: true })

  const servers = [await serve(DIST)]
  APP = `http://127.0.0.1:${servers[0].address().port}/`
  if (design) {
    servers.push(await serve(DESIGN_EXPORT, designScene))
    DESIGN = `http://127.0.0.1:${servers[1].address().port}/`
  }

  // Port 0 lets the browser pick a free port; it reports it in DevToolsActivePort.
  const profile = await mkdtemp(join(tmpdir(), 'intentune-checks-'))
  const browser = spawn(findBrowser(), ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check', '--hide-scrollbars', 'about:blank'], { stdio: 'ignore' })
  const [port, path] = (await waitForFile(join(profile, 'DevToolsActivePort'), 15000)).split(/\r?\n/)

  const ws = new WebSocket(`ws://127.0.0.1:${port}${path}`)
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
  let id = 0
  const pending = new Map()
  const waiters = []
  const consoleErrors = []
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data)
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id)
      pending.delete(message.id)
      if (message.error) reject(new Error(message.error.message))
      else resolve(message.result)
    } else if (message.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(message.params.type)) {
      consoleErrors.push(message.params.args.map((arg) => arg.value ?? arg.description).join(' ').slice(0, 300))
    } else if (message.method === 'Runtime.exceptionThrown') {
      const details = message.params.exceptionDetails
      consoleErrors.push('EXCEPTION ' + (details.exception?.description ?? details.text).slice(0, 300))
    } else if (message.method) {
      for (const waiter of [...waiters]) {
        if (waiter.method === message.method) {
          waiters.splice(waiters.indexOf(waiter), 1)
          waiter.resolve(message.params)
        }
      }
    }
  }
  const raw = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    pending.set(++id, { resolve, reject })
    ws.send(JSON.stringify({ id, method, params, sessionId }))
  })
  const { targetId } = await raw('Target.createTarget', { url: 'about:blank' })
  const { sessionId } = await raw('Target.attachToTarget', { targetId, flatten: true })
  const send = (method, params) => raw(method, params, sessionId)
  await send('Page.enable')
  await send('Runtime.enable')

  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
  const ev = async (expression) => {
    const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description ?? result.exceptionDetails.text)
    return result.result.value
  }
  const size = (width, height, { mobile = width < 700, scale = 2 } = {}) =>
    send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: scale, mobile })

  /**
   * Loads a URL at a size, waits for fonts, and installs small lookup helpers.
   * With `webFonts: true` it waits (up to 10s) until the web fonts have really
   * loaded, and returns whether they did. `document.fonts.ready` alone can
   * resolve before the deferred font stylesheet has even applied. Each weight is
   * a separate face, so it also waits for any face of those families still loading.
   */
  const open = async (url, width, height, options = {}) => {
    await size(width, height, options)
    const loaded = new Promise((resolve) => waiters.push({ method: 'Page.loadEventFired', resolve }))
    await send('Page.navigate', { url })
    await loaded
    let webFonts = null
    if (options.webFonts) {
      webFonts = await ev(`new Promise((resolve) => {
        const families = ['Bricolage Grotesque', 'Instrument Sans']
        const ready = () => {
          const faces = [...document.fonts].filter((face) => families.includes(face.family.replace(/"/g, '')))
          return families.every((family) => faces.some((face) => face.family.replace(/"/g, '') === family && face.status === 'loaded')) && !faces.some((face) => face.status === 'loading')
        }
        const started = Date.now()
        const poll = () => (ready() ? resolve(true) : Date.now() - started > 10000 ? resolve(false) : setTimeout(poll, 100))
        poll()
      })`)
    }
    await ev(`Promise.race([document.fonts.ready, new Promise((r) => setTimeout(r, 4000))]).then(() => new Promise((r) => setTimeout(r, ${options.settle ?? 350})))`)
    await ev(`(() => {
      const name = (b) => (b.getAttribute('aria-label') || b.textContent || '').replace(/\\s+/g, ' ').trim()
      const visible = () => [...document.querySelectorAll('button')].filter((b) => b.getClientRects().length)
      window.__name = name
      window.__btn = (text) => visible().find((b) => name(b) === text) || visible().find((b) => name(b).startsWith(text))
    })()`)
    return { webFonts }
  }
  const click = async (text, pause = 120) => {
    const ok = await ev(`(() => { const b = window.__btn(${JSON.stringify(text)}); if (!b) return false; b.click(); return true })()`)
    await wait(pause)
    return ok
  }
  /** Types into the composer and presses Enter, as a keyboard would. */
  const type = async (text) => {
    await ev(`document.querySelector('input').focus()`)
    await send('Input.insertText', { text })
    await wait(60)
    const typed = await ev(`document.querySelector('input').value`)
    await key('Enter', 'Enter', 13)
    await wait(70)
    return typed
  }
  /** Presses a key. Enter and Space carry text, so they activate buttons. */
  const key = async (name, code = name, keyCode = 0) => {
    const text = { Enter: '\r', ' ': ' ' }[name]
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: name, code, windowsVirtualKeyCode: keyCode, ...(text ? { text } : {}) })
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: name, code, windowsVirtualKeyCode: keyCode })
    await wait(80)
  }
  const reducedMotion = (on) => send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: on ? 'reduce' : 'no-preference' }] })
  const png = async (clip) => Buffer.from((await send('Page.captureScreenshot', { format: 'png', ...(clip ? { clip: { ...clip, scale: 1 } } : {}) })).data, 'base64')
  const shot = async (name, clip) => writeFile(join(outDir, `${name}.png`), await png(clip))

  const close = async () => {
    try { ws.close() } catch { /* already closed */ }
    browser.kill()
    await new Promise((resolve) => (browser.exitCode !== null ? resolve() : browser.once('exit', resolve)))
    for (const server of servers) server.close()
    await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }).catch(() => {})
  }

  return { send, ev, wait, size, open, click, type, key, reducedMotion, png, shot, close, consoleErrors }
}

/** Collects pass/fail lines for a check script and sets the exit code. */
export function createReport(title) {
  const lines = [`# ${title}`]
  const failures = []
  return {
    section: (name) => lines.push(`\n## ${name}`),
    note: (text) => lines.push(`     ${text}`),
    check(name, ok, detail = '') {
      lines.push(`${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? `  — ${detail}` : ''}`)
      if (!ok) failures.push(name + (detail ? ` — ${detail}` : ''))
    },
    fail: (text) => failures.push(text),
    async finish(outDir) {
      const text = `${lines.join('\n')}\n\n${failures.length ? `FAILED (${failures.length})\n${failures.join('\n')}` : 'ALL CHECKS PASSED'}\n`
      await writeFile(join(outDir, 'results.txt'), text)
      console.log(text)
      process.exitCode = failures.length ? 1 : 0
    },
  }
}

/** Decodes an 8-bit RGB or RGBA PNG into { width, height, channels, data }. */
export function decodePng(buffer) {
  let offset = 8
  let width = 0
  let height = 0
  let colorType = 6
  const chunks = []
  while (offset < buffer.length) {
    const length = buffer.readUInt32BE(offset)
    const type = buffer.toString('ascii', offset + 4, offset + 8)
    const body = buffer.subarray(offset + 8, offset + 8 + length)
    if (type === 'IHDR') {
      width = body.readUInt32BE(0)
      height = body.readUInt32BE(4)
      colorType = body[9]
    }
    if (type === 'IDAT') chunks.push(body)
    offset += 12 + length
  }
  const channels = colorType === 6 ? 4 : 3
  const raw = inflateSync(Buffer.concat(chunks))
  const stride = width * channels
  const data = Buffer.alloc(stride * height)
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)]
    for (let x = 0; x < stride; x++) {
      const value = raw[y * (stride + 1) + 1 + x]
      const left = x >= channels ? data[y * stride + x - channels] : 0
      const up = y > 0 ? data[(y - 1) * stride + x] : 0
      const upLeft = y > 0 && x >= channels ? data[(y - 1) * stride + x - channels] : 0
      let predicted = 0
      if (filter === 1) predicted = left
      else if (filter === 2) predicted = up
      else if (filter === 3) predicted = (left + up) >> 1
      else if (filter === 4) {
        const p = left + up - upLeft
        const a = Math.abs(p - left)
        const b = Math.abs(p - up)
        const c = Math.abs(p - upLeft)
        predicted = a <= b && a <= c ? left : b <= c ? up : upLeft
      }
      data[y * stride + x] = (value + predicted) & 255
    }
  }
  return { width, height, channels, data }
}

const linear = (value) => {
  const c = value / 255
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}
const luminance = ([r, g, b]) => 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)

/** WCAG contrast ratio between two RGB colours. */
export function contrast(a, b) {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (high + 0.05) / (low + 0.05)
}
