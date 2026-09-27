import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Award, Check, Eye, EyeOff, Lock, Pause, Play, Plus, RotateCcw, Trash2, Vote, X } from 'lucide-react'
import { trophiesApi } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import type { EventAttendee, LanEvent, Trophy, TrophyEdition, TrophyMode } from '../../types'
import Badge from '../ui/Badge'
import Button from '../ui/Button'
import TrophyIcon from './TrophyIcon'

// The event page's trophies: admins put trophies from the cabinet in play and
// run them (open/close the vote, pick or adjust winners, reveal); attendees
// vote; everyone sees the revealed winners. The server enforces every rule —
// this only shows the actions that make sense for the current status.

function Avatar({ name, url, size = 'w-6 h-6' }: { name: string; url: string | null; size?: string }) {
  return url ? (
    <img src={url} alt="" className={`${size} object-cover shrink-0`} />
  ) : (
    <span className={`${size} bg-muted flex items-center justify-center font-black text-xs shrink-0`}>
      {name.charAt(0).toUpperCase()}
    </span>
  )
}

function WinnersList({ edition }: { edition: TrophyEdition }) {
  return (
    <div className="space-y-2">
      {edition.winners.map((w) => (
        <div key={w.user_id} className="flex items-start gap-3">
          <Avatar name={w.username} url={w.avatar_url} size="w-8 h-8" />
          <div className="min-w-0">
            <p className="font-bold text-foreground">
              {w.username}
              {w.vote_count != null && <span className="font-mono-label text-muted-foreground text-[10px] ml-2">{w.vote_count} 🗳️</span>}
            </p>
            {w.citation && <p className="text-sm text-muted-foreground italic">« {w.citation} »</p>}
          </div>
        </div>
      ))}
    </div>
  )
}

function Ballot({
  edition,
  nominees,
  onVoted,
}: {
  edition: TrophyEdition
  nominees: EventAttendee[]
  onVoted: (e: TrophyEdition) => void
}) {
  const { t } = useTranslation()
  const { push } = useToast()
  const [busy, setBusy] = useState(false)

  const vote = async (nomineeId: number) => {
    setBusy(true)
    try {
      onVoted(await trophiesApi.vote(edition.id, nomineeId))
    } catch {
      push(t('trophies.voteFailed'), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <p className="font-mono-label text-muted-foreground text-[10px] mb-2">
        {edition.my_vote ? t('trophies.youVoted') : t('trophies.castYourVote')}
      </p>
      <div className="flex flex-wrap gap-2">
        {nominees.map((a) => {
          const mine = edition.my_vote === a.user_id
          return (
            <button
              key={a.user_id}
              disabled={busy}
              onClick={() => !mine && vote(a.user_id)}
              aria-pressed={mine}
              className={`flex items-center gap-2 px-2 py-1.5 border text-sm transition-colors disabled:opacity-50 ${
                mine ? 'border-accent bg-accent/10 text-accent' : 'border-border text-foreground hover:border-border-hover'
              }`}
            >
              <Avatar name={a.username} url={a.avatar_url} />
              {a.username}
              {mine && <Check size={12} />}
            </button>
          )
        })}
      </div>
    </div>
  )
}

interface WinnerRow { user_id: number; citation: string }

function WinnersEditor({
  edition,
  attendees,
  onChange,
}: {
  edition: TrophyEdition
  attendees: EventAttendee[]
  onChange: (e: TrophyEdition) => void
}) {
  const { t } = useTranslation()
  const { push } = useToast()
  const initial = (): WinnerRow[] => edition.winners.map((w) => ({ user_id: w.user_id, citation: w.citation ?? '' }))
  const [rows, setRows] = useState<WinnerRow[]>(initial)
  const [discord, setDiscord] = useState(false)
  const [busy, setBusy] = useState(false)

  // Server-side changes (close → proposed winners) reset the editor.
  useEffect(() => { setRows(initial()) }, [edition.id, edition.status, JSON.stringify(edition.winners)])

  const byId = new Map(attendees.map((a) => [a.user_id, a]))
  const nameOf = (uid: number) =>
    byId.get(uid)?.username ?? edition.winners.find((w) => w.user_id === uid)?.username ?? '?'
  const avatarOf = (uid: number) =>
    byId.get(uid)?.avatar_url ?? edition.winners.find((w) => w.user_id === uid)?.avatar_url ?? null
  const dirty = JSON.stringify(rows) !== JSON.stringify(initial())
  const candidates = attendees.filter((a) => !rows.some((r) => r.user_id === a.user_id))

  const save = async () => {
    const updated = await trophiesApi.setWinners(
      edition.id, rows.map((r) => ({ user_id: r.user_id, citation: r.citation.trim() || null })),
    )
    onChange(updated)
    return updated
  }

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    try {
      await fn()
    } catch {
      push(t('trophies.actionFailed'), 'error')
    } finally {
      setBusy(false)
    }
  }

  const reveal = () => run(async () => {
    if (!confirm(t('trophies.revealConfirm', { name: edition.trophy.name }))) return
    if (dirty) await save()
    onChange(await trophiesApi.reveal(edition.id, discord))
  })

  return (
    <div className="space-y-3">
      {rows.length === 0 && <p className="text-xs text-muted-foreground">{t('trophies.noWinnerYet')}</p>}
      {rows.map((r, i) => (
        <div key={r.user_id} className="flex flex-wrap items-center gap-2">
          <span className="flex items-center gap-2 min-w-[8rem]">
            <Avatar name={nameOf(r.user_id)} url={avatarOf(r.user_id)} />
            <span className="font-bold text-sm text-foreground">{nameOf(r.user_id)}</span>
          </span>
          <input
            value={r.citation}
            onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, citation: e.target.value } : x)))}
            placeholder={t('trophies.citationPlaceholder')}
            maxLength={200}
            className="flex-1 min-w-[10rem] h-9 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none"
          />
          <button onClick={() => setRows(rows.filter((_, j) => j !== i))} className="text-muted-foreground hover:text-red-400" aria-label={t('common.delete')}>
            <X size={14} />
          </button>
        </div>
      ))}
      {candidates.length > 0 && (
        <select
          value=""
          onChange={(e) => e.target.value && setRows([...rows, { user_id: Number(e.target.value), citation: '' }])}
          className="h-9 px-2 bg-input border border-border text-foreground text-xs focus:border-accent outline-none"
        >
          <option value="">{t('trophies.addWinner')}</option>
          {candidates.map((a) => <option key={a.user_id} value={a.user_id}>{a.username}</option>)}
        </select>
      )}
      <div className="flex flex-wrap items-center gap-3 pt-1">
        {dirty && (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => run(save)}>
            <Check size={12} /> {t('common.save')}
          </Button>
        )}
        <Button size="sm" disabled={busy || rows.length === 0} onClick={reveal}>
          <Eye size={12} /> {t('trophies.reveal')}
        </Button>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
          <input type="checkbox" checked={discord} onChange={(e) => setDiscord(e.target.checked)} />
          {t('trophies.postToDiscord')}
        </label>
      </div>
    </div>
  )
}

function EditionCard({
  edition,
  isAdmin,
  isAttendee,
  currentUserId,
  attendees,
  onChange,
  onRemoved,
}: {
  edition: TrophyEdition
  isAdmin: boolean
  isAttendee: boolean
  currentUserId?: number
  attendees: EventAttendee[]
  onChange: (e: TrophyEdition) => void
  onRemoved: () => void
}) {
  const { t } = useTranslation()
  const { push } = useToast()
  const [busy, setBusy] = useState(false)
  const { status, mode } = edition

  const run = async (fn: () => Promise<TrophyEdition | void>) => {
    setBusy(true)
    try {
      const updated = await fn()
      if (updated) onChange(updated)
    } catch {
      push(t('trophies.actionFailed'), 'error')
    } finally {
      setBusy(false)
    }
  }
  const setStatus = (s: 'draft' | 'voting' | 'closed') => run(() => trophiesApi.updateEdition(edition.id, { status: s }))

  const statusVariant = { draft: 'muted', voting: 'accent', closed: 'warning', revealed: 'success' } as const

  return (
    <div className="border border-border p-4 space-y-4">
      <div>
        <div className="flex items-center gap-3">
          <TrophyIcon trophy={edition.trophy} />
          <p className="flex-1 min-w-0 font-black text-foreground leading-tight">{edition.trophy.name}</p>
          <Badge variant={statusVariant[status]} className="shrink-0">{t(`trophies.status_${status}`)}</Badge>
        </div>
        {(edition.trophy.description || isAdmin) && (
          <p className="text-xs text-muted-foreground mt-2">
            {edition.trophy.description}
            {isAdmin && (
              <span className="font-mono-label text-[10px] ml-2">
                {edition.trophy.description ? '· ' : ''}{t(`trophies.mode_${mode}`)}
              </span>
            )}
          </p>
        )}
      </div>

      {(status === 'voting' || (isAdmin && status === 'closed' && mode === 'vote')) && (
        <p className="font-mono-label text-muted-foreground text-[10px]">
          {t('trophies.turnout', { voters: edition.voters_count, eligible: edition.eligible_count })}
        </p>
      )}

      {status === 'voting' && (
        isAttendee
          ? <Ballot edition={edition} nominees={attendees.filter((a) => a.user_id !== currentUserId)} onVoted={onChange} />
          : <p className="text-xs text-muted-foreground">{t('trophies.attendeesOnly')}</p>
      )}

      {status === 'closed' && !isAdmin && (
        <p className="text-sm text-muted-foreground">🥁 {t('trophies.resultsSoon')}</p>
      )}

      {status === 'revealed' && <WinnersList edition={edition} />}

      {isAdmin && status === 'closed' && edition.tally && edition.tally.length > 0 && (
        <div className="border-l-2 border-border pl-3 space-y-1">
          <p className="font-mono-label text-muted-foreground text-[10px]">{t('trophies.tally')}</p>
          {edition.tally.map((l) => (
            <p key={l.user_id} className="text-sm text-foreground">
              {l.username} <span className="font-mono text-muted-foreground">· {l.votes}</span>
            </p>
          ))}
        </div>
      )}

      {isAdmin && ((status === 'draft' && mode === 'direct') || status === 'closed') && (
        <WinnersEditor edition={edition} attendees={attendees} onChange={onChange} />
      )}

      {isAdmin && (
        <div className="flex flex-wrap gap-2 pt-1 border-t border-border">
          {status === 'draft' && mode === 'vote' && (
            <Button size="sm" disabled={busy} onClick={() => setStatus('voting')}><Play size={12} /> {t('trophies.openVote')}</Button>
          )}
          {status === 'voting' && (
            <>
              <Button size="sm" disabled={busy} onClick={() => setStatus('closed')}><Lock size={12} /> {t('trophies.closeVote')}</Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => setStatus('draft')}><Pause size={12} /> {t('trophies.pauseVote')}</Button>
            </>
          )}
          {status === 'closed' && (
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => setStatus('voting')}><RotateCcw size={12} /> {t('trophies.reopenVote')}</Button>
          )}
          {status === 'revealed' && (
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => confirm(t('trophies.unrevealConfirm')) && setStatus(mode === 'vote' ? 'closed' : 'draft')}
            >
              <EyeOff size={12} /> {t('trophies.unreveal')}
            </Button>
          )}
          {status === 'draft' && (
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => run(() => trophiesApi.updateEdition(edition.id, { mode: mode === 'vote' ? 'direct' : 'vote' }))}
            >
              {mode === 'vote' ? <Award size={12} /> : <Vote size={12} />}
              {t(mode === 'vote' ? 'trophies.switchToDirect' : 'trophies.switchToVote')}
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            className="ml-auto"
            onClick={() =>
              confirm(t('trophies.removeEditionConfirm', { name: edition.trophy.name })) &&
              run(async () => { await trophiesApi.deleteEdition(edition.id); onRemoved() })
            }
          >
            <Trash2 size={12} /> {t('trophies.removeEdition')}
          </Button>
        </div>
      )}
    </div>
  )
}

export default function EventTrophiesSection({
  event,
  isAdmin,
  currentUserId,
}: {
  event: LanEvent
  isAdmin: boolean
  currentUserId?: number
}) {
  const { t } = useTranslation()
  const { push } = useToast()
  const [editions, setEditions] = useState<TrophyEdition[] | null>(null)
  const [cabinet, setCabinet] = useState<Trophy[]>([])
  const [pick, setPick] = useState('')
  const [mode, setMode] = useState<TrophyMode>('vote')

  const load = () => trophiesApi.editions(event.id).then(setEditions).catch(() => setEditions([]))

  useEffect(() => {
    load()
    if (isAdmin) trophiesApi.list().then(setCabinet).catch(() => setCabinet([]))
  }, [event.id, isAdmin])

  // The Hub's "votes are open" banner links to #trophies — React Router doesn't
  // scroll to a hash, and this block only exists once the editions are in.
  const loaded = editions !== null
  useEffect(() => {
    if (loaded && window.location.hash === '#trophies') {
      document.getElementById('trophies')?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [loaded])

  if (editions === null) return null
  if (!isAdmin && editions.length === 0) return null

  const isAttendee = event.my_rsvp === 'in'
  const available = cabinet.filter((c) => !c.archived_at && !editions.some((e) => e.trophy.id === c.id))
  const replace = (updated: TrophyEdition) => setEditions(editions.map((e) => (e.id === updated.id ? updated : e)))

  const add = async () => {
    if (!pick) return
    try {
      const created = await trophiesApi.addEdition(event.id, { trophy_id: Number(pick), mode })
      setEditions([...editions, created])
      setPick('')
    } catch {
      push(t('trophies.actionFailed'), 'error')
    }
  }

  return (
    <div id="trophies" className="border border-border bg-card p-6 mt-6 scroll-mt-24">
      <p className="font-mono-label text-accent flex items-center gap-1.5 mb-4">
        <Award size={12} strokeWidth={1.5} /> {t('trophies.eventBlockTitle')}
      </p>

      {editions.length === 0 ? (
        <p className="text-xs text-muted-foreground mb-4">{t('trophies.eventEmpty')}</p>
      ) : (
        <div className="space-y-3 mb-4">
          {editions.map((e) => (
            <EditionCard
              key={e.id}
              edition={e}
              isAdmin={isAdmin}
              isAttendee={isAttendee}
              currentUserId={currentUserId}
              attendees={event.attendees}
              onChange={replace}
              onRemoved={() => setEditions(editions.filter((x) => x.id !== e.id))}
            />
          ))}
        </div>
      )}

      {isAdmin && (
        cabinet.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t('trophies.cabinetEmptyHint')}</p>
        ) : available.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 pt-4 border-t border-border">
            <select
              value={pick}
              onChange={(e) => setPick(e.target.value)}
              className="h-9 px-2 bg-input border border-border text-foreground text-sm focus:border-accent outline-none"
            >
              <option value="">{t('trophies.putInPlay')}</option>
              {available.map((c) => <option key={c.id} value={c.id}>{c.emoji ? `${c.emoji} ` : ''}{c.name}</option>)}
            </select>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as TrophyMode)}
              className="h-9 px-2 bg-input border border-border text-foreground text-sm focus:border-accent outline-none"
            >
              <option value="vote">{t('trophies.mode_vote')}</option>
              <option value="direct">{t('trophies.mode_direct')}</option>
            </select>
            <Button size="sm" variant="outline" disabled={!pick} onClick={add}>
              <Plus size={12} /> {t('common.add')}
            </Button>
          </div>
        )
      )}
    </div>
  )
}
