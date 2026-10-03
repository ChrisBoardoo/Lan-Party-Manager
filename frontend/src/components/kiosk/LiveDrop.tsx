import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { KioskMedia } from '../../types'
import { timeAgo } from '../../lib/kioskTime'
import { playDropShutter } from '../../lib/kioskSound'
import { WallMedia } from './LoveWall'

// The #LoveWall "drop": a post made while the display runs takes the whole
// screen for a few seconds. Accent slats fall over the frame and open on the
// photo, then the credit and the caption type in. Keyed by media id, so each
// drop starts from the top.

const SLATS = 7
const SLAT_STAGGER_MS = 45
// When the slats start opening on the photo — the shutter sound lands on it.
const OPEN_AT_MS = 1_250
// A slow or broken file must not stall the drop: reveal whatever's there.
const READY_FALLBACK_MS = 2_500
// The caption starts typing once the credit has risen.
const CAPTION_AT_MS = 2_600

function useTypewriter(text: string, startMs: number, stepMs = 32): string {
  // Code points, not UTF-16 units, so an emoji never shows half-typed.
  const chars = useMemo(() => Array.from(text), [text])
  const [n, setN] = useState(0)
  useEffect(() => {
    setN(0)
    if (!chars.length) return
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setN(chars.length)
      return
    }
    let tick: ReturnType<typeof setInterval> | undefined
    const start = setTimeout(() => {
      tick = setInterval(() => setN((c) => Math.min(c + 1, chars.length)), stepMs)
    }, startMs)
    return () => {
      clearTimeout(start)
      if (tick) clearInterval(tick)
    }
  }, [chars, startMs, stepMs])
  return chars.slice(0, n).join('')
}

export default function LiveDrop({ item, more, serverTime }: { item: KioskMedia; more: number; serverTime: string }) {
  const { t } = useTranslation()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const id = setTimeout(() => setReady(true), READY_FALLBACK_MS)
    return () => clearTimeout(id)
  }, [])
  useEffect(() => {
    if (!ready) return
    const id = setTimeout(playDropShutter, OPEN_AT_MS)
    return () => clearTimeout(id)
  }, [ready])

  const caption = useTypewriter(ready ? item.caption ?? '' : '', CAPTION_AT_MS)
  const ago = timeAgo(item.created_at, serverTime, t)
  const backdrop = item.file_type === 'video' ? item.thumbnail_url : item.url

  return (
    <div className="kiosk-flash fixed inset-0 z-30 bg-background overflow-hidden flex flex-col">
      {ready && backdrop && (
        <div className="lw-backdrop absolute inset-0 pointer-events-none" aria-hidden="true">
          <img src={backdrop} alt="" className="lw-backdrop-img w-full h-full object-cover" />
        </div>
      )}

      <div className="relative flex items-center justify-between px-[4vw] pt-[3vh] shrink-0">
        <div className="lw-in flex items-center gap-[0.8vw] font-mono-kiosk text-accent text-[1.4vw] tracking-widest">
          <span className="w-[0.9vw] h-[0.9vw] bg-accent kiosk-pulse" />
          {t('kiosk.dropLabel')}
        </div>
        {ready && more > 0 && (
          <div className="lw-rise font-mono-kiosk text-muted-foreground text-[1.2vw]" style={{ '--lw-delay': '1200ms' } as React.CSSProperties}>
            {t('kiosk.dropMore', { count: more })}
          </div>
        )}
      </div>

      <div className="relative flex-1 min-h-0 flex items-center justify-center px-[4vw] py-[2vh]">
        {/* overflow-hidden: the photo develops from a zoomed-in frame and must
            stay inside the slats' footprint while it settles. */}
        <div className="relative overflow-hidden shadow-[0_3vh_8vh_rgba(0,0,0,0.6)]">
          <div className={ready ? 'lw-drop-photo' : 'opacity-0'}>
            <WallMedia item={item} onReady={() => setReady(true)} className="block max-w-[80vw] max-h-[56vh] w-auto h-auto" />
          </div>
          {ready &&
            Array.from({ length: SLATS }).map((_, i) => (
              <div
                key={i}
                className="lw-slat absolute inset-y-0 bg-accent"
                style={{
                  left: `${(i * 100) / SLATS}%`,
                  // +1px so neighbouring slats never leave a hairline seam.
                  width: `calc(${100 / SLATS}% + 1px)`,
                  '--lw-delay': `${i * SLAT_STAGGER_MS}ms`,
                } as React.CSSProperties}
              />
            ))}
        </div>
      </div>

      {ready && (
        <div className="relative flex items-end gap-[1.6vw] px-[4vw] pb-[5vh] shrink-0">
          <div className="lw-rise shrink-0" style={{ '--lw-delay': '1100ms' } as React.CSSProperties}>
            {item.uploader_avatar_url ? (
              <img src={item.uploader_avatar_url} alt="" className="w-[5.5vw] h-[5.5vw] object-cover" />
            ) : (
              <div className="w-[5.5vw] h-[5.5vw] bg-muted flex items-center justify-center font-black text-[2.6vw]">
                {(item.uploader ?? '?').charAt(0).toUpperCase()}
              </div>
            )}
          </div>
          <div className="min-w-0">
            <div className="lw-rise flex items-baseline gap-[1.2vw]" style={{ '--lw-delay': '1250ms' } as React.CSSProperties}>
              <span className="text-[3.4vw] font-black tracking-tighter leading-none truncate">{item.uploader}</span>
              {ago && <span className="font-mono-kiosk text-muted-foreground text-[1.1vw] shrink-0">{ago}</span>}
            </div>
            {item.caption && (
              <div
                className="lw-rise font-mono text-[1.6vw] leading-snug mt-[1.5vh] max-w-[80vw] min-h-[1.4em]"
                style={{ '--lw-delay': '1400ms' } as React.CSSProperties}
              >
                {caption}
                <span className="lw-caret text-accent">▌</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
