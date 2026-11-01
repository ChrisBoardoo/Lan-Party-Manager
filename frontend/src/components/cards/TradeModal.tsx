import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import { cardsApi } from '../../lib/api'
import { apiErrorMessage } from '../../lib/apiError'
import { idsFor, keysForIds, tradeOptions, type TradeOption } from '../../lib/cardTrades'
import { useLoad } from '../../hooks/useLoad'
import { useToast } from '../../contexts/ToastContext'
import LoadError from '../ui/LoadError'
import PlayerCard from './PlayerCard'

// "Propose a trade": their duplicates on the left (what I'd receive), mine on
// the right (what I'd give), 1 to 3 on each side. Mine that they're missing
// come first and stand out — that's the offer most likely to be accepted. On a
// phone the two columns stack, "you receive" on top. The server checks it all
// again (card_trades.py); this only lays out the choice.

const MAX_PER_SIDE = 3

export interface TradeTarget {
  recipient: { id: number; username: string }
  /** Their card ids to preselect (a listing, a suggestion, a zoomed card). */
  take?: number[]
  /** My card ids to preselect (a suggestion). */
  give?: number[]
  listingId?: number | null
}

function Option({
  option,
  selected,
  disabled,
  missingLabel,
  onToggle,
}: {
  option: TradeOption
  selected: boolean
  disabled: boolean
  missingLabel: string
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled}
      aria-pressed={selected}
      className={`text-left p-1.5 border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
        selected ? 'border-accent bg-accent/10' : 'border-transparent hover:border-border-hover'
      }`}
    >
      <PlayerCard card={option.card} interactive={false} />
      <span className="mt-1.5 block font-mono-label text-[10px] text-muted-foreground tabular-nums">
        ×{option.count}
        {selected && <span className="text-accent"> → {option.count - 1}</span>}
      </span>
      {option.missing && <span className="block font-mono-label text-[10px] text-accent leading-tight mt-0.5">{missingLabel}</span>}
    </button>
  )
}

function Side({
  title,
  options,
  chosen,
  setChosen,
  missingLabel,
  empty,
}: {
  title: string
  options: TradeOption[]
  chosen: string[]
  setChosen: (keys: string[]) => void
  missingLabel: string
  empty: string
}) {
  const toggle = (key: string) =>
    setChosen(chosen.includes(key) ? chosen.filter((k) => k !== key) : [...chosen, key].slice(0, MAX_PER_SIDE))
  return (
    <section className="bg-card p-4 sm:p-5 min-w-0">
      <p className="font-mono-label text-accent mb-3">
        {title} <span className="text-muted-foreground">({chosen.length}/{MAX_PER_SIDE})</span>
      </p>
      {options.length === 0 ? (
        <p className="text-sm text-muted-foreground">{empty}</p>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
          {options.map((o) => (
            <Option
              key={o.key}
              option={o}
              selected={chosen.includes(o.key)}
              disabled={!chosen.includes(o.key) && chosen.length >= MAX_PER_SIDE}
              missingLabel={missingLabel}
              onToggle={() => toggle(o.key)}
            />
          ))}
        </div>
      )}
    </section>
  )
}

export default function TradeModal({
  viewerId,
  target,
  onClose,
  onSent,
}: {
  viewerId: number
  target: TradeTarget
  onClose: () => void
  onSent: () => void
}) {
  const { t } = useTranslation()
  const { push } = useToast()
  const { recipient } = target
  const { data, loading, error, retry } = useLoad(
    () => Promise.all([cardsApi.collection(viewerId), cardsApi.collection(recipient.id)]),
    [viewerId, recipient.id],
  )
  const [take, setTake] = useState<string[]>([])
  const [give, setGive] = useState<string[]>([])
  const [note, setNote] = useState('')
  const [sending, setSending] = useState(false)

  const mine = data?.[0]
  const theirs = data?.[1]
  const takeOptions = useMemo(() => tradeOptions(theirs, mine, viewerId), [theirs, mine, viewerId])
  const giveOptions = useMemo(() => tradeOptions(mine, theirs, recipient.id), [mine, theirs, recipient.id])

  // Preselect what the entry point asked for, once the collections are in.
  useEffect(() => {
    if (!mine || !theirs) return
    const allowed = (keys: string[], options: TradeOption[]) =>
      keys.filter((k) => options.some((o) => o.key === k)).slice(0, MAX_PER_SIDE)
    setTake(allowed(keysForIds(theirs.types, target.take ?? []), takeOptions))
    setGive(allowed(keysForIds(mine.types, target.give ?? []), giveOptions))
  }, [mine, theirs, takeOptions, giveOptions, target.take, target.give])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
    }
  }, [onClose])

  const send = async () => {
    setSending(true)
    try {
      await cardsApi.propose({
        recipient_id: recipient.id,
        give: idsFor(giveOptions, give),
        take: idsFor(takeOptions, take),
        listing_id: target.listingId ?? null,
        note: note.trim() || null,
      })
      push(t('cards.trade.sent', { name: recipient.username }))
      onSent()
    } catch (e) {
      push(apiErrorMessage(e, t), 'error')
    } finally {
      setSending(false)
    }
  }

  const ready = take.length > 0 && give.length > 0 && !sending
  return (
    <div
      className="fixed inset-0 z-50 bg-background/90 overflow-y-auto p-3 sm:p-6 flex items-start md:items-center justify-center"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t('cards.trade.proposeTo', { name: recipient.username })}
        className="bg-card border border-border w-full max-w-4xl my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-4 px-4 sm:px-5 py-4 border-b border-border">
          <p className="font-mono-label text-foreground">{t('cards.trade.proposeTo', { name: recipient.username })}</p>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground p-1" aria-label={t('common.close')}>
            <X size={16} />
          </button>
        </div>
        {loading ? (
          <p className="font-mono-label text-muted-foreground animate-pulse p-5">{t('common.loading')}</p>
        ) : error ? (
          <div className="p-5"><LoadError message={error} onRetry={retry} /></div>
        ) : (
          <>
            <div className="grid md:grid-cols-2 gap-px bg-border">
              <Side
                title={t('cards.trade.youReceive')}
                options={takeOptions}
                chosen={take}
                setChosen={setTake}
                missingLabel={t('cards.trade.youMiss')}
                empty={t('cards.trade.nothingToTake', { name: recipient.username })}
              />
              <Side
                title={t('cards.trade.youGive')}
                options={giveOptions}
                chosen={give}
                setChosen={setGive}
                missingLabel={t('cards.trade.theyMiss', { name: recipient.username })}
                empty={t('cards.trade.nothingToGive', { name: recipient.username })}
              />
            </div>
            <div className="px-4 sm:px-5 py-4 border-t border-border flex flex-col sm:flex-row sm:items-center gap-3">
              <input
                value={note}
                onChange={(e) => setNote(e.target.value.slice(0, 200))}
                placeholder={t('cards.trade.notePlaceholder')}
                aria-label={t('cards.trade.notePlaceholder')}
                className="flex-1 min-w-0 bg-background border border-border px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-accent"
              />
              <div className="flex gap-2 justify-end">
                <button onClick={onClose} className="font-mono-label text-[11px] px-4 py-2 border border-border text-muted-foreground hover:text-foreground">
                  {t('common.cancel')}
                </button>
                <button
                  onClick={send}
                  disabled={!ready}
                  className="font-mono-label text-[11px] px-4 py-2 bg-accent text-accent-foreground hover:bg-accent/90 disabled:opacity-40 disabled:pointer-events-none"
                >
                  {t('cards.trade.send')}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
