import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import { tournamentsApi, eventsApi } from '../lib/api'
import type {
  GameStatsDetail, GameStatsSummary, LanEvent, TournamentGame, UnlinkedTournament,
} from '../types'
import { BarChart3, Link2 } from 'lucide-react'

export function formatWinRate(rate: number | null): string {
  return rate == null ? '—' : `${Math.round(rate * 100)} %`
}

// Arena > "Stats by game": per-player W/L/D per catalog game, all LANs or one.
// Everything is derived server-side from decided matches — nothing to maintain.
export default function GameStatsTab() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [events, setEvents] = useState<LanEvent[]>([])
  const [eventId, setEventId] = useState<number | undefined>(undefined)
  const [overview, setOverview] = useState<GameStatsSummary[] | null>(null)
  const [gameId, setGameId] = useState<number | null>(null)
  const [detail, setDetail] = useState<GameStatsDetail | null>(null)

  useEffect(() => {
    eventsApi
      .getAll()
      .then((es) => setEvents([...es].sort((a, b) => b.start_date.localeCompare(a.start_date))))
      .catch(() => setEvents([]))
  }, [])

  const loadOverview = () =>
    tournamentsApi
      .statsOverview(eventId)
      .then((o) => {
        setOverview(o)
        // Keep the current game if it's still in scope, else show the most played.
        setGameId((cur) => (cur != null && o.some((g) => g.game_id === cur) ? cur : o[0]?.game_id ?? null))
      })
      .catch(() => setOverview([]))

  useEffect(() => { loadOverview() }, [eventId])

  useEffect(() => {
    if (gameId == null) { setDetail(null); return }
    tournamentsApi.statsDetail(gameId, eventId).then(setDetail).catch(() => setDetail(null))
  }, [gameId, eventId])

  const hasDraws = !!detail?.players.some((p) => p.draws > 0)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <label className="font-mono-label text-muted-foreground">{t('tournaments.stats.scope')}</label>
        <select
          value={eventId ?? ''}
          onChange={(e) => setEventId(e.target.value ? Number(e.target.value) : undefined)}
          className="h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none"
        >
          <option value="">{t('tournaments.stats.scopeGlobal')}</option>
          {events.map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}
        </select>
      </div>

      {overview === null ? (
        <div className="h-40 bg-muted animate-pulse" />
      ) : overview.length === 0 ? (
        <div className="border border-border p-8 text-center">
          <BarChart3 size={24} strokeWidth={1} className="text-muted-foreground mx-auto mb-3" />
          <p className="font-mono-label text-muted-foreground mb-2">{t('tournaments.stats.empty')}</p>
          <p className="text-xs text-muted-foreground">{t('tournaments.stats.emptyHint')}</p>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {overview.map((g) => (
              <button
                key={g.game_id}
                onClick={() => setGameId(g.game_id)}
                className={`px-3 py-2 border font-mono-label text-xs transition-colors ${
                  gameId === g.game_id
                    ? 'border-accent text-accent bg-accent/10'
                    : 'border-border text-muted-foreground hover:text-foreground hover:border-border-hover'
                }`}
              >
                {g.name} <span className="opacity-60">· {g.matches}</span>
              </button>
            ))}
          </div>

          {detail && (
            <div className="border border-border bg-card">
              <div className="p-4 border-b border-border">
                <h2 className="text-2xl font-black tracking-tight text-foreground">{detail.name}</h2>
                <p className="font-mono-label text-muted-foreground text-[10px] mt-1">
                  {t('tournaments.stats.summaryLine', {
                    tournaments: detail.tournaments, matches: detail.matches, players: detail.players.length,
                  })}
                </p>
              </div>
              {detail.players.length === 0 ? (
                <p className="p-6 text-center font-mono-label text-muted-foreground">{t('tournaments.stats.noLinkedPlayers')}</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border bg-muted">
                        <th className="px-4 py-2 text-left font-mono-label text-muted-foreground">{t('tournaments.stats.player')}</th>
                        <th className="px-3 py-2 text-center font-mono-label text-muted-foreground" title={t('tournaments.stats.playedLong')}>{t('tournaments.stats.played')}</th>
                        <th className="px-3 py-2 text-center font-mono-label text-muted-foreground">{t('tournaments.standingsTable.w')}</th>
                        <th className="px-3 py-2 text-center font-mono-label text-muted-foreground">{t('tournaments.standingsTable.l')}</th>
                        {hasDraws && <th className="px-3 py-2 text-center font-mono-label text-muted-foreground">{t('tournaments.standingsTable.d')}</th>}
                        <th className="px-3 py-2 text-center font-mono-label text-muted-foreground" title={t('tournaments.stats.winRateHint')}>%</th>
                        <th className="px-3 py-2 text-center font-mono-label text-muted-foreground" title={t('tournaments.stats.titlesLong')}>🏆</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.players.map((p, idx) => (
                        <tr key={p.user_id} className={`border-b border-border last:border-0 ${idx === 0 && p.wins > 0 ? 'bg-accent/5' : ''}`}>
                          <td className="px-4 py-3">
                            <Link to={`/players/${p.user_id}`} className="flex items-center gap-2 group w-fit">
                              {p.avatar_url ? (
                                <img src={p.avatar_url} alt="" className="w-6 h-6 object-cover" />
                              ) : (
                                <span className="w-6 h-6 bg-muted flex items-center justify-center font-black text-xs">
                                  {p.username.charAt(0).toUpperCase()}
                                </span>
                              )}
                              <span className="font-bold text-foreground group-hover:text-accent transition-colors">{p.username}</span>
                            </Link>
                          </td>
                          <td className="px-3 py-3 text-center font-mono text-muted-foreground">{p.played}</td>
                          <td className="px-3 py-3 text-center font-mono text-foreground">{p.wins}</td>
                          <td className="px-3 py-3 text-center font-mono text-muted-foreground">{p.losses}</td>
                          {hasDraws && <td className="px-3 py-3 text-center font-mono text-muted-foreground">{p.draws}</td>}
                          <td className="px-3 py-3 text-center font-mono text-foreground">{formatWinRate(p.win_rate)}</td>
                          <td className="px-3 py-3 text-center font-mono font-black text-accent">{p.titles || ''}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {isAdmin && <UnlinkedTournaments onLinked={loadOverview} />}
    </div>
  )
}

// Admin-only: legacy tournaments whose free-text game name didn't match the
// catalog when the column was added. Until attached they're left out of stats.
function UnlinkedTournaments({ onLinked }: { onLinked: () => void }) {
  const { t } = useTranslation()
  const [rows, setRows] = useState<UnlinkedTournament[]>([])
  const [catalog, setCatalog] = useState<TournamentGame[]>([])
  const [busy, setBusy] = useState<number | null>(null)

  const load = () => tournamentsApi.unlinked().then(setRows).catch(() => setRows([]))

  useEffect(() => {
    load()
    tournamentsApi.games().then((g) => setCatalog([...g].sort((a, b) => a.name.localeCompare(b.name)))).catch(() => {})
  }, [])

  if (rows.length === 0) return null

  const attach = async (tid: number, gameId: number) => {
    setBusy(tid)
    try {
      await tournamentsApi.update(tid, { game_id: gameId })
      await load()
      onLinked()
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="border border-border bg-card">
      <div className="p-4 border-b border-border">
        <p className="font-mono-label text-accent flex items-center gap-1.5">
          <Link2 size={12} strokeWidth={1.5} /> {t('tournaments.stats.unlinkedTitle', { count: rows.length })}
        </p>
        <p className="text-xs text-muted-foreground mt-1">{t('tournaments.stats.unlinkedDesc')}</p>
      </div>
      {rows.map((r) => (
        <div key={r.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-b border-border last:border-0">
          <span className="text-sm text-foreground">{r.game_name}</span>
          <select
            defaultValue=""
            disabled={busy === r.id}
            onChange={(e) => e.target.value && attach(r.id, Number(e.target.value))}
            className="h-9 px-2 bg-input border border-border text-foreground text-xs focus:border-accent outline-none max-w-xs disabled:opacity-50"
          >
            <option value="">{t('tournaments.stats.attachTo')}</option>
            {catalog.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
        </div>
      ))}
    </div>
  )
}
