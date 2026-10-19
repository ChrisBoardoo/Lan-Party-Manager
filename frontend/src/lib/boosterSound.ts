// Booster opening sounds, synthesised with Web Audio like kioskSound.ts — no
// audio files, nothing to download. Every sound follows a click (the browser
// allows audio after a user gesture). Muting is remembered per viewer.

const MUTE_KEY = 'lpm.cards.muted'

let ctx: AudioContext | null = null
let master: GainNode | null = null

export function isMuted(): boolean {
  try {
    return localStorage.getItem(MUTE_KEY) === '1'
  } catch {
    return false
  }
}

export function setMuted(muted: boolean) {
  try {
    localStorage.setItem(MUTE_KEY, muted ? '1' : '0')
  } catch {
    // Private mode: the toggle still works for this opening.
  }
  if (master && ctx) master.gain.setTargetAtTime(muted ? 0 : 0.7, ctx.currentTime, 0.02)
}

function audio(): { ac: AudioContext; out: GainNode } | null {
  if (typeof window === 'undefined' || isMuted()) return null
  try {
    if (!ctx) {
      const Ctor = window.AudioContext || (window as any).webkitAudioContext
      if (!Ctor) return null
      ctx = new Ctor()
      master = ctx.createGain()
      master.gain.value = 0.7
      master.connect(ctx.destination)
    }
    if (ctx.state === 'suspended') ctx.resume().catch(() => {})
    return { ac: ctx, out: master! }
  } catch {
    return null
  }
}

function osc(
  ac: AudioContext, out: AudioNode, type: OscillatorType, freq: number, start: number, dur: number,
  gain: number, endFreq?: number, attack = 0.01,
) {
  const o = ac.createOscillator()
  const g = ac.createGain()
  o.type = type
  o.frequency.setValueAtTime(freq, start)
  if (endFreq) o.frequency.exponentialRampToValueAtTime(endFreq, start + dur)
  g.gain.setValueAtTime(0.0001, start)
  g.gain.linearRampToValueAtTime(gain, start + attack)
  g.gain.exponentialRampToValueAtTime(0.0001, start + dur)
  o.connect(g)
  g.connect(out)
  o.start(start)
  o.stop(start + dur + 0.05)
}

function noise(
  ac: AudioContext, out: AudioNode, start: number, dur: number, gain: number,
  filter: BiquadFilterType, freq: number, endFreq?: number, attack = 0.005,
) {
  const buf = ac.createBuffer(1, Math.ceil(ac.sampleRate * dur), ac.sampleRate)
  const data = buf.getChannelData(0)
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1
  const src = ac.createBufferSource()
  src.buffer = buf
  const f = ac.createBiquadFilter()
  f.type = filter
  f.frequency.setValueAtTime(freq, start)
  if (endFreq) f.frequency.exponentialRampToValueAtTime(endFreq, start + dur)
  f.Q.value = 0.9
  const g = ac.createGain()
  g.gain.setValueAtTime(0.0001, start)
  g.gain.linearRampToValueAtTime(gain, start + attack)
  g.gain.exponentialRampToValueAtTime(0.0001, start + dur)
  src.connect(f)
  f.connect(g)
  g.connect(out)
  src.start(start)
  src.stop(start + dur)
}

/** The pack charging: a rising sweep under a swelling hiss. */
export function playCharge(ms: number) {
  const a = audio()
  if (!a) return
  const t = a.ac.currentTime
  const d = ms / 1000
  noise(a.ac, a.out, t, d, 0.18, 'bandpass', 300, 3200, d * 0.9)
  osc(a.ac, a.out, 'sawtooth', 70, t, d, 0.05, 280, d * 0.9)
  osc(a.ac, a.out, 'sine', 220, t, d, 0.07, 880, d * 0.9)
}

/** The tear: a crisp rip, a sub thump and a glassy ping. */
export function playTear() {
  const a = audio()
  if (!a) return
  const t = a.ac.currentTime
  noise(a.ac, a.out, t, 0.28, 0.5, 'highpass', 1800, 5200)
  noise(a.ac, a.out, t + 0.04, 0.18, 0.3, 'bandpass', 900, 300)
  osc(a.ac, a.out, 'sine', 120, t, 0.45, 0.55, 38)
  osc(a.ac, a.out, 'triangle', 1568, t + 0.05, 0.9, 0.12)
  osc(a.ac, a.out, 'triangle', 2349, t + 0.09, 0.8, 0.06)
}

/** A card flying into place. */
export function playDeal(i: number) {
  const a = audio()
  if (!a) return
  const t = a.ac.currentTime
  noise(a.ac, a.out, t, 0.16, 0.12, 'bandpass', 1200 + i * 120, 4000)
}

/** A card turning over, and the soft bell of a common card. */
export function playFlip() {
  const a = audio()
  if (!a) return
  const t = a.ac.currentTime
  noise(a.ac, a.out, t, 0.12, 0.16, 'bandpass', 2600, 900)
  osc(a.ac, a.out, 'triangle', 1318.5, t + 0.28, 0.5, 0.09)
  osc(a.ac, a.out, 'triangle', 1975.5, t + 0.36, 0.6, 0.06)
}

/** The last card charging up: a low drone climbing, a heartbeat under it. */
export function playAnticipation(ms: number) {
  const a = audio()
  if (!a) return
  const t = a.ac.currentTime
  const d = ms / 1000
  osc(a.ac, a.out, 'sawtooth', 55, t, d, 0.06, 165, d * 0.8)
  osc(a.ac, a.out, 'sine', 330, t, d, 0.06, 990, d * 0.9)
  for (let k = 0; k < 4; k++) {
    const beat = t + k * (d / 4)
    osc(a.ac, a.out, 'sine', 70, beat, 0.18, 0.35 + k * 0.08, 45)
  }
  noise(a.ac, a.out, t, d, 0.1, 'bandpass', 500, 6000, d * 0.95)
}

/** An Epic: an impact, a big major chord opening up, a shimmering arpeggio. */
export function playEpic() {
  const a = audio()
  if (!a) return
  const t = a.ac.currentTime
  noise(a.ac, a.out, t, 0.6, 0.45, 'lowpass', 6000, 200)
  osc(a.ac, a.out, 'sine', 90, t, 1.1, 0.6, 30)
  const chord = [261.63, 329.63, 392, 523.25, 659.25]
  const f = a.ac.createBiquadFilter()
  f.type = 'lowpass'
  f.frequency.setValueAtTime(400, t)
  f.frequency.exponentialRampToValueAtTime(5000, t + 0.8)
  f.connect(a.out)
  for (const hz of chord) {
    osc(a.ac, f, 'sawtooth', hz, t + 0.05, 2.6, 0.045, undefined, 0.25)
    osc(a.ac, f, 'sawtooth', hz * 1.005, t + 0.05, 2.6, 0.03, undefined, 0.25)
  }
  const arp = [1046.5, 1318.5, 1568, 2093, 2637, 3136]
  arp.forEach((hz, i) => {
    osc(a.ac, a.out, 'sine', hz, t + 0.35 + i * 0.08, 0.9, 0.07)
    osc(a.ac, a.out, 'sine', hz, t + 0.95 + i * 0.08, 0.7, 0.03) // echo
  })
}

/** A common last card: a brighter bell than a plain flip. */
export function playRevealCommon() {
  const a = audio()
  if (!a) return
  const t = a.ac.currentTime
  osc(a.ac, a.out, 'sine', 70, t, 0.4, 0.3, 40)
  ;[783.99, 1046.5, 1318.5].forEach((hz, i) => osc(a.ac, a.out, 'triangle', hz, t + 0.05 + i * 0.07, 0.8, 0.08))
}
