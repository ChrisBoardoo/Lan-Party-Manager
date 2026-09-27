// Self-contained Web Audio chimes for the kiosk — no audio files, no external
// dependency. Best-effort: some browsers block autoplay audio until the page
// has had a user gesture, in which case these are silently no-ops. Sound is
// always optional on the big screen, never load-bearing.

let ctx: AudioContext | null = null

function getCtx(): AudioContext | null {
  if (typeof window === 'undefined') return null
  try {
    if (!ctx) {
      const Ctor = window.AudioContext || (window as any).webkitAudioContext
      if (!Ctor) return null
      ctx = new Ctor()
    }
    if (ctx.state === 'suspended') ctx.resume().catch(() => {})
    return ctx
  } catch {
    return null
  }
}

function tone(ac: AudioContext, freq: number, start: number, dur: number, gain = 0.15) {
  const osc = ac.createOscillator()
  const g = ac.createGain()
  osc.type = 'triangle'
  osc.frequency.value = freq
  g.gain.setValueAtTime(0, start)
  g.gain.linearRampToValueAtTime(gain, start + 0.02)
  g.gain.exponentialRampToValueAtTime(0.0001, start + dur)
  osc.connect(g)
  g.connect(ac.destination)
  osc.start(start)
  osc.stop(start + dur)
}

/** A short two-note attention ping for a new announcement. */
export function playAnnouncementChime() {
  const ac = getCtx()
  if (!ac) return
  const t = ac.currentTime
  tone(ac, 880, t, 0.18)
  tone(ac, 1174.7, t + 0.14, 0.28)
}

function noiseBurst(ac: AudioContext, start: number, dur: number, gain: number) {
  const buf = ac.createBuffer(1, Math.ceil(ac.sampleRate * dur), ac.sampleRate)
  const data = buf.getChannelData(0)
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1
  const src = ac.createBufferSource()
  src.buffer = buf
  const band = ac.createBiquadFilter()
  band.type = 'bandpass'
  band.frequency.value = 2400
  band.Q.value = 0.8
  const g = ac.createGain()
  g.gain.setValueAtTime(gain, start)
  g.gain.exponentialRampToValueAtTime(0.0001, start + dur)
  src.connect(band)
  band.connect(g)
  g.connect(ac.destination)
  src.start(start)
  src.stop(start + dur)
}

/** A camera shutter (two filtered clicks) and a soft rising pair, for a new
 *  #LoveWall post opening on screen. */
export function playDropShutter() {
  const ac = getCtx()
  if (!ac) return
  const t = ac.currentTime
  noiseBurst(ac, t, 0.05, 0.25)
  noiseBurst(ac, t + 0.09, 0.07, 0.18)
  tone(ac, 659.25, t + 0.25, 0.35, 0.08)
  tone(ac, 987.77, t + 0.36, 0.5, 0.08)
}

/** A rising triad fanfare for a tournament champion. */
export function playChampionFanfare() {
  const ac = getCtx()
  if (!ac) return
  const t = ac.currentTime
  ;[523.25, 659.25, 783.99, 1046.5].forEach((f, i) => tone(ac, f, t + i * 0.13, 0.5, 0.18))
}
