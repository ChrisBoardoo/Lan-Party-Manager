import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ProRataResult, User } from '../types'
import { useAppConfig } from '../contexts/AppConfigContext'
import { useAuth } from '../contexts/AuthContext'
import { eventsApi, expensesApi, usersApi } from '../lib/api'
import { Check, ArrowRight, Wallet, Phone, Pencil, UserPlus } from 'lucide-react'

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
  onDone,
  onCancel,
}: {
  data: ProRataResult
  userId: number
  initialArrival: string
  initialDeparture: string
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
    } catch (e: any) {
      setError(t('finances.adjust.failed', { detail: e.response?.data?.detail ?? '' }))
    } finally {
      setBusy(false)
    }
  }

  const dateInput = 'bg-background border border-border px-2 py-1 font-mono text-xs text-foreground'
  return (
    <div className="col-span-12 flex flex-wrap items-end gap-3 pt-2">
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
      <p className="w-full text-[10px] text-muted-foreground">{t('finances.adjust.hint')}</p>
      {error && <p className="w-full font-mono-label text-[10px] text-red-400">{error}</p>}
    </div>
  )
}

export default function ProRataTable({ data, onSettlementChange }: ProRataTableProps) {
  const { t } = useTranslation()
  const { currency } = useAppConfig()
  const { user, isTreasurer } = useAuth()
  const [busyKey, setBusyKey] = useState<string | null>(null)
  // user id whose stay is being edited; 'new' = adding a member not in the split yet
  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const [members, setMembers] = useState<User[]>([])
  const [newMember, setNewMember] = useState<number | null>(null)
  const maxAmount = Math.max(...data.shares.map((s) => s.amount), 1)
  const canAdjust = isTreasurer && data.event_id != null

  const togglePaid = async (toUserId: number, paid: boolean) => {
    if (data.event_id == null) return
    const key = `${toUserId}`
    setBusyKey(key)
    try {
      if (paid) {
        await expensesApi.unmarkSettlement(data.event_id, toUserId)
      } else {
        await expensesApi.markSettlement(data.event_id, toUserId)
      }
      onSettlementChange?.()
    } finally {
      setBusyKey(null)
    }
  }

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
          {/* Header */}
          <div className="grid grid-cols-12 gap-4 px-4 py-3 bg-muted border-b border-border">
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

          {data.shares.map((share) => (
            <div
              key={share.user_id}
              className="grid grid-cols-12 gap-4 px-4 py-4 items-center border-b border-border last:border-0 hover:bg-muted/50 transition-colors duration-150"
            >
              {/* Player */}
              <div className="col-span-3 flex items-center gap-3">
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
                <span className="font-sans font-semibold text-sm text-foreground truncate">
                  {share.username}
                </span>
              </div>

              {/* Nights */}
              <div className="col-span-2 text-center">
                <span className="font-mono text-foreground font-bold">{share.nights}</span>
                <span className="font-mono-label text-muted-foreground ml-1">n</span>
                {canAdjust && editing !== share.user_id && (
                  <button
                    onClick={() => setEditing(share.user_id)}
                    title={t('finances.adjust.edit')}
                    className="ml-2 text-muted-foreground hover:text-accent align-middle"
                  >
                    <Pencil size={11} strokeWidth={1.5} />
                  </button>
                )}
              </div>

              {/* Percentage bar */}
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
                <span className="font-mono text-xl font-black text-foreground tabular-nums">
                  {share.amount.toFixed(2)}
                  <span className="text-sm text-muted-foreground ml-1">{currency}</span>
                </span>
              </div>

              {editing === share.user_id && (
                <StayEditor
                  data={data}
                  userId={share.user_id}
                  initialArrival={share.arrival_date ?? data.event_start ?? ''}
                  initialDeparture={share.departure_date ?? data.event_end ?? ''}
                  onDone={doneEditing}
                  onCancel={() => setEditing(null)}
                />
              )}
            </div>
          ))}

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
        <div>
          <p className="font-mono-label text-muted-foreground mb-3 flex items-center gap-1.5">
            <Wallet size={14} className="text-accent" strokeWidth={1.5} /> {t('finances.settlementTitle')}
          </p>
          {data.settlements.length === 0 ? (
            <div className="text-center py-10 border border-border">
              <p className="font-mono-label text-muted-foreground">{t('finances.allSettled')}</p>
            </div>
          ) : (
            <div className="border border-border divide-y divide-border">
              {data.settlements.map((line) => {
                const isDebtor = user?.id === line.from_user_id
                const busy = busyKey === `${line.to_user_id}`
                return (
                  <div
                    // A pair can have a recorded payment *and* a line still owed
                    // (e.g. a receipt added after the payment).
                    key={`${line.from_user_id}-${line.to_user_id}-${line.paid ? `paid-${line.payment_id ?? ''}` : 'owed'}`}
                    className="flex flex-wrap items-center gap-3 px-4 py-3"
                  >
                    <div className="flex items-center gap-2 text-sm min-w-0">
                      <span className="font-semibold text-foreground truncate">{line.from_username}</span>
                      <ArrowRight size={13} className="text-muted-foreground flex-shrink-0" />
                      <span className="font-semibold text-foreground truncate">{line.to_username}</span>
                    </div>

                    <span className="font-mono font-black text-foreground tabular-nums">
                      {line.amount.toFixed(2)}
                      <span className="text-xs text-muted-foreground ml-1">{currency}</span>
                    </span>

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
                      {isDebtor ? (
                        <button
                          onClick={() => togglePaid(line.to_user_id, line.paid)}
                          disabled={busy}
                          className={`font-mono-label text-[11px] px-3 py-1.5 border transition-colors disabled:opacity-50 ${
                            line.paid
                              ? 'border-green-500 text-green-500 hover:border-red-400 hover:text-red-400'
                              : 'border-accent text-accent hover:bg-accent hover:text-accent-foreground'
                          }`}
                        >
                          {line.paid ? (
                            <span className="flex items-center gap-1"><Check size={12} /> {t('finances.paymentSent')}</span>
                          ) : (
                            t('finances.markPaid')
                          )}
                        </button>
                      ) : line.paid ? (
                        <span className="font-mono-label text-green-500 flex items-center gap-1 text-[11px]">
                          <Check size={12} /> {t('finances.paymentSent')}
                        </span>
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
      )}
    </div>
  )
}
