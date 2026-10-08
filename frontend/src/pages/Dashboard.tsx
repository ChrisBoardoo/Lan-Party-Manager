import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import { useAppConfig } from '../contexts/AppConfigContext'
import { useUpcomingEvent } from '../contexts/UpcomingEventContext'
import { usersApi, expensesApi, tournamentsApi, activityApi, mediaApi, miniGamesApi, xpApi } from '../lib/api'
import { useActivityFeed } from '../hooks/useActivityFeed'
import { User, Tournament, ActivityLogEntry, HallOfFameEntry, MediaItem, MiniGameInfo, MiniGameScore, XpCrewEntry } from '../types'
import { timeAgo, formatDate } from '../lib/formatDate'
import Badge from '../components/ui/Badge'
import Lightbox from '../components/ui/Lightbox'
import EventCountdown from '../components/ui/EventCountdown'
import CravingChatSection from '../components/CravingChatSection'
import TrophyVoteBanner from '../components/trophies/TrophyVoteBanner'
import XpCoin from '../components/xp/XpCoin'
import XpLeaderboard from '../components/xp/XpLeaderboard'
import { ReactionBar } from '../components/MediaReactions'
import { ChefHat, Trophy, DollarSign, User as UserIcon, ArrowRight, Medal, Activity, ImageIcon, Play, UserX, UserCheck, Gamepad2, Download, CalendarDays, MessageCircle, ChevronDown, ChevronUp } from 'lucide-react'
import { formatMiniGameScore } from '../components/MiniGames'
import { buildCsv, csvFormatFor, downloadCsv } from '../lib/csv'

const ACTIVITY_PREVIEW_COUNT = 6

const RECENT_MEDIA_COUNT = 8

const ACTION_ICONS: Record<string, string> = {
  media_upload: '📸',
  match_completed: '⚔️',
  expense_created: '💸',
  lan_countdown: '⏳',
  rsvp_adjusted: '🗓️',
}

export default function Dashboard() {
  const { user } = useAuth()
  const { currency, treasuryEnabled, minigamesEnabled, trophiesEnabled, xpEnabled } = useAppConfig()
  const { nextEvent, chatEvent } = useUpcomingEvent()
  const { t, i18n } = useTranslation()
  const [users, setUsers] = useState<User[]>([])
  const [tournaments, setTournaments] = useState<Tournament[]>([])
  const [totalExpenses, setTotalExpenses] = useState(0)
  const [activity, setActivity] = useState<ActivityLogEntry[]>([])
  const [hallOfFame, setHallOfFame] = useState<HallOfFameEntry[]>([])
  const [recentMedia, setRecentMedia] = useState<MediaItem[]>([])
  const [viewer, setViewer] = useState<{ items: MediaItem[]; index: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [reactingActivityId, setReactingActivityId] = useState<number | null>(null)
  const [activityExpanded, setActivityExpanded] = useState(false)
  // The Hub is where people land between two LANs, which is exactly when a mini-game
  // is worth surfacing — so the card lives here as well as behind the Arena tab.
  const [featuredGame, setFeaturedGame] = useState<MiniGameInfo | null>(null)
  const [featuredTop, setFeaturedTop] = useState<MiniGameScore | null>(null)
  const [featuredMine, setFeaturedMine] = useState<MiniGameScore | null>(null)
  const [crewXp, setCrewXp] = useState<XpCrewEntry[]>([])

  useEffect(() => {
    Promise.all([
      usersApi.getAll(),
      tournamentsApi.getAll(),
      activityApi.getAll(20),
      tournamentsApi.getHallOfFame(),
      mediaApi.getAll(),
    ]).then(([u, tour, act, hof, media]) => {
      setUsers(u)
      setTournaments(tour)
      setActivity(act)
      setHallOfFame(hof)
      setRecentMedia(media.slice(0, RECENT_MEDIA_COUNT))
    }).finally(() => setLoading(false))
  }, [])

  // Separate from the main load: mini-games are opt-in, so this only runs when the
  // feature is on, and a failure here must never blank the rest of the Hub.
  useEffect(() => {
    if (!minigamesEnabled) {
      setFeaturedGame(null)
      return
    }
    let cancelled = false
    miniGamesApi
      .listGames()
      .then(async (list) => {
        const game = list[0]
        if (!game || cancelled) return
        const [board, mine] = await Promise.all([
          miniGamesApi.leaderboard(game.slug, 1),
          miniGamesApi.myBest(game.slug),
        ])
        if (cancelled) return
        setFeaturedGame(game)
        setFeaturedTop(board[0] ?? null)
        setFeaturedMine(mine)
      })
      .catch(() => {
        if (!cancelled) setFeaturedGame(null)
      })
    return () => { cancelled = true }
  }, [minigamesEnabled])

  // XP is opt-in and require_feature-gated: own effect, own catch, same reason as
  // the mini-games card above.
  useEffect(() => {
    if (!xpEnabled) { setCrewXp([]); return }
    xpApi.crew().then(setCrewXp).catch(() => setCrewXp([]))
  }, [xpEnabled])
  const xpByUser = new Map(crewXp.map((e) => [e.user_id, e]))

  useActivityFeed(!loading, (newItems) => {
    setActivity((prev) => {
      const existingIds = new Set(prev.map((e) => e.id))
      const fresh = newItems.filter((e) => !existingIds.has(e.id))
      if (!fresh.length) return prev
      return [...fresh, ...prev].slice(0, 20)
    })
  })

  // Kept out of the Promise.all above: /prorata is require_feature("treasury"),
  // which 404s for non-admins while the feature is off — one rejection there
  // would blank the whole hub for them.
  useEffect(() => {
    if (!treasuryEnabled) { setTotalExpenses(0); return }
    expensesApi.getProRata().then((pr) => setTotalExpenses(pr.total_expenses ?? 0)).catch(() => setTotalExpenses(0))
  }, [treasuryEnabled])

  const profilesDone = users.filter((u) => u.profile_complete).length
  const mealVolunteers = users.filter((u) => u.is_meal_prep_volunteer).length
  const onlineCount = users.filter((u) => u.is_online).length
  const isAdmin = user?.role === 'admin'

  const stats = [
    { label: t('dashboard.statPlayers'), value: users.length, icon: UserIcon, sub: t('dashboard.statPlayersSub', { count: profilesDone }) },
    { label: t('dashboard.statMealPrep'), value: mealVolunteers, icon: ChefHat, sub: t('dashboard.statMealPrepSub') },
    { label: t('dashboard.statTournaments'), value: tournaments.length, icon: Trophy, sub: t('dashboard.statTournamentsSub') },
    ...(treasuryEnabled
      ? [{ label: t('dashboard.statBudget'), value: `${totalExpenses.toFixed(0)}${currency}`, icon: DollarSign, sub: t('dashboard.statBudgetSub') }]
      : []),
  ]

  const toggleActivityReaction = async (activityId: number, emoji: string) => {
    setReactingActivityId(activityId)
    try {
      const updated = await activityApi.react(activityId, emoji)
      setActivity((prev) => prev.map((e) => (e.id === activityId ? updated : e)))
    } catch {
      // A failed toggle just leaves the row as it was — nothing to recover.
    } finally {
      setReactingActivityId(null)
    }
  }

  const handleToggleActive = async (e: React.MouseEvent, target: User) => {
    e.preventDefault()
    e.stopPropagation()
    if (target.is_active && !confirm(t('players.deactivateConfirm', { username: target.username }))) return
    if (target.is_active) {
      await usersApi.deactivate(target.id)
    } else {
      await usersApi.reactivate(target.id)
    }
    const updated = await usersApi.getAll()
    setUsers(updated)
  }

  // Client-side CSV (lib/csv.ts), no backend endpoint. Sizes were pulled off
  // the roster cards themselves (too much roster-feedback noise per player);
  // admins still need the full list at a glance to order merch, hence this export.
  const exportSizesCsv = () => {
    const header = [t('dashboard.csvUsername'), t('dashboard.csvSize')]
    const rows = [header, ...users.map((u) => [u.username, u.clothing_size ?? ''])]
    downloadCsv(buildCsv(rows, csvFormatFor(i18n.language)), 'tshirt-sizes.csv')
  }

  return (
    <main className="max-w-6xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="mb-12">
        <div className="font-mono-label text-accent mb-3">{t('dashboard.tagline')}</div>
        <h1 className="text-5xl lg:text-7xl font-black tracking-tighter text-foreground leading-none mb-4">
          {t('dashboard.heroLine1')}
          <br />
          <span className="text-accent">{t('dashboard.heroLine2')}</span>
        </h1>
        <p className="text-muted-foreground text-base">
          {t('dashboard.welcomeBack')}{' '}
          <span className="text-foreground font-bold">{user?.username}</span>
          {user?.role !== 'user' && (
            <span className="font-mono-label text-accent ml-2">[{t(`nav.role.${user?.role}`)}]</span>
          )}
        </p>
      </div>

      {/* Upcoming event banner — only when the next event is within 30 days */}
      {nextEvent && (
        <Link
          to={`/events/${nextEvent.id}`}
          className="mb-12 border border-accent bg-accent/5 p-6 flex flex-wrap items-center justify-between gap-4 hover:bg-accent/10 transition-colors"
        >
          <div className="flex items-center gap-3 min-w-0">
            <CalendarDays size={20} strokeWidth={1.5} className="text-accent flex-shrink-0" />
            <div className="min-w-0">
              <p className="font-mono-label text-accent mb-1">{t('dashboard.upcomingEvent')}</p>
              <p className="text-lg font-black tracking-tight text-foreground truncate">{nextEvent.title}</p>
              <p className="text-sm text-muted-foreground">
                {formatDate(nextEvent.start_date)}
                {nextEvent.start_date !== nextEvent.end_date && <> → {formatDate(nextEvent.end_date)}</>}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4 flex-shrink-0">
            <EventCountdown startDate={nextEvent.start_date} format="full" />
          </div>
        </Link>
      )}
      {nextEvent && trophiesEnabled && nextEvent.my_rsvp === 'in' && <TrophyVoteBanner eventId={nextEvent.id} />}

      {/* Stats bar */}
      <div className={`grid grid-cols-2 ${treasuryEnabled ? 'md:grid-cols-4' : 'md:grid-cols-3'} gap-px bg-border mb-12`}>
        {stats.map(({ label, value, icon: Icon, sub }) => (
          <div key={label} className="bg-card p-6 group">
            <div className="flex items-start justify-between mb-3">
              <p className="font-mono-label text-muted-foreground">{label}</p>
              <Icon size={16} strokeWidth={1.5} className="text-muted-foreground group-hover:text-accent transition-colors" />
            </div>
            <p className="text-4xl font-black tracking-tighter text-foreground">{value}</p>
            <p className="font-mono-label text-muted-foreground mt-1">{sub}</p>
          </div>
        ))}
      </div>

      {/* Quick actions */}
      {!user?.profile_complete && (
        <div className="mb-12 border-l-2 border-accent pl-6 py-2">
          <p className="font-mono-label text-accent mb-1">{t('dashboard.actionRequired')}</p>
          <p className="text-sm text-muted-foreground mb-3">
            {t('dashboard.completeProfile')}
          </p>
          <Link
            to="/profile"
            className="inline-flex items-center gap-2 font-mono-label text-foreground hover:text-accent transition-colors"
          >
            {t('dashboard.goToProfile')} <ArrowRight size={12} />
          </Link>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-12">
        {/* Players grid */}
        <div className="lg:col-span-2">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-black tracking-tight text-foreground">{t('dashboard.crewRoster')}</h2>
            <div className="flex items-center gap-3">
              <span className="font-mono-label text-muted-foreground">
                {t('dashboard.playerCount', { count: users.length })}
              </span>
              {onlineCount > 0 && (
                <span className="font-mono-label text-green-500 flex items-center gap-1.5">
                  <span className="w-2 h-2 bg-green-500 inline-block" aria-hidden="true" />
                  {t('dashboard.onlineCount', { count: onlineCount })}
                </span>
              )}
              {isAdmin && (
                <button
                  onClick={exportSizesCsv}
                  className="font-mono-label text-muted-foreground hover:text-accent transition-colors flex items-center gap-1.5"
                  title={t('dashboard.exportSizes')}
                >
                  <Download size={12} strokeWidth={1.5} /> {t('dashboard.exportSizes')}
                </button>
              )}
            </div>
          </div>

          {loading ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-px bg-border">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="bg-card h-40 animate-pulse" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-px bg-border">
              {users.map((u) => (
                <Link
                  key={u.id}
                  to={`/players/${u.id}`}
                  className={`bg-card p-5 relative group transition-colors hover:bg-muted/50 block ${
                    u.id === user?.id ? 'border-t-2 border-accent' : ''
                  } ${!u.is_active ? 'opacity-50' : ''}`}
                >
                  {isAdmin && u.id !== user?.id && (
                    <button
                      onClick={(e) => handleToggleActive(e, u)}
                      title={u.is_active ? t('players.deactivateAccount') : t('players.reactivateAccount')}
                      className="absolute bottom-4 right-4 z-10 p-1 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-red-400 transition-opacity"
                    >
                      {u.is_active ? <UserX size={14} strokeWidth={1.5} /> : <UserCheck size={14} strokeWidth={1.5} />}
                    </button>
                  )}
                  <div className="relative w-12 h-12 mb-3">
                    <div className="w-12 h-12 bg-muted border border-border overflow-hidden">
                      {u.avatar_url ? (
                        <img src={u.avatar_url} alt={u.username} className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <span className="text-xl font-black text-muted-foreground">
                            {u.username[0].toUpperCase()}
                          </span>
                        </div>
                      )}
                    </div>
                    {u.is_online && (
                      <span
                        title={t('dashboard.online')}
                        aria-label={t('dashboard.online')}
                        className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-green-500 border border-background animate-online-pulse"
                      />
                    )}
                  </div>
                  <p className="font-bold text-sm text-foreground truncate mb-1">{u.username}</p>
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <p className="font-mono-label text-muted-foreground truncate">{t(`nav.role.${u.role}`)}</p>
                    {xpByUser.has(u.id) && (
                      <span
                        className="flex items-center gap-1 font-mono-label text-muted-foreground text-[10px] flex-shrink-0"
                        title={t('xp.total', { total: xpByUser.get(u.id)!.total.toLocaleString() })}
                      >
                        <XpCoin level={xpByUser.get(u.id)!.level} size={14} />
                        {t('xp.levelShort', { level: xpByUser.get(u.id)!.level })}
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {u.profile_complete ? (
                      <Badge variant="success">{t('dashboard.ready')}</Badge>
                    ) : (
                      <Badge variant="warning">{t('dashboard.pending')}</Badge>
                    )}
                    {u.is_meal_prep_volunteer && <Badge variant="muted">🍕 {t('dashboard.chef')}</Badge>}
                    {u.is_tournament_organizer && <Badge variant="muted">🏆 {t('dashboard.organizer')}</Badge>}
                    {!u.is_active && <Badge variant="danger">{t('dashboard.inactiveBadge')}</Badge>}
                  </div>
                </Link>
              ))}
            </div>
          )}

          {/* Craving Chat — right under the roster on purpose (crew feedback:
              buried inside LAN PARTY > event > scroll was "not practical").
              Clearly tied to the upcoming event, but reachable in one glance
              from the Hub instead of several clicks — see md/2.features/Craving_chat_v2.md.
              The title itself links to the full-page version (CravingChatPage,
              also reachable from the Navbar's temporary chat icon). */}
          {chatEvent && (
            <div className="mt-6">
              <Link to="/craving-chat" className="flex items-center gap-2 mb-4 w-fit group">
                <MessageCircle size={14} strokeWidth={1.5} className="text-accent" />
                <h2 className="text-lg font-black tracking-tight text-foreground group-hover:text-accent transition-colors">
                  {t('cravingChat.blockTitle')}
                </h2>
              </Link>
              <CravingChatSection eventId={chatEvent.id} attendees={chatEvent.attendees} />
            </div>
          )}
        </div>

        {/* Sidebar: Activity + Hall of Fame */}
        <div className="space-y-6">
          {/* Activity feed */}
          <div>
            <div className="flex items-center gap-2 mb-4">
              <Activity size={14} strokeWidth={1.5} className="text-accent" />
              <h2 className="text-lg font-black tracking-tight text-foreground">{t('dashboard.activity')}</h2>
            </div>
            <div className="border border-border bg-card">
              {loading ? (
                <div className="p-4 space-y-3">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="h-8 bg-muted animate-pulse" />
                  ))}
                </div>
              ) : activity.length === 0 ? (
                <div className="p-6 text-center">
                  <p className="font-mono-label text-muted-foreground text-xs">{t('dashboard.noActivityYet')}</p>
                </div>
              ) : (
                <div>
                  {(activityExpanded ? activity : activity.slice(0, ACTIVITY_PREVIEW_COUNT)).map((entry) => (
                    <div
                      key={entry.id}
                      className="flex items-start gap-3 px-4 py-3 border-b border-border last:border-0"
                    >
                      {entry.media ? (
                        <button
                          type="button"
                          onClick={() => setViewer({ items: [entry.media!], index: 0 })}
                          className="w-10 h-10 flex-shrink-0 border border-border bg-muted overflow-hidden"
                        >
                          {entry.media.file_type === 'image' ? (
                            <img
                              src={entry.media.url}
                              alt={entry.media.original_name}
                              className="w-full h-full object-cover"
                            />
                          ) : entry.media.thumbnail_url ? (
                            <img
                              src={entry.media.thumbnail_url}
                              alt={entry.media.original_name}
                              className="w-full h-full object-cover"
                            />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center">
                              <Play size={12} strokeWidth={1.5} className="text-muted-foreground" />
                            </div>
                          )}
                        </button>
                      ) : (
                        <span className="text-sm mt-0.5">
                          {ACTION_ICONS[entry.action] ?? '•'}
                        </span>
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-foreground leading-snug truncate">
                          {entry.description}
                        </p>
                        <p className="font-mono-label text-muted-foreground text-[10px] mt-0.5">
                          {entry.user.username} · {timeAgo(entry.created_at)}
                        </p>
                        <div className="mt-1.5">
                          <ReactionBar
                            reactions={entry.reactions}
                            onToggle={(emoji) => toggleActivityReaction(entry.id, emoji)}
                            busy={reactingActivityId === entry.id}
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                  {activity.length > ACTIVITY_PREVIEW_COUNT && (
                    <button
                      type="button"
                      onClick={() => setActivityExpanded((prev) => !prev)}
                      className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 font-mono-label text-muted-foreground hover:text-accent transition-colors"
                    >
                      {activityExpanded ? (
                        <>{t('dashboard.activitySeeLess')} <ChevronUp size={12} strokeWidth={1.5} /></>
                      ) : (
                        <>{t('dashboard.activitySeeAll', { count: activity.length })} <ChevronDown size={12} strokeWidth={1.5} /></>
                      )}
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Crew XP */}
          <XpLeaderboard entries={crewXp} currentUserId={user?.id} />

          {/* Mini-games */}
          {minigamesEnabled && featuredGame && (
            <div>
              <div className="flex items-center gap-2 mb-4">
                <Gamepad2 size={14} strokeWidth={1.5} className="text-accent" />
                <h2 className="text-lg font-black tracking-tight text-foreground">
                  {t('dashboard.miniGames')}
                </h2>
              </div>
              <Link
                to="/minigames"
                className="block border border-border bg-card p-4 hover:border-accent transition-colors duration-150 group"
              >
                <div className="flex items-center justify-between gap-3 mb-3">
                  <span className="font-bold text-sm text-foreground truncate">
                    {t(`minigames.game.${featuredGame.slug}.name`, featuredGame.slug)}
                  </span>
                  <ArrowRight
                    size={14}
                    strokeWidth={1.5}
                    className="text-muted-foreground group-hover:text-accent flex-shrink-0 transition-colors duration-150"
                  />
                </div>
                <div className="flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <div className="font-mono-label text-muted-foreground text-[10px]">
                      {t('minigames.topScore')}
                    </div>
                    <div className="text-foreground tabular-nums truncate">
                      {featuredTop ? (
                        <>
                          <span className="font-black">
                            {formatMiniGameScore(featuredGame.metric, featuredTop.score)}
                          </span>{' '}
                          <span className="text-muted-foreground text-xs">
                            {featuredTop.user.username}
                          </span>
                        </>
                      ) : (
                        <span className="text-muted-foreground text-xs">
                          {t('minigames.noScoresYet')}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <div className="font-mono-label text-muted-foreground text-[10px]">
                      {t('minigames.yourBest')}
                    </div>
                    <div className="text-accent font-black tabular-nums">
                      {featuredMine
                        ? formatMiniGameScore(featuredGame.metric, featuredMine.score)
                        : '—'}
                    </div>
                  </div>
                </div>
              </Link>
            </div>
          )}

          {/* Hall of Fame */}
          {hallOfFame.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-4">
                <Medal size={14} strokeWidth={1.5} className="text-accent" />
                <h2 className="text-lg font-black tracking-tight text-foreground">{t('dashboard.hallOfFame')}</h2>
              </div>
              <div className="border border-border bg-card">
                {hallOfFame.map((entry, idx) => (
                  <div
                    key={entry.user_id}
                    className="flex items-center gap-3 px-4 py-3 border-b border-border last:border-0"
                  >
                    <span className={`font-mono font-black text-sm w-5 text-center ${
                      idx === 0 ? 'text-yellow-400' : idx === 1 ? 'text-gray-400' : idx === 2 ? 'text-orange-400' : 'text-muted-foreground'
                    }`}>
                      {idx + 1}
                    </span>
                    <div className="w-8 h-8 bg-muted border border-border overflow-hidden flex-shrink-0">
                      {entry.avatar_url ? (
                        <img src={entry.avatar_url} alt={entry.username} className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <span className="text-xs font-black text-muted-foreground">
                            {entry.username[0].toUpperCase()}
                          </span>
                        </div>
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-bold text-foreground truncate">{entry.username}</p>
                      <p className="font-mono-label text-muted-foreground text-[10px]">
                        {t('dashboard.hofLine', { wins: entry.wins, count: entry.participations })}
                      </p>
                    </div>
                    {idx === 0 && <Trophy size={12} className="text-yellow-400 flex-shrink-0" />}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recent Media */}
          {recentMedia.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <ImageIcon size={14} strokeWidth={1.5} className="text-accent" />
                  <h2 className="text-lg font-black tracking-tight text-foreground">{t('dashboard.recentMedia')}</h2>
                </div>
                <Link to="/media" className="font-mono-label text-muted-foreground hover:text-accent text-[10px]">
                  {t('dashboard.viewAll')}
                </Link>
              </div>
              <div className="grid grid-cols-4 gap-1">
                {recentMedia.map((item, i) => (
                  <button
                    key={item.id}
                    onClick={() => setViewer({ items: recentMedia, index: i })}
                    className="aspect-square border border-border bg-card overflow-hidden group relative"
                  >
                    {item.file_type === 'image' ? (
                      <img
                        src={item.url}
                        alt={item.original_name}
                        className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                      />
                    ) : item.thumbnail_url ? (
                      <img
                        src={item.thumbnail_url}
                        alt={item.original_name}
                        className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center">
                        <Play size={14} strokeWidth={1.5} className="text-muted-foreground" />
                      </div>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {viewer && <Lightbox items={viewer.items} index={viewer.index} onClose={() => setViewer(null)} />}

      {/* Bottom links */}
      <div className={`grid grid-cols-1 ${treasuryEnabled ? 'md:grid-cols-2' : ''} gap-px bg-border mb-12`}>
        <Link
          to="/tournaments"
          className={`bg-card p-8 group hover:bg-muted/50 transition-colors flex items-start justify-between ${treasuryEnabled ? 'border-b md:border-b-0 border-border' : ''}`}
        >
          <div>
            <Trophy size={20} strokeWidth={1.5} className="text-accent mb-3" />
            <h3 className="text-xl font-black tracking-tight text-foreground mb-1">{t('nav.arena')}</h3>
            <p className="text-sm text-muted-foreground">{t('dashboard.arenaDesc')}</p>
          </div>
          <ArrowRight size={16} strokeWidth={1.5} className="text-muted-foreground group-hover:text-accent transition-colors mt-1" />
        </Link>
        {treasuryEnabled && (
          <Link
            to="/finances"
            className="bg-card p-8 group hover:bg-muted/50 transition-colors flex items-start justify-between"
          >
            <div>
              <DollarSign size={20} strokeWidth={1.5} className="text-accent mb-3" />
              <h3 className="text-xl font-black tracking-tight text-foreground mb-1">{t('nav.treasury')}</h3>
              <p className="text-sm text-muted-foreground">{t('dashboard.treasuryDesc')}</p>
            </div>
            <ArrowRight size={16} strokeWidth={1.5} className="text-muted-foreground group-hover:text-accent transition-colors mt-1" />
          </Link>
        )}
      </div>

      {/* Admin — invite management */}
      {user?.role === 'admin' && (
        <div className="mb-12 border-l-2 border-accent pl-6 py-2">
          <p className="font-mono-label text-accent mb-1">{t('dashboard.playerInvitesAdminOnly')}</p>
          <p className="text-sm text-muted-foreground mb-3">
            {t('dashboard.inviteCodesDesc')}
          </p>
          <Link
            to="/events"
            className="inline-flex items-center gap-2 font-mono-label text-foreground hover:text-accent transition-colors"
          >
            {t('dashboard.goToLanParty')} <ArrowRight size={12} />
          </Link>
        </div>
      )}
    </main>
  )
}
