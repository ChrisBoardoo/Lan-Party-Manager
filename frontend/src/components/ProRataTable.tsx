import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ProRataResult, SettlementLine, User } from '../types'
import { useAppConfig } from '../contexts/AppConfigContext'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from '../contexts/ToastContext'
import { eventsApi, expensesApi, usersApi } from '../lib/api'
import { apiErrorMessage } from '../lib/apiError'
import { formatDate } from '../lib/formatDate'
import TransferModal from './TransferModal'
import { Check, ArrowRight, Wallet, Phone, Pencil, UserPlus, Trash2, ArrowLeftRight, RotateCcw, Lock } from 'lucide-react'

interface ProRataTableProps {
  data: ProRataResult
  onSettlementChange?: () => void
}

/**
 * Treasurer/admin correction of one member's stay: the only way to change it
 * once the LAN has started (the server locks members out of their own dates
 * from the first day, since they set everyone's share). Logged server-side,
 * and the member gets a notification.
 */
function StayEditor({
  data,
  userId,
  initialArrival,
  initialDeparture,
  deleted = false,
  onDone,
  onCancel,
}: {
  data: ProRataResult
  userId: number
  initialArrival: string
  initialDeparture: string
  // A deleted account can only be taken out of the split.
  deleted?: boolean
  onDone: () => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const [arrival, setArrival] = useState(initialArrival)
  const [departure, setDeparture] = useState(initialDeparture)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const save = async (status: 'in' | 'out') => {
    if (data.event_id == null) return
    setBusy(true)
    setError('')
    try {
      await eventsApi.adjustRsvp(
        data.event_id,
        userId,
        status === 'in' ? { status, arrival_date: arrival, departure_date: departure } : { status }
      )
      onDone()
    } catch (e) {
      setError(t('finances.adjust.failed', { detail: apiErrorMessage(e, t) }))
    } finally {
      setBusy(false)
    }
  }

  const dateInput = 'bg-background border border-border px-2 py-1 font-mono text-xs text-foreground'
  return (
    <div className="col-span-12 flex flex-wrap items-end gap-3 pt-2">
      {!deleted && (<>
      <label className="flex flex-col gap-1 font-mono-label text-muted-foreground text-[10px]">
        {t('finances.adjust.arrival')}
        <input
          type="date"
          className={dateInput}
          value={arrival}
          min={data.event_start ?? undefined}
          max={departure || (data.event_end ?? undefined)}
          onChange={(e) => setArrival(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 font-mono-label text-muted-foreground text-[10px]">
        {t('finances.adjust.departure')}
        <input
          type="date"
          className={dateInput}
          value={departure}
          min={arrival || (data.event_start ?? undefined)}
          max={data.event_end ?? undefined}
          onChange={(e) => setDeparture(e.target.value)}
        />
      </label>
      <button
        onClick={() => save('in')}
        disabled={busy || !arrival || !departure}
        className="font-mono-label text-[11px] px-3 py-1.5 border border-accent text-accent hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50"
      >
        {t('finances.adjust.save')}
      </button>
      </>)}
      <button
        onClick={() => save('out')}
        disabled={busy}
        className="font-mono-label text-[11px] px-3 py-1.5 border border-border text-muted-foreground hover:border-red-400 hover:text-red-400 transition-colors disabled:opacity-50"
      >
        {t('finances.adjust.remove')}
      </button>
      <button
        onClick={onCancel}
        disabled={busy}
        className="font-mono-label text-[11px] text-muted-foreground hover:text-foreground underline"
      >
        {t('finances.adjust.cancel')}
      </button>
      <p className="w-full text-[10px] text-muted-foreground">
        {t(deleted ? 'finances.adjust.hintDeleted' : 'finances.adjust.hint')}
      </p>
      {error && <p className="w-full font-mono-label text-[10px] text-red-400">{error}</p>}
    </div>
  )
}

export default function ProRataTable({ data, onSettlementChange }: ProRataTableProps) {
  const { t } = useTranslation()
  const { currency } = useAppConfig()
  const { user, isTreasurer } = useAuth()
  const { push } = useToast()
  const [busyKey, setBusyKey] = useState<string | null>(null)
  // user id whose stay is being edited; 'new' = adding a member not in the split yet
  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const [members, setMembers] = useState<User[]>([])
  const [newMember, setNewMember] = useState<number | null>(null)
  const [transferOpen, setTransferOpen] = useState(false)
  const maxAmount = Math.max(...data.shares.map((s) => s.amount), 1)
  const canAdjust = isTreasurer && data.event_id != null
  const money = (amount: number) => `${amount.toFixed(2)} ${currency}`

  // Every write ends in a toast when it fails (1.4.1 rule), then reloads.
  const run = async (key: string, action: () => Promise<unknown>, success?: string) => {
    setBusyKey(key)
    try {
      await action()
      if (success) push(success)
      onSettlementChange?.()
    } catch (e) {
      push(apiErrorMessage(e, t), 'error')
    } finally {
      setBusyKey(null)
    }
  }

  // fromUserId: the treasurer acting for a debtor who can't log in any more.
  const markPaid = (toUserId: number, fromUserId?: number) => {
    if (data.event_id == null) return
    const eventId = data.event_id
    run(`${fromUserId ?? ''}-${toUserId}`, () => expensesApi.markSettlement(eventId, toUserId, fromUserId))
  }

  // A recorded transfer: the treasurer/an admin deletes any; a member the
  // "payment sent" they recorded themselves. A pre-1.3.4 "paid" flag (no
  // transfer id) is reversed through the old endpoint, by its debtor.
  const canDelete = (line: SettlementLine) =>
    line.transfer_id != null
      ? isTreasurer || (line.recorded_by_user_id === user?.id && line.from_user_id === user?.id)
      : user?.id === line.from_user_id
  const deleteLine = (line: SettlementLine) => {
    if (!confirm(t('finances.transfer.deleteConfirm', { amount: money(line.amount), from: line.from_username, to: line.to_username }))) return
    run(
      `del-${line.transfer_id ?? `${line.from_user_id}-${line.to_user_id}`}`,
      () => line.transfer_id != null
        ? expensesApi.deleteTransfer(line.transfer_id)
        : expensesApi.unmarkSettlement(data.event_id!, line.to_user_id),
      t('finances.transfer.deleted'),
    )
  }

  const recalculate = () => {
    if (data.event_id == null || !confirm(t('finances.transfer.recalculateConfirm'))) return
    const eventId = data.event_id
    run('recalculate', () => expensesApi.recalculatePlan(eventId), t('finances.transfer.planRecalculated'))
  }

  const toPay = data.settlements.filter((l) => !l.paid)
  const recorded = data.settlements.filter((l) => l.paid)

  const startAdding = async () => {
    setEditing('new')
    setNewMember(null)
    if (!members.length) {
      try {
        setMembers(await usersApi.getAll())
      } catch {
        // the picker just stays empty
      }
    }
  }

  const doneEditing = () => {
    setEditing(null)
    onSettlementChange?.()
  }

  const inSplit = new Set(data.shares.map((s) => s.user_id))

  return (
    <div className="space-y-6">
      {data.event_title && (
        <p className="font-mono-label text-accent">// {data.event_title.toUpperCase()}</p>
      )}
      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-border">
        {[
          { label: t('finances.table.totalBudget'), value: `${data.total_expenses.toFixed(2)} ${currency}` },
          {
            label: t('finances.table.eventDuration'),
            value: t('finances.table.nights', { count: data.total_nights }),
          },
          { label: t('finances.table.attendees'), value: String(data.shares.length) },
          { label: t('finances.table.personNights'), value: String(data.total_person_nights) },
        ].map(({ label, value }) => (
          <div key={label} className="bg-card p-4">
            <p className="font-mono-label text-muted-foreground mb-1">{label}</p>
            <p className="text-2xl font-black tracking-tight text-foreground">{value}</p>
          </div>
        ))}
      </div>

      {/* Share breakdown */}
      {data.shares.length === 0 ? (
        <div className="text-center py-12 border border-border">
          <p className="font-mono-label text-muted-foreground">
            {t('finances.table.noAttendees')}
          </p>
        </div>
      ) : (
        <div className="border border-border">
          {/* Header (desktop table only) */}
          <div className="hidden md:grid grid-cols-12 gap-4 px-4 py-3 bg-muted border-b border-border">
            <div className="col-span-3 font-mono-label text-muted-foreground">{t('finances.table.player')}</div>
            <div className="col-span-2 font-mono-label text-muted-foreground text-center">
              {t('finances.table.nightsHeader')}
            </div>
            <div className="col-span-2 font-mono-label text-muted-foreground text-center">
              {t('finances.table.share')}
            </div>
            <div className="col-span-5 font-mono-label text-muted-foreground text-right">
              {t('finances.table.amountDue')}
            </div>
          </div>

          {data.shares.map((share) => {
            const avatar = (
              <div className="w-8 h-8 bg-muted border border-border flex items-center justify-center flex-shrink-0">
                {share.avatar_url ? (
                  <img
                    src={share.avatar_url}
                    alt={share.username}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <span className="text-sm font-bold text-muted-foreground">
                    {share.username[0].toUpperCase()}
                  </span>
                )}
              </div>
            )
            const editStay = canAdjust && editing !== share.user_id && (
              <button
                onClick={() => setEditing(share.user_id)}
                title={t('finances.adjust.edit')}
                aria-label={t('finances.adjust.edit')}
                className="ml-2 p-1 -m-1 text-muted-foreground hover:text-accent align-middle"
              >
                <Pencil size={11} strokeWidth={1.5} />
              </button>
            )
            const amount = (
              <span className="font-mono text-xl font-black text-foreground tabular-nums whitespace-nowrap">
                {share.amount.toFixed(2)}
                <span className="text-sm text-muted-foreground ml-1">{currency}</span>
              </span>
            )
            return (
              <div
                key={share.user_id}
                className="border-b border-border last:border-0 hover:bg-muted/50 transition-colors duration-150"
              >
                {/* Phone: one line per player — in the 12 columns the names
                    were cut down to their first letter. */}
                <div className="md:hidden flex items-center gap-3 px-4 py-3">
                  {avatar}
                  <div className="flex-1 min-w-0">
                    <p className="font-sans font-semibold text-sm text-foreground truncate">{share.username}</p>
                    <p className="font-mono-label text-[10px] text-muted-foreground">
                      {share.nights} n · {share.percentage}%
                      {editStay}
                    </p>
                  </div>
                  {amount}
                </div>

                <div className="hidden md:grid grid-cols-12 gap-4 px-4 py-4 items-center">
                  {/* Player */}
                  <div className="col-span-3 flex items-center gap-3 min-w-0">
                    {avatar}
                    <span className="font-sans font-semibold text-sm text-foreground truncate">
                      {share.username}
                    </span>
                  </div>

                  {/* Nights */}
                  <div className="col-span-2 text-center">
                    <span className="font-mono text-foreground font-bold">{share.nights}</span>
                    <span className="font-mono-label text-muted-foreground ml-1">n</span>
                    {editStay}
                  </div>

                  {/* Percentage */}
                  <div className="col-span-2 flex flex-col items-center gap-1">
                    <span className="font-mono text-sm font-bold text-foreground">
                      {share.percentage}%
                    </span>
                  </div>

                  {/* Amount */}
                  <div className="col-span-5 flex items-center justify-end gap-3">
                    {/* Progress bar */}
                    <div className="flex-1 h-1 bg-muted">
                      <div
                        className="h-full bg-accent transition-all duration-500"
                        style={{ width: `${(share.amount / maxAmount) * 100}%` }}
                      />
                    </div>
                    {amount}
                  </div>
                </div>

                {editing === share.user_id && (
                  <div className="px-4 pb-4">
                    <StayEditor
                      data={data}
                      userId={share.user_id}
                      initialArrival={share.arrival_date ?? data.event_start ?? ''}
                      initialDeparture={share.departure_date ?? data.event_end ?? ''}
                      deleted={share.deleted}
                      onDone={doneEditing}
                      onCancel={() => setEditing(null)}
                    />
                  </div>
                )}
              </div>
            )
          })}

          {/* Total row */}
          <div className="grid grid-cols-12 gap-4 px-4 py-4 bg-muted border-t-2 border-accent">
            <div className="col-span-7 font-mono-label text-accent">{t('finances.table.total')}</div>
            <div className="col-span-5 text-right font-mono text-xl font-black text-accent tabular-nums">
              {data.total_expenses.toFixed(2)}
              <span className="text-sm ml-1">{currency}</span>
            </div>
          </div>
        </div>
      )}

      {/* Treasurer: add a member who isn't in the split yet (a latecomer) */}
      {canAdjust && (
        <div className="space-y-2">
          {editing === 'new' ? (
            <div className="border border-border p-4 grid grid-cols-12 gap-2">
              <select
                className="col-span-12 sm:col-span-6 bg-background border border-border px-2 py-1 text-sm text-foreground"
                value={newMember ?? ''}
                onChange={(e) => setNewMember(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">{t('finances.adjust.pickMember')}</option>
                {members
                  .filter((m) => !inSplit.has(m.id) && m.is_active)
                  .map((m) => (
                    <option key={m.id} value={m.id}>{m.username}</option>
                  ))}
              </select>
              {newMember != null ? (
                <StayEditor
                  key={newMember}
                  data={data}
                  userId={newMember}
                  initialArrival={data.event_start ?? ''}
                  initialDeparture={data.event_end ?? ''}
                  onDone={doneEditing}
                  onCancel={() => setEditing(null)}
                />
              ) : (
                <button
                  onClick={() => setEditing(null)}
                  className="col-span-12 text-left font-mono-label text-[11px] text-muted-foreground hover:text-foreground underline"
                >
                  {t('finances.adjust.cancel')}
                </button>
              )}
            </div>
          ) : (
            <button
              onClick={startAdding}
              className="font-mono-label text-[11px] text-muted-foreground hover:text-accent flex items-center gap-1.5"
            >
              <UserPlus size={12} strokeWidth={1.5} /> {t('finances.adjust.add')}
            </button>
          )}
        </div>
      )}

      {/* Who owes whom — settlement */}
      {data.shares.length > 0 && (
        <div className="space-y-6">
          <div>
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
              <p className="font-mono-label text-muted-foreground flex items-center gap-1.5">
                <Wallet size={14} className="text-accent" strokeWidth={1.5} /> {t('finances.settlementTitle')}
              </p>
              {/* Treasurer/admin: transfers (partial, outside the plan, catch-up) and the plan itself */}
              {canAdjust && (
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                  <button
                    onClick={recalculate}
                    disabled={busyKey === 'recalculate'}
                    className="font-mono-label text-[11px] text-muted-foreground hover:text-accent flex items-center gap-1.5 whitespace-nowrap disabled:opacity-50"
                  >
                    <RotateCcw size={12} strokeWidth={1.5} /> {t('finances.transfer.recalculate')}
                  </button>
                  <button
                    onClick={() => setTransferOpen(true)}
                    className="font-mono-label text-[11px] px-3 py-1.5 border border-accent text-accent hover:bg-accent hover:text-accent-foreground transition-colors flex items-center gap-1.5 whitespace-nowrap"
                  >
                    <ArrowLeftRight size={12} strokeWidth={1.5} /> {t('finances.transfer.record')}
                  </button>
                </div>
              )}
            </div>
            {data.plan?.frozen && data.plan.frozen_on && (
              <p className="text-xs text-muted-foreground mb-3 flex items-center gap-1.5">
                <Lock size={11} strokeWidth={1.5} className="flex-shrink-0" />
                {t('finances.transfer.planFrozen', { date: formatDate(data.plan.frozen_on) })}
              </p>
            )}
            {toPay.length === 0 ? (
              <div className="text-center py-10 border border-border">
                <p className="font-mono-label text-muted-foreground">{t('finances.allSettled')}</p>
              </div>
            ) : (
              <div className="border border-border divide-y divide-border">
                {toPay.map((line) => {
                  const isDebtor = user?.id === line.from_user_id
                  const onBehalf = !isDebtor && isTreasurer && !!line.from_inactive
                  const busy = busyKey === `${onBehalf ? line.from_user_id : ''}-${line.to_user_id}`
                  return (
                    <div key={`${line.from_user_id}-${line.to_user_id}`} className="flex flex-wrap items-center gap-3 px-4 py-3">
                      <div className="flex items-center gap-2 text-sm min-w-0">
                        <span className="font-semibold text-foreground truncate">{line.from_username}</span>
                        <ArrowRight size={13} className="text-muted-foreground flex-shrink-0" />
                        <span className="font-semibold text-foreground truncate">{line.to_username}</span>
                      </div>

                      <span className="font-mono font-black text-foreground tabular-nums">
                        {line.amount.toFixed(2)}
                        <span className="text-xs text-muted-foreground ml-1">{currency}</span>
                      </span>

                      {/* Changed by a transfer made outside the plan */}
                      {line.label && (
                        <span
                          title={t('finances.transfer.labelHint')}
                          className="font-mono-label text-[10px] px-1.5 py-0.5 border border-yellow-500/50 text-yellow-400"
                        >
                          {t(`finances.transfer.label.${line.label}`)}
                        </span>
                      )}

                      {/* Creditor's contact phone — shown only to the debtor who owes them */}
                      {isDebtor && line.to_phone && (
                        <a
                          href={`tel:${line.to_phone}`}
                          className="font-mono-label text-accent flex items-center gap-1 text-[11px] hover:underline"
                        >
                          <Phone size={12} strokeWidth={1.5} /> {line.to_phone}
                        </a>
                      )}

                      <div className="ml-auto">
                        {isDebtor || onBehalf ? (
                          <button
                            onClick={() => markPaid(line.to_user_id, onBehalf ? line.from_user_id : undefined)}
                            title={onBehalf ? t('finances.markPaidOnBehalf') : undefined}
                            disabled={busy}
                            className="font-mono-label text-[11px] px-3 py-1.5 border border-accent text-accent hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50"
                          >
                            {t('finances.markPaid')}
                          </button>
                        ) : (
                          <span className="font-mono-label text-muted-foreground text-[11px]">
                            {t('finances.markPaidPending')}
                          </span>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Recorded transfers: one line each, with its date, note and who entered it */}
          {recorded.length > 0 && (
            <div>
              <p className="font-mono-label text-muted-foreground mb-3 flex items-center gap-1.5">
                <Check size={14} className="text-green-500" strokeWidth={1.5} /> {t('finances.transfer.historyTitle')}
              </p>
              <div className="border border-border divide-y divide-border">
                {recorded.map((line) => (
                  <div
                    key={line.transfer_id ?? `flag-${line.from_user_id}-${line.to_user_id}`}
                    className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3"
                  >
                    <span className="font-mono-label text-[10px] text-muted-foreground whitespace-nowrap min-w-[6.5rem] flex-shrink-0">
                      {line.transferred_on ? formatDate(line.transferred_on) : '—'}
                    </span>
                    <div className="flex items-center gap-2 text-sm min-w-0">
                      <span className="font-semibold text-foreground truncate">{line.from_username}</span>
                      <ArrowRight size={13} className="text-muted-foreground flex-shrink-0" />
                      <span className="font-semibold text-foreground truncate">{line.to_username}</span>
                    </div>
                    <span className="font-mono font-black text-green-500 tabular-nums">
                      {line.amount.toFixed(2)}
                      <span className="text-xs text-muted-foreground ml-1">{currency}</span>
                    </span>
                    {line.on_behalf && line.recorded_by_username && (
                      <span className="font-mono-label text-[10px] text-muted-foreground">
                        {t('finances.transfer.recordedBy', { name: line.recorded_by_username })}
                      </span>
                    )}
                    {line.note && <span className="text-xs text-muted-foreground italic truncate">{line.note}</span>}
                    {canDelete(line) && (
                      <button
                        onClick={() => deleteLine(line)}
                        disabled={busyKey === `del-${line.transfer_id ?? `${line.from_user_id}-${line.to_user_id}`}`}
                        title={t('finances.transfer.delete')}
                        aria-label={t('finances.transfer.delete')}
                        className="ml-auto p-1 text-muted-foreground hover:text-red-400 transition-colors disabled:opacity-50"
                      >
                        <Trash2 size={13} strokeWidth={1.5} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {transferOpen && (
        <TransferModal data={data} onClose={() => setTransferOpen(false)} onSaved={() => onSettlementChange?.()} />
      )}
    </div>
  )
}
