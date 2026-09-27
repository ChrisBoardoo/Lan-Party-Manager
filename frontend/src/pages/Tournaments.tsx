import { useEffect, useState } from 'react'
import { useForm, useFieldArray, UseFormRegister } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import { useAppConfig } from '../contexts/AppConfigContext'
import { tournamentsApi, usersApi, eventsApi } from '../lib/api'
import { isEmbeddedInDesktop, requestOpenExternal } from '../lib/desktopBridge'
import { Tournament, Team, User, RoundRobinStanding } from '../types'
import { formatDate } from '../lib/formatDate'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import Badge from '../components/ui/Badge'
import TournamentBracket from '../components/TournamentBracket'
import CreateTournamentModal from '../components/CreateTournamentModal'
import SponsorStrip from '../components/SponsorStrip'
import MiniGames from '../components/MiniGames'
import GameStatsTab from '../components/GameStatsTab'
import {
  Plus, Trophy, Users, User as UserIcon, ChevronRight, X, ArrowRight,
  Zap, Trash2, RefreshCw, Table2, Check, Pencil, ExternalLink, Gamepad2, BarChart3,
} from 'lucide-react'

// ── Add Team Modal ────────────────────────────────────────────────────────────
// Account first: a player is picked from the members list (this LAN's attendees
// on top), and only an explicit "guest without an account" gets a free-text
// name. Per-game stats, the Hall of Fame and badges can only count players
// linked to an account, so linking is the default path, not an optional extra.

const GUEST = 'guest'

interface MemberRow {
  /** '' = nobody picked yet, GUEST = free-text guest, otherwise a user id. */
  pick: string
  /** Only used for a guest. */
  player_name: string
}

interface TeamForm {
  team_name: string
  color: string
  seed: string
  members: MemberRow[]
}

function toRow(m: { player_name: string; user_id: number | null }): MemberRow {
  if (m.user_id) return { pick: String(m.user_id), player_name: '' }
  return { pick: m.player_name ? GUEST : '', player_name: m.player_name }
}

function PlayerSelect({
  field,
  pick,
  placeholder,
  attendees,
  others,
  takenBy,
  register,
}: {
  field: `members.${number}`
  pick: string
  placeholder: string
  attendees: User[]
  others: User[]
  takenBy: Map<number, string>
  register: UseFormRegister<TeamForm>
}) {
  const { t } = useTranslation()
  const label = (u: User) => (takenBy.has(u.id) ? `${u.username} · ${takenBy.get(u.id)}` : u.username)
  return (
    <div className="flex-1 min-w-0 space-y-2">
      <select
        className="w-full h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none"
        {...register(`${field}.pick`)}
      >
        <option value="">{placeholder}</option>
        {attendees.length > 0 && (
          <optgroup label={t('tournaments.teamModal.attendeesGroup')}>
            {attendees.map((u) => <option key={u.id} value={u.id}>{label(u)}</option>)}
          </optgroup>
        )}
        {others.length > 0 && (
          <optgroup label={attendees.length > 0 ? t('tournaments.teamModal.otherMembersGroup') : t('tournaments.teamModal.membersGroup')}>
            {others.map((u) => <option key={u.id} value={u.id}>{label(u)}</option>)}
          </optgroup>
        )}
        <option value={GUEST}>{t('tournaments.teamModal.guestOption')}</option>
      </select>
      {pick === GUEST && (
        <input
          placeholder={t('tournaments.teamModal.playerNamePlaceholder')}
          className="w-full h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none"
          {...register(`${field}.player_name`)}
        />
      )}
    </div>
  )
}

function AddTeamModal({
  tournament,
  team,
  allUsers,
  onClose,
  onAdd,
}: {
  tournament: Tournament
  team?: Team
  allUsers: User[]
  onClose: () => void
  onAdd: () => void
}) {
  const { t } = useTranslation()
  const isEditing = !!team
  const { register, handleSubmit, control, watch, formState: { isSubmitting } } = useForm<TeamForm>({
    defaultValues: team
      ? {
          team_name: team.team_name,
          color: team.color ?? '#FF3D00',
          seed: team.seed != null ? String(team.seed) : '',
          members: team.members.length > 0 ? team.members.map(toRow) : [{ pick: '', player_name: '' }],
        }
      : { members: [{ pick: '', player_name: '' }], seed: '' },
  })
  const { fields, append, remove } = useFieldArray({ control, name: 'members' })
  const rows = watch('members')
  const [memberError, setMemberError] = useState<string | null>(null)
  const isIndividual = tournament.event_type === 'individual'
  const isRoundRobin = tournament.bracket_type === 'round_robin'

  // This LAN's attendees go on top of the list.
  const [attendeeIds, setAttendeeIds] = useState<Set<number>>(new Set())
  useEffect(() => {
    if (tournament.event_id == null) return
    eventsApi
      .get(tournament.event_id)
      .then((e) => setAttendeeIds(new Set(e.attendees.map((a) => a.user_id))))
      .catch(() => {})
  }, [tournament.event_id])
  const attendees = allUsers.filter((u) => attendeeIds.has(u.id))
  const others = allUsers.filter((u) => !attendeeIds.has(u.id))

  // Who's already on another team of this tournament — shown next to their name
  // so nobody gets drafted twice in the rush of the day.
  const takenBy = new Map<number, string>()
  for (const other of tournament.teams) {
    if (other.id === team?.id) continue
    for (const m of other.members) if (m.user_id) takenBy.set(m.user_id, other.team_name)
  }

  const onSubmit = async (data: TeamForm) => {
    const byId = new Map(allUsers.map((u) => [u.id, u]))
    const members = data.members.flatMap((m) => {
      if (m.pick === GUEST) return m.player_name.trim() ? [{ player_name: m.player_name.trim() }] : []
      const u = m.pick ? byId.get(Number(m.pick)) : undefined
      return u ? [{ player_name: u.username, user_id: u.id }] : []
    })
    if (isIndividual && members.length === 0) {
      setMemberError(t('tournaments.teamModal.playerNameRequired'))
      return
    }
    const payload = {
      team_name: isIndividual ? members[0]?.player_name || data.team_name : data.team_name,
      color: isIndividual ? undefined : (data.color || undefined),
      seed: data.seed ? Number(data.seed) : undefined,
      members,
    }
    if (isEditing && team) {
      await tournamentsApi.updateTeam(tournament.id, team.id, payload)
    } else {
      await tournamentsApi.addTeam(tournament.id, payload)
    }
    onAdd()
    onClose()
  }

  const titleKey = isEditing
    ? 'tournaments.teamModal.editTeamTitle'
    : (isIndividual ? 'tournaments.teamModal.addPlayer' : 'tournaments.teamModal.addTeam')

  return (
    <div className="fixed inset-0 bg-background/90 z-50 flex items-center justify-center p-6">
      <div className="bg-card border border-border w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b border-border sticky top-0 bg-card">
          <p className="font-mono-label text-accent">{t(titleKey)}</p>
          <button onClick={onClose}><X size={16} className="text-muted-foreground hover:text-foreground" /></button>
        </div>
        <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-4">
          {isIndividual ? (
            <PlayerSelect
              field="members.0"
              pick={rows?.[0]?.pick ?? ''}
              placeholder={t('tournaments.teamModal.pickPlayer')}
              attendees={attendees}
              others={others}
              takenBy={takenBy}
              register={register}
            />
          ) : (
            <>
              <Input
                label={t('tournaments.teamModal.teamNameLabel')}
                placeholder={t('tournaments.teamModal.teamNamePlaceholder')}
                {...register('team_name', { required: t('tournaments.teamModal.teamNameRequired') })}
              />
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-mono-label text-muted-foreground block mb-1.5">{t('tournaments.teamModal.colorLabel')}</label>
                  <input
                    type="color"
                    defaultValue="#FF3D00"
                    className="w-full h-12 bg-input border border-border cursor-pointer"
                    {...register('color')}
                  />
                </div>
                {isRoundRobin && (
                  <Input
                    label={t('tournaments.teamModal.seedLabel')}
                    type="number"
                    min={1}
                    placeholder={t('tournaments.teamModal.seedPlaceholder')}
                    {...register('seed')}
                  />
                )}
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="font-mono-label text-muted-foreground">{t('tournaments.teamModal.playersMax', { max: tournament.max_team_size })}</label>
                  {fields.length < tournament.max_team_size && (
                    <button type="button" onClick={() => append({ pick: '', player_name: '' })} className="font-mono-label text-accent text-[10px] hover:text-accent/80">
                      {t('tournaments.teamModal.addPlayerShort')}
                    </button>
                  )}
                </div>
                <div className="space-y-2">
                  {fields.map((field, idx) => (
                    <div key={field.id} className="flex items-start gap-2">
                      <PlayerSelect
                        field={`members.${idx}`}
                        pick={rows?.[idx]?.pick ?? ''}
                        placeholder={t('tournaments.teamModal.playerNPlaceholder', { n: idx + 1 })}
                        attendees={attendees}
                        others={others}
                        takenBy={takenBy}
                        register={register}
                      />
                      {fields.length > 1 && (
                        <button type="button" onClick={() => remove(idx)} className="p-2 text-muted-foreground hover:text-red-400">
                          <X size={12} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {rows?.some((m) => m.pick === GUEST) && (
            <p className="text-xs text-muted-foreground">{t('tournaments.teamModal.guestHint')}</p>
          )}
          {memberError && <p className="font-mono-label text-red-500">{memberError}</p>}

          <div className="flex gap-3 pt-2">
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting
                ? (isEditing ? t('common.saving') : t('tournaments.teamModal.adding'))
                : isEditing
                  ? <><Check size={14} /> {t('common.save')}</>
                  : isIndividual
                    ? <><UserIcon size={14} /> {t('tournaments.teamModal.addPlayer')}</>
                    : <><Users size={14} /> {t('tournaments.teamModal.addTeam')}</>
              }
            </Button>
            <Button variant="ghost" type="button" onClick={onClose}>{t('common.cancel')}</Button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Round-Robin Standings Table ───────────────────────────────────────────────

function StandingsTable({ standings }: { standings: RoundRobinStanding[] }) {
  const { t } = useTranslation()
  if (standings.length === 0) return (
    <p className="text-center font-mono-label text-muted-foreground py-6">{t('tournaments.standingsTable.noMatchesYet')}</p>
  )

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted">
            <th className="px-4 py-2 text-left font-mono-label text-muted-foreground">{t('tournaments.standingsTable.hash')}</th>
            <th className="px-4 py-2 text-left font-mono-label text-muted-foreground">{t('tournaments.standingsTable.team')}</th>
            <th className="px-4 py-2 text-center font-mono-label text-muted-foreground">{t('tournaments.standingsTable.mp')}</th>
            <th className="px-4 py-2 text-center font-mono-label text-muted-foreground">{t('tournaments.standingsTable.w')}</th>
            <th className="px-4 py-2 text-center font-mono-label text-muted-foreground">{t('tournaments.standingsTable.d')}</th>
            <th className="px-4 py-2 text-center font-mono-label text-muted-foreground">{t('tournaments.standingsTable.l')}</th>
            <th className="px-4 py-2 text-center font-mono-label text-muted-foreground">{t('tournaments.standingsTable.pts')}</th>
          </tr>
        </thead>
        <tbody>
          {standings.map((row, idx) => (
            <tr key={row.team_id} className={`border-b border-border last:border-0 ${idx === 0 ? 'bg-accent/5' : ''}`}>
              <td className="px-4 py-3 font-mono-label text-muted-foreground">{idx + 1}</td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  {row.color && <div className="w-2.5 h-2.5 flex-shrink-0" style={{ backgroundColor: row.color }} />}
                  <span className="font-bold text-foreground">{row.team_name}</span>
                  {row.seed != null && (
                    <span className="font-mono-label text-muted-foreground text-[10px]">#{row.seed}</span>
                  )}
                </div>
              </td>
              <td className="px-4 py-3 text-center font-mono text-muted-foreground">{row.played}</td>
              <td className="px-4 py-3 text-center font-mono text-foreground">{row.wins}</td>
              <td className="px-4 py-3 text-center font-mono text-muted-foreground">{row.draws}</td>
              <td className="px-4 py-3 text-center font-mono text-muted-foreground">{row.losses}</td>
              <td className="px-4 py-3 text-center font-mono font-black text-accent">{row.points}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Tournaments() {
  const { user } = useAuth()
  const { t } = useTranslation()
  const [tournaments, setTournaments] = useState<Tournament[]>([])
  const [selected, setSelected] = useState<Tournament | null>(null)
  const [allUsers, setAllUsers] = useState<User[]>([])
  const [standings, setStandings] = useState<RoundRobinStanding[]>([])
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showAddTeam, setShowAddTeam] = useState(false)
  const [editingTeam, setEditingTeam] = useState<Team | undefined>(undefined)
  const [generatingBrackets, setGeneratingBrackets] = useState(false)
  const [loading, setLoading] = useState(true)

  const { minigamesEnabled } = useAppConfig()
  const [tab, setTab] = useState<'tournaments' | 'stats' | 'minigames'>('tournaments')

  const canCreateTournament = user?.is_tournament_organizer || user?.role === 'admin' || user?.role === 'treasurer'
  const isOrganizer = selected ? selected.organizer_id === user?.id || user?.role === 'admin' : false

  const loadTournaments = async () => {
    const data = await tournamentsApi.getAll()
    setTournaments(data)
    if (selected) {
      const fresh = data.find((t) => t.id === selected.id)
      if (fresh) setSelected(fresh)
    }
    setLoading(false)
  }

  const loadSelected = async () => {
    if (!selected) return
    const fresh = await tournamentsApi.get(selected.id)
    setSelected(fresh)
    setTournaments((prev) => prev.map((t) => (t.id === fresh.id ? fresh : t)))
    if (fresh.bracket_type === 'round_robin' && fresh.matches.length > 0) {
      const s = await tournamentsApi.getStandings(fresh.id)
      setStandings(s)
    }
  }

  const loadStandings = async (t: Tournament) => {
    if (t.bracket_type === 'round_robin' && t.matches.length > 0) {
      const s = await tournamentsApi.getStandings(t.id)
      setStandings(s)
    } else {
      setStandings([])
    }
  }

  useEffect(() => {
    Promise.all([tournamentsApi.getAll(), usersApi.getAll()]).then(([t, u]) => {
      setTournaments(t)
      setAllUsers(u)
      setLoading(false)
    })
  }, [])

  useEffect(() => {
    if (selected) loadStandings(selected)
  }, [selected?.id])

  const handleGenerateBrackets = async () => {
    if (!selected) return
    setGeneratingBrackets(true)
    try {
      await tournamentsApi.generateBrackets(selected.id)
      await loadSelected()
    } finally {
      setGeneratingBrackets(false)
    }
  }

  const handleDeleteTeam = async (teamId: number) => {
    if (!selected || !confirm(t('tournaments.removeTeamConfirm'))) return
    await tournamentsApi.deleteTeam(selected.id, teamId)
    await loadSelected()
  }

  const handleDeleteTournament = async () => {
    if (!selected || !confirm(t('tournaments.deleteTournamentConfirm', { name: selected.game_name }))) return
    await tournamentsApi.delete(selected.id)
    setSelected(null)
    await loadTournaments()
  }

  const statusVariant = (s: string) => {
    if (s === 'completed') return 'success'
    if (s === 'pending') return 'muted'
    return 'accent'
  }

  const isRoundRobin = selected?.bracket_type === 'round_robin'

  return (
    <main className="max-w-6xl mx-auto px-6 py-12">
      <div className="flex items-start justify-between mb-12">
        <div>
          <div className="font-mono-label text-accent mb-3">{t('tournaments.tagline')}</div>
          <h1 className="text-5xl lg:text-6xl font-black tracking-tighter text-foreground leading-none">
            {t('tournaments.heroLine1')}
            <br />
            <span className="text-accent">{t('tournaments.heroLine2')}</span>
          </h1>
        </div>
        {canCreateTournament && tab === 'tournaments' && (
          <Button onClick={() => setShowCreateModal(true)}>
            <Plus size={14} /> {t('tournaments.newEvent')}
          </Button>
        )}
      </div>

      {/* Stats and mini-games ride as tabs here rather than as navbar items: Arena is
          already where competition lives, and the navbar has no room left above its
          3xl label breakpoint (see CLAUDE.md). Further games become further tabs. */}
      <div className="flex gap-px border-b border-border mb-8 overflow-x-auto">
        {([
          ['tournaments', t('tournaments.tabTournaments'), Trophy],
          ['stats', t('tournaments.tabStats'), BarChart3],
          ...(minigamesEnabled ? [['minigames', t('tournaments.tabMiniGames'), Gamepad2] as const] : []),
        ] as const).map(([key, label, Icon]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-2 px-4 py-3 font-mono-label border-b-2 -mb-px transition-colors duration-150 ${
              tab === key
                ? 'border-accent text-accent'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Icon size={14} strokeWidth={1.5} />
            {label}
          </button>
        ))}
      </div>

      {/* Asymmetric on purpose: the tournaments grid is merely hidden, so switching
          tabs doesn't lose the selected tournament — while MiniGames is unmounted, so
          leaving the tab actually stops the game. `display:none` does not pause
          requestAnimationFrame, so keeping it mounted would run the game invisibly and
          let the player die off-screen. */}
      {tab === 'minigames' && <MiniGames />}
      {tab === 'stats' && <GameStatsTab />}

      <div className={`grid grid-cols-1 lg:grid-cols-3 gap-8 ${tab === 'tournaments' ? '' : 'hidden'}`}>
        {/* Tournament list */}
        <div className="space-y-px">
          <p className="font-mono-label text-muted-foreground mb-3">
            {t('tournaments.tournamentCount', { count: tournaments.length })}
          </p>
          {loading ? (
            Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-20 bg-muted animate-pulse" />)
          ) : tournaments.length === 0 ? (
            <div className="border border-border p-8 text-center">
              <Trophy size={24} strokeWidth={1} className="text-muted-foreground mx-auto mb-3" />
              <p className="font-mono-label text-muted-foreground">{t('tournaments.noTournamentsYet')}</p>
            </div>
          ) : (
            tournaments.map((tr) => (
              <button
                key={tr.id}
                onClick={() => setSelected(tr)}
                className={`w-full text-left p-4 border flex items-center justify-between transition-all duration-150 ${
                  selected?.id === tr.id
                    ? 'border-accent bg-accent/5'
                    : 'border-border hover:border-border-hover hover:bg-muted/30'
                }`}
              >
                <div className="flex-1 min-w-0">
                  <p className="font-bold text-sm text-foreground truncate">{tr.game_name}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <Badge variant={statusVariant(tr.status) as any}>{tr.status.toUpperCase()}</Badge>
                    <span className="font-mono-label text-muted-foreground text-[10px]">
                      {t(tr.event_type === 'individual' ? 'tournaments.playersCount' : 'tournaments.teamsCount', { count: tr.teams.length })}
                    </span>
                    {tr.bracket_type === 'round_robin' && (
                      <span className="font-mono-label text-muted-foreground text-[10px]">{t('tournaments.rrBadge')}</span>
                    )}
                  </div>
                </div>
                <ChevronRight size={14} strokeWidth={1.5} className="text-muted-foreground flex-shrink-0" />
              </button>
            ))
          )}
        </div>

        {/* Tournament detail */}
        <div className="lg:col-span-2">
          {!selected ? (
            <div className="border border-border h-64 flex items-center justify-center">
              <div className="text-center">
                <Zap size={24} strokeWidth={1} className="text-muted-foreground mx-auto mb-3" />
                <p className="font-mono-label text-muted-foreground">{t('tournaments.selectTournament')}</p>
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Tournament header */}
              <div className="border border-border bg-card p-6">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h2 className="text-2xl font-black tracking-tight text-foreground mb-1">
                      {selected.game_name}
                    </h2>
                    <div className="flex items-center gap-3 flex-wrap">
                      <Badge variant={statusVariant(selected.status) as any}>
                        {t(`roundLabels.${selected.status}`, selected.status.replace(/_/g, ' ').toUpperCase())}
                      </Badge>
                      <span className="font-mono-label text-muted-foreground">
                        {{
                          single_elimination: t('tournaments.modal.bracketSingleElim'),
                          round_robin: t('tournaments.modal.bracketRoundRobin'),
                          groups_then_knockout: t('tournaments.modal.bracketGroupsKnockout'),
                        }[selected.bracket_type] ?? selected.bracket_type.replace(/_/g, ' ')}
                      </span>
                      {selected.event_type === 'individual' ? (
                        <span className="font-mono-label text-muted-foreground">{t('tournaments.soloLabel')}</span>
                      ) : (
                        <span className="font-mono-label text-muted-foreground">
                          {t('tournaments.maxPlayersPerTeam', { max: selected.max_team_size })}
                        </span>
                      )}
                    </div>
                  </div>
                  {isOrganizer && (
                    <button onClick={handleDeleteTournament} className="text-muted-foreground hover:text-red-400 transition-colors p-1">
                      <Trash2 size={14} strokeWidth={1.5} />
                    </button>
                  )}
                </div>
                <p className="font-mono-label text-muted-foreground text-[10px]">
                  {t('tournaments.byLine', { name: selected.organizer.username, date: formatDate(selected.created_at) })}
                </p>
              </div>

              {/* Teams section */}
              <div className="border border-border bg-card">
                <div className="flex items-center justify-between p-4 border-b border-border">
                  <p className="font-mono-label text-accent">
                    {selected.event_type === 'individual' ? t('tournaments.playersLabel') : t('tournaments.teamsLabel')} ({selected.teams.length})
                  </p>
                  {isOrganizer && selected.status === 'pending' && (
                    <button
                      onClick={() => { setEditingTeam(undefined); setShowAddTeam(true) }}
                      className="font-mono-label text-muted-foreground hover:text-foreground text-[10px] flex items-center gap-1"
                    >
                      <Plus size={10} /> {selected.event_type === 'individual' ? t('tournaments.teamModal.addPlayer') : t('tournaments.teamModal.addTeam')}
                    </button>
                  )}
                </div>
                {selected.teams.length === 0 ? (
                  <div className="p-8 text-center">
                    <Users size={20} strokeWidth={1} className="text-muted-foreground mx-auto mb-2" />
                    <p className="font-mono-label text-muted-foreground">{t('tournaments.noTeamsYet')}</p>
                  </div>
                ) : (
                  <div>
                    {selected.teams.map((team) => (
                      <div
                        key={team.id}
                        className="flex items-center justify-between px-4 py-3 border-b border-border last:border-0 hover:bg-muted/30 group"
                      >
                        <div className="flex items-center gap-3">
                          {team.color && <div className="w-3 h-3 flex-shrink-0" style={{ backgroundColor: team.color }} />}
                          <div>
                            <div className="flex items-center gap-2">
                              <p className="font-semibold text-sm text-foreground">{team.team_name}</p>
                              {team.seed != null && (
                                <span className="font-mono-label text-muted-foreground text-[10px]">{t('tournaments.seedPrefix', { seed: team.seed })}</span>
                              )}
                            </div>
                            <p className="font-mono-label text-muted-foreground text-[10px]">
                              {team.members.map((m) => m.player_name).join(', ')}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {isOrganizer && selected.status === 'pending' && (
                            <>
                              <button
                                onClick={() => { setEditingTeam(team); setShowAddTeam(true) }}
                                className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-foreground transition-all"
                                title={t('common.edit')}
                              >
                                <Pencil size={12} />
                              </button>
                              <button
                                onClick={() => handleDeleteTeam(team.id)}
                                className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-red-400 transition-all"
                                title={t('common.delete')}
                              >
                                <X size={12} />
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Generate brackets */}
              {isOrganizer && selected.status === 'pending' && selected.teams.length >= 2 && (
                <div className="border border-border bg-card p-6 flex items-center justify-between">
                  <div>
                    <p className="font-mono-label text-muted-foreground mb-1">{t('tournaments.readyToFight')}</p>
                    <p className="text-sm text-muted-foreground">
                      {t('tournaments.generateSentence', {
                        scheduleType: isRoundRobin ? t('tournaments.roundRobinSchedule') : t('tournaments.bracketsWord'),
                        count: selected.teams.length,
                        unit: t(selected.event_type === 'individual' ? 'tournaments.playerUnit' : 'tournaments.teamUnit', { count: selected.teams.length }),
                      })}
                    </p>
                  </div>
                  <Button onClick={handleGenerateBrackets} disabled={generatingBrackets}>
                    <Zap size={14} />
                    {generatingBrackets ? t('tournaments.generating') : t('tournaments.generate')}
                  </Button>
                </div>
              )}

              {/* Round-robin standings */}
              {isRoundRobin && selected.matches.length > 0 && (
                <div className="border border-border bg-card">
                  <div className="flex items-center justify-between p-4 border-b border-border">
                    <div className="flex items-center gap-2">
                      <Table2 size={14} strokeWidth={1.5} className="text-accent" />
                      <p className="font-mono-label text-accent">{t('tournaments.standings')}</p>
                    </div>
                    <button
                      onClick={loadSelected}
                      className="font-mono-label text-muted-foreground hover:text-foreground flex items-center gap-1 text-[10px]"
                    >
                      <RefreshCw size={10} /> {t('tournaments.refresh')}
                    </button>
                  </div>
                  <StandingsTable standings={standings} />
                </div>
              )}

              {/* Match list / Bracket */}
              {selected.matches.length > 0 && (
                <div className="border border-border bg-card p-6">
                  <div className="flex items-center justify-between mb-4">
                    <p className="font-mono-label text-accent">
                      {isRoundRobin ? t('tournaments.matchList') : t('tournaments.bracket')}
                    </p>
                    <div className="flex items-center gap-3">
                      {isEmbeddedInDesktop() ? (
                        <button
                          type="button"
                          onClick={() =>
                            requestOpenExternal(`${window.location.origin}/tournaments/${selected.id}/bracket`)
                          }
                          className="font-mono-label text-muted-foreground hover:text-accent flex items-center gap-1 text-[10px]"
                        >
                          <ExternalLink size={10} /> {t('tournaments.openInNewPage')}
                        </button>
                      ) : (
                        <a
                          href={`/tournaments/${selected.id}/bracket`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-mono-label text-muted-foreground hover:text-accent flex items-center gap-1 text-[10px]"
                        >
                          <ExternalLink size={10} /> {t('tournaments.openInNewPage')}
                        </a>
                      )}
                      <button
                        onClick={loadSelected}
                        className="font-mono-label text-muted-foreground hover:text-foreground flex items-center gap-1 text-[10px]"
                      >
                        <RefreshCw size={10} /> {t('tournaments.refresh')}
                      </button>
                    </div>
                  </div>
                  <TournamentBracket tournament={selected} onUpdate={loadSelected} />
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="mt-8">
        <SponsorStrip />
      </div>

      {showCreateModal && (
        <CreateTournamentModal onClose={() => setShowCreateModal(false)} onCreate={loadTournaments} />
      )}
      {showAddTeam && selected && (
        <AddTeamModal
          tournament={selected}
          team={editingTeam}
          allUsers={allUsers}
          onClose={() => { setShowAddTeam(false); setEditingTeam(undefined) }}
          onAdd={loadSelected}
        />
      )}
    </main>
  )
}
