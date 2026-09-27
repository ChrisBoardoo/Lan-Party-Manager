import { Fragment, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import { planningApi, eventsApi } from '../lib/api'
import { LanEvent, PlanningEvent, PlanningScheduleView, ScheduleBlock } from '../types'
import { formatDate } from '../lib/formatDate'
import { CALENDAR_PALETTE, defaultColorKeyFor, swatchFor } from '../lib/calendarColors'
import i18n from '../i18n'
import Button from '../components/ui/Button'
import {
  CalendarClock, CalendarDays, ChevronDown, ChevronUp, List, Plus, Trash2, Lock, Unlock, X,
} from 'lucide-react'

// LAN-friendly hour window for the MVP grid (10:00 → 23:00). Configurable range
// is a deferred enhancement.
const HOURS = Array.from({ length: 14 }, (_, i) => i + 10)

export function daysBetween(startISO: string, endISO: string): string[] {
  const days: string[] = []
  const d = new Date(startISO + 'T00:00:00Z')
  const end = new Date(endISO + 'T00:00:00Z')
  while (d <= end) {
    days.push(d.toISOString().slice(0, 10))
    d.setUTCDate(d.getUTCDate() + 1)
  }
  return days
}

export function slotISO(day: string, hour: number): string {
  return `${day}T${String(hour).padStart(2, '0')}:00:00`
}

export function hourLabel(hour: number): string {
  return `${String(hour % 24).padStart(2, '0')}:00`
}

// `locked_start`/`locked_end` are naive "YYYY-MM-DDTHH:MM:SS" strings (no
// timezone — see slotISO), so hour extraction is a straight slice, not a
// `Date` parse, and lexicographic string comparison is chronological. This
// matches ScheduleView's existing sort (`.localeCompare` on the same strings).
export function hourOf(iso: string): number {
  return Number(iso.slice(11, 13))
}

export function nowNaiveISO(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:00`
}

export function dayHeader(day: string): string {
  const locale = i18n.language?.startsWith('fr') ? 'fr-FR' : 'en-GB'
  return new Date(day + 'T00:00:00Z').toLocaleDateString(locale, {
    weekday: 'short', day: '2-digit', timeZone: 'UTC',
  })
}

export default function Planning() {
  const { user } = useAuth()
  const { t } = useTranslation()
  const isAdmin = user?.role === 'admin'

  const [events, setEvents] = useState<LanEvent[]>([])
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null)
  const [data, setData] = useState<PlanningEvent | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'vote' | 'schedule'>('vote')
  const [newGame, setNewGame] = useState('')
  const [proposing, setProposing] = useState(false)
  const [scheduleView, setScheduleView] = useState<PlanningScheduleView>('list')

  // Load events once, pick the soonest upcoming (else most recent) by default.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const evts = await eventsApi.getAll()
        if (cancelled) return
        setEvents(evts)
        const todayISO = new Date().toISOString().slice(0, 10)
        const upcoming = evts
          .filter((e) => e.end_date >= todayISO)
          .sort((a, b) => a.start_date.localeCompare(b.start_date))
        const chosen = upcoming[0] ?? [...evts].sort((a, b) => b.start_date.localeCompare(a.start_date))[0]
        setSelectedEventId(chosen ? chosen.id : null)
        if (!chosen) setLoading(false)
      } catch {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  // (Re)load the planning payload whenever the selected event changes.
  useEffect(() => {
    if (selectedEventId == null) return
    let cancelled = false
    setLoading(true)
    ;(async () => {
      try {
        const payload = await planningApi.getEvent(selectedEventId)
        if (!cancelled) setData(payload)
      } catch {
        if (!cancelled) setData(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [selectedEventId])

  // Adopt the account's saved preference whenever it changes (a real reload,
  // not the optimistic `data` updates from voting/locking — those don't touch
  // `my_schedule_view`, so this effect stays quiet during them).
  useEffect(() => {
    if (data?.my_schedule_view) setScheduleView(data.my_schedule_view)
  }, [data?.my_schedule_view])

  const changeScheduleView = (view: PlanningScheduleView) => {
    setScheduleView(view)
    planningApi.setViewPreference(view).catch(() => { /* best-effort — worst case it just doesn't stick */ })
  }

  const replaceBlock = (updated: ScheduleBlock) =>
    setData((d) => (d ? { ...d, blocks: d.blocks.map((b) => (b.id === updated.id ? updated : b)) } : d))

  const canManage = (block: ScheduleBlock) => isAdmin || (!!user && block.created_by === user.id)

  const dayInMyWindow = (day: string): boolean => {
    if (!data || !data.is_attending) return false
    const lo = data.my_arrival_date ?? data.event_start
    const hi = data.my_departure_date ?? data.event_end
    return day >= lo && day <= hi
  }

  const handlePropose = async () => {
    const game = newGame.trim()
    if (!game || selectedEventId == null) return
    setProposing(true)
    try {
      const block = await planningApi.proposeBlock(selectedEventId, { game })
      setData((d) => (d ? { ...d, blocks: [...d.blocks, block] } : d))
      setNewGame('')
    } finally {
      setProposing(false)
    }
  }

  const toggleSlot = async (block: ScheduleBlock, slot: string) => {
    const has = block.my_slots.includes(slot)
    const next = has ? block.my_slots.filter((s) => s !== slot) : [...block.my_slots, slot]
    try {
      const updated = await planningApi.setVotes(block.id, next)
      replaceBlock(updated)
    } catch { /* rejected slot / disabled — leave state unchanged */ }
  }

  const handleDelete = async (block: ScheduleBlock) => {
    if (!confirm(t('planning.deleteConfirm', { game: block.game }))) return
    await planningApi.deleteBlock(block.id)
    setData((d) => (d ? { ...d, blocks: d.blocks.filter((b) => b.id !== block.id) } : d))
  }

  const days = data ? daysBetween(data.event_start, data.event_end) : []
  const proposed = data ? data.blocks.filter((b) => b.status === 'proposed') : []
  const locked = data ? data.blocks.filter((b) => b.status === 'locked') : []
  const canPropose = !!data && (data.can_propose || isAdmin)

  return (
    <main className="max-w-6xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="flex items-center gap-3 mb-2">
        <CalendarClock size={22} strokeWidth={1.5} className="text-accent" />
        <h1 className="text-3xl font-black tracking-tight text-foreground">{t('planning.title')}</h1>
      </div>
      <p className="text-sm text-muted-foreground mb-8 max-w-2xl">{t('planning.subtitle')}</p>

      {/* Event switcher */}
      {events.length > 0 && (
        <div className="mb-8 flex items-center gap-3 flex-wrap">
          <span className="font-mono-label text-muted-foreground">{t('planning.event')}</span>
          <select
            value={selectedEventId ?? ''}
            onChange={(e) => setSelectedEventId(Number(e.target.value))}
            className="h-9 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none"
          >
            {events.map((e) => (
              <option key={e.id} value={e.id}>
                {e.title} — {formatDate(e.start_date)}
              </option>
            ))}
          </select>
        </div>
      )}

      {loading ? (
        <div className="p-12 text-center">
          <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
        </div>
      ) : !data ? (
        <div className="border border-border bg-card p-12 text-center">
          <p className="text-muted-foreground">{t('planning.noEvents')}</p>
        </div>
      ) : (
        <>
          {/* Tabs */}
          <div className="flex border-b border-border mb-8">
            {(['vote', 'schedule'] as const).map((key) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                className={`px-5 py-3 font-mono-label transition-colors -mb-px border-b-2 ${
                  tab === key ? 'text-accent border-accent' : 'text-muted-foreground border-transparent hover:text-foreground'
                }`}
              >
                {t(`planning.tab.${key}`)}
              </button>
            ))}
          </div>

          {tab === 'vote' ? (
            <>
              {/* Propose */}
              {canPropose ? (
                <div className="flex items-center gap-2 mb-6">
                  <input
                    value={newGame}
                    onChange={(e) => setNewGame(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handlePropose() }}
                    placeholder={t('planning.proposePlaceholder')}
                    maxLength={120}
                    className="flex-1 max-w-sm h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none"
                  />
                  <Button size="sm" onClick={handlePropose} disabled={proposing || !newGame.trim()}>
                    <Plus size={14} /> {t('planning.propose')}
                  </Button>
                </div>
              ) : (
                <p className="font-mono-label text-muted-foreground mb-6">{t('planning.proposingDisabled')}</p>
              )}

              {/* Voting note */}
              {!data.is_attending && (
                <p className="text-sm text-accent mb-6">{t('planning.rsvpToVote')}</p>
              )}
              {data.is_attending && !data.can_vote && !isAdmin && (
                <p className="text-sm text-muted-foreground mb-6">{t('planning.votingDisabled')}</p>
              )}

              {proposed.length === 0 ? (
                <div className="border border-border bg-card p-12 text-center">
                  <p className="text-muted-foreground">{t('planning.noBlocks')}</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {proposed.map((block) => (
                    <BlockGrid
                      key={block.id}
                      block={block}
                      days={days}
                      dayInMyWindow={dayInMyWindow}
                      votable={(data.can_vote || isAdmin) && data.is_attending}
                      canManage={canManage(block)}
                      onToggle={(slot) => toggleSlot(block, slot)}
                      onDelete={() => handleDelete(block)}
                      onLock={replaceBlock}
                    />
                  ))}
                </div>
              )}
            </>
          ) : (
            <>
              <div className="flex items-center justify-end gap-1 mb-4">
                {(['list', 'calendar'] as const).map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => changeScheduleView(v)}
                    aria-pressed={scheduleView === v}
                    title={t(`planning.calendar.view.${v}`)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 font-mono-label text-[10px] border transition-colors ${
                      scheduleView === v
                        ? 'border-accent text-accent'
                        : 'border-border text-muted-foreground hover:text-foreground hover:border-border-hover'
                    }`}
                  >
                    {v === 'list' ? <List size={12} strokeWidth={1.5} /> : <CalendarDays size={12} strokeWidth={1.5} />}
                    {t(`planning.calendar.view.${v}`)}
                  </button>
                ))}
              </div>
              {scheduleView === 'calendar' ? (
                <CalendarView blocks={locked} days={days} canManage={canManage} onChange={replaceBlock} />
              ) : (
                <ScheduleView blocks={locked} canManage={canManage} onChange={replaceBlock} />
              )}
            </>
          )}
        </>
      )}
    </main>
  )
}

// ── Voting grid for one proposed game ────────────────────────────────────────────

function BlockGrid({
  block, days, dayInMyWindow, votable, canManage, onToggle, onDelete, onLock,
}: {
  block: ScheduleBlock
  days: string[]
  dayInMyWindow: (day: string) => boolean
  votable: boolean
  canManage: boolean
  onToggle: (slot: string) => void
  onDelete: () => void
  onLock: (updated: ScheduleBlock) => void
}) {
  const { t } = useTranslation()
  const [locking, setLocking] = useState(false)
  // Collapsed by default — a full day×hour grid per proposed game gets long
  // fast once a few games are on the table, so each one opens on demand
  // instead of forcing a scroll through every calendar to find the one you
  // want to vote on.
  const [expanded, setExpanded] = useState(false)

  const counts: Record<string, number> = {}
  for (const tally of block.tallies) counts[tally.slot_start] = tally.count
  const mine = new Set(block.my_slots)
  const maxCount = Math.max(1, ...block.tallies.map((tl) => tl.count))
  const best = block.tallies.reduce<{ slot: string; count: number } | null>(
    (acc, tl) => (!acc || tl.count > acc.count ? { slot: tl.slot_start, count: tl.count } : acc), null,
  )
  const voteTotal = block.tallies.reduce((sum, tl) => sum + tl.count, 0)

  return (
    <div className="border border-border bg-card">
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-border">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          title={t(expanded ? 'planning.hideCalendar' : 'planning.showCalendar')}
          className="flex items-center gap-2 min-w-0 flex-1 text-left group"
        >
          {expanded ? (
            <ChevronUp size={14} strokeWidth={1.5} className="text-muted-foreground group-hover:text-foreground transition-colors flex-shrink-0" />
          ) : (
            <ChevronDown size={14} strokeWidth={1.5} className="text-muted-foreground group-hover:text-foreground transition-colors flex-shrink-0" />
          )}
          <span className="font-black text-lg tracking-tight text-foreground truncate">{block.game}</span>
          {best && best.count > 0 && (
            <span className="font-mono-label text-muted-foreground text-[10px] hidden sm:inline">
              {t('planning.best')}: {dayHeader(best.slot.slice(0, 10))} {best.slot.slice(11, 16)} · {best.count}
            </span>
          )}
          {!expanded && voteTotal > 0 && (
            <span className="font-mono-label text-accent text-[10px] flex-shrink-0">
              {t('planning.voteCount', { count: voteTotal })}
            </span>
          )}
        </button>
        {canManage && (
          <div className="flex items-center gap-1 flex-shrink-0">
            <button
              onClick={() => { setLocking((v) => !v); if (!locking) setExpanded(true) }}
              className="flex items-center gap-1 px-2 py-1 font-mono-label text-[10px] text-muted-foreground hover:text-accent border border-border hover:border-accent transition-colors"
            >
              <Lock size={11} /> {t('planning.lock')}
            </button>
            <button
              onClick={onDelete}
              className="p-1.5 text-muted-foreground hover:text-red-400 transition-colors"
              title={t('common.delete')}
            >
              <Trash2 size={13} strokeWidth={1.5} />
            </button>
          </div>
        )}
      </div>

      {locking && <LockEditor block={block} days={days} onClose={() => setLocking(false)} onLocked={(u) => { onLock(u); setLocking(false) }} />}

      {/* day × hour grid */}
      {expanded && (
      <div className="p-4 overflow-x-auto">
        <div
          className="inline-grid gap-px bg-border border border-border"
          style={{ gridTemplateColumns: `56px repeat(${days.length}, minmax(60px, 1fr))` }}
        >
          <div className="bg-card" />
          {days.map((day) => (
            <div key={day} className="bg-card px-2 py-1.5 text-center font-mono-label text-[10px] text-muted-foreground whitespace-nowrap">
              {dayHeader(day)}
            </div>
          ))}
          {HOURS.map((hour) => (
            <Fragment key={hour}>
              <div className="bg-card px-2 py-1.5 text-right font-mono-label text-[10px] text-muted-foreground tabular-nums">
                {hourLabel(hour)}
              </div>
              {days.map((day) => {
                const slot = slotISO(day, hour)
                const count = counts[slot] ?? 0
                const isMine = mine.has(slot)
                const editable = votable && dayInMyWindow(day)
                const alpha = count > 0 ? 0.12 + 0.55 * (count / maxCount) : 0
                return (
                  <button
                    key={slot}
                    type="button"
                    disabled={!editable}
                    onClick={() => onToggle(slot)}
                    title={count > 0 ? `${count}` : undefined}
                    className={`h-7 flex items-center justify-center text-[10px] font-mono tabular-nums transition-colors ${
                      editable ? 'cursor-pointer hover:bg-muted' : 'cursor-default'
                    } ${isMine ? 'outline outline-1 -outline-offset-1 outline-accent text-foreground' : 'text-muted-foreground'} ${
                      editable ? 'bg-input' : 'bg-card'
                    }`}
                    style={count > 0 ? { backgroundColor: `rgba(255,61,0,${alpha})` } : undefined}
                  >
                    {count > 0 ? count : ''}
                  </button>
                )
              })}
            </Fragment>
          ))}
        </div>
      </div>
      )}
    </div>
  )
}

// ── Inline lock editor (organizer picks a final window) ──────────────────────────

function LockEditor({
  block, days, onClose, onLocked,
}: {
  block: ScheduleBlock
  days: string[]
  onClose: () => void
  onLocked: (updated: ScheduleBlock) => void
}) {
  const { t } = useTranslation()
  const [day, setDay] = useState(days[0] ?? '')
  const [start, setStart] = useState(HOURS[0])
  const [end, setEnd] = useState(HOURS[Math.min(2, HOURS.length - 1)])
  const [color, setColor] = useState(() => defaultColorKeyFor(block.game))
  const [saving, setSaving] = useState(false)

  const save = async () => {
    if (end <= start || !day) return
    setSaving(true)
    try {
      const updated = await planningApi.lockBlock(block.id, {
        locked_start: slotISO(day, start),
        locked_end: slotISO(day, end),
        color,
      })
      onLocked(updated)
    } finally {
      setSaving(false)
    }
  }

  const selectCls = 'h-9 px-2 bg-input border border-border text-foreground text-sm focus:border-accent outline-none'

  return (
    <div className="flex items-end gap-2 flex-wrap px-4 py-3 border-b border-border bg-muted/30">
      <label className="flex flex-col gap-1">
        <span className="font-mono-label text-[10px] text-muted-foreground">{t('planning.day')}</span>
        <select value={day} onChange={(e) => setDay(e.target.value)} className={selectCls}>
          {days.map((d) => <option key={d} value={d}>{dayHeader(d)}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="font-mono-label text-[10px] text-muted-foreground">{t('planning.start')}</span>
        <select value={start} onChange={(e) => setStart(Number(e.target.value))} className={selectCls}>
          {HOURS.map((h) => <option key={h} value={h}>{hourLabel(h)}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="font-mono-label text-[10px] text-muted-foreground">{t('planning.end')}</span>
        <select value={end} onChange={(e) => setEnd(Number(e.target.value))} className={selectCls}>
          {HOURS.filter((h) => h > start).map((h) => <option key={h} value={h}>{hourLabel(h)}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="font-mono-label text-[10px] text-muted-foreground">{t('planning.color')}</span>
        <div className="flex items-center gap-1 flex-wrap max-w-[200px] h-9">
          {CALENDAR_PALETTE.map((swatch) => (
            <button
              key={swatch.key}
              type="button"
              onClick={() => setColor(swatch.key)}
              title={t(`planning.colors.${swatch.key}`)}
              aria-label={t(`planning.colors.${swatch.key}`)}
              aria-pressed={color === swatch.key}
              className={`w-5 h-5 flex-shrink-0 transition-shadow ${
                color === swatch.key ? 'ring-2 ring-offset-1 ring-offset-muted ring-foreground' : ''
              }`}
              style={{ backgroundColor: swatch.hex }}
            />
          ))}
        </div>
      </label>
      <Button size="sm" onClick={save} disabled={saving || end <= start}>{t('planning.confirmLock')}</Button>
      <button onClick={onClose} className="p-2 text-muted-foreground hover:text-foreground" title={t('common.cancel')}>
        <X size={14} />
      </button>
    </div>
  )
}

// ── Read-only locked schedule ────────────────────────────────────────────────────

function ScheduleView({
  blocks, canManage, onChange,
}: {
  blocks: ScheduleBlock[]
  canManage: (block: ScheduleBlock) => boolean
  onChange: (updated: ScheduleBlock) => void
}) {
  const { t } = useTranslation()

  if (blocks.length === 0) {
    return (
      <div className="border border-border bg-card p-12 text-center">
        <p className="text-muted-foreground">{t('planning.noLocked')}</p>
      </div>
    )
  }

  const sorted = [...blocks].sort((a, b) => (a.locked_start ?? '').localeCompare(b.locked_start ?? ''))

  const unlock = async (block: ScheduleBlock) => {
    const updated = await planningApi.unlockBlock(block.id)
    onChange(updated)
  }

  return (
    <div className="space-y-2">
      {sorted.map((block) => (
        <div key={block.id} className="flex items-center justify-between gap-3 border border-border bg-card px-4 py-4">
          <div className="flex items-center gap-4 min-w-0">
            <div className="w-1 h-10 bg-accent flex-shrink-0" />
            <div className="min-w-0">
              <p className="font-black text-lg tracking-tight text-foreground truncate">{block.game}</p>
              {block.locked_start && (
                <p className="font-mono-label text-[11px] text-accent mt-0.5">
                  {dayHeader(block.locked_start.slice(0, 10))} · {block.locked_start.slice(11, 16)}
                  {block.locked_end ? `–${block.locked_end.slice(11, 16)}` : ''}
                </p>
              )}
            </div>
          </div>
          {canManage(block) && (
            <button
              onClick={() => unlock(block)}
              className="flex items-center gap-1 px-2 py-1 font-mono-label text-[10px] text-muted-foreground hover:text-accent border border-border hover:border-accent transition-colors flex-shrink-0"
            >
              <Unlock size={11} /> {t('planning.unlock')}
            </button>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Google-Calendar-style grid view of the locked schedule ───────────────────────
// Deliberate break from the app's otherwise sharp-cornered, single-accent-color
// design system — see md/calendarview.md. Colored, rounded event chips only
// live here.

const ROW_HEIGHT = 40 // px per hour row

type CalendarEntry = { block: ScheduleBlock; day: string; start: number; end: number }

function CalendarView({
  blocks, days, canManage, onChange,
}: {
  blocks: ScheduleBlock[]
  days: string[]
  canManage: (block: ScheduleBlock) => boolean
  onChange: (updated: ScheduleBlock) => void
}) {
  const { t } = useTranslation()
  const [now, setNow] = useState(() => new Date())
  const [selectedId, setSelectedId] = useState<number | null>(null)

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000)
    return () => clearInterval(id)
  }, [])

  const entries: CalendarEntry[] = useMemo(() => blocks
    .filter((b): b is ScheduleBlock & { locked_start: string; locked_end: string } =>
      !!b.locked_start && !!b.locked_end)
    .map((b) => {
      const start = hourOf(b.locked_start)
      let end = hourOf(b.locked_end)
      // Defensive only — today's LockEditor can't produce this (same-day,
      // end > start), but a directly-edited row shouldn't break the grid.
      if (end <= start) end += 24
      return { block: b, day: b.locked_start.slice(0, 10), start, end }
    }), [blocks])

  const minHour = entries.length ? Math.max(0, Math.min(...entries.map((e) => e.start)) - 1) : 0
  const maxHour = entries.length ? Math.min(30, Math.max(...entries.map((e) => e.end)) + 1) : 0
  const hours = useMemo(
    () => Array.from({ length: Math.max(0, maxHour - minHour) }, (_, i) => i + minHour),
    [minHour, maxHour],
  )

  const nowStr = nowNaiveISO(now)
  const todayISO = nowStr.slice(0, 10)
  const nextEntry = entries
    .filter((e) => e.block.locked_end! > nowStr)
    .sort((a, b) => (a.block.locked_start ?? '').localeCompare(b.block.locked_start ?? ''))[0]
  const nowFraction = now.getHours() + now.getMinutes() / 60 - minHour

  const selected = entries.find((e) => e.block.id === selectedId)?.block ?? null

  const unlock = async (block: ScheduleBlock) => {
    const updated = await planningApi.unlockBlock(block.id)
    onChange(updated)
    setSelectedId(null)
  }

  if (blocks.length === 0) {
    return (
      <div className="border border-border bg-card p-12 text-center">
        <p className="text-muted-foreground">{t('planning.noLocked')}</p>
      </div>
    )
  }

  return (
    <div className="border border-border bg-card">
      {nextEntry && (
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-muted/30">
          <span className="w-2 h-2 rounded-full bg-accent flex-shrink-0 animate-pulse" />
          <span className="font-mono-label text-[10px] text-muted-foreground">{t('planning.calendar.nextUp')}</span>
          <span className="text-sm font-semibold text-foreground truncate">{nextEntry.block.game}</span>
          <span className="font-mono-label text-[10px] text-accent tabular-nums flex-shrink-0">
            {dayHeader(nextEntry.day)} · {hourLabel(nextEntry.start)}–{hourLabel(nextEntry.end)}
          </span>
        </div>
      )}

      <div className="p-4 overflow-x-auto">
        <div className="inline-flex" style={{ minWidth: '100%' }}>
          {/* Hour gutter */}
          <div className="flex-shrink-0" style={{ width: 48 }}>
            <div style={{ height: 28 }} />
            {hours.map((h) => (
              <div
                key={h}
                style={{ height: ROW_HEIGHT }}
                className="flex items-start justify-end pr-2 -translate-y-2 font-mono-label text-[10px] text-muted-foreground tabular-nums"
              >
                {hourLabel(h)}
              </div>
            ))}
          </div>

          {/* Day columns */}
          {days.map((day) => {
            const dayEntries = entries.filter((e) => e.day === day)
            const isToday = day === todayISO && nowFraction >= 0 && nowFraction <= hours.length
            return (
              <div key={day} className="flex-1 min-w-[130px] border-l border-border">
                <div
                  style={{ height: 28 }}
                  className="px-2 flex items-center justify-center font-mono-label text-[10px] text-muted-foreground border-b border-border whitespace-nowrap"
                >
                  {dayHeader(day)}
                </div>
                <div className="relative" style={{ height: hours.length * ROW_HEIGHT }}>
                  {hours.map((h, i) => (
                    <div key={h} className="absolute left-0 right-0 border-t border-border/60" style={{ top: i * ROW_HEIGHT }} />
                  ))}
                  {isToday && (
                    <div className="absolute left-0 right-0 z-10 flex items-center" style={{ top: nowFraction * ROW_HEIGHT }}>
                      <span className="w-1.5 h-1.5 rounded-full bg-accent -ml-0.5 flex-shrink-0" />
                      <span className="flex-1 h-px bg-accent" />
                    </div>
                  )}
                  {dayEntries.map(({ block, start, end }) => {
                    const swatch = swatchFor(block.color, block.game)
                    const isNext = nextEntry?.block.id === block.id
                    return (
                      <button
                        key={block.id}
                        type="button"
                        onClick={() => setSelectedId((id) => (id === block.id ? null : block.id))}
                        className={`absolute left-1 right-1 rounded px-2 py-1 text-left overflow-hidden transition-shadow ${
                          isNext ? 'ring-2 ring-accent ring-offset-1 ring-offset-card' : ''
                        } ${selectedId === block.id ? 'outline outline-2 outline-foreground' : ''}`}
                        style={{
                          top: (start - minHour) * ROW_HEIGHT + 1,
                          height: (end - start) * ROW_HEIGHT - 2,
                          backgroundColor: swatch.hex,
                          color: swatch.textHex,
                        }}
                      >
                        <span className="block text-xs font-semibold leading-tight truncate">{block.game}</span>
                        <span className="block font-mono text-[10px] opacity-80 tabular-nums">
                          {hourLabel(start)}–{hourLabel(end)}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {selected && (
        <div className="flex items-center justify-between gap-3 px-4 py-3 border-t border-border bg-muted/30">
          <div className="min-w-0">
            <p className="font-black tracking-tight text-foreground truncate">{selected.game}</p>
            {selected.locked_start && (
              <p className="font-mono-label text-[11px] text-accent mt-0.5">
                {dayHeader(selected.locked_start.slice(0, 10))} · {selected.locked_start.slice(11, 16)}
                {selected.locked_end ? `–${selected.locked_end.slice(11, 16)}` : ''}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {canManage(selected) && (
              <button
                onClick={() => unlock(selected)}
                className="flex items-center gap-1 px-2 py-1 font-mono-label text-[10px] text-muted-foreground hover:text-accent border border-border hover:border-accent transition-colors"
              >
                <Unlock size={11} /> {t('planning.unlock')}
              </button>
            )}
            <button onClick={() => setSelectedId(null)} className="p-1.5 text-muted-foreground hover:text-foreground" title={t('common.cancel')}>
              <X size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
