import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ChevronLeft, ChevronRight, ShoppingBag, X } from 'lucide-react'
import { cardsApi } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from '../contexts/ToastContext'
import type { CardCollection, CardItem, CardsMe, CollectionMember } from '../types'
import PlayerCard from '../components/cards/PlayerCard'
import BoosterOpening, { BoosterPack } from '../components/cards/BoosterOpening'
import MonthlyContract from '../components/quests/MonthlyContract'

// A member's card collection: one stack per collected member (their best card
// on top, the count beside it), a completion counter, and a zoomed view to
// tilt the cards under the light. Readable by the whole crew — the showcase is
// what gets people talking between two LANs.

function Stack({ member, onOpen }: { member: CollectionMember; onOpen: () => void }) {
  const { t } = useTranslation()
  const top = member.cards[0]
  const depth = Math.min(member.count - 1, 2)
  return (
    <button type="button" onClick={onOpen} className="group text-left focus-visible:outline-none">
      <div className="relative">
        {/* Cards behind the top one, offset like a pile on a table. */}
        {Array.from({ length: depth }, (_, i) => (
          <div
            key={i}
            className="absolute inset-0 border border-border bg-card"
            style={{ transform: `translate(${(i + 1) * 5}px, ${(i + 1) * 5}px)` }}
            aria-hidden="true"
          />
        ))}
        <PlayerCard card={top} className="relative transition-transform duration-200 group-hover:-translate-y-1 group-focus-visible:-translate-y-1" />
      </div>
      <div className="flex items-baseline justify-between gap-2 mt-3 pr-2">
        <span className="font-bold text-sm text-foreground truncate">{member.username}</span>
        <span className="font-mono-label text-[10px] text-muted-foreground shrink-0">
          {member.epic_count > 0 && <span className="text-accent mr-2">{t('cards.epicCount', { count: member.epic_count })}</span>}
          ×{member.count}
        </span>
      </div>
    </button>
  )
}

// Switching cards in the zoomed view: the card slides out to one side as the
// next one comes in from the other, like a card dealt from a hand — even when
// both are the same member's identical card (each switch is its own turn).
const SWAP_MS = 360
const SWIPE_PX = 50

type SwapDir = 'next' | 'prev'

function Zoom({ member, onClose }: { member: CollectionMember; onClose: () => void }) {
  const { t } = useTranslation()
  const [index, setIndex] = useState(0)
  const [turn, setTurn] = useState<{ n: number; dir: SwapDir | null }>({ n: 0, dir: null })
  const [leaving, setLeaving] = useState<{ card: CardItem; dir: SwapDir; n: number } | null>(null)
  const indexRef = useRef(0)
  const swipeFrom = useRef<number | null>(null)
  const count = member.cards.length

  const go = useCallback((dir: SwapDir) => {
    if (count < 2) return
    const from = indexRef.current
    const to = dir === 'next' ? (from + 1) % count : (from - 1 + count) % count
    indexRef.current = to
    setLeaving({ card: member.cards[from], dir, n: Date.now() })
    setIndex(to)
    setTurn((tn) => ({ n: tn.n + 1, dir }))
  }, [count, member.cards])
  const prev = useCallback(() => go('prev'), [go])
  const next = useCallback(() => go('next'), [go])

  useEffect(() => {
    if (!leaving) return
    const id = window.setTimeout(() => setLeaving(null), SWAP_MS)
    return () => window.clearTimeout(id)
  }, [leaving])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft') prev()
      if (e.key === 'ArrowRight') next()
    }
    window.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
    }
  }, [onClose, prev, next])

  const card = member.cards[index]
  return (
    <div
      className="fixed inset-0 z-50 bg-background/95 backdrop-blur-sm flex flex-col items-center justify-center p-6 overflow-hidden"
      role="dialog"
      aria-modal="true"
      aria-label={member.username}
      onClick={onClose}
    >
      <button onClick={onClose} className="absolute top-5 right-5 text-muted-foreground hover:text-foreground p-1" aria-label={t('common.close')}>
        <X size={18} />
      </button>
      <div className="flex items-center gap-4 sm:gap-8" onClick={(e) => e.stopPropagation()}>
        {count > 1 && (
          <button onClick={prev} className="text-muted-foreground hover:text-foreground p-2" aria-label={t('cards.previous')}>
            <ChevronLeft size={22} />
          </button>
        )}
        {/* touch-action: none so a finger tilts the card instead of scrolling;
            a horizontal swipe switches cards, like the arrows. */}
        <div
          className="relative w-[min(78vw,360px)] [touch-action:none]"
          onPointerDown={(e) => { swipeFrom.current = e.clientX }}
          onPointerUp={(e) => {
            const from = swipeFrom.current
            swipeFrom.current = null
            if (from == null) return
            if (e.clientX - from <= -SWIPE_PX) next()
            else if (e.clientX - from >= SWIPE_PX) prev()
          }}
        >
          {leaving && (
            <div key={`out-${leaving.n}`} className={`absolute inset-0 pointer-events-none lpm-swap-out-${leaving.dir}`} aria-hidden="true">
              <PlayerCard card={leaving.card} interactive={false} />
            </div>
          )}
          <div key={`in-${turn.n}`} className={turn.dir ? `lpm-swap-in-${turn.dir}` : ''}>
            <PlayerCard card={card} />
          </div>
        </div>
        {count > 1 && (
          <button onClick={next} className="text-muted-foreground hover:text-foreground p-2" aria-label={t('cards.next')}>
            <ChevronRight size={22} />
          </button>
        )}
      </div>
      {count > 1 && (
        <p className="font-mono-label text-muted-foreground text-[10px] mt-6">
          {index + 1} / {count}
        </p>
      )}
    </div>
  )
}

/** My unopened boosters, and the XP shop. */
function Boosters({
  me,
  onOpen,
  onBuy,
  buying,
}: {
  me: CardsMe
  onOpen: (from: number) => void
  onBuy: () => void
  buying: boolean
}) {
  const { t } = useTranslation()
  const { i18n } = useTranslation()
  const limitReached = me.purchases_left === 0
  const canBuy = me.xp_balance != null && me.xp_balance >= me.booster_price && !limitReached
  // Stored as naive UTC by the server.
  const nextPurchase = me.next_purchase_at
    ? new Date(me.next_purchase_at.endsWith('Z') ? me.next_purchase_at : `${me.next_purchase_at}Z`).toLocaleDateString(
        i18n.language, { weekday: 'long', day: 'numeric', month: 'long' },
      )
    : null
  return (
    <section className="mb-14 grid gap-px bg-border border border-border lg:grid-cols-[1fr_auto]">
      <div className="bg-card p-6">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
          <p className="font-mono-label text-accent">
            {me.boosters.length > 0 ? t('cards.boostersTitle', { count: me.boosters.length }) : t('cards.boostersTitleEmpty')}
          </p>
          {me.boosters.length > 0 && (
            <button
              onClick={() => onOpen(0)}
              className="font-mono-label text-[11px] px-4 py-2 bg-accent text-accent-foreground hover:bg-accent/90"
            >
              {t('cards.openAll', { count: me.boosters.length })}
            </button>
          )}
        </div>
        {me.boosters.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('cards.noBooster')}</p>
        ) : (
          <div className="flex flex-wrap gap-4">
            {me.boosters.map((b, i) => (
              <button
                key={b.id}
                onClick={() => onOpen(i)}
                className="w-24 sm:w-28 transition-transform hover:-translate-y-1 focus-visible:-translate-y-1 focus-visible:outline-none"
                aria-label={t('cards.opening.open')}
              >
                <BoosterPack booster={b} />
              </button>
            ))}
          </div>
        )}
      </div>
      {me.xp_balance != null && (
        <div className="bg-card p-6 lg:w-72 flex flex-col justify-between gap-4">
          <div>
            <p className="font-mono-label text-accent flex items-center gap-1.5 mb-2">
              <ShoppingBag size={12} strokeWidth={1.5} /> {t('cards.shopTitle')}
            </p>
            <p className="text-2xl font-black tracking-tight tabular-nums text-foreground">
              {t('cards.balance', { balance: me.xp_balance })}
            </p>
            <p className="text-xs text-muted-foreground mt-1">{t('cards.shopHint')}</p>
            <p className={`font-mono-label text-[10px] mt-2 ${limitReached ? 'text-accent' : 'text-muted-foreground'}`}>
              {limitReached && nextPurchase
                ? t('cards.weeklyLimitReached', { date: nextPurchase })
                : t('cards.purchasesLeft', { count: me.purchases_left ?? me.purchases_per_week, max: me.purchases_per_week })}
            </p>
          </div>
          <button
            onClick={onBuy}
            disabled={!canBuy || buying}
            className="font-mono-label text-[11px] px-4 py-2 border border-accent text-accent hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-40 disabled:pointer-events-none"
          >
            {t('cards.buy', { price: me.booster_price })}
          </button>
        </div>
      )}
    </section>
  )
}

export default function CollectionPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { push } = useToast()
  const params = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const ownerId = params.userId ? Number(params.userId) : user?.id
  const isMine = ownerId === user?.id
  const [collection, setCollection] = useState<CardCollection | null>(null)
  const [me, setMe] = useState<CardsMe | null>(null)
  const [error, setError] = useState(false)
  const [zoomed, setZoomed] = useState<CollectionMember | null>(null)
  const [opening, setOpening] = useState<CardsMe['boosters'] | null>(null)
  const [buying, setBuying] = useState(false)
  const autoOpened = useRef(false)

  const loadCollection = useCallback(() => {
    if (!ownerId) return
    cardsApi.collection(ownerId).then(setCollection).catch(() => setError(true))
  }, [ownerId])

  useEffect(() => {
    setCollection(null)
    setError(false)
    loadCollection()
  }, [loadCollection])

  useEffect(() => {
    if (!isMine) {
      setMe(null)
      return
    }
    cardsApi.me().then(setMe).catch(() => setMe(null))
  }, [isMine])

  // The Hub banner lands on /collection#open: go straight to the opening.
  useEffect(() => {
    if (!me || autoOpened.current || location.hash !== '#open') return
    autoOpened.current = true
    if (me.boosters.length > 0) setOpening(me.boosters)
    navigate(location.pathname, { replace: true })
  }, [me, location.hash, location.pathname, navigate])

  const closeOpening = () => {
    setOpening(null)
    cardsApi.me().then(setMe).catch(() => {})
    loadCollection()
  }

  const buy = async () => {
    setBuying(true)
    try {
      setMe(await cardsApi.buy())
      push(t('cards.bought'))
    } catch {
      push(t('cards.buyFailed'), 'error')
    } finally {
      setBuying(false)
    }
  }

  // The owner's own signature card carries their name; the API doesn't repeat it.
  const ownerName = collection?.members.find((m) => m.user_id === ownerId)?.username

  return (
    <main className="max-w-6xl mx-auto px-6 py-12">
      <div className="flex flex-wrap items-end justify-between gap-6 mb-12">
        <div>
          <div className="font-mono-label text-accent mb-3">{t('cards.tagline')}</div>
          <h1 className="text-5xl lg:text-6xl font-black tracking-tighter text-foreground leading-none">
            {isMine ? t('cards.myCollection') : t('cards.collectionOf', { name: ownerName ?? '…' })}
          </h1>
        </div>
        {collection && (
          <div className="flex gap-px bg-border border border-border">
            {[
              { label: t('cards.statMembers'), value: `${collection.collected} / ${collection.crew_size}` },
              { label: t('cards.statCards'), value: String(collection.total_cards) },
              { label: t('cards.statEpic'), value: String(collection.epic_cards), accent: collection.epic_cards > 0 },
            ].map((s) => (
              <div key={s.label} className="bg-card px-5 py-3">
                <p className="font-mono-label text-muted-foreground text-[10px]">{s.label}</p>
                <p className={`text-2xl font-black tracking-tight tabular-nums ${s.accent ? 'text-accent' : 'text-foreground'}`}>{s.value}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {isMine && <MonthlyContract shopLink={false} className="mb-6" />}

      {isMine && me && (
        <Boosters me={me} onOpen={(from) => setOpening(me.boosters.slice(from))} onBuy={buy} buying={buying} />
      )}

      {error ? (
        <p className="font-mono-label text-muted-foreground">{t('cards.loadFailed')}</p>
      ) : !collection ? (
        <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
      ) : collection.members.length === 0 ? (
        <div className="border border-border p-12 text-center">
          <p className="font-mono-label text-muted-foreground">{isMine ? t('cards.emptyMine') : t('cards.emptyOther')}</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-x-6 gap-y-10">
          {collection.members.map((m) => (
            <Stack key={m.user_id} member={m} onOpen={() => setZoomed(m)} />
          ))}
        </div>
      )}

      {zoomed && <Zoom member={zoomed} onClose={() => setZoomed(null)} />}
      {opening && opening.length > 0 && (
        <BoosterOpening
          boosters={opening}
          onClose={closeOpening}
          onOpened={loadCollection}
          onShowCollection={() => {
            closeOpening()
            window.scrollTo({ top: 0 })
          }}
        />
      )}
    </main>
  )
}
