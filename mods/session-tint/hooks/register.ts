import type { Hook, Register, RenderElement, ThemeColors } from 'claude-code'

type Api = Parameters<Hook<'session.start'>>[0]

import { makeColors } from './make-colors.js'
import { TOPICS as TOPIC_LIST } from './topics.js'

// One color per topic. The first prompt that names a topic picks it;
// /tint <topic> overrides; /tint off clears. The list lives in topics.js,
// which setup writes from the choices made in the setup wizard.
type Topic = {
  id: string
  label: string
  color: string // accent, six-digit hex
  hue: number // tint for the surfaces
  words: string[] // matched as whole words
  parent?: string // the broader topic this one is an area of
  hues?: number[] // the aurora's own hues; absent, neighbors of `hue`
  isMuted?: boolean // near-neutral surfaces
  dot?: string // the shape put in front of the chat's title
}

const TOPICS: Topic[] = TOPIC_LIST

// A chat with no topic yet: charcoal surfaces under a northern-lights aurora.
const DEFAULT: Topic = {
  id: 'default',
  label: 'No topic',
  color: '#3fa99b',
  hue: 215,
  words: [],
  hues: [165, 140, 265, 200],
  isMuted: true,
}

const hex = (h: number, s: number, l: number): string => {
  const a = (s / 100) * Math.min(l / 100, 1 - l / 100)
  const f = (n: number) => {
    const k = (n + h / 30) % 12
    const c = l / 100 - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))
    return Math.round(c * 255).toString(16).padStart(2, '0')
  }
  return `#${f(0)}${f(8)}${f(4)}`
}

const themeFor = (t: Topic): { colors: ThemeColors; unpainted?: string } => {
  const m = t.isMuted === true ? 0.4 : 1
  const { theme, problems } = makeColors({
    label: `Tint: ${t.label}`,
    id: `tint-${t.id}`,
    roles: { accent: t.color },
    dark: {
      gray: {
        anchors: {
          'surface-0': hex(t.hue, 28 * m, 8),
          'surface-1': hex(t.hue, 26 * m, 11),
          'surface-2': hex(t.hue, 24 * m, 14),
          'surface-3': hex(t.hue, 22 * m, 16),
          'text-primary': hex(t.hue, 30 * m, 93),
          'text-secondary': hex(t.hue, 18 * m, 80),
          'text-muted': hex(t.hue, 14 * m, 68),
        },
      },
    },
    light: {
      gray: {
        anchors: {
          'surface-0': hex(t.hue, 45 * m, 89),
          'surface-1': hex(t.hue, 50 * m, 93),
          'surface-2': hex(t.hue, 55 * m, 97),
          'text-primary': hex(t.hue, 35 * m, 12),
          'text-secondary': hex(t.hue, 25 * m, 26),
          'text-muted': hex(t.hue, 18 * m, 36),
        },
      },
    },
  })
  return { colors: theme, unpainted: problems.find(p => p.startsWith("Desktop won't paint")) }
}

const THEMES = new Map([...TOPICS, DEFAULT].map(t => [t.id, themeFor(t)]))

// The aurora: soft blobs of the topic's color drifting slowly behind the chat.
// Each blob rests where the markup puts it, so it looks finished with motion off.
// The chat's status changes the light: brighter and breathing while Claude works,
// an amber glow in the top right corner while the chat waits on the person.
const SCENE = 'aurora-'

type Status = 'idle' | 'working' | 'waiting'

const DRIFT = [71, 89, 97, 113]

// How strong the topic's light is in each status.
const LEVEL: Record<Status, number> = { idle: 0.78, working: 1, waiting: 0.78 }

// `from` is what the last drawing showed: a status to fade from, 'fresh' for a scene
// drawn for the first time (it fades up from the dark), or 'same' for no fade.
const auroraFor = (t: Topic, status: Status, from: Status | 'fresh' | 'same'): string => {
  const hues = t.hues ?? [t.hue, (t.hue + 34) % 360, (t.hue + 326) % 360, (t.hue + 62) % 360]
  const m = t.isMuted === true ? 0.4 : 1
  const light = hues.map((h, i) => `.c${i}{stop-color:${hex(h, 85, 68)}}`).join('')
  const dark = hues.map((h, i) => `.c${i}{stop-color:${hex(h, 80, 46)}}`).join('')
  const grads = hues
    .map(
      (_, i) =>
        `<radialGradient id="g${i}"><stop class="c${i}" offset="0" stop-opacity="1"/>` +
        `<stop class="c${i}" offset="0.55" stop-opacity="0.46"/><stop class="c${i}" offset="1" stop-opacity="0"/></radialGradient>`,
    )
    .join('')
  // Start each drift where the clock puts it, so a redraw does not jump the blobs.
  const now = Date.now() / 1000
  const drift = DRIFT.map((d, i) => `.b${i}{animation-name:d${i};animation-duration:${d}s;animation-delay:-${(now % (2 * d)).toFixed(1)}s}`).join('')
  // Amber, or a cool white-blue on the warm topics where amber would not show.
  const amber = t.hue <= 80 || t.hue >= 330 ? hex(192, 90, 68) : hex(40, 96, 56)

  // The topic's light: ease from the last level to this one, then breathe while working.
  const level = LEVEL[status]
  const fade = from === 'fresh' ? 3.6 : 2.8
  const start = from === 'fresh' ? 0 : from === 'same' ? level : LEVEL[from]
  const moves: string[] = []
  if (start !== level) moves.push(`shift ${fade}s ease-in-out 1 both`)
  if (status === 'working') moves.push(`breathe 6s ease-in-out ${start !== level ? fade : 0}s infinite alternate`)
  const lv = `.lv{opacity:${level}${moves.length > 0 ? `;animation:${moves.join(',')}` : ''}}`

  // The amber glow: ease in when the chat starts waiting, ease out when it stops.
  const wasWaiting = from === 'waiting'
  const isWaiting = status === 'waiting'
  const glow = isWaiting
    ? `.wait{opacity:0.8;animation:${wasWaiting ? '' : `glowin ${fade}s ease-in-out 1 both,`}pulse 4s ease-in-out ${wasWaiting ? 0 : fade}s infinite alternate}`
    : wasWaiting
      ? `.wait{opacity:0;animation:glowout ${fade}s ease-in-out 1 both}`
      : ''

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 1000" preserveAspectRatio="xMidYMid slice">` +
    `<style>` +
    `.bg{fill:${hex(t.hue, 45 * m, 89)}}${light}` +
    `@media (prefers-color-scheme: dark){.bg{fill:${hex(t.hue, 28 * m, 8)}}${dark}}` +
    `.b{transform-box:fill-box;transform-origin:center;animation-timing-function:ease-in-out;animation-iteration-count:infinite;animation-direction:alternate}` +
    drift +
    `@keyframes d0{from{transform:translate(0,0) scale(1)}to{transform:translate(260px,120px) scale(1.25)}}` +
    `@keyframes d1{from{transform:translate(0,0) scale(1.1)}to{transform:translate(-300px,160px) scale(0.9)}}` +
    `@keyframes d2{from{transform:translate(0,0) scale(1)}to{transform:translate(220px,-180px) scale(1.3)}}` +
    `@keyframes d3{from{transform:translate(0,0) scale(1.2)}to{transform:translate(-240px,-140px) scale(0.95)}}` +
    lv +
    `@keyframes shift{from{opacity:${start}}to{opacity:${level}}}` +
    `@keyframes breathe{from{opacity:1}to{opacity:0.86}}` +
    glow +
    `@keyframes glowin{from{opacity:0}to{opacity:0.8}}` +
    `@keyframes glowout{from{opacity:0.8}to{opacity:0}}` +
    `@keyframes pulse{from{opacity:0.8}to{opacity:0.55}}` +
    `</style>` +
    `<defs>${grads}<radialGradient id="ga"><stop offset="0" stop-color="${amber}" stop-opacity="0.95"/>` +
    `<stop offset="0.5" stop-color="${amber}" stop-opacity="0.4"/><stop offset="1" stop-color="${amber}" stop-opacity="0"/></radialGradient></defs>` +
    `<rect class="bg" width="1600" height="1000"/>` +
    `<g class="lv">` +
    `<ellipse class="b b0" cx="260" cy="170" rx="620" ry="430" fill="url(#g0)"/>` +
    `<ellipse class="b b1" cx="1380" cy="210" rx="640" ry="460" fill="url(#g1)"/>` +
    `<ellipse class="b b2" cx="330" cy="900" rx="600" ry="420" fill="url(#g2)"/>` +
    `<ellipse class="b b3" cx="1320" cy="880" rx="660" ry="440" fill="url(#g3)"/>` +
    `</g>` +
    (isWaiting || wasWaiting ? `<ellipse class="wait" cx="1470" cy="90" rx="560" ry="400" fill="url(#ga)"/>` : '') +
    `</svg>`
  )
}

const TOPIC_BY_ID = new Map([...TOPICS, DEFAULT].map(t => [t.id, t]))

// What this chat is doing now (one process per chat; a reload starts at idle),
// what it was doing before, and when that changed.
let status: Status = 'idle'
let before: Status = 'idle'
let changedAt = 0
// The scene drawn last, and when it was first drawn.
let drawn = ''
let freshAt = 0

function to($: Api, next: Status): void {
  if (status === next) return
  before = status
  status = next
  changedAt = Date.now()
  $.ui.invalidate('ui.render')
}

// A topic's words as whole-word tests.
const TESTS = new Map(TOPICS.map(t => [t.id, t.words.map(w => new RegExp(`(?:^|[^a-z0-9])${w.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![a-z0-9])`))]))

// The topic with the most words in the text. Where a broad topic wins and one of
// its own areas was named too, the area takes it.
const pick = (text: string): Topic | undefined => {
  const s = text.toLowerCase()
  const hits = new Map(TOPICS.map(t => [t.id, (TESTS.get(t.id) ?? []).filter(r => r.test(s)).length]))
  const most = (among: Topic[]): Topic | undefined => {
    let best: Topic | undefined
    let bestHits = 0
    for (const t of among) {
      const n = hits.get(t.id) ?? 0
      if (n > bestHits) {
        best = t
        bestHits = n
      }
    }
    return best
  }
  const best = most(TOPICS)
  if (best === undefined) return undefined
  const top = best.parent ?? best.id
  return most(TOPICS.filter(t => t.parent === top)) ?? best
}

const DOTS: Record<string, string> = Object.fromEntries(TOPICS.filter(t => t.dot !== undefined).map(t => [t.id, t.dot as string]))
const ALL_DOTS = Object.values(DOTS)

// The chat's current title: the last custom or AI title in the tail of its transcript.
async function currentTitle($: Api, transcript: string): Promise<string | undefined> {
  if (transcript === '') return undefined
  const { size } = await $.fs.stat(transcript)
  const offset = Math.max(0, size - 512 * 1024)
  const tail = await $.fs.read(transcript, { offset, length: size - offset })
  let title: string | undefined
  for (const m of tail.matchAll(/"(?:customTitle|aiTitle)":"((?:[^"\\]|\\.)*)"/g)) {
    try {
      title = JSON.parse(`"${m[1]}"`) as string
    } catch {
      // a line cut by the range; skip it
    }
  }
  return title
}

const keyFor = (sessionId: string) => `tint:${sessionId}`

// The topic this process has applied (reset on reload; the store is the truth).
let applied: string | undefined

async function apply($: Api, id: string): Promise<void> {
  const t = THEMES.get(id)
  if (t === undefined) return
  if (t.unpainted !== undefined) $.ui.toast(`session-tint: ${t.unpainted}`)
  const set = await $.theme.set({ colors: t.colors, backdrop: { scene: SCENE + id, glass: { blur: 24, opacity: 0.5 } } })
  if (!set.isDrawn) $.ui.toast(`session-tint: color not drawn: ${set.reason}`)
  if (id !== DEFAULT.id) applied = id
}

export const register: Register = on => {
  // Draw the aurora and keep its status current.
  on('ui.render', { component: 'Backdrop' }, ($, e, next) => {
    if (e.surface !== 'desktop' && e.surface !== 'mobile') return next(e)
    const name = e.props.scene
    const topic = name.startsWith(SCENE) ? TOPIC_BY_ID.get(name.slice(SCENE.length)) : undefined
    if (topic === undefined) return next(e)
    const { Svg } = $.ui.resolve(e)
    const now = Date.now()
    if (name !== drawn) {
      drawn = name
      freshAt = now
    }
    const from = now - freshAt < 3600 ? 'fresh' : now - changedAt < 2800 ? before : 'same'
    const alt = status === 'working' ? 'Bright light, Claude is working' : status === 'waiting' ? 'A glow in the corner, waiting on you' : 'Soft colored light drifting slowly'
    return h(Svg, { source: auroraFor(topic, status, from), alt, isInteractive: true }) as RenderElement
  })

  on('turn.start', ($, e, next) => {
    if (e.agentId === undefined) to($, 'working')
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined) to($, 'idle')
    return result
  })

  // A question to the person, or a permission prompt, is the chat waiting on them.
  on('tool.call', { tool: 'AskUserQuestion' }, async ($, e, next) => {
    to($, 'waiting')
    try {
      return await next(e)
    } finally {
      to($, 'working')
    }
  })

  on('tool.check', async ($, e, next) => {
    const verdict = await next(e)
    if (verdict.decision === 'ask') to($, 'waiting')
    return verdict
  })

  on('tool.run', ($, e, next) => {
    if (status === 'waiting') to($, 'working')
    return next(e)
  })

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'tint',
      description: `Color this session by topic: ${TOPICS.map(t => t.id).join(', ')}, auto, or off`,
    })
    const saved = await $.store.get(keyFor(await $.session.id()))
    if (typeof saved === 'string' && saved !== 'off') await apply($, saved)
    else if (saved === undefined) await apply($, DEFAULT.id)
    return next(e)
  })

  on('prompt.submit', async ($, e, next) => {
    if (e.command === undefined && e.isMeta !== true && applied === undefined) {
      const key = keyFor(await $.session.id())
      const saved = await $.store.get(key)
      if (saved === undefined) {
        const t = pick(e.text)
        if (t !== undefined) {
          await $.store.set(key, t.id)
          await apply($, t.id)
          $.ui.toast(`Tinted ${t.label}. /tint to change.`)
        }
      }
    }
    return next(e)
  })

  // Put the topic's dot at the front of the chat's title, so the sidebar shows it.
  on('classic.UserPromptSubmit', async ($, e, next) => {
    const result = await next(e)
    if (result.block !== undefined) return result
    const topic = await $.store.get(keyFor(await $.session.id()))
    const dot = typeof topic === 'string' ? DOTS[topic] : undefined
    if (dot === undefined) return result
    const title = await currentTitle($, e.transcript_path)
    if (title === undefined || title.startsWith(dot)) return result
    const bare = ALL_DOTS.reduce((t, d) => (t.startsWith(d) ? t.slice(d.length).trimStart() : t), title)
    return { ...result, sessionTitle: `${dot} ${bare}` }
  })

  on('command.run', { command: 'tint' }, async ($, e) => {
    const arg = e.args.trim().toLowerCase()
    const key = keyFor(await $.session.id())
    const list = TOPICS.map(t => `${t.id} (${t.label})`).join(', ')

    if (arg === '') {
      const saved = await $.store.get(key)
      const now = TOPICS.find(t => t.id === saved)?.label ?? 'none'
      return { text: `Tint: ${now}. Use /tint <topic>, /tint auto, or /tint off. Topics: ${list}`, isTextDisplayOnly: true }
    }
    if (arg === 'off') {
      await $.store.set(key, 'off')
      applied = 'off'
      await $.theme.clear()
      return { text: 'Tint off for this session.', isTextDisplayOnly: true }
    }
    if (arg === 'auto') {
      await $.store.delete(key)
      applied = undefined
      await apply($, DEFAULT.id)
      return { text: 'Tint will pick from your next prompt.', isTextDisplayOnly: true }
    }
    const t = TOPICS.find(x => x.id === arg || x.label.toLowerCase() === arg)
    if (t === undefined) return { text: `Unknown topic "${arg}". Topics: ${list}`, isTextDisplayOnly: true }
    await $.store.set(key, t.id)
    await apply($, t.id)
    return { text: `Tinted ${t.label}.`, isTextDisplayOnly: true }
  })
}
