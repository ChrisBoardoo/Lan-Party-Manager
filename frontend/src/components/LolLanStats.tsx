import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronRight, Download, Gamepad2, Trash2 } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { lolApi } from '../lib/api'
import {
  LOL_SORT_ASCENDING_FIRST, LolSortKey, formatDamage, formatDuration, formatOneDecimal,
  lolCsvFilename, lolStatsCsv, sortLolLines,
} from '../lib/lolStats'
import { csvFormatFor, downloadCsv } from '../lib/csv'
import { timeAgo } from '../lib/formatDate'
import { todayIso } from '../lib/eventDates'
import { formatWinRate } from './GameStatsTab'
import type { LolCategory, LolMatch, LolStats } from '../types'

const CATEGORIES: LolCategory[] = ['custom', 'aram', 'aram_chaos', 'matchmade']

// Games > League of Legends tracker: every game the members' desktop apps
// sent — fun customs, ARAM, ranked, tournament matches alike — overall, or
// one LAN's (backend/router_lol.py). The table shows even while empty: before
// the first game it's what tells the crew what's about to be tracked.
// `scopeName` (the LAN's title, none for global) only names the CSV export.
export default function LolLanStats({ eventId, scopeName }: { eventId?: number; scopeName?: string }) {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [category, setCategory] = useState<LolCategory | null>(null)
  const [stats, setStats] = useState<LolStats | null>(null)
  const [sortKey, setSortKey] = useState<LolSortKey>('kda')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const load = () =>
    lolApi.stats(eventId, category ?? undefined).then(setStats).catch(() => setStats(null))

  useEffect(() => { load() }, [eventId, category])

  const sortBy = (key: LolSortKey) => {
    if (key === sortKey) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir(LOL_SORT_ASCENDING_FIRST.includes(key) ? 'asc' : 'desc')
    }
  }

  const header = (key: LolSortKey, label: string, title?: string) => (
    <th className="px-3 py-2 text-center font-mono-label text-muted-foreground" title={title}>
      <button onClick={() => sortBy(key)} className={`hover:text-foreground ${sortKey === key ? 'text-accent' : ''}`}>
        {label}{sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
      </button>
    </th>
  )

  const rows = stats ? sortLolLines(stats.players, sortKey, sortDir) : []

  // The table as shown — this LAN or global, this category, this sort.
  const exportCsv = () => {
    const headers = [
      'player', 'games', 'wins', 'losses', 'winRate', 'kills', 'deaths', 'assists', 'kda', 'damage',
      'avgKills', 'avgDeaths', 'avgAssists', 'avgDamage',
    ].map((k) => t(`games.lol.csv.${k}`))
    downloadCsv(
      lolStatsCsv(rows, headers, csvFormatFor(i18n.language)),
      lolCsvFilename(scopeName, category, todayIso()),
    )
  }

  return (
    <div className="border border-border bg-card">
      <div className="p-4 border-b border-border space-y-3">
        <div>
          <p className="font-mono-label text-accent flex items-center gap-1.5">
            <Gamepad2 size={12} strokeWidth={1.5} /> {t('games.lol.title')}
          </p>
          <p className="text-xs text-muted-foreground mt-1">{t('games.lol.hint')}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {[null, ...CATEGORIES].map((c) => (
            <button
              key={c ?? 'all'}
              onClick={() => setCategory(c)}
              className={`px-3 py-1.5 border font-mono-label text-xs transition-colors ${
                category === c
                  ? 'border-accent text-accent bg-accent/10'
                  : 'border-border text-muted-foreground hover:text-foreground hover:border-border-hover'
              }`}
            >
              {t(`games.lol.category.${c ?? 'all'}`)}
            </button>
          ))}
        </div>
        {stats && (
          <p className="font-mono-label text-muted-foreground text-[10px]">
            {t('games.lol.summaryLine', { count: stats.matches })}
          </p>
        )}
      </div>

      {stats === null ? (
        <div className="h-24 bg-muted animate-pulse" />
      ) : (
        <>
          {stats.records.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-px bg-border border-b border-border">
              {stats.records.map((r) => (
                <div key={r.kind} className="bg-card p-4">
                  <p className="font-mono-label text-muted-foreground text-[10px]">{t(`games.lol.record.${r.kind}`)}</p>
                  <p className="text-2xl font-black text-foreground mt-1">
                    {r.kind === 'damage' ? formatDamage(r.value) : r.value}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    <Link to={`/players/${r.user_id}`} className="font-bold text-foreground hover:text-accent">{r.username}</Link>
                    {r.champion && <> · {r.champion}</>}
                  </p>
                </div>
              ))}
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted">
                  <th className="px-4 py-2 text-left font-mono-label text-muted-foreground">{t('tournaments.stats.player')}</th>
                  {header('games', t('games.lol.games'), t('games.lol.gamesLong'))}
                  {header('win_rate', '%', t('games.lol.winRateHint'))}
                  {header('avg_kills', 'K', t('games.lol.avgHint'))}
                  {header('avg_deaths', 'D', t('games.lol.avgHint'))}
                  {header('avg_assists', 'A', t('games.lol.avgHint'))}
                  {header('kda', 'KDA', t('games.lol.kdaHint'))}
                  {header('avg_damage', t('games.lol.damage'), t('games.lol.damageHint'))}
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.user_id} className="border-b border-border last:border-0">
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
                    <td className="px-3 py-3 text-center font-mono text-muted-foreground">{p.games}</td>
                    <td className="px-3 py-3 text-center font-mono text-foreground">{formatWinRate(p.win_rate)}</td>
                    <td className="px-3 py-3 text-center font-mono text-foreground">{formatOneDecimal(p.avg_kills)}</td>
                    <td className="px-3 py-3 text-center font-mono text-muted-foreground">{formatOneDecimal(p.avg_deaths)}</td>
                    <td className="px-3 py-3 text-center font-mono text-foreground">{formatOneDecimal(p.avg_assists)}</td>
                    <td className="px-3 py-3 text-center font-mono font-black text-accent">{formatOneDecimal(p.kda)}</td>
                    <td className="px-3 py-3 text-center font-mono text-foreground">{formatDamage(p.avg_damage)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* Below the table, not in a row: the table scrolls sideways on a phone
              and would cut the message. No game yet (overall, or during this
              LAN) vs games with no member in them (nobody's Riot ID matched). */}
          {rows.length === 0 && (
            <p className="px-4 py-8 text-center font-mono-label text-muted-foreground">
              {stats.matches > 0
                ? t('games.lol.empty')
                : t(eventId ? 'games.lol.noGamesYetLan' : 'games.lol.noGamesYet')}
            </p>
          )}
          {rows.length > 0 && (
            <div className="flex justify-end px-4 py-3 border-t border-border">
              <button
                onClick={exportCsv}
                title={t('games.lol.csvExportHint')}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-border font-mono-label text-xs text-muted-foreground hover:text-foreground hover:border-border-hover transition-colors"
              >
                <Download size={12} strokeWidth={1.5} /> {t('games.lol.csvExport')}
              </button>
            </div>
          )}
        </>
      )}

      {isAdmin && <CapturedMatches eventId={eventId} onDeleted={load} />}
    </div>
  )
}

// Admin-only, collapsed by default: the captured games themselves, so a test
// run or a remake can be taken out of the stats.
function CapturedMatches({ eventId, onDeleted }: { eventId?: number; onDeleted: () => void }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [matches, setMatches] = useState<LolMatch[] | null>(null)
  const [busy, setBusy] = useState<number | null>(null)

  const load = () => lolApi.matches(eventId).then(setMatches).catch(() => setMatches([]))

  useEffect(() => {
    if (open) load()
  }, [open, eventId])

  const remove = async (m: LolMatch) => {
    if (!window.confirm(t('games.lol.deleteConfirm'))) return
    setBusy(m.id)
    try {
      await lolApi.deleteMatch(m.id)
      await load()
      onDeleted()
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="border-t border-border">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-1.5 px-4 py-3 font-mono-label text-xs text-muted-foreground hover:text-foreground"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />} {t('games.lol.manageTitle')}
      </button>
      {open && matches !== null && (
        matches.length === 0 ? (
          <p className="px-4 pb-4 text-xs text-muted-foreground">{t('games.lol.noMatches')}</p>
        ) : (
          matches.map((m) => (
            <div key={m.id} className="flex items-center justify-between gap-3 px-4 py-3 border-t border-border">
              <div className="min-w-0 flex-1">
                <p className="text-sm text-foreground">
                  {t(`games.lol.category.${m.category}`)}
                  <span className="text-muted-foreground"> · {formatDuration(m.duration_s)} · {timeAgo(m.played_at)}</span>
                </p>
                <p className="text-xs text-muted-foreground truncate">
                  {m.players.map((p) => p.username ?? p.riot_id).join(', ')}
                  {m.submitted_by && <> — {t('games.lol.sentBy', { name: m.submitted_by })}</>}
                </p>
              </div>
              <button
                onClick={() => remove(m)}
                disabled={busy === m.id}
                title={t('games.lol.deleteMatch')}
                className="flex-shrink-0 text-muted-foreground hover:text-red-400 disabled:opacity-50"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))
        )
      )}
    </div>
  )
}
