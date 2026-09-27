import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronUp, Users, Search } from 'lucide-react'
import { gamesApi, usersApi } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'
import type { GameMatch, GameLibraryEntry, User } from '../types'
import Button from './ui/Button'

const PLAYER_COUNT_PRESETS = [2, 3, 4] as const

function Avatar({ username, avatarUrl }: { username: string; avatarUrl: string | null }) {
  return (
    <div className="w-8 h-8 bg-muted border border-border overflow-hidden flex-shrink-0">
      {avatarUrl ? (
        <img src={avatarUrl} alt={username} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full flex items-center justify-center">
          <span className="text-xs font-black text-muted-foreground">{username[0].toUpperCase()}</span>
        </div>
      )}
    </div>
  )
}

function MatchRow({ match }: { match: GameMatch }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="border-b border-border last:border-0">
      <div className="flex items-center gap-3 px-4 py-3">
        <Avatar username={match.username} avatarUrl={match.avatar_url} />
        <span className="text-sm font-medium text-foreground flex-1 min-w-0 truncate">{match.username}</span>
        <span className="font-mono-label text-accent text-xs flex-shrink-0">
          {t('games.sharedCount', { count: match.shared_count })}
        </span>
        <button
          onClick={() => setExpanded((e) => !e)}
          className="text-muted-foreground hover:text-foreground flex-shrink-0"
          title={t('games.sharedGamesToggle')}
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>
      {expanded && (
        <div className="px-4 pb-3 flex flex-wrap gap-2">
          {match.shared_games.map((g) => (
            <span key={g.game_id} className="font-mono-label text-[10px] text-muted-foreground border border-border px-2 py-1">
              {g.name}{g.max_players ? ` · ${g.max_players}p` : ''}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function SessionGameRow({ game }: { game: GameLibraryEntry }) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-border last:border-0">
      <div className="min-w-0">
        <span className="text-sm font-medium text-foreground">{game.name}</span>
        {game.genre && <span className="ml-2 font-mono-label text-[10px] text-muted-foreground">{game.genre}</span>}
      </div>
      <span className="font-mono-label text-xs text-muted-foreground flex-shrink-0 flex items-center gap-1">
        <Users size={12} /> {game.max_players ?? '—'}
      </span>
    </div>
  )
}

// Games > "What are we playing?": who shares my games, and what a given group
// can all play tonight — both from the members' libraries (backend/router_games.py).
export default function GameFinderTab() {
  const { t } = useTranslation()
  const { user } = useAuth()

  const [matches, setMatches] = useState<GameMatch[]>([])
  const [roster, setRoster] = useState<User[]>([])
  const [loading, setLoading] = useState(true)

  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [rosterFilter, setRosterFilter] = useState('')
  const [target, setTarget] = useState<number | null>(null)
  const [customTarget, setCustomTarget] = useState('')
  const [sessionGames, setSessionGames] = useState<GameLibraryEntry[] | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      gamesApi.matches().then(setMatches).catch(() => setMatches([])),
      usersApi.getAll().then(setRoster).catch(() => setRoster([])),
    ]).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (user) setSelected(new Set([user.id]))
  }, [user])

  const filteredRoster = useMemo(() => {
    const q = rosterFilter.trim().toLowerCase()
    if (!q) return roster
    return roster.filter((u) => u.username.toLowerCase().includes(q))
  }, [roster, rosterFilter])

  const toggleSelected = (userId: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(userId) ? next.delete(userId) : next.add(userId)
      return next
    })
  }

  const findGames = () => {
    if (selected.size === 0) return
    const minPlayers = target ?? (customTarget.trim() ? parseInt(customTarget, 10) : undefined)
    setBusy(true)
    gamesApi.session(Array.from(selected), minPlayers)
      .then((r) => setSessionGames(r.games))
      .finally(() => setBusy(false))
  }

  return (
    <>
      {loading ? (
        <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
      ) : (
        <div className="space-y-8">
          {/* Players like me */}
          <section className="border border-border bg-card p-6">
            <p className="font-mono-label text-accent mb-1">{t('games.matchesTitle')}</p>
            <p className="text-xs text-muted-foreground mb-4">{t('games.matchesHint')}</p>
            <div className="border border-border bg-background">
              {matches.length === 0 ? (
                <p className="px-4 py-6 text-center text-sm text-muted-foreground">{t('games.matchesEmpty')}</p>
              ) : (
                matches.map((m) => <MatchRow key={m.user_id} match={m} />)
              )}
            </div>
          </section>

          {/* Build a session */}
          <section className="border border-border bg-card p-6">
            <p className="font-mono-label text-accent mb-1">{t('games.sessionBuilderTitle')}</p>
            <p className="text-xs text-muted-foreground mb-4">{t('games.sessionBuilderHint')}</p>

            <p className="font-mono-label text-muted-foreground text-xs mb-2">{t('games.selectPlayers')}</p>
            <div className="relative mb-3">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                value={rosterFilter}
                onChange={(e) => setRosterFilter(e.target.value)}
                placeholder={t('common.search')}
                className="w-full bg-muted border border-border pl-9 pr-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-accent outline-none"
              />
            </div>
            <div className="border border-border bg-background max-h-56 overflow-y-auto mb-4">
              {filteredRoster.map((u) => (
                <label key={u.id} className="flex items-center gap-3 px-4 py-2 border-b border-border last:border-0 cursor-pointer hover:bg-muted">
                  <input
                    type="checkbox"
                    checked={selected.has(u.id)}
                    onChange={() => toggleSelected(u.id)}
                    className="accent-accent"
                  />
                  <Avatar username={u.username} avatarUrl={u.avatar_url} />
                  <span className="text-sm text-foreground truncate">
                    {u.username}{u.id === user?.id ? ` (${t('gear.you')})` : ''}
                  </span>
                </label>
              ))}
            </div>

            <p className="font-mono-label text-muted-foreground text-xs mb-2">{t('games.playerCountLabel')}</p>
            <div className="flex flex-wrap gap-2 mb-4">
              {PLAYER_COUNT_PRESETS.map((n) => (
                <button
                  key={n}
                  onClick={() => { setTarget(n); setCustomTarget('') }}
                  className={`px-3 py-1.5 border font-mono-label text-xs transition-colors ${
                    target === n ? 'border-accent bg-accent text-accent-foreground' : 'border-border text-muted-foreground hover:border-border-hover'
                  }`}
                >
                  {n}
                </button>
              ))}
              <input
                type="number" min={1} max={999}
                value={customTarget}
                onChange={(e) => { setCustomTarget(e.target.value); setTarget(null) }}
                placeholder={t('games.playerCountCustom')}
                className="w-32 bg-muted border border-border px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-accent outline-none"
              />
            </div>

            <Button size="sm" onClick={findGames} disabled={busy || selected.size === 0}>
              {t('games.buildButton')}
            </Button>

            {sessionGames !== null && (
              <div className="mt-4">
                <p className="text-xs text-muted-foreground mb-2">{t('games.sessionResultHint')}</p>
                <div className="border border-border bg-background">
                  {sessionGames.length === 0 ? (
                    <p className="px-4 py-6 text-center text-sm text-muted-foreground">{t('games.sessionEmpty')}</p>
                  ) : (
                    sessionGames.map((g) => <SessionGameRow key={g.game_id} game={g} />)
                  )}
                </div>
              </div>
            )}
          </section>
        </div>
      )}
    </>
  )
}
