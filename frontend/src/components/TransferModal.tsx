import { useEffect, useId, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, Plus, X } from 'lucide-react'
import Button from './ui/Button'
import { ProRataResult, TransferInput, User } from '../types'
import { expensesApi, usersApi } from '../lib/api'
import { apiErrorMessage, isApiStatus } from '../lib/apiError'
import { todayIso } from '../lib/eventDates'
import { useAppConfig } from '../contexts/AppConfigContext'
import { useToast } from '../contexts/ToastContext'

const AMOUNT_RE = /^\d+([.,]\d{1,2})?$/
const MAX_AMOUNT = 100_000

const parseAmount = (raw: string): number | null => {
  if (!AMOUNT_RE.test(raw.trim())) return null
  const value = Number(raw.trim().replace(',', '.'))
  return value > 0 && value <= MAX_AMOUNT ? value : null
}

/**
 * Treasurer/admin: record one or several transfers between members (Trésorerie
 * 2.0) — a partial reimbursement, a payment made outside the plan, or the
 * catch-up of bank transfers made during the LAN, with their real date. The
 * server recalculates the plan when a transfer predates it; this says so
 * before saving, and asks to confirm a member who isn't in the split.
 */
export default function TransferModal({
  data,
  onClose,
  onSaved,
}: {
  data: ProRataResult
  onClose: () => void
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const { currency } = useAppConfig()
  const { push } = useToast()
  const today = todayIso()
  const uid = useId()
  const idOf = (name: string) => `${uid}-${name}`
  const [allUsers, setAllUsers] = useState<User[]>([])
  const [from, setFrom] = useState<number | null>(null)
  const [to, setTo] = useState<number | null>(null)
  const [amount, setAmount] = useState('')
  const [amountTouched, setAmountTouched] = useState(false)
  const [date, setDate] = useState(today)
  const [note, setNote] = useState('')
  const [pending, setPending] = useState<TransferInput[]>([])
  const [confirmOutside, setConfirmOutside] = useState(false)
  const [confirmCatchUp, setConfirmCatchUp] = useState(false)
  // The server knows the split better (who fronted without staying): when it
  // refuses a member as outside it, the confirmation box shows up anyway.
  const [serverOutside, setServerOutside] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    // The members picker still works without the full list: the split's own
    // members come from the prorata.
    usersApi.getAll().then(setAllUsers).catch(() => setAllUsers([]))
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !busy) onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy, onClose])

  // Who's in the split: the shares, plus anyone a line names (someone who
  // fronted money without staying is owed, so appears there).
  const inSplit = useMemo(() => {
    const ids = new Set(data.shares.map((s) => s.user_id))
    data.settlements.forEach((l) => { ids.add(l.from_user_id); ids.add(l.to_user_id) })
    return ids
  }, [data])

  const names = useMemo(() => {
    const map = new Map<number, string>()
    data.shares.forEach((s) => map.set(s.user_id, s.username))
    data.settlements.forEach((l) => { map.set(l.from_user_id, l.from_username); map.set(l.to_user_id, l.to_username) })
    allUsers.forEach((u) => { if (!map.has(u.id)) map.set(u.id, u.username) })
    return map
  }, [data, allUsers])

  const splitMembers = [...inSplit].sort((a, b) => (names.get(a) ?? '').localeCompare(names.get(b) ?? ''))
  const others = allUsers
    .filter((u) => !inSplit.has(u.id) && u.is_active && !u.deleted_at)
    .sort((a, b) => a.username.localeCompare(b.username))

  // Pre-fill with what `from` still owes `to` in the plan, until the amount is typed.
  useEffect(() => {
    if (amountTouched || from == null || to == null) return
    const line = data.settlements.find((l) => !l.paid && l.from_user_id === from && l.to_user_id === to)
    setAmount(line ? line.amount.toFixed(2) : '')
  }, [from, to, amountTouched, data.settlements])
  const prefilled = !amountTouched && from != null && to != null && amount !== ''

  const value = parseAmount(amount)
  const currentProblem =
    from == null || to == null ? '' // incomplete, nothing to say yet
      : from === to ? t('finances.transfer.sameMember')
        : value == null ? t('finances.transfer.invalidAmount')
          : date > today ? t('finances.transfer.futureDate')
            : ''
  const currentReady = from != null && to != null && !currentProblem
  const current: TransferInput | null = currentReady
    ? { from_user_id: from!, to_user_id: to!, amount: value!, transferred_on: date, ...(note.trim() ? { note: note.trim() } : {}) }
    : null
  const batch = current ? [...pending, current] : pending

  const planDay = data.plan?.frozen ? data.plan.frozen_on ?? today : today
  const catchUp = batch.some((x) => x.transferred_on < planDay)
  const outsideNames = [...new Set(batch.flatMap((x) => [x.from_user_id, x.to_user_id]).filter((id) => !inSplit.has(id)))]
    .map((id) => names.get(id) ?? '?')
  const needsOutside = outsideNames.length > 0 || serverOutside
  const canSave = batch.length > 0 && !busy && (!catchUp || confirmCatchUp) && (!needsOutside || confirmOutside)

  const addAnother = () => {
    if (!current) return
    setPending((p) => [...p, current])
    setFrom(null)
    setTo(null)
    setAmount('')
    setAmountTouched(false)
    setNote('')
  }

  const save = async () => {
    if (!canSave || data.event_id == null) return
    setBusy(true)
    try {
      const res = await expensesApi.recordTransfers(data.event_id, batch, confirmOutside)
      push(t('finances.transfer.saved', { count: batch.length }))
      if (res.plan_recalculated) push(t('finances.transfer.planRecalculated'), 'info')
      onSaved()
      onClose()
    } catch (e) {
      const message = apiErrorMessage(e, t)
      // "Not in this event's split: …" (router_expenses.record_transfers)
      if (isApiStatus(e, 400) && message.includes('split')) setServerOutside(true)
      push(message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const select = 'w-full h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none transition-colors'
  const field = 'w-full h-10 px-3 bg-input border border-border text-foreground text-sm placeholder:text-muted-foreground focus:border-accent outline-none transition-colors'
  const label = 'font-mono-label text-muted-foreground text-[10px] mb-1 block'
  const memberOptions = (
    <>
      <option value="">{t('finances.transfer.pick')}</option>
      {splitMembers.map((id) => <option key={id} value={id}>{names.get(id)}</option>)}
      {others.map((u) => <option key={u.id} value={u.id}>{u.username} ({t('finances.transfer.outsideTag')})</option>)}
    </>
  )

  return (
    <div className="fixed inset-0 bg-background/90 z-50 flex items-center justify-center p-6" role="dialog" aria-modal="true" aria-label={t('finances.transfer.modalTitle')}>
      <div className="bg-card border border-border w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b border-border">
          <p className="font-mono-label text-accent">{t('finances.transfer.modalTitle')}</p>
          <button onClick={onClose} disabled={busy} aria-label={t('common.cancel')}>
            <X size={16} className="text-muted-foreground hover:text-foreground" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {pending.length > 0 && (
            <div className="border border-border divide-y divide-border">
              <p className="px-3 py-2 font-mono-label text-[10px] text-muted-foreground">
                {t('finances.transfer.pending', { count: pending.length })}
              </p>
              {pending.map((p, i) => (
                <div key={i} className="px-3 py-2 flex items-center gap-2 text-sm">
                  <span className="text-foreground truncate">{names.get(p.from_user_id)} → {names.get(p.to_user_id)}</span>
                  <span className="font-mono font-bold text-foreground tabular-nums">{p.amount.toFixed(2)} {currency}</span>
                  <span className="font-mono-label text-[10px] text-muted-foreground">{p.transferred_on}</span>
                  <button
                    type="button"
                    onClick={() => setPending((list) => list.filter((_, j) => j !== i))}
                    className="ml-auto font-mono-label text-[10px] text-muted-foreground hover:text-red-400"
                  >
                    {t('finances.transfer.removePending')}
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <label htmlFor={idOf('from')}>
              <span className={label}>{t('finances.transfer.from')}</span>
              <select id={idOf('from')} aria-label={t('finances.transfer.from')} className={select} value={from ?? ''} onChange={(e) => setFrom(e.target.value ? Number(e.target.value) : null)}>
                {memberOptions}
              </select>
            </label>
            <label htmlFor={idOf('to')}>
              <span className={label}>{t('finances.transfer.to')}</span>
              <select id={idOf('to')} aria-label={t('finances.transfer.to')} className={select} value={to ?? ''} onChange={(e) => setTo(e.target.value ? Number(e.target.value) : null)}>
                {memberOptions}
              </select>
            </label>
            <label htmlFor={idOf('amount')}>
              <span className={label}>{t('finances.transfer.amount')} ({currency})</span>
              <input
                id={idOf('amount')}
                aria-label={t('finances.transfer.amount')}
                className={field}
                inputMode="decimal"
                value={amount}
                onChange={(e) => { setAmount(e.target.value); setAmountTouched(true) }}
                placeholder="0.00"
              />
            </label>
            <label htmlFor={idOf('date')}>
              <span className={label}>{t('finances.transfer.date')}</span>
              <input id={idOf('date')} aria-label={t('finances.transfer.date')} type="date" className={field} value={date} max={today} onChange={(e) => setDate(e.target.value)} />
            </label>
            <label htmlFor={idOf('note')} className="col-span-2">
              <span className={label}>{t('finances.transfer.note')}</span>
              <input
                id={idOf('note')}
                aria-label={t('finances.transfer.note')}
                className={field}
                maxLength={200}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={t('finances.transfer.notePlaceholder')}
              />
            </label>
          </div>

          {prefilled && (
            <p className="text-xs text-muted-foreground">
              {t('finances.transfer.prefillHint', { from: names.get(from!), to: names.get(to!) })}
            </p>
          )}
          {currentProblem && <p className="font-mono-label text-[10px] text-red-400">{currentProblem}</p>}

          {needsOutside && (
            <div className="border border-yellow-500/40 bg-yellow-500/5 p-3 space-y-2">
              <p className="text-xs text-yellow-200 flex gap-2">
                <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
                {t('finances.transfer.outsideWarning', { names: outsideNames.join(', ') || '…' })}
              </p>
              <label htmlFor={idOf('outside')} className="flex items-center gap-2 text-xs text-foreground">
                <input id={idOf('outside')} aria-label={t('finances.transfer.outsideConfirm')} type="checkbox" checked={confirmOutside} onChange={(e) => setConfirmOutside(e.target.checked)} />
                {t('finances.transfer.outsideConfirm')}
              </label>
            </div>
          )}
          {catchUp && (
            <div className="border border-accent/50 bg-accent/5 p-3 space-y-2">
              <p className="text-xs text-foreground flex gap-2">
                <AlertTriangle size={14} className="flex-shrink-0 mt-0.5 text-accent" />
                {t('finances.transfer.catchUpWarning')}
              </p>
              <label htmlFor={idOf('catchup')} className="flex items-center gap-2 text-xs text-foreground">
                <input id={idOf('catchup')} aria-label={t('finances.transfer.catchUpConfirm')} type="checkbox" checked={confirmCatchUp} onChange={(e) => setConfirmCatchUp(e.target.checked)} />
                {t('finances.transfer.catchUpConfirm')}
              </label>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 p-6 border-t border-border">
          <button
            type="button"
            onClick={addAnother}
            disabled={!current || busy}
            className="font-mono-label text-[11px] text-muted-foreground hover:text-accent disabled:opacity-40 flex items-center gap-1.5"
          >
            <Plus size={12} strokeWidth={1.5} /> {t('finances.transfer.addAnother')}
          </button>
          <Button size="sm" onClick={save} disabled={!canSave}>
            {t('finances.transfer.save', { count: Math.max(batch.length, 1) })}
          </Button>
        </div>
      </div>
    </div>
  )
}
