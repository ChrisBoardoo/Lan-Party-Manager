import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useToast } from '../../contexts/ToastContext'
import { apiErrorMessage } from '../../lib/apiError'
import { useTranslation } from 'react-i18next'
import { Volume2, VolumeX, X } from 'lucide-react'
import { cardsApi } from '../../lib/api'
import {
  isMuted, playAnticipation, playCharge, playDeal, playEpic, playFlip, playRevealCommon, playTear, setMuted,
} from '../../lib/boosterSound'
import type { Booster, BoosterOpening as Opening } from '../../types'
import Confetti from '../kiosk/Confetti'
import PlayerCard, { CardBack } from './PlayerCard'
import SparkLayer, { type SparkLayerHandle } from './SparkLayer'

// Opening boosters, one after the other. The sequence (timings below, the look
// in index.css under "Booster opening"):
//   intro      the pack drops in and floats; it tilts under the pointer
//   charging   a click: it shakes harder and harder, light leaks from the seal —
//              meanwhile the server reveals the content (POST .../open)
//   dealt      it tears (cap off, flash, shockwave, sparks); the cards rise
//              face-down into a fan; each click flips one
//   spotlight  the last card — the only slot an Epic can be in — is kept for
//              last, lifted to the centre, charges up, then lands: an Epic with
//              rays, a rainbow shockwave, confetti and its fanfare
//   done       recap, next booster / collection / close
// The server already marked the booster opened at "charging": closing midway
// loses nothing, the cards are in the collection.

const CHARGE_MS = 950
const DEAL_START_MS = 280
const DEAL_STEP_MS = 90
const SPOT_LIFT_MS = 650
const SPOT_CHARGE_MS = 1250
const COMMON_HOLD_MS = 1100

export const PACK_COLORS: Record<Booster['source_type'], string> = {
  attendance: '#FF3D00',
  trophy: '#FFB800',
  xp_level: '#3D8BFF',
  purchase: '#C8C8C8',
}

const RAINBOW = ['#FF3D00', '#FFB800', '#5CFFB0', '#3D8BFF', '#B13DFF', '#FFFFFF']

function reducedMotion() {
  return !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

/** The sealed pack. Also used, small and still, in the list of boosters to open. */
export function BoosterPack({ booster, className = '' }: { booster: Booster; className?: string }) {
  const { t } = useTranslation()
  const art = (
    <div className="lpm-pack__art">
      <div className="lpm-pack__sheen" />
      <span className="lpm-pack__label">Booster</span>
      <span className="lpm-pack__logo">LPM</span>
      <span className="lpm-pack__small">{booster.event_title}</span>
      <span className="lpm-pack__small">{t('cards.opening.cardsCount', { count: booster.size })}</span>
      <span className="lpm-pack__badge">
        {t(`cards.opening.source.${booster.source_type}`)} · {t('cards.opening.epicChance', { rate: Math.round(booster.epic_rate * 100) })}
      </span>
    </div>
  )
  return (
    <div className={`lpm-pack ${className}`} style={{ ['--pack-c' as string]: PACK_COLORS[booster.source_type] }}>
      <div className="lpm-pack__cap">{art}</div>
      <div className="lpm-pack__main">{art}</div>
      <div className="lpm-pack__seam" />
    </div>
  )
}

function layout(n: number) {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const narrow = vw < 640
  const maxCols = narrow ? (n <= 4 ? 2 : 3) : 5
  const cols = Math.max(1, Math.min(n, maxCols))
  const rows = Math.ceil(n / cols)
  const gap = narrow ? 12 : 24
  const byWidth = (vw * 0.92 - gap * (cols - 1)) / cols
  const byHeight = ((vh * 0.6 - gap * (rows - 1)) / rows) * (63 / 88)
  return { cols, gap, cw: Math.round(Math.max(72, Math.min(230, byWidth, byHeight))) }
}

type Stage = 'intro' | 'charging' | 'dealt' | 'done'
type SpotPhase = 'lift' | 'anticipate' | 'revealed'
interface Fx { id: number; kind: 'flash' | 'shock' | 'rainbow'; x: number; y: number; color?: string }

export default function BoosterOpening({
  boosters,
  onClose,
  onOpened,
  onShowCollection,
}: {
  boosters: Booster[]
  onClose: () => void
  /** After each booster the server opened, to refresh what's behind. */
  onOpened?: () => void
  onShowCollection?: () => void
}) {
  const { t } = useTranslation()
  const [index, setIndex] = useState(0)
  const [stage, setStage] = useState<Stage>('intro')
  const { push } = useToast()
  const [opening, setOpening] = useState<Opening | null>(null)
  const [flipped, setFlipped] = useState<boolean[]>([])
  const [spot, setSpot] = useState<SpotPhase | null>(null)
  const [spotFlipped, setSpotFlipped] = useState(false)
  const [fx, setFx] = useState<Fx[]>([])
  const [confetti, setConfetti] = useState(false)
  const [nope, setNope] = useState<number | null>(null)
  const [hint, setHint] = useState<string | null>(null)
  const [error, setError] = useState(false)
  const [muted, setMutedState] = useState(isMuted())
  const [geo, setGeo] = useState(() => layout(2))

  const sparks = useRef<SparkLayerHandle>(null)
  const packRef = useRef<HTMLDivElement>(null)
  const tiltRef = useRef<HTMLDivElement>(null)
  const slotRefs = useRef<(HTMLDivElement | null)[]>([])
  const spotCardRef = useRef<HTMLDivElement>(null)
  const packCenter = useRef<{ x: number; y: number } | null>(null)
  const timers = useRef<number[]>([])
  const fxId = useRef(0)

  const booster = boosters[index]
  const cards = opening?.cards ?? []
  const rare = cards.length - 1
  const remaining = boosters.length - index - 1

  const later = (fn: () => void, ms: number) => {
    timers.current.push(window.setTimeout(fn, ms))
  }
  useEffect(() => () => timers.current.forEach(clearTimeout), [])

  // Keep the page behind still.
  useEffect(() => {
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [])

  useEffect(() => {
    const onResize = () => setGeo(layout(cards.length || 2))
    onResize()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [cards.length])

  const addFx = (kind: Fx['kind'], x: number, y: number, color?: string) => {
    const id = ++fxId.current
    setFx((list) => [...list, { id, kind, x, y, color }])
    later(() => setFx((list) => list.filter((f) => f.id !== id)), 1000)
  }

  const centerOf = (el: Element | null) => {
    const r = el?.getBoundingClientRect()
    return r ? { x: r.left + r.width / 2, y: r.top + r.height / 2, r } : null
  }

  // ── intro → charging → dealt ────────────────────────────────────────────────
  const start = async () => {
    if (stage !== 'intro' || !booster) return
    setError(false)
    setStage('charging')
    playCharge(CHARGE_MS)
    const began = Date.now()
    let res: Opening
    try {
      res = await cardsApi.open(booster.id)
    } catch (e) {
      // The 409 of a withheld booster (taken out of the LAN) now says so.
      setStage('intro')
      setError(true)
      push(apiErrorMessage(e, t), 'error')
      return
    }
    onOpened?.()
    const wait = reducedMotion() ? 0 : Math.max(0, CHARGE_MS - (Date.now() - began))
    later(() => tear(res), wait)
  }

  const tear = (res: Opening) => {
    const c = centerOf(packRef.current)
    if (c) {
      packCenter.current = { x: c.x, y: c.y }
      const seamY = c.r.top + c.r.height * 0.14
      addFx('flash', 0, 0)
      addFx('shock', c.x, seamY, PACK_COLORS[booster.source_type])
      sparks.current?.burst(c.x, seamY, {
        count: 140, speed: 13, colors: ['#FFFFFF', PACK_COLORS[booster.source_type], '#FFE3B0'], life: 80, size: 16,
      })
    }
    playTear()
    setOpening(res)
    setFlipped(res.cards.map(() => false))
    setStage('dealt')
    res.cards.forEach((_, i) => later(() => playDeal(i), DEAL_START_MS + i * DEAL_STEP_MS))
  }

  // Cards rise from where the pack was: set each slot's start offset before paint.
  useLayoutEffect(() => {
    if (stage !== 'dealt' || !packCenter.current) return
    const from = packCenter.current
    slotRefs.current.forEach((el, i) => {
      const c = centerOf(el)
      if (!el || !c) return
      el.style.setProperty('--fx', `${from.x - c.x}px`)
      el.style.setProperty('--fy', `${from.y - c.y}px`)
      el.style.setProperty('--fr', `${(i - (cards.length - 1) / 2) * -9}deg`)
      el.style.setProperty('--delay', `${DEAL_START_MS + i * DEAL_STEP_MS}ms`)
    })
    packCenter.current = null
  }, [stage, cards.length])

  // ── flipping ────────────────────────────────────────────────────────────────
  const flip = useCallback((i: number) => {
    setFlipped((f) => f.map((v, k) => (k === i ? true : v)))
    playFlip()
    later(() => {
      const c = centerOf(slotRefs.current[i])
      if (c) sparks.current?.burst(c.x, c.y, { count: 26, speed: 6, colors: ['#FFFFFF', '#FF3D00', '#FFB800'], life: 50, size: 12 })
    }, 300)
  }, [])

  const startSpot = () => {
    setSpot('lift')
    setSpotFlipped(false)
  }

  // Lift the last card from its slot to the centre, then charge, then land.
  useLayoutEffect(() => {
    if (spot !== 'lift') return
    const from = slotRefs.current[rare]?.getBoundingClientRect()
    const el = spotCardRef.current
    const to = el?.getBoundingClientRect()
    if (el && from && to && !reducedMotion()) {
      const dx = from.left + from.width / 2 - (to.left + to.width / 2)
      const dy = from.top + from.height / 2 - (to.top + to.height / 2)
      el.animate(
        [{ transform: `translate(${dx}px, ${dy}px) scale(${from.width / to.width})` }, { transform: 'none' }],
        { duration: SPOT_LIFT_MS, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' },
      )
    }
    const lift = reducedMotion() ? 0 : SPOT_LIFT_MS
    const charge = reducedMotion() ? 0 : SPOT_CHARGE_MS
    later(() => {
      setSpot('anticipate')
      playAnticipation(charge)
    }, lift)
    later(() => land(), lift + charge)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spot])

  const land = () => {
    const card = cards[rare]
    setSpotFlipped(true)
    setFlipped((f) => f.map((v, k) => (k === rare ? true : v)))
    setSpot('revealed')
    const c = centerOf(spotCardRef.current)
    if (card.rarity === 'epic') {
      addFx('flash', 0, 0)
      if (c) {
        addFx('rainbow', c.x, c.y)
        later(() => addFx('rainbow', c.x, c.y), 220)
        sparks.current?.burst(c.x, c.y, { count: 220, speed: 16, colors: RAINBOW, life: 110, size: 18, gravity: 0.08 })
      }
      setConfetti(true)
      playEpic()
    } else {
      if (c) sparks.current?.burst(c.x, c.y, { count: 60, speed: 8, colors: ['#FFFFFF', '#FF3D00', '#FFB800'], life: 60 })
      playRevealCommon()
      later(() => endSpot(), reducedMotion() ? 600 : COMMON_HOLD_MS)
    }
  }

  // Back to its slot, face up.
  const endSpot = () => {
    const el = spotCardRef.current
    const to = slotRefs.current[rare]?.getBoundingClientRect()
    const from = el?.getBoundingClientRect()
    const finish = () => {
      setSpot(null)
      setConfetti(false)
      setStage('done')
    }
    if (el && to && from && !reducedMotion()) {
      const dx = to.left + to.width / 2 - (from.left + from.width / 2)
      const dy = to.top + to.height / 2 - (from.top + from.height / 2)
      el.animate(
        [{ transform: 'none' }, { transform: `translate(${dx}px, ${dy}px) scale(${to.width / from.width})` }],
        { duration: 500, easing: 'cubic-bezier(0.5, 0, 0.2, 1)', fill: 'forwards' },
      ).onfinish = finish
    } else {
      finish()
    }
  }

  const clickCard = (i: number) => {
    if (stage !== 'dealt' || spot || flipped[i]) return
    if (i === rare) {
      if (flipped.some((v, k) => !v && k !== rare)) {
        setNope(i)
        setHint(t('cards.opening.lastHint'))
        later(() => setNope(null), 420)
        later(() => setHint(null), 2200)
        return
      }
      startSpot()
      return
    }
    flip(i)
  }

  const revealAll = () => {
    if (stage !== 'dealt' || spot) return
    const pending = flipped.map((v, k) => (!v && k !== rare ? k : -1)).filter((k) => k >= 0)
    pending.forEach((k, n) => later(() => flip(k), n * 220))
    later(() => startSpot(), pending.length * 220 + (pending.length ? 450 : 0))
  }

  const nextBooster = () => {
    timers.current.forEach(clearTimeout)
    timers.current = []
    setOpening(null)
    setFlipped([])
    setSpot(null)
    setFx([])
    setStage('intro')
    setIndex((i) => i + 1)
  }

  // Keyboard: Space/Enter does the next obvious thing, Escape leaves.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
        return
      }
      if (e.key !== ' ' && e.key !== 'Enter') return
      e.preventDefault()
      if (stage === 'intro') start()
      else if (spot === 'revealed' && cards[rare]?.rarity === 'epic') endSpot()
      else if (stage === 'dealt' && !spot) {
        const next = flipped.findIndex((v, k) => !v && k !== rare)
        clickCard(next >= 0 ? next : rare)
      } else if (stage === 'done' && remaining > 0) nextBooster()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const tilt = (e: React.PointerEvent) => {
    const el = tiltRef.current
    if (!el || stage !== 'intro' || reducedMotion()) return
    const r = el.getBoundingClientRect()
    el.style.setProperty('--lpm-rx', `${((0.5 - (e.clientY - r.top) / r.height) * 18).toFixed(1)}deg`)
    el.style.setProperty('--lpm-ry', `${(((e.clientX - r.left) / r.width - 0.5) * 18).toFixed(1)}deg`)
  }
  const untilt = () => {
    tiltRef.current?.style.removeProperty('--lpm-rx')
    tiltRef.current?.style.removeProperty('--lpm-ry')
  }

  const toggleSound = () => {
    setMuted(!muted)
    setMutedState(!muted)
  }

  if (!booster) return null
  const color = PACK_COLORS[booster.source_type]
  const newIds = new Set(opening?.new_member_ids ?? [])
  const rareCard = cards[rare]
  const newCount = cards.filter((c) => newIds.has(c.face.user_id)).length

  return (
    <div
      className="lpm-opening"
      data-stage={stage}
      style={{ ['--pack-c' as string]: color }}
      role="dialog"
      aria-modal="true"
      aria-label={t('cards.opening.title')}
    >
      <div className="lpm-opening__glow" />
      <SparkLayer ref={sparks} dustColor={color} />

      {/* Top bar */}
      <div className="absolute top-0 inset-x-0 flex items-center justify-between px-5 py-4 z-20">
        <p className="font-mono-label text-[10px] text-muted-foreground">
          <span className="text-accent">// {t('cards.opening.title')}</span>
          {boosters.length > 1 && <span className="ml-3">{index + 1} / {boosters.length}</span>}
        </p>
        <div className="flex items-center gap-3">
          <button onClick={toggleSound} className="text-muted-foreground hover:text-foreground p-1" aria-label={t(muted ? 'cards.opening.soundOn' : 'cards.opening.soundOff')}>
            {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
          </button>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground p-1" aria-label={t('common.close')}>
            <X size={18} />
          </button>
        </div>
      </div>

      {/* The pack */}
      {(stage === 'intro' || stage === 'charging' || stage === 'dealt') && (
        <div
          key={booster.id}
          className="lpm-pack-stage z-10"
          onClick={start}
          onPointerMove={tilt}
          onPointerLeave={untilt}
          role="button"
          aria-label={t('cards.opening.open')}
        >
          <div className="lpm-pack-stage__float">
            <div ref={tiltRef} className="lpm-pack-stage__tilt">
              <div ref={packRef}>
                <BoosterPack booster={booster} />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* The deal */}
      {opening && (stage === 'dealt' || stage === 'done') && (
        <div
          className="lpm-deal z-10"
          style={{ ['--cols' as string]: geo.cols, ['--cw' as string]: `${geo.cw}px`, ['--gap' as string]: `${geo.gap}px` }}
        >
          {cards.map((card, i) => {
            const isRare = i === rare
            return (
              <div key={card.id} ref={(el) => { slotRefs.current[i] = el }} className="lpm-deal__slot">
                <div
                  className={`lpm-flip ${isRare ? 'lpm-flip--rare' : ''} ${nope === i ? 'lpm-flip--nope' : ''}`}
                  data-flipped={flipped[i] ? 'true' : 'false'}
                  data-hidden={isRare && spot ? 'true' : 'false'}
                  onClick={() => clickCard(i)}
                  role="button"
                  tabIndex={flipped[i] ? -1 : 0}
                  aria-label={flipped[i] ? undefined : t('cards.opening.flip', { n: i + 1 })}
                >
                  <div className="lpm-flip__inner">
                    <div className="lpm-flip__back"><CardBack label={booster.event_title} /></div>
                    <div className="lpm-flip__front"><PlayerCard card={card} interactive={!!flipped[i]} /></div>
                  </div>
                </div>
                {flipped[i] && !(isRare && spot) && (
                  <>
                    {card.rarity === 'epic' ? (
                      <span className="lpm-badge lpm-badge--epic">{t('cards.rarity.epic')}</span>
                    ) : newIds.has(card.face.user_id) ? (
                      <span className="lpm-badge">{t('cards.opening.new')}</span>
                    ) : null}
                  </>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* The last card's spotlight */}
      {spot && rareCard && (
        <div className="lpm-spot z-30" data-phase={spot} onClick={() => spot === 'revealed' && rareCard.rarity === 'epic' && endSpot()}>
          {spot === 'revealed' && <div className={`lpm-rays ${rareCard.rarity === 'epic' ? 'lpm-rays--epic' : ''}`} />}
          {spot === 'revealed' && rareCard.rarity === 'epic' && (
            <p className="lpm-epic-title relative">{t('cards.opening.epicTitle')}</p>
          )}
          <div ref={spotCardRef} className="lpm-spot__card">
            <div className="lpm-spot__aura" />
            <div className="lpm-spot__shake">
              <div className="lpm-flip" data-flipped={spotFlipped ? 'true' : 'false'}>
                <div className="lpm-flip__inner">
                  <div className="lpm-flip__back"><CardBack label={booster.event_title} /></div>
                  <div className="lpm-flip__front"><PlayerCard card={rareCard} interactive={spotFlipped} /></div>
                </div>
              </div>
            </div>
          </div>
          {spot === 'revealed' && rareCard.rarity === 'epic' && (
            <div className="relative text-center lpm-rise-in" style={{ ['--delay' as string]: '500ms' }}>
              <p className="text-sm text-foreground mb-4">{t('cards.opening.epicCaption', { name: rareCard.face.username })}</p>
              <button
                onClick={(e) => { e.stopPropagation(); endSpot() }}
                className="font-mono-label text-[11px] px-6 py-2.5 bg-foreground text-background hover:bg-foreground/90"
              >
                {t('cards.opening.continue')}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Effects */}
      {fx.map((f) =>
        f.kind === 'flash' ? (
          <div key={f.id} className="lpm-flash z-40" />
        ) : (
          <div
            key={f.id}
            className={`lpm-shock z-40 ${f.kind === 'rainbow' ? 'lpm-shock--rainbow' : ''}`}
            style={{ left: f.x, top: f.y, ['--shock-c' as string]: f.color ?? '#fff' }}
          />
        ),
      )}
      {confetti && <div className="absolute inset-0 z-40 pointer-events-none"><Confetti run /></div>}

      {/* Bottom bar */}
      <div className="absolute bottom-0 inset-x-0 px-5 pb-8 pt-4 flex flex-col items-center gap-3 z-20 text-center">
        {stage === 'intro' && (
          <>
            {error && <p className="font-mono-label text-[11px] text-red-400">{t('cards.opening.failed')}</p>}
            <p className="font-mono-label text-[11px] text-foreground kiosk-pulse">{t('cards.opening.tapToOpen')}</p>
          </>
        )}
        {stage === 'dealt' && !spot && (
          <div className="flex flex-col items-center gap-3 lpm-rise-in" style={{ ['--delay' as string]: '900ms' }}>
            <p className="font-mono-label text-[11px] text-foreground">{hint ?? t('cards.opening.flipPrompt')}</p>
            <button onClick={revealAll} className="font-mono-label text-[10px] text-muted-foreground hover:text-foreground underline">
              {t('cards.opening.revealAll')}
            </button>
          </div>
        )}
        {stage === 'done' && (
          <div className="flex flex-col items-center gap-4 lpm-rise-in">
            <p className="font-mono-label text-[11px] text-muted-foreground">
              {t('cards.opening.summary', { count: cards.length })}
              {newCount > 0 && <span className="text-accent"> · {t('cards.opening.newCount', { count: newCount })}</span>}
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              {remaining > 0 && (
                <button onClick={nextBooster} className="font-mono-label text-[11px] px-5 py-2 bg-accent text-accent-foreground hover:bg-accent/90">
                  {t('cards.opening.next', { count: remaining })}
                </button>
              )}
              {onShowCollection && (
                <button onClick={onShowCollection} className="font-mono-label text-[11px] px-5 py-2 border border-foreground text-foreground hover:bg-foreground hover:text-background">
                  {t('cards.opening.toCollection')}
                </button>
              )}
              <button onClick={onClose} className="font-mono-label text-[11px] px-5 py-2 text-muted-foreground hover:text-foreground">
                {t('common.close')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
