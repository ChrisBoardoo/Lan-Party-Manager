import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { eventsApi, tournamentsApi } from '../lib/api'
import { Draw, drawTeams, maxTeams } from '../lib/randomTeams'
import { apiErrorMessage } from '../lib/apiError'
import { Tournament, User } from '../types'
import Button from './ui/Button'
import Input from './ui/Input'
import { Check, Dices, RefreshCw, X } from 'lucide-react'

// One color per drawn team, in order; the organizer can still change them after.
const DRAW_COLORS = [
  '#FF3D00', '#2979FF', '#00C853', '#FFD600', '#AA00FF',
  '#00B8D4', '#FF4081', '#FF9100', '#76FF03', '#8D6E63',
]

/**
 * Random team draw for a pending team tournament: pick the players (this LAN's
 * attendees pre-checked), the format and the team size, draw, redraw as often as
 * needed, place whoever is left over by hand, then save. Saving replaces every
 * existing team, so the organizer can come back and draw again until the brackets
 * are generated.
 */
export default function RandomTeamsModal({
  tournament,
  allUsers,
  onClose,
  onDone,
}: {
  tournament: Tournament
  allUsers: User[]
  onClose: () => void
  onDone: () => void
}) {
  const { t } = useTranslation()
  const [format, setFormat] = useState(tournament.bracket_type)
  const [sizeInput, setSizeInput] = useState(String(Math.max(2, tournament.max_team_size)))
  // '' = as many full teams as the players make
  const [countInput, setCountInput] = useState('')
  const [attendeeIds, setAttendeeIds] = useState<Set<number>>(new Set())
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const [draw, setDraw] = useState<Draw<User> | null>(null)
  // leftover user id → index of the team they're added to (absent = left out)
  const [placement, setPlacement] = useState<Record<number, number>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (tournament.event_id == null) return
    eventsApi
      .get(tournament.event_id)
      .then((e) => {
        const ids = new Set(e.attendees.map((a) => a.user_id))
        setAttendeeIds(ids)
        setPicked(new Set(ids))
      })
      .catch(() => {})
  }, [tournament.event_id])

  const members = allUsers.filter((u) => u.is_active && !u.deleted_at)
  const attendees = members.filter((u) => attendeeIds.has(u.id))
  const others = members.filter((u) => !attendeeIds.has(u.id))
  const pool = members.filter((u) => picked.has(u.id))

  const size = Math.min(10, Math.max(0, parseInt(sizeInput, 10) || 0))
  const most = maxTeams(pool.length, size)
  const count = countInput === '' ? most : Math.min(most, Math.max(0, parseInt(countInput, 10) || 0))
  const problem =
    size < 2 ? t('tournaments.draw.sizeRange')
    : most < 2 ? t('tournaments.draw.notEnough', { need: size * 2, size })
    : count < 2 ? t('tournaments.draw.minTeams')
    : ''
  const canDraw = !problem
  const leftover = pool.length - count * size

  // Changing a setting throws the current draw away: it no longer matches.
  const reset = () => {
    setDraw(null)
    setPlacement({})
  }

  const toggle = (id: number) => {
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
    reset()
  }

  const runDraw = () => {
    setDraw(drawTeams(pool, count, size))
    setPlacement({})
    setError('')
  }

  const teamName = (i: number) => t('tournaments.draw.teamName', { n: i + 1 })

  const save = async () => {
    if (!draw) return
    const existing = tournament.teams.length
    if (existing > 0 && !confirm(t('tournaments.draw.replaceConfirm', { count: existing }))) return
    setBusy(true)
    setError('')
    try {
      if (format !== tournament.bracket_type || size !== tournament.max_team_size) {
        await tournamentsApi.update(tournament.id, { bracket_type: format, max_team_size: size })
      }
      await tournamentsApi.replaceTeams(
        tournament.id,
        draw.teams.map((team, i) => ({
          team_name: teamName(i),
          color: DRAW_COLORS[i % DRAW_COLORS.length],
          members: [...team, ...draw.leftovers.filter((u) => placement[u.id] === i)].map((u) => ({
            player_name: u.username,
            user_id: u.id,
          })),
        }))
      )
      onClose()
    } catch (e) {
      setError(t('tournaments.draw.failed', { detail: apiErrorMessage(e, t) }))
    } finally {
      setBusy(false)
      // Also after a failure: the format may have been saved before the teams were refused.
      onDone()
    }
  }

  const checkbox = (u: User) => (
    <label key={u.id} className="flex items-center gap-2 text-sm text-foreground cursor-pointer min-w-0">
      <input type="checkbox" checked={picked.has(u.id)} onChange={() => toggle(u.id)} disabled={busy} />
      <span className="truncate">{u.username}</span>
    </label>
  )
  const groupLabel = 'font-mono-label text-muted-foreground text-[10px] mb-2'
  const selectCls = 'w-full h-12 px-4 bg-input border border-border text-foreground focus:border-accent outline-none text-sm'

  return (
    <div className="fixed inset-0 bg-background/90 z-50 flex items-center justify-center p-6">
      <div className="bg-card border border-border w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b border-border sticky top-0 bg-card z-10">
          <div className="min-w-0">
            <p className="font-mono-label text-accent">{t('tournaments.draw.title')}</p>
            <p className="text-sm text-muted-foreground truncate">{tournament.game_name}</p>
          </div>
          <button onClick={onClose}><X size={16} className="text-muted-foreground hover:text-foreground" /></button>
        </div>

        <div className="p-6 space-y-5">
          {/* 1. Format */}
          <div>
            <label className="font-mono-label text-muted-foreground block mb-1.5">{t('tournaments.modal.bracketTypeLabel')}</label>
            <select className={selectCls} value={format} onChange={(e) => setFormat(e.target.value)} disabled={busy}>
              <option value="single_elimination">{t('tournaments.modal.bracketSingleElim')}</option>
              <option value="round_robin">{t('tournaments.modal.bracketRoundRobin')}</option>
              <option value="groups_then_knockout">{t('tournaments.modal.bracketGroupsKnockout')}</option>
            </select>
          </div>

          {/* 2–3. Team size and number of teams */}
          <div className="grid grid-cols-2 gap-3 items-end">
            <Input
              label={t('tournaments.draw.teamSize')}
              type="number"
              min={2}
              max={10}
              value={sizeInput}
              onChange={(e) => { setSizeInput(e.target.value); reset() }}
              disabled={busy}
            />
            <Input
              label={t('tournaments.draw.teamCount', { max: most })}
              type="number"
              min={2}
              max={Math.max(2, most)}
              placeholder={String(most)}
              value={countInput}
              onChange={(e) => { setCountInput(e.target.value); reset() }}
              disabled={busy}
            />
          </div>

          {/* Players */}
          <div>
            <p className="font-mono-label text-muted-foreground mb-2">{t('tournaments.draw.players', { count: pool.length })}</p>
            <div className="border border-border p-3 space-y-3 max-h-56 overflow-y-auto">
              {attendees.length > 0 && (
                <div>
                  <p className={groupLabel}>{t('tournaments.teamModal.attendeesGroup')}</p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-3 gap-y-1.5">{attendees.map(checkbox)}</div>
                </div>
              )}
              {others.length > 0 && (
                <div>
                  <p className={groupLabel}>
                    {attendees.length > 0 ? t('tournaments.teamModal.otherMembersGroup') : t('tournaments.teamModal.membersGroup')}
                  </p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-3 gap-y-1.5">{others.map(checkbox)}</div>
                </div>
              )}
            </div>
          </div>

          {/* What the draw will make */}
          <p className={`text-sm ${canDraw ? 'text-foreground' : 'text-red-400'}`}>
            {canDraw
              ? <>
                  {t('tournaments.draw.summary', { teams: count, size })}
                  {leftover > 0 && <span className="text-muted-foreground"> · {t('tournaments.draw.leftoverCount', { count: leftover })}</span>}
                </>
              : problem}
          </p>

          {/* 4–5. Draw, redraw */}
          {draw && (
            <div className="space-y-2">
              {draw.teams.map((team, i) => {
                const extra = draw.leftovers.filter((u) => placement[u.id] === i)
                return (
                  <div key={i} className="flex items-start gap-3 border border-border px-3 py-2">
                    <div className="w-3 h-3 mt-1 flex-shrink-0" style={{ backgroundColor: DRAW_COLORS[i % DRAW_COLORS.length] }} />
                    <div className="min-w-0">
                      <p className="font-semibold text-sm text-foreground">{teamName(i)}</p>
                      <p className="text-sm text-muted-foreground">
                        {team.map((u) => u.username).join(', ')}
                        {extra.length > 0 && <span className="text-accent">, {extra.map((u) => u.username).join(', ')}</span>}
                      </p>
                    </div>
                  </div>
                )
              })}
              {draw.leftovers.length > 0 && (
                <div className="border border-accent/40 bg-accent/5 px-3 py-2 space-y-2">
                  <p className="font-mono-label text-accent text-[10px]">{t('tournaments.draw.leftoversTitle')}</p>
                  {draw.leftovers.map((u) => (
                    <div key={u.id} className="flex items-center gap-3">
                      <span className="text-sm text-foreground flex-1 truncate">{u.username}</span>
                      <select
                        className="h-9 px-2 bg-input border border-border text-foreground text-sm focus:border-accent outline-none"
                        value={placement[u.id] ?? ''}
                        onChange={(e) => {
                          const value = e.target.value
                          setPlacement((prev) => {
                            const next = { ...prev }
                            if (value === '') delete next[u.id]
                            else next[u.id] = Number(value)
                            return next
                          })
                        }}
                        disabled={busy}
                      >
                        <option value="">{t('tournaments.draw.leaveOut')}</option>
                        {draw.teams.map((_, i) => (
                          <option key={i} value={i}>{teamName(i)}</option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {tournament.teams.length > 0 && (
            <p className="text-xs text-muted-foreground">{t('tournaments.draw.replaceNote', { count: tournament.teams.length })}</p>
          )}
          {error && <p className="font-mono-label text-[10px] text-red-400">{error}</p>}

          <div className="flex flex-wrap gap-3 pt-1">
            {draw ? (
              <>
                <Button onClick={save} disabled={busy}>
                  <Check size={14} /> {busy ? t('common.saving') : t('tournaments.draw.save')}
                </Button>
                <Button variant="outline" onClick={runDraw} disabled={busy || !canDraw}>
                  <RefreshCw size={14} /> {t('tournaments.draw.redraw')}
                </Button>
              </>
            ) : (
              <Button onClick={runDraw} disabled={!canDraw}>
                <Dices size={14} /> {t('tournaments.draw.draw')}
              </Button>
            )}
            <Button variant="ghost" onClick={onClose} disabled={busy}>{t('common.cancel')}</Button>
          </div>
          <p className="text-[10px] text-muted-foreground">{t('tournaments.draw.redrawHint')}</p>
        </div>
      </div>
    </div>
  )
}
