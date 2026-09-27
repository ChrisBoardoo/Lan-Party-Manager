import { useEffect, useRef } from 'react'

// A tiny self-contained canvas confetti burst — no library (keeps the bundle
// lean, per the design principles). Respects prefers-reduced-motion by rendering
// nothing. Runs for a few seconds then stops on its own.

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  rot: number
  vr: number
  size: number
  color: string
}

const COLORS = ['#FF3D00', '#FAFAFA', '#FFD400', '#00E5FF', '#7C4DFF']

export default function Confetti({ run }: { run: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!run) return
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduced) return
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let raf = 0
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const resize = () => {
      canvas.width = canvas.clientWidth * dpr
      canvas.height = canvas.clientHeight * dpr
    }
    resize()
    window.addEventListener('resize', resize)

    const W = () => canvas.width
    const H = () => canvas.height
    const particles: Particle[] = []
    const spawn = (n: number) => {
      for (let i = 0; i < n; i++) {
        particles.push({
          x: Math.random() * W(),
          y: -20 * dpr,
          vx: (Math.random() - 0.5) * 6 * dpr,
          vy: (Math.random() * 3 + 2) * dpr,
          rot: Math.random() * Math.PI,
          vr: (Math.random() - 0.5) * 0.3,
          size: (Math.random() * 8 + 5) * dpr,
          color: COLORS[Math.floor(Math.random() * COLORS.length)],
        })
      }
    }
    spawn(220)
    const started = performance.now()

    const frame = (now: number) => {
      ctx.clearRect(0, 0, W(), H())
      // Keep a light drizzle going for the first couple of seconds.
      if (now - started < 2200 && particles.length < 420) spawn(6)
      for (const p of particles) {
        p.x += p.vx
        p.y += p.vy
        p.vy += 0.05 * dpr
        p.rot += p.vr
        ctx.save()
        ctx.translate(p.x, p.y)
        ctx.rotate(p.rot)
        ctx.fillStyle = p.color
        ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.5)
        ctx.restore()
      }
      // Drop particles that have fallen off-screen.
      for (let i = particles.length - 1; i >= 0; i--) {
        if (particles[i].y > H() + 40 * dpr) particles.splice(i, 1)
      }
      if (now - started < 6000 || particles.length > 0) {
        raf = requestAnimationFrame(frame)
      }
    }
    raf = requestAnimationFrame(frame)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
    }
  }, [run])

  if (!run) return null
  return <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none" />
}
