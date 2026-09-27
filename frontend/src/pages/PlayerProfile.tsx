import { useEffect, useState } from 'react'
import { useParams, useNavigate, Navigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import { useAppConfig } from '../contexts/AppConfigContext'
import { usersApi, eventsApi, setupApi, trophiesApi } from '../lib/api'
import { formatDate } from '../lib/formatDate'
import { User, LanEvent, BadgeAward, Setup, UserGameStatsLine, UserTrophy } from '../types'
import Badge from '../components/ui/Badge'
import BadgeList from '../components/BadgeList'
import SetupView from '../components/SetupView'
import { ReactionBar } from '../components/MediaReactions'
import PhotoLightbox from '../components/ui/PhotoLightbox'
import Input from '../components/ui/Input'
import SponsorStrip from '../components/SponsorStrip'
import { formatWinRate } from '../components/GameStatsTab'
import TrophyCase from '../components/trophies/TrophyCase'
import { Shield, CalendarDays, ArrowLeft, KeyRound, Pencil, Check, X, Trash2 } from 'lucide-react'

function isUpcoming(end: string) {
  return new Date(end) >= new Date(new Date().toDateString())
}

export default function PlayerProfile() {
  const { userId } = useParams<{ userId: string }>()
  const navigate = useNavigate()
  const { user: currentUser, isAdmin } = useAuth()
  const { recapEnabled, setupEnabled, trophiesEnabled } = useAppConfig()
  const { t } = useTranslation()
  const [player, setPlayer] = useState<User | null>(null)
  const [badges, setBadges] = useState<BadgeAward[]>([])
  const [gameStats, setGameStats] = useState<UserGameStatsLine[]>([])
  const [trophies, setTrophies] = useState<UserTrophy[]>([])
  const [setup, setSetup] = useState<Setup | null>(null)
  const [reacting, setReacting] = useState(false)
  const [showAvatar, setShowAvatar] = useState(false)
  const [upcomingEvents, setUpcomingEvents] = useState<LanEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState(false)
  const [editingUsername, setEditingUsername] = useState(false)
  const [usernameDraft, setUsernameDraft] = useState('')
  const [usernameError, setUsernameError] = useState('')

  const id = Number(userId)
  const isSelf = currentUser?.id === id

  const load = async () => {
    try {
      const [p, events] = await Promise.all([usersApi.get(id), eventsApi.getAll()])
      setPlayer(p)
      setUpcomingEvents(
        events.filter((e) => isUpcoming(e.end_date) && e.attendees.some((a) => a.user_id === id))
      )
    } catch {
      setPlayer(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [id])

  // Badges load in their OWN effect with their own catch, and never inside the
  // Promise.all above. The endpoint is recap-gated, and require_feature answering
  // 404 to a non-admin is a normal response — folding it into the page's critical
  // path would blank this page for members only, and never for admins (who bypass
  // the gate), making it invisible from an admin account.
  useEffect(() => {
    if (!recapEnabled) {
      setBadges([])
      return
    }
    usersApi.badges(id).then(setBadges).catch(() => setBadges([]))
  }, [id, recapEnabled])

  // Trophy showcase — feature-gated, so same own-effect pattern as badges.
  useEffect(() => {
    if (!trophiesEnabled) { setTrophies([]); return }
    trophiesApi.forUser(id).then(setTrophies).catch(() => setTrophies([]))
  }, [id, trophiesEnabled])

  // Per-game tournament record — its own effect so a failure never blanks the page.
  useEffect(() => {
    usersApi.gameStats(id).then(setGameStats).catch(() => setGameStats([]))
  }, [id])

  // Same shape, same reason: setup is feature-gated, so its 404 is a normal
  // response and must not reach the page's critical path.
  useEffect(() => {
    if (!setupEnabled) {
      setSetup(null)
      return
    }
    setupApi.get(id).then(setSetup).catch(() => setSetup(null))
  }, [id, setupEnabled])

  if (isSelf) return <Navigate to="/profile" replace />

  const startEditUsername = () => {
    if (!player) return
    setUsernameDraft(player.username)
    setUsernameError('')
    setEditingUsername(true)
  }

  const saveUsername = async () => {
    if (!player) return
    const next = usernameDraft.trim()
    if (next === player.username) {
      setEditingUsername(false)
      return
    }
    if (next.length < 3) {
      setUsernameError(t('profile.usernameTooShort'))
      return
    }
    setUpdating(true)
    setUsernameError('')
    try {
      await usersApi.update(id, { username: next })
      await load()
      setEditingUsername(false)
    } catch (e: any) {
      setUsernameError(
        e.response?.status === 400 ? t('profile.usernameTaken') : t('profile.usernameChangeFailed')
      )
    } finally {
      setUpdating(false)
    }
  }

  const handleRoleChange = async (role: string) => {
    setUpdating(true)
    try {
      await usersApi.updateRole(id, role)
      await load()
    } finally {
      setUpdating(false)
    }
  }

  const handleOrganizerToggle = async () => {
    if (!player) return
    setUpdating(true)
    try {
      await usersApi.update(id, { is_tournament_organizer: !player.is_tournament_organizer })
      await load()
    } finally {
      setUpdating(false)
    }
  }

  const handleActiveToggle = async () => {
    if (!player) return
    if (player.is_active && !confirm(t('players.deactivateConfirm', { username: player.username }))) return
    setUpdating(true)
    try {
      if (player.is_active) {
        await usersApi.deactivate(id)
      } else {
        await usersApi.reactivate(id)
      }
      await load()
    } finally {
      setUpdating(false)
    }
  }

  const handleResetPassword = async () => {
    if (!player) return
    if (!confirm(t('players.resetPasswordConfirm', { username: player.username }))) return
    setUpdating(true)
    try {
      const { temp_password } = await usersApi.resetPassword(id)
      window.prompt(t('players.tempPasswordShown'), temp_password)
    } finally {
      setUpdating(false)
    }
  }

  const handleDeleteAccount = async () => {
    if (!player) return
    if (!confirm(t('players.deleteAccountWarning', { username: player.username }))) return
    const typed = window.prompt(t('players.deleteAccountPrompt', { username: player.username }))
    if (typed !== player.username) {
      if (typed !== null) alert(t('players.deleteAccountMismatch'))
      return
    }
    setUpdating(true)
    try {
      await usersApi.deleteAccount(id)
      navigate('/')
    } finally {
      setUpdating(false)
    }
  }

  if (loading) {
    return (
      <main className="max-w-3xl mx-auto px-6 py-12">
        <div className="h-64 bg-muted animate-pulse" />
      </main>
    )
  }

  if (!player) {
    return (
      <main className="max-w-3xl mx-auto px-6 py-12 text-center">
        <p className="font-mono-label text-muted-foreground">{t('players.notFound')}</p>
      </main>
    )
  }

  return (
    <main className="max-w-3xl mx-auto px-6 py-12">
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-2 font-mono-label text-muted-foreground hover:text-foreground transition-colors mb-8"
      >
        <ArrowLeft size={12} /> {t('common.back')}
      </button>

      <div className="flex items-center gap-6 mb-8">
        <div className="w-20 h-20 bg-muted border border-border overflow-hidden flex-shrink-0">
          {player.avatar_url ? (
            <button
              type="button"
              title={t('profile.viewAvatar')}
              aria-label={t('profile.viewAvatar')}
              onClick={() => setShowAvatar(true)}
              className="w-full h-full cursor-zoom-in"
            >
              <img src={player.avatar_url} alt={player.username} className="w-full h-full object-cover" />
            </button>
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <span className="text-3xl font-black text-muted-foreground">
                {player.username[0].toUpperCase()}
              </span>
            </div>
          )}
        </div>
        <div>
          {editingUsername ? (
            <div className="mb-2">
              <div className="flex items-center gap-1.5">
                <Input
                  value={usernameDraft}
                  onChange={(e) => setUsernameDraft(e.target.value)}
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') { e.preventDefault(); saveUsername() }
                    if (e.key === 'Escape') setEditingUsername(false)
                  }}
                  className="h-10 text-lg font-bold"
                />
                <button
                  type="button"
                  onClick={saveUsername}
                  disabled={updating}
                  className="p-2 text-accent hover:text-foreground transition-colors disabled:opacity-50"
                  title={t('common.save')}
                >
                  <Check size={16} strokeWidth={2} />
                </button>
                <button
                  type="button"
                  onClick={() => setEditingUsername(false)}
                  disabled={updating}
                  className="p-2 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
                  title={t('common.cancel')}
                >
                  <X size={16} strokeWidth={2} />
                </button>
              </div>
              {usernameError && (
                <p className="font-mono-label text-red-500 text-[10px] mt-1">{usernameError}</p>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2 mb-2">
              <h1 className="text-3xl font-black tracking-tight text-foreground">{player.username}</h1>
              {isAdmin && (
                <button
                  type="button"
                  onClick={startEditUsername}
                  className="text-muted-foreground hover:text-accent transition-colors"
                  title={t('players.editUsername')}
                >
                  <Pencil size={14} strokeWidth={1.5} />
                </button>
              )}
            </div>
          )}
          <div className="flex items-center gap-2 flex-wrap">
            {player.role === 'admin' && <Shield size={14} className="text-accent" strokeWidth={1.5} />}
            <Badge variant={player.role === 'admin' ? 'accent' : player.role === 'treasurer' ? 'warning' : 'default'}>
              {t(`nav.role.${player.role}`)}
            </Badge>
            {player.is_meal_prep_volunteer && <Badge variant="muted">🍕 {t('dashboard.chef')}</Badge>}
            {player.is_tournament_organizer && <Badge variant="muted">🏆 {t('dashboard.organizer')}</Badge>}
            {player.clothing_size && <Badge variant="muted">{player.clothing_size}</Badge>}
            {!player.is_active && <Badge variant="danger">{t('dashboard.inactiveBadge')}</Badge>}
          </div>
        </div>
      </div>

      {trophies.length > 0 && (
        <div className="mb-6">
          <p className="font-mono-label text-accent mb-4">{t('trophies.showcaseTitle')}</p>
          <TrophyCase trophies={trophies} />
        </div>
      )}

      {badges.length > 0 && (
        <div className="mb-6">
          <p className="font-mono-label text-accent mb-4">{t('recap.badgesTitle')}</p>
          <BadgeList badges={badges} />
        </div>
      )}

      {gameStats.length > 0 && (
        <div className="mb-6">
          <p className="font-mono-label text-accent mb-4">{t('players.gameStatsTitle')}</p>
          <div className="border border-border bg-card">
            {gameStats.map((g) => (
              <div key={g.game_id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 py-3 border-b border-border last:border-0">
                <span className="font-bold text-sm text-foreground">{g.name}</span>
                <span className="font-mono-label text-muted-foreground text-xs tabular-nums">
                  {t('players.gameStatsLine', { played: g.played, wins: g.wins, losses: g.losses })}
                  {g.draws > 0 && ` ${t('players.gameStatsDraws', { draws: g.draws })}`}
                  {g.win_rate != null && ` · ${formatWinRate(g.win_rate)}`}
                  {g.titles > 0 && <span className="text-accent"> · 🏆×{g.titles}</span>}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {setup?.has_content && (
        <div className="mb-6">
          <p className="font-mono-label text-accent mb-4">
            {t('setup.playerTitle', { username: player.username })}
          </p>
          <SetupView
            components={setup.components}
            customFields={setup.custom_fields}
            photos={setup.photos}
          />
          <div className="mt-3">
            <ReactionBar
              reactions={setup.reactions}
              busy={reacting}
              onToggle={async (emoji) => {
                setReacting(true)
                try {
                  setSetup(await setupApi.react(id, emoji))
                } catch {
                  // A failed toggle just leaves the row as it was.
                } finally {
                  setReacting(false)
                }
              }}
            />
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        <div className="border border-border bg-card p-6 space-y-3">
          <p className="font-mono-label text-muted-foreground">{t('profile.account')}</p>
          {player.email && (
            <div>
              <p className="font-mono-label text-muted-foreground text-[10px]">{t('profile.email')}</p>
              <p className="font-semibold text-foreground text-sm">{player.email}</p>
            </div>
          )}
          <div>
            <p className="font-mono-label text-muted-foreground text-[10px]">{t('profile.role')}</p>
            <p className="font-semibold text-foreground text-sm">{t(`nav.role.${player.role}`)}</p>
          </div>
        </div>

        {upcomingEvents.length > 0 && (
          <div className="border border-border bg-card p-6 space-y-3">
            <p className="font-mono-label text-muted-foreground flex items-center gap-1.5">
              <CalendarDays size={12} strokeWidth={1.5} /> {t('profile.upcomingEvents')}
            </p>
            <div className="space-y-2">
              {upcomingEvents.map((e) => {
                const attendee = e.attendees.find((a) => a.user_id === id)
                return (
                  <div key={e.id} className="border-t border-border pt-2 first:border-t-0 first:pt-0">
                    <p className="text-sm font-semibold text-foreground truncate">{e.title}</p>
                    {attendee?.arrival_date && attendee.departure_date && (
                      <p className="font-mono-label text-accent text-[10px] mt-0.5">
                        {formatDate(attendee.arrival_date)} → {formatDate(attendee.departure_date)}
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {isAdmin && (
        <div className="border border-border bg-card p-6 mt-6">
          <p className="font-mono-label text-accent mb-4">{t('players.adminControls')}</p>
          <div className="flex flex-wrap items-center gap-6">
            <div>
              <label className="font-mono-label text-muted-foreground block mb-1.5">{t('players.changeRole')}</label>
              <select
                value={player.role}
                onChange={(e) => handleRoleChange(e.target.value)}
                disabled={updating}
                className="h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none disabled:opacity-50"
              >
                <option value="user">{t('nav.role.user')}</option>
                <option value="treasurer">{t('nav.role.treasurer')}</option>
                <option value="admin">{t('nav.role.admin')}</option>
              </select>
            </div>
            <div>
              <label className="font-mono-label text-muted-foreground block mb-1.5">{t('players.organizerLabel')}</label>
              <button
                onClick={handleOrganizerToggle}
                disabled={updating}
                className={`h-10 px-4 font-mono-label text-xs border transition-colors disabled:opacity-50 ${
                  player.is_tournament_organizer
                    ? 'border-accent text-accent bg-accent/10'
                    : 'border-border text-muted-foreground hover:border-foreground hover:text-foreground'
                }`}
              >
                {player.is_tournament_organizer ? t('players.revokeOrganizer') : t('players.grantOrganizer')}
              </button>
            </div>
            <div>
              <label className="font-mono-label text-muted-foreground block mb-1.5">{t('players.accountStatus')}</label>
              {player.deleted_at ? (
                <p className="h-10 px-4 flex items-center font-mono-label text-xs text-red-400 border border-red-900/50 bg-red-950/20">
                  {t('players.accountDeleted')}
                </p>
              ) : (
                <button
                  onClick={handleActiveToggle}
                  disabled={updating}
                  className={`h-10 px-4 font-mono-label text-xs border transition-colors disabled:opacity-50 ${
                    !player.is_active
                      ? 'border-accent text-accent bg-accent/10'
                      : 'border-border text-muted-foreground hover:border-red-700 hover:text-red-400'
                  }`}
                >
                  {player.is_active ? t('players.deactivateAccount') : t('players.reactivateAccount')}
                </button>
              )}
            </div>
            <div>
              <label className="font-mono-label text-muted-foreground block mb-1.5">{t('players.resetPassword')}</label>
              <button
                onClick={handleResetPassword}
                disabled={updating}
                className="h-10 px-4 font-mono-label text-xs border border-border text-muted-foreground hover:border-foreground hover:text-foreground transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                <KeyRound size={12} strokeWidth={1.5} /> {t('players.resetPassword')}
              </button>
            </div>
            {!player.deleted_at && (
              <div>
                <label className="font-mono-label text-muted-foreground block mb-1.5">{t('players.deleteAccount')}</label>
                <button
                  onClick={handleDeleteAccount}
                  disabled={updating}
                  className="h-10 px-4 font-mono-label text-xs border border-red-900/50 text-red-400 hover:border-red-700 hover:bg-red-950/30 transition-colors disabled:opacity-50 flex items-center gap-1.5"
                >
                  <Trash2 size={12} strokeWidth={1.5} /> {t('players.deleteAccount')}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="mt-8">
        <SponsorStrip />
      </div>

      {showAvatar && player.avatar_url && (
        <PhotoLightbox
          photos={[{ id: player.id, url: player.avatar_url, caption: player.username }]}
          index={0}
          onClose={() => setShowAvatar(false)}
        />
      )}
    </main>
  )
}
