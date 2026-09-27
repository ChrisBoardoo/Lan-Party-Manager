import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Package, Plus, Check, X, Trash2, Hand, Sparkles } from 'lucide-react'
import { gearApi } from '../lib/api'
import type { GearEvent, GearItem, GearSuggestion } from '../types'
import { useAuth } from '../contexts/AuthContext'
import Button from './ui/Button'

const CATEGORIES = ['network', 'power', 'display', 'peripheral', 'consumable', 'misc'] as const

// The per-event BYO gear list. Members pledge kit they're bringing; admins post
// requests a member can claim; and a member's "gear locker" is offered pre-ticked
// for one-tap carryover. Self-contained (fetches its own data with its own catch)
// so a disabled/empty gear feature never takes the event page down.
export default function GearSection({ eventId }: { eventId: number }) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [data, setData] = useState<GearEvent | null>(null)
  const [suggestions, setSuggestions] = useState<GearSuggestion[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const [name, setName] = useState('')
  const [qty, setQty] = useState(1)
  const [category, setCategory] = useState('')
  const [reqName, setReqName] = useState('')

  const [carryoverDismissed, setCarryoverDismissed] = useState(false)
  const [ticked, setTicked] = useState<Set<string>>(new Set())

  const load = () => {
    gearApi.getForEvent(eventId).then(setData).catch(() => setData(null))
    gearApi.suggestions().then(setSuggestions).catch(() => setSuggestions([]))
  }

  useEffect(() => {
    setLoading(true)
    Promise.all([
      gearApi.getForEvent(eventId).then(setData).catch(() => setData(null)),
      gearApi.suggestions().then(setSuggestions).catch(() => setSuggestions([])),
    ]).finally(() => setLoading(false))
  }, [eventId])

  const items = data?.items ?? []
  const myPledgedNames = useMemo(
    () => new Set(items.filter((i) => i.pledged_by === user?.id).map((i) => i.name.toLowerCase())),
    [items, user?.id],
  )
  // Locker items I haven't already pledged for THIS event.
  const availableSuggestions = useMemo(
    () => suggestions.filter((s) => !myPledgedNames.has(s.name.toLowerCase())),
    [suggestions, myPledgedNames],
  )

  // Pre-tick every available suggestion the FIRST time the locker loads (the
  // "auto-select" default). Seed once — re-running on later data changes would
  // silently re-tick items the user deliberately unticked.
  const seededRef = useRef(false)
  useEffect(() => {
    if (seededRef.current || suggestions.length === 0) return
    setTicked(new Set(availableSuggestions.map((s) => s.name.toLowerCase())))
    seededRef.current = true
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suggestions])

  const pledges = items.filter((i) => i.pledged_by !== null)
  const openRequests = items.filter((i) => i.is_request && i.pledged_by === null)
  const showCarryover = !loading && !carryoverDismissed && availableSuggestions.length > 0

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    try { await fn(); load() } finally { setBusy(false) }
  }

  const addPledge = () => {
    if (!name.trim()) return
    run(async () => {
      await gearApi.pledge(eventId, { name: name.trim(), quantity: qty, category: category || null })
      setName(''); setQty(1); setCategory('')
    })
  }

  const postRequest = () => {
    if (!reqName.trim()) return
    run(async () => { await gearApi.request(eventId, { name: reqName.trim() }); setReqName('') })
  }

  const toggleTick = (key: string) => {
    setTicked((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  const confirmCarryover = () => {
    const chosen = availableSuggestions.filter((s) => ticked.has(s.name.toLowerCase()))
    if (chosen.length === 0) { setCarryoverDismissed(true); return }
    run(async () => {
      await gearApi.carryover(eventId, chosen.map((s) => ({ name: s.name, category: s.category, quantity: s.quantity })))
      setCarryoverDismissed(true)
    })
  }

  if (loading) {
    return (
      <div className="border border-border bg-card p-8 text-center">
        <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="font-mono-label text-muted-foreground text-xs flex items-center gap-1.5">
          <Package size={13} /> {t('gear.pledgedCount', { count: data?.pledged_count ?? 0 })}
        </span>
        {(data?.open_request_count ?? 0) > 0 && (
          <span className="font-mono-label text-accent text-xs">{t('gear.neededCount', { count: data!.open_request_count })}</span>
        )}
      </div>

      {/* Carryover — your usual kit, pre-ticked */}
      {showCarryover && (
        <div className="border border-accent/40 bg-accent/5 p-4">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles size={15} className="text-accent" />
            <p className="font-mono-label text-foreground text-sm">{t('gear.carryoverTitle')}</p>
          </div>
          <p className="text-xs text-muted-foreground mb-3">{t('gear.carryoverHint')}</p>
          <div className="flex flex-wrap gap-2 mb-4">
            {availableSuggestions.map((s) => {
              const key = s.name.toLowerCase()
              const on = ticked.has(key)
              return (
                <button
                  key={key}
                  onClick={() => toggleTick(key)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 border font-mono-label text-xs transition-colors ${
                    on ? 'border-accent bg-accent text-accent-foreground' : 'border-border text-muted-foreground hover:border-border-hover'
                  }`}
                >
                  {on ? <Check size={12} /> : <Plus size={12} />}
                  {s.name}
                  {s.quantity > 1 && <span className="opacity-70">×{s.quantity}</span>}
                </button>
              )
            })}
          </div>
          <div className="flex items-center gap-3">
            <Button size="sm" onClick={confirmCarryover} disabled={busy}>
              {t('gear.carryoverConfirm', { count: ticked.size })}
            </Button>
            <button onClick={() => setCarryoverDismissed(true)} className="font-mono-label text-xs text-muted-foreground hover:text-foreground">
              {t('gear.carryoverDismiss')}
            </button>
          </div>
        </div>
      )}

      {/* Open requests to claim */}
      {openRequests.length > 0 && (
        <div className="border border-border bg-card">
          <div className="px-4 py-2 border-b border-border">
            <p className="font-mono-label text-accent text-xs">{t('gear.neededHeading')}</p>
          </div>
          {openRequests.map((it) => (
            <div key={it.id} className="flex items-center justify-between px-4 py-3 border-b border-border last:border-0">
              <span className="text-sm font-medium text-foreground">
                {it.name}{it.quantity > 1 ? ` ×${it.quantity}` : ''}
                {it.category && <CategoryChip category={it.category} />}
              </span>
              <div className="flex items-center gap-2">
                <button onClick={() => run(() => gearApi.claim(it.id))} disabled={busy}
                  className="font-mono-label text-xs text-foreground hover:text-accent flex items-center gap-1.5">
                  <Hand size={13} /> {t('gear.claim')}
                </button>
                {(isAdmin || it.created_by === user?.id) && (
                  <button onClick={() => run(() => gearApi.delete(it.id))} disabled={busy} className="text-muted-foreground hover:text-red-400">
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Who's bringing what */}
      <div className="border border-border bg-card">
        <div className="px-4 py-2 border-b border-border">
          <p className="font-mono-label text-muted-foreground text-xs">{t('gear.bringingHeading')}</p>
        </div>
        {pledges.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-muted-foreground">{t('gear.empty')}</p>
        ) : (
          pledges.map((it) => (
            <GearRow key={it.id} item={it} me={user?.id} isAdmin={isAdmin} busy={busy}
              onDelete={() => run(() => gearApi.delete(it.id))}
              onRelease={() => run(() => gearApi.unclaim(it.id))} />
          ))
        )}
      </div>

      {/* Add what you're bringing */}
      <div className="border border-border bg-card p-4">
        <p className="font-mono-label text-foreground text-sm mb-3">{t('gear.addTitle')}</p>
        <div className="flex flex-wrap gap-2">
          <input value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addPledge()}
            placeholder={t('gear.namePlaceholder')} maxLength={120}
            className="flex-1 min-w-[180px] bg-muted border border-border px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-accent outline-none" />
          <input type="number" min={1} max={999} value={qty} onChange={(e) => setQty(Math.max(1, parseInt(e.target.value) || 1))}
            className="w-16 bg-muted border border-border px-3 py-2 text-sm text-foreground focus:border-accent outline-none" />
          <select value={category} onChange={(e) => setCategory(e.target.value)}
            className="bg-muted border border-border px-3 py-2 text-sm text-foreground focus:border-accent outline-none">
            <option value="">{t('gear.categoryNone')}</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{t(`gear.categories.${c}`)}</option>)}
          </select>
          <Button size="sm" onClick={addPledge} disabled={busy || !name.trim()}>
            <Plus size={13} /> {t('gear.addButton')}
          </Button>
        </div>
      </div>

      {/* Admin: post a request */}
      {isAdmin && (
        <div className="border border-border bg-card p-4">
          <p className="font-mono-label text-foreground text-sm mb-3">{t('gear.requestTitle')}</p>
          <div className="flex flex-wrap gap-2">
            <input value={reqName} onChange={(e) => setReqName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && postRequest()}
              placeholder={t('gear.requestPlaceholder')} maxLength={120}
              className="flex-1 min-w-[180px] bg-muted border border-border px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-accent outline-none" />
            <Button size="sm" variant="outline" onClick={postRequest} disabled={busy || !reqName.trim()}>
              {t('gear.requestButton')}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function CategoryChip({ category }: { category: string }) {
  const { t } = useTranslation()
  const known = (CATEGORIES as readonly string[]).includes(category)
  return (
    <span className="ml-2 font-mono-label text-[10px] text-muted-foreground border border-border px-1.5 py-0.5">
      {known ? t(`gear.categories.${category}`) : category}
    </span>
  )
}

function GearRow({ item, me, isAdmin, busy, onDelete, onRelease }: {
  item: GearItem; me?: number; isAdmin: boolean; busy: boolean; onDelete: () => void; onRelease: () => void
}) {
  const { t } = useTranslation()
  const mine = item.pledged_by === me
  const canManage = isAdmin || mine || item.created_by === me
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-border last:border-0">
      <div className="flex items-center gap-3 min-w-0">
        {item.pledged_avatar_url ? (
          <img src={item.pledged_avatar_url} alt="" className="w-6 h-6 object-cover flex-shrink-0" />
        ) : (
          <div className="w-6 h-6 bg-muted flex items-center justify-center font-black text-[10px] flex-shrink-0">
            {(item.pledged_username || '?').charAt(0).toUpperCase()}
          </div>
        )}
        <div className="min-w-0">
          <span className="text-sm font-medium text-foreground">
            {item.name}{item.quantity > 1 ? ` ×${item.quantity}` : ''}
            {item.category && <CategoryChip category={item.category} />}
          </span>
          <p className="font-mono-label text-[10px] text-muted-foreground truncate">
            {mine ? t('gear.you') : item.pledged_username}
            {item.is_request && <span className="text-accent"> · {t('gear.claimed')}</span>}
          </p>
        </div>
      </div>
      {canManage && (
        <div className="flex items-center gap-2 flex-shrink-0">
          {item.is_request && mine && (
            <button onClick={onRelease} disabled={busy} className="font-mono-label text-[10px] text-muted-foreground hover:text-foreground flex items-center gap-1">
              <X size={12} /> {t('gear.release')}
            </button>
          )}
          <button onClick={onDelete} disabled={busy} className="text-muted-foreground hover:text-red-400">
            <Trash2 size={13} />
          </button>
        </div>
      )}
    </div>
  )
}
