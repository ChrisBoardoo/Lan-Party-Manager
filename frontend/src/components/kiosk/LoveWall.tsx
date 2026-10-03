import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import QRCode from 'react-qr-code'
import type { KioskMedia } from '../../types'
import { timeAgo } from '../../lib/kioskTime'

// #LoveWall — the kiosk's photo scene. The newest post takes the hero tile, the
// crowd's favourite (most reactions) is pinned beside it, and the other tiles
// keep swapping through the rest so every post gets its moment. Each tile
// arrives with the same reveal: an accent curtain sweeps across, and the photo
// "develops" underneath (see the .lw-* classes in index.css).

/** Emojis to float over a wall item — the reactions it got since the last poll. */
export interface ReactionBurst {
  key: number
  mediaId: number
  emojis: string[]
  until: number
}

// A small tile swaps to another item this often.
const CYCLE_MS = 4_200
// Delay between tiles on the scene's opening reveal.
const INTRO_STAGGER_MS = 180
// Tiles mounted this soon after the scene opens are part of the intro.
const INTRO_WINDOW_MS = 1_500
// Inline videos decode continuously — cap them so a modest projector PC keeps up.
const MAX_VIDEOS = 2
// A slow or unplayable file must not hold its tile's reveal back forever.
const READY_FALLBACK_MS = 3_000

// Grid layout by number of small tiles beside the hero ("h").
const LAYOUTS: Record<number, { areas: string; cols: string; rows: string }> = {
  0: { areas: '"h"', cols: '1fr', rows: '1fr' },
  1: { areas: '"h a"', cols: '1.6fr 1fr', rows: '1fr' },
  2: { areas: '"h a" "h b"', cols: '1.6fr 1fr', rows: '1fr 1fr' },
  3: { areas: '"h a b" "h c c"', cols: '1.8fr 1fr 1fr', rows: '1fr 1fr' },
  4: { areas: '"h a b" "h c d"', cols: '1.8fr 1fr 1fr', rows: '1fr 1fr' },
}
const SMALL_AREAS = ['a', 'b', 'c', 'd']

interface Rotation {
  pool: KioskMedia[]
  fixed: KioskMedia[]
  count: number
  prefer: number[]
}

// The next pool item for a free slot: a just-reacted one first (so its emojis
// have a tile to float over), else round-robin from the cursor.
function nextItem(r: Rotation, exclude: number[], showing: number[], cursor: { current: number }): KioskMedia | null {
  const videos = [...r.fixed, ...r.pool.filter((m) => showing.includes(m.id))]
    .filter((m) => m.file_type === 'video').length
  const ok = (m: KioskMedia) => !exclude.includes(m.id) && (m.file_type !== 'video' || videos < MAX_VIDEOS)
  for (const id of r.prefer) {
    const m = r.pool.find((p) => p.id === id)
    if (m && ok(m)) return m
  }
  for (let i = 0; i < r.pool.length; i++) {
    const m = r.pool[(cursor.current + i) % r.pool.length]
    if (ok(m)) {
      cursor.current = (cursor.current + i + 1) % r.pool.length
      return m
    }
  }
  return null
}

// Drop slots whose item left the pool (deleted, or promoted to hero/favourite)
// and fill up to the slot count.
function refill(slots: number[], r: Rotation, cursor: { current: number }): number[] {
  const next = slots.filter((id) => r.pool.some((m) => m.id === id)).slice(0, r.count)
  while (next.length < r.count) {
    const m = nextItem(r, next, next, cursor)
    if (!m) break
    next.push(m.id)
  }
  return next
}

export default function LoveWall({
  media,
  mediaTotal,
  reactionsTotal,
  serverTime,
  joinBase,
  bursts,
}: {
  media: KioskMedia[]
  mediaTotal: number
  reactionsTotal: number
  serverTime: string
  joinBase: string
  bursts: ReactionBurst[]
}) {
  const { t } = useTranslation()
  const hero = media[0]
  const love = media.find((m) => m.love_pick && m.id !== hero.id) ?? null
  const pool = media.filter((m) => m.id !== hero.id && m.id !== love?.id)
  const count = Math.min(4, media.length - 1) - (love ? 1 : 0)

  // Latest values for the swap timer, which outlives any one render.
  const rotation = useRef<Rotation>({ pool, fixed: [], count, prefer: [] })
  rotation.current = { pool, fixed: love ? [hero, love] : [hero], count, prefer: bursts.map((b) => b.mediaId) }
  const cursor = useRef(0)
  const turn = useRef(0)
  const [slots, setSlots] = useState<number[]>(() => refill([], rotation.current, cursor))
  const slotsRef = useRef(slots)
  slotsRef.current = slots

  const mediaKey = `${media.map((m) => m.id).join(',')}|${love?.id ?? ''}`
  useEffect(() => {
    const next = refill(slotsRef.current, rotation.current, cursor)
    if (next.join(',') !== slotsRef.current.join(',')) setSlots(next)
  }, [mediaKey, count])

  useEffect(() => {
    const id = setInterval(() => {
      const current = slotsRef.current
      if (!current.length) return
      const idx = turn.current++ % current.length
      const others = current.filter((_, i) => i !== idx)
      const m = nextItem(rotation.current, current, others, cursor)
      if (m) setSlots(current.map((sid, i) => (i === idx ? m.id : sid)))
    }, CYCLE_MS)
    return () => clearInterval(id)
  }, [])

  const openedAt = useRef(Date.now())
  const intro = Date.now() - openedAt.current < INTRO_WINDOW_MS
  const slotItems = slots
    .map((id) => pool.find((m) => m.id === id))
    .filter((m): m is KioskMedia => !!m)
  const small = love ? [love, ...slotItems] : slotItems
  const layout = LAYOUTS[small.length]

  return (
    <div className="absolute inset-0 flex flex-col px-[4vw] py-[2vh] gap-[2.5vh]">
      <h1 className="lw-title text-[4vw] font-black tracking-tighter leading-none shrink-0">
        <span className="text-accent">#</span>
        {t('kiosk.wallTitle')}
      </h1>

      <div className="flex-1 min-h-0 flex gap-[1.2vw]">
        <div
          className="flex-1 min-w-0 grid gap-[1.2vw]"
          style={{ gridTemplateAreas: layout.areas, gridTemplateColumns: layout.cols, gridTemplateRows: layout.rows }}
        >
          <WallTile
            key={hero.id}
            item={hero}
            area="h"
            hero
            delay={0}
            bursts={bursts}
            serverTime={serverTime}
          />
          {small.map((m, i) => (
            <WallTile
              key={m.id}
              item={m}
              area={SMALL_AREAS[i]}
              delay={intro ? (i + 1) * INTRO_STAGGER_MS : 0}
              bursts={bursts}
              serverTime={serverTime}
            />
          ))}
        </div>

        <div className="w-[13vw] shrink-0 flex flex-col justify-between">
          <div className="lw-in space-y-[3vh]" style={{ '--lw-delay': '200ms' } as React.CSSProperties}>
            <WallStat value={mediaTotal} label={t('kiosk.wallMediaLabel', { count: mediaTotal })} />
            {reactionsTotal > 0 && (
              <WallStat value={reactionsTotal} label={t('kiosk.wallReactionsLabel', { count: reactionsTotal })} accent />
            )}
          </div>
          {/* Close the loop: see the wall, scan, post — it lands here. */}
          <div className="lw-rise flex flex-col gap-[1.5vh]" style={{ '--lw-delay': '300ms' } as React.CSSProperties}>
            <div className="bg-white p-[0.8vw] w-full">
              <QRCode value={`${joinBase}/media`} size={256} style={{ width: '100%', height: 'auto' }} viewBox="0 0 256 256" />
            </div>
            <div className="font-mono-kiosk text-accent text-[1.1vw] tracking-widest">📸 {t('kiosk.wallPostYours')}</div>
            <div className="text-[1vw] text-muted-foreground leading-snug">{t('kiosk.wallPostYoursHint')}</div>
          </div>
        </div>
      </div>
    </div>
  )
}

function WallStat({ value, label, accent = false }: { value: number; label: string; accent?: boolean }) {
  return (
    <div className="border-t border-border pt-[1.2vh]">
      <div className={`text-[3.6vw] font-black tracking-tighter leading-none tabular-nums ${accent ? 'text-accent' : ''}`}>
        {value}
      </div>
      <div className="font-mono-kiosk text-muted-foreground text-[0.95vw] mt-[0.8vh]">{label}</div>
    </div>
  )
}

function WallTile({
  item,
  area,
  hero = false,
  delay,
  bursts,
  serverTime,
}: {
  item: KioskMedia
  area: string
  hero?: boolean
  delay: number
  bursts: ReactionBurst[]
  serverTime: string
}) {
  const { t } = useTranslation()
  const [ready, setReady] = useState(false)
  // Frozen at mount: the kiosk re-renders every second, and a changing
  // animation-delay would jolt an animation that's already running.
  const [ownDelay] = useState(delay)
  const mountedAt = useRef(Date.now())
  const floatDelays = useRef(new Map<string, number>())

  useEffect(() => {
    const id = setTimeout(() => setReady(true), READY_FALLBACK_MS)
    return () => clearTimeout(id)
  }, [])

  const ago = timeAgo(item.created_at, serverTime, t)
  const reactions = item.reactions.slice(0, hero ? 4 : 3)
  const floats = bursts
    .filter((b) => b.mediaId === item.id)
    .flatMap((b) => b.emojis.map((emoji, i) => ({ key: `${b.key}-${i}`, emoji, i, seed: b.key * 37 + i * 23 })))

  return (
    <div
      className={`lw-tile relative overflow-hidden bg-muted min-w-0 min-h-0 ${item.love_pick ? 'lw-love' : ''}`}
      style={{ gridArea: area, '--lw-delay': `${ownDelay}ms` } as React.CSSProperties}
    >
      <div className={`absolute inset-0 ${ready ? 'lw-develop' : 'opacity-0'}`}>
        <div className={`absolute inset-0 ${hero ? 'lw-kenburns' : ''}`}>
          <WallMedia item={item} onReady={() => setReady(true)} className="w-full h-full object-cover" />
        </div>
      </div>
      {!ready && <div className="absolute inset-0 bg-muted kiosk-pulse" />}
      {ready && <div className="lw-curtain absolute inset-0 bg-accent" />}

      {ready && (
        <>
          <div className="lw-rise absolute inset-x-0 bottom-0 h-3/5 bg-gradient-to-t from-black/85 via-black/35 to-transparent pointer-events-none" />

          <div className="lw-rise absolute top-0 inset-x-0 p-[1vw] flex items-start justify-between gap-[1vw]">
            {item.love_pick ? (
              <span className="bg-accent text-accent-foreground font-mono-kiosk text-[0.9vw] px-[0.7vw] py-[0.5vh]">
                ❤ {t('kiosk.wallLovePick')}
              </span>
            ) : <span />}
            {item.file_type === 'video' && (
              <span className="bg-background/70 font-mono-kiosk text-[0.8vw] px-[0.6vw] py-[0.4vh]">▶ {t('kiosk.wallVideo')}</span>
            )}
          </div>

          <div className={`lw-rise absolute inset-x-0 bottom-0 flex items-end justify-between gap-[1vw] ${hero ? 'p-[1.6vw]' : 'p-[1vw]'}`}>
            <div className="min-w-0">
              {item.caption && (
                <div
                  className={`font-black tracking-tight leading-tight mb-[1vh] ${hero ? 'text-[2.2vw] line-clamp-2' : 'text-[1.1vw] truncate'}`}
                >
                  {item.caption}
                </div>
              )}
              <div className={`flex items-center gap-[0.6vw] font-mono-kiosk min-w-0 ${hero ? 'text-[1.1vw]' : 'text-[0.85vw]'}`}>
                {hero && (item.uploader_avatar_url ? (
                  <img src={item.uploader_avatar_url} alt="" className="w-[2.2vw] h-[2.2vw] object-cover shrink-0" />
                ) : item.uploader ? (
                  <span className="w-[2.2vw] h-[2.2vw] bg-muted flex items-center justify-center font-black text-[1vw] shrink-0">
                    {item.uploader.charAt(0).toUpperCase()}
                  </span>
                ) : null)}
                {item.uploader && <span className="text-foreground truncate">{item.uploader}</span>}
                {ago && <span className="text-muted-foreground shrink-0">· {ago}</span>}
              </div>
            </div>
            {reactions.length > 0 && (
              <div className="flex gap-[0.4vw] shrink-0">
                {reactions.map((r) => (
                  <span
                    key={r.emoji}
                    className={`bg-background/70 font-mono tabular-nums px-[0.5vw] py-[0.3vh] ${hero ? 'text-[1.1vw]' : 'text-[0.85vw]'}`}
                  >
                    {r.emoji} {r.count}
                  </span>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {floats.map((f) => {
        // A tile that just swapped in because of this reaction waits for its
        // own reveal before the emojis rise.
        if (!floatDelays.current.has(f.key)) {
          const wait = Math.max(0, ownDelay + 1_300 - (Date.now() - mountedAt.current))
          floatDelays.current.set(f.key, wait + f.i * 160)
        }
        return (
          <span
            key={f.key}
            className="lw-float absolute pointer-events-none leading-none"
            style={{
              left: `${12 + (f.seed % 70)}%`,
              bottom: '22%',
              fontSize: hero ? '3.4vw' : '2.4vw',
              animationDelay: `${floatDelays.current.get(f.key)}ms`,
            }}
          >
            {f.emoji}
          </span>
        )
      })}
    </div>
  )
}

/** A wall item's picture: the image, or the video (muted, looping) with its
 *  thumbnail as the fallback when the projector's browser can't play it. */
export function WallMedia({ item, onReady, className }: { item: KioskMedia; onReady: () => void; className?: string }) {
  const [videoFailed, setVideoFailed] = useState(false)
  const playVideo = item.file_type === 'video' && !videoFailed
  const still = item.file_type === 'video' ? item.thumbnail_url : item.url

  useEffect(() => {
    if (!playVideo && !still) onReady()
  }, [playVideo, still]) // eslint-disable-line react-hooks/exhaustive-deps

  if (playVideo) {
    return (
      <video
        src={item.url}
        poster={item.thumbnail_url ?? undefined}
        muted
        loop
        autoPlay
        playsInline
        className={className}
        onLoadedData={onReady}
        onError={() => setVideoFailed(true)}
      />
    )
  }
  if (!still) {
    return <div className={`${className} bg-muted flex items-center justify-center text-[4vw] text-muted-foreground`}>▶</div>
  }
  return <img src={still} alt="" decoding="async" className={className} onLoad={onReady} onError={onReady} />
}
