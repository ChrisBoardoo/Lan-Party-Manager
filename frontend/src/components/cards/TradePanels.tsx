import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowLeftRight } from 'lucide-react'
import { cardsApi } from '../../lib/api'
import { apiErrorMessage } from '../../lib/apiError'
import { suggestionPrefill } from '../../lib/cardTrades'
import { useLoad } from '../../hooks/useLoad'
import { useToast } from '../../contexts/ToastContext'
import LoadError from '../ui/LoadError'
import PlayerCard from './PlayerCard'
import type { CardItem, CardTrade } from '../../types'
import type { TradeTarget } from './TradeModal'

// The trading side of the Collection page (backend/card_trades.py): the
// "a trade would suit you both" suggestions, the crew's market (listings),
// and my offers — received, sent, and the history.

// The accepted trade's cards cross over before the list refreshes.
const SWAP_MS = 700

function reducedMotion() {
  return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

/** A naive-UTC timestamp from the server, as a local date. */
function day(iso: string | null, lang: string): string {
  if (!iso) return ''
  return new Date(iso.endsWith('Z') ? iso : `${iso}Z`).toLocaleDateString(lang, { day: 'numeric', month: 'long' })
}

function Mini({ cards }: { cards: CardItem[] }) {
  return (
    <div className="flex flex-wrap gap-2">
      {cards.map((c) => (
        <div key={c.id} className="w-16 sm:w-20">
          <PlayerCard card={c} interactive={false} />
        </div>
      ))}
    </div>
  )
}

const BUTTON = 'font-mono-label text-[11px] px-4 py-2 transition-colors disabled:opacity-40 disabled:pointer-events-none'
const PRIMARY = `${BUTTON} bg-accent text-accent-foreground hover:bg-accent/90`
const SECONDARY = `${BUTTON} border border-border text-muted-foreground hover:text-foreground hover:border-border-hover`

// ── Suggestions ───────────────────────────────────────────────────────────────

/** "A trade with Powet would suit you both": their duplicates I'm missing
 *  against mine they're missing. Nothing shown when there's none. */
export function TradeSuggestions({ onPropose }: { onPropose: (target: TradeTarget) => void }) {
  const { t } = useTranslation()
  const { data, error, retry } = useLoad(() => cardsApi.suggestions(), [])
  if (error) return <div className="mb-10"><LoadError message={error} onRetry={retry} /></div>
  if (!data || data.length === 0) return null
  return (
    <section className="mb-10 border border-border divide-y divide-border" aria-label={t('cards.trade.suggestionsTitle')}>
      {data.map((s) => (
        <div key={s.member.id} className="bg-card p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <ArrowLeftRight size={16} strokeWidth={1.5} className="text-accent shrink-0 mt-0.5" />
            <div className="min-w-0">
              <p className="text-sm text-foreground">{t('cards.trade.suggestionWith', { name: s.member.username })}</p>
              <p className="font-mono-label text-[10px] text-muted-foreground mt-1">
                {t('cards.trade.suggestionDetail', { they: s.they_give.length, mine: s.i_give.length })}
              </p>
            </div>
          </div>
          <button
            onClick={() => onPropose({ recipient: { id: s.member.id, username: s.member.username }, ...suggestionPrefill(s) })}
            className={`${PRIMARY} self-start sm:self-auto shrink-0`}
          >
            {t('cards.trade.propose')}
          </button>
        </div>
      ))}
    </section>
  )
}

// ── Market ────────────────────────────────────────────────────────────────────

export function MarketPanel({ viewerId, onPropose }: { viewerId: number; onPropose: (target: TradeTarget) => void }) {
  const { t } = useTranslation()
  const { push } = useToast()
  const { data, loading, error, retry, reload } = useLoad(() => cardsApi.listings(), [])
  const [missingOnly, setMissingOnly] = useState(false)
  const [epicOnly, setEpicOnly] = useState(false)
  const [eventId, setEventId] = useState<number | 'all'>('all')
  const [busy, setBusy] = useState<number | null>(null)

  const events = useMemo(() => {
    const seen = new Map<number, string>()
    for (const l of data ?? []) seen.set(l.card.face.event_id, l.card.face.event_title)
    return [...seen.entries()]
  }, [data])

  const shown = (data ?? []).filter(
    (l) =>
      (!missingOnly || (!l.mine && l.viewer_count === 0)) &&
      (!epicOnly || l.card.rarity === 'epic') &&
      (eventId === 'all' || l.card.face.event_id === eventId),
  )

  const close = async (listingId: number) => {
    setBusy(listingId)
    try {
      await cardsApi.closeListing(listingId)
      push(t('cards.market.closed'))
      reload()
    } catch (e) {
      push(apiErrorMessage(e, t), 'error')
    } finally {
      setBusy(null)
    }
  }

  const chip = (on: boolean) =>
    `font-mono-label text-[11px] px-3 py-1.5 border transition-colors ${
      on ? 'border-accent text-accent bg-accent/10' : 'border-border text-muted-foreground hover:text-foreground'
    }`

  return (
    <section>
      <div className="flex flex-wrap items-center gap-2 mb-8">
        <button className={chip(missingOnly)} aria-pressed={missingOnly} onClick={() => setMissingOnly((v) => !v)}>
          {t('cards.market.missingOnly')}
        </button>
        <button className={chip(epicOnly)} aria-pressed={epicOnly} onClick={() => setEpicOnly((v) => !v)}>
          {t('cards.market.epicOnly')}
        </button>
        {events.length > 1 && (
          <select
            value={eventId}
            onChange={(e) => setEventId(e.target.value === 'all' ? 'all' : Number(e.target.value))}
            aria-label={t('cards.market.allLans')}
            className="font-mono-label text-[11px] bg-card border border-border text-foreground px-3 py-1.5"
          >
            <option value="all">{t('cards.market.allLans')}</option>
            {events.map(([id, title]) => <option key={id} value={id}>{title}</option>)}
          </select>
        )}
      </div>
      {loading ? (
        <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
      ) : error ? (
        <LoadError message={error} onRetry={retry} />
      ) : shown.length === 0 ? (
        <div className="border border-border p-10 text-center">
          <p className="font-mono-label text-muted-foreground">
            {(data ?? []).length === 0 ? t('cards.market.empty') : t('cards.market.emptyFiltered')}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 2xl:grid-cols-6 gap-x-6 gap-y-10">
          {shown.map((l) => (
            <div key={l.id} className="min-w-0">
              <PlayerCard card={l.card} />
              <p className="font-mono-label text-[10px] text-muted-foreground mt-3 break-words">
                {l.mine ? t('cards.market.mine') : t('cards.market.by', { name: l.owner.username })}
                {!l.mine && l.viewer_count === 0 && <span className="text-accent"> · {t('cards.trade.youMiss')}</span>}
              </p>
              {l.note && <p className="text-xs text-foreground mt-1 break-words">« {l.note} »</p>}
              {l.mine ? (
                <button onClick={() => close(l.id)} disabled={busy === l.id} className={`${SECONDARY} mt-3 w-full`}>
                  {t('cards.market.close')}
                </button>
              ) : l.card.face.user_id === viewerId ? (
                <p className="font-mono-label text-[10px] text-muted-foreground mt-3">{t('cards.market.yourFace')}</p>
              ) : (
                <button
                  onClick={() => onPropose({ recipient: { id: l.owner.id, username: l.owner.username }, take: [l.card.id], listingId: l.id })}
                  className={`${PRIMARY} mt-3 w-full`}
                >
                  {t('cards.market.makeOffer')}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

// ── My offers ─────────────────────────────────────────────────────────────────

function statusLabel(trade: CardTrade, t: (key: string) => string): string {
  if (trade.status === 'cancelled') {
    return trade.closed_reason === 'unavailable' ? t('cards.trade.status.unavailable') : t('cards.trade.status.cancelled')
  }
  return t(`cards.trade.status.${trade.status}`)
}

function TradeRow({
  trade,
  viewerId,
  swapping,
  children,
}: {
  trade: CardTrade
  viewerId: number
  swapping: boolean
  children?: React.ReactNode
}) {
  const { t, i18n } = useTranslation()
  const received = trade.recipient.id === viewerId
  const other = received ? trade.proposer : trade.recipient
  const youGet = received ? trade.give : trade.take
  const youGive = received ? trade.take : trade.give
  return (
    <div className="bg-card p-4 sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-4">
        <p className="font-mono-label text-foreground">
          {received ? t('cards.trade.from', { name: other.username }) : t('cards.trade.to', { name: other.username })}
        </p>
        <p className={`font-mono-label text-[10px] ${trade.status === 'accepted' ? 'text-accent' : 'text-muted-foreground'}`}>
          {trade.status === 'pending'
            ? t('cards.trade.expires', { date: day(trade.expires_at, i18n.language) })
            : `${statusLabel(trade, t)} · ${day(trade.decided_at, i18n.language)}`}
        </p>
      </div>
      <div className="grid sm:grid-cols-2 gap-4">
        <div className={swapping ? 'lpm-trade-get' : ''}>
          <p className="font-mono-label text-[10px] text-accent mb-2">{t('cards.trade.youReceive')}</p>
          <Mini cards={youGet} />
        </div>
        <div className={swapping ? 'lpm-trade-give' : ''}>
          <p className="font-mono-label text-[10px] text-muted-foreground mb-2">{t('cards.trade.youGive')}</p>
          <Mini cards={youGive} />
        </div>
      </div>
      {trade.note && <p className="text-sm text-muted-foreground mt-4 break-words">« {trade.note} »</p>}
      {children && <div className="flex flex-wrap gap-2 mt-4 justify-end">{children}</div>}
    </div>
  )
}

export function TradesPanel({ viewerId, onChanged }: { viewerId: number; onChanged: () => void }) {
  const { t } = useTranslation()
  const { push } = useToast()
  const { data, loading, error, retry, reload } = useLoad(() => cardsApi.trades(), [])
  const [busy, setBusy] = useState<number | null>(null)
  const [swapping, setSwapping] = useState<number | null>(null)

  const act = async (trade: CardTrade, verb: 'accept' | 'decline' | 'cancel') => {
    setBusy(trade.id)
    try {
      await cardsApi.answer(trade.id, verb)
      if (verb === 'accept') {
        push(t('cards.trade.acceptedToast', { name: trade.proposer.username }))
        if (!reducedMotion()) {
          setSwapping(trade.id)
          await new Promise((r) => window.setTimeout(r, SWAP_MS))
          setSwapping(null)
        }
      } else {
        push(t(verb === 'decline' ? 'cards.trade.declinedToast' : 'cards.trade.cancelledToast'))
      }
    } catch (e) {
      push(apiErrorMessage(e, t), 'error')
    } finally {
      setBusy(null)
      reload()
      onChanged()
    }
  }

  if (loading) return <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
  if (error) return <LoadError message={error} onRetry={retry} />
  if (!data) return null

  const sections: { key: string; title: string; trades: CardTrade[] }[] = [
    { key: 'received', title: t('cards.trade.received'), trades: data.received },
    { key: 'sent', title: t('cards.trade.sentTitle'), trades: data.sent },
    { key: 'history', title: t('cards.trade.history'), trades: data.history },
  ]
  if (sections.every((s) => s.trades.length === 0)) {
    return (
      <div className="border border-border p-10 text-center">
        <p className="font-mono-label text-muted-foreground">{t('cards.trade.none')}</p>
      </div>
    )
  }
  return (
    <div className="space-y-10">
      {sections.filter((s) => s.trades.length > 0).map((s) => (
        <section key={s.key}>
          <p className="font-mono-label text-accent mb-3">{s.title} ({s.trades.length})</p>
          <div className="border border-border divide-y divide-border">
            {s.trades.map((trade) => (
              <TradeRow key={trade.id} trade={trade} viewerId={viewerId} swapping={swapping === trade.id}>
                {s.key === 'received' && (
                  <>
                    <button onClick={() => act(trade, 'decline')} disabled={busy !== null} className={SECONDARY}>
                      {t('cards.trade.decline')}
                    </button>
                    <button onClick={() => act(trade, 'accept')} disabled={busy !== null} className={PRIMARY}>
                      {t('cards.trade.accept')}
                    </button>
                  </>
                )}
                {s.key === 'sent' && (
                  <button onClick={() => act(trade, 'cancel')} disabled={busy !== null} className={SECONDARY}>
                    {t('cards.trade.cancel')}
                  </button>
                )}
              </TradeRow>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
