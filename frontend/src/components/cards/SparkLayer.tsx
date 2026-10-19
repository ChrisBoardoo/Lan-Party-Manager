import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'

// The booster opening's particles: bursts of glowing sparks (the tear, each
// flip, an Epic) and slow dust drifting up behind everything. One full-screen
// canvas, additive blending, a pre-rendered glow sprite per colour so a burst
// of 200 stays cheap. No library. Renders nothing under prefers-reduced-motion.

export interface SparkLayerHandle {
  burst: (x: number, y: number, opts?: BurstOptions) => void
}

interface BurstOptions {
  count?: number
  colors?: string[]
  speed?: number // px per frame at dpr 1
  size?: number
  life?: number // frames
  gravity?: number
}

interface Spark {
  x: number
  y: number
  vx: number
  vy: number
  life: number
  max: number
  size: number
  sprite: HTMLCanvasElement
  gravity: number
}

function reduced() {
  return !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

const DUST = 46

const SparkLayer = forwardRef<SparkLayerHandle, { dustColor?: string }>(function SparkLayer({ dustColor = '#FF3D00' }, ref) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const sparks = useRef<Spark[]>([])
  const sprites = useRef(new Map<string, HTMLCanvasElement>())

  const sprite = (color: string) => {
    let s = sprites.current.get(color)
    if (!s) {
      s = document.createElement('canvas')
      s.width = s.height = 64
      const g = s.getContext('2d')!
      const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32)
      grad.addColorStop(0, '#ffffff')
      grad.addColorStop(0.18, color)
      grad.addColorStop(1, 'rgba(0,0,0,0)')
      g.fillStyle = grad
      g.fillRect(0, 0, 64, 64)
      sprites.current.set(color, s)
    }
    return s
  }

  useImperativeHandle(ref, () => ({
    burst(x, y, opts = {}) {
      if (reduced()) return
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const { count = 60, colors = ['#FFFFFF', '#FF3D00', '#FFB800'], speed = 9, size = 14, life = 70, gravity = 0.12 } = opts
      for (let i = 0; i < count; i++) {
        const angle = Math.random() * Math.PI * 2
        const v = (0.25 + Math.random() * 0.75) * speed * dpr
        const max = life * (0.5 + Math.random() * 0.7)
        sparks.current.push({
          x: x * dpr,
          y: y * dpr,
          vx: Math.cos(angle) * v,
          vy: Math.sin(angle) * v - speed * 0.25 * dpr,
          life: max,
          max,
          size: size * (0.4 + Math.random()) * dpr,
          sprite: sprite(colors[i % colors.length]),
          gravity: gravity * dpr,
        })
      }
    },
  }))

  useEffect(() => {
    if (reduced()) return
    const canvas = canvasRef.current
    const g = canvas?.getContext('2d')
    if (!canvas || !g) return
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const resize = () => {
      canvas.width = canvas.clientWidth * dpr
      canvas.height = canvas.clientHeight * dpr
    }
    resize()
    window.addEventListener('resize', resize)

    const dustSprite = sprite(dustColor)
    const dust = Array.from({ length: DUST }, () => ({
      x: Math.random(),
      y: Math.random(),
      v: 0.0004 + Math.random() * 0.0012,
      s: (2 + Math.random() * 5) * dpr,
      a: 0.15 + Math.random() * 0.35,
      w: Math.random() * Math.PI * 2,
    }))

    let raf = 0
    const frame = () => {
      g.clearRect(0, 0, canvas.width, canvas.height)
      g.globalCompositeOperation = 'lighter'
      for (const d of dust) {
        d.y -= d.v
        d.w += 0.01
        if (d.y < -0.05) {
          d.y = 1.05
          d.x = Math.random()
        }
        g.globalAlpha = d.a
        const px = (d.x + Math.sin(d.w) * 0.01) * canvas.width
        g.drawImage(dustSprite, px - d.s, d.y * canvas.height - d.s, d.s * 2, d.s * 2)
      }
      const list = sparks.current
      for (let i = list.length - 1; i >= 0; i--) {
        const p = list[i]
        p.vx *= 0.97
        p.vy = p.vy * 0.97 + p.gravity
        p.x += p.vx
        p.y += p.vy
        p.life -= 1
        if (p.life <= 0) {
          list.splice(i, 1)
          continue
        }
        const k = p.life / p.max
        g.globalAlpha = Math.min(1, k * 1.4)
        const s = p.size * (0.4 + k * 0.6)
        g.drawImage(p.sprite, p.x - s, p.y - s, s * 2, s * 2)
      }
      g.globalAlpha = 1
      raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
    }
  }, [dustColor])

  return <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none" aria-hidden="true" />
})

export default SparkLayer
