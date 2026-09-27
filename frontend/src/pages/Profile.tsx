import { useState, useRef, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { useAppConfig } from '../contexts/AppConfigContext'
import { usersApi, eventsApi, discordApi, steamApi } from '../lib/api'
import { isEmbeddedInDesktop, requestDiscordAuth, requestSteamAuth } from '../lib/desktopBridge'
import { formatDate } from '../lib/formatDate'
import Button from '../components/ui/Button'
import Badge from '../components/ui/Badge'
import Input from '../components/ui/Input'
import BadgeList from '../components/BadgeList'
import MySetupCard from '../components/MySetupCard'
import GamesLibraryCard from '../components/GamesLibraryCard'
import RiotIdCard from '../components/RiotIdCard'
import { CLOTHING_SIZES, LanEvent, BadgeAward } from '../types'
import { Camera, Check, Shield, CalendarDays, RotateCw, KeyRound, Phone, Pencil, X, Link2, Unlink } from 'lucide-react'

interface ProfileForm {
  clothing_size: string
  phone: string
  is_meal_prep_volunteer: boolean
  is_tournament_organizer: boolean
}

interface PasswordChangeForm {
  current_password: string
  new_password: string
  confirm_new_password: string
}

export default function Profile() {
  const { user, refreshUser, isAdmin } = useAuth()
  const { recapEnabled, setupEnabled, merchSizeEnabled, gamesEnabled, lolStatsEnabled } = useAppConfig()
  const { t } = useTranslation()
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [avatarLoading, setAvatarLoading] = useState(false)
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null)
  const [avatarError, setAvatarError] = useState('')
  const [upcomingEvents, setUpcomingEvents] = useState<LanEvent[]>([])
  const [badges, setBadges] = useState<BadgeAward[]>([])
  const fileRef = useRef<HTMLInputElement>(null)

  const [editingUsername, setEditingUsername] = useState(false)
  const [usernameDraft, setUsernameDraft] = useState('')
  const [usernameSaving, setUsernameSaving] = useState(false)
  const [usernameError, setUsernameError] = useState('')

  const startEditUsername = () => {
    setUsernameDraft(user?.username ?? '')
    setUsernameError('')
    setEditingUsername(true)
  }

  const saveUsername = async () => {
    if (!user) return
    const next = usernameDraft.trim()
    if (next === user.username) {
      setEditingUsername(false)
      return
    }
    if (next.length < 3) {
      setUsernameError(t('profile.usernameTooShort'))
      return
    }
    setUsernameSaving(true)
    setUsernameError('')
    try {
      await usersApi.update(user.id, { username: next })
      await refreshUser()
      setEditingUsername(false)
    } catch (e: any) {
      setUsernameError(
        e.response?.status === 400 ? t('profile.usernameTaken') : t('profile.usernameChangeFailed')
      )
    } finally {
      setUsernameSaving(false)
    }
  }

  useEffect(() => {
    eventsApi.getAll().then((events) => {
      setUpcomingEvents(events.filter((e) => e.my_rsvp === 'in'))
    })
  }, [])

  // Own effect, own catch — the badges endpoint is recap-gated, and a 404 while
  // the feature is off is a normal response, not a page failure.
  useEffect(() => {
    if (!user || !recapEnabled) {
      setBadges([])
      return
    }
    usersApi.badges(user.id).then(setBadges).catch(() => setBadges([]))
  }, [user, recapEnabled])

  // ── Discord linking ──
  const [searchParams, setSearchParams] = useSearchParams()
  const [discordEnabled, setDiscordEnabled] = useState(false)
  const [discordBusy, setDiscordBusy] = useState(false)
  const [discordNotice, setDiscordNotice] = useState('')
  // See DiscordButton.tsx's `busyRef` — React state alone can't stop a
  // second invocation from a duplicate WebView2 click event landing in the
  // same tick, since `disabled` only takes effect on the next render.
  const discordBusyRef = useRef(false)

  useEffect(() => {
    discordApi.config().then((c) => setDiscordEnabled(c.enabled)).catch(() => {})
  }, [])

  useEffect(() => {
    const d = searchParams.get('discord')
    if (!d) return
    if (d === 'linked') refreshUser()
    setDiscordNotice(d)
    searchParams.delete('discord')
    setSearchParams(searchParams, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const linkDiscord = async () => {
    if (discordBusyRef.current) return
    discordBusyRef.current = true
    setDiscordBusy(true)
    try {
      if (isEmbeddedInDesktop()) {
        requestDiscordAuth('link')
      } else {
        window.location.href = await discordApi.link()
      }
    } finally {
      // See DiscordButton.tsx's `go()` — the desktop app's case keeps this
      // component mounted (it hands off to the system browser), unlike a
      // plain top-level redirect.
      discordBusyRef.current = false
      setDiscordBusy(false)
    }
  }

  const unlinkDiscord = async () => {
    setDiscordBusy(true)
    setDiscordNotice('')
    try {
      await discordApi.unlink()
      await refreshUser()
    } catch {
      setDiscordNotice('unlink_failed')
    } finally {
      setDiscordBusy(false)
    }
  }

  // ── Steam linking (link-only — no login/registration via Steam, see md/Steam_Link.md) ──
  const [steamEnabled, setSteamEnabled] = useState(false)
  const [steamBusy, setSteamBusy] = useState(false)
  const [steamNotice, setSteamNotice] = useState('')
  const steamBusyRef = useRef(false)

  useEffect(() => {
    steamApi.config().then((c) => setSteamEnabled(c.enabled)).catch(() => {})
  }, [])

  useEffect(() => {
    const s = searchParams.get('steam')
    if (!s) return
    if (s === 'linked') refreshUser()
    setSteamNotice(s)
    searchParams.delete('steam')
    setSearchParams(searchParams, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const linkSteam = async () => {
    if (steamBusyRef.current) return
    steamBusyRef.current = true
    setSteamBusy(true)
    try {
      if (isEmbeddedInDesktop()) {
        requestSteamAuth()
      } else {
        window.location.href = await steamApi.link()
      }
    } finally {
      steamBusyRef.current = false
      setSteamBusy(false)
    }
  }

  const unlinkSteam = async () => {
    setSteamBusy(true)
    setSteamNotice('')
    try {
      await steamApi.unlink()
      await refreshUser()
    } catch {
      setSteamNotice('unlink_failed')
    } finally {
      setSteamBusy(false)
    }
  }

  const { register, handleSubmit, watch, setValue } = useForm<ProfileForm>({
    defaultValues: {
      clothing_size: user?.clothing_size ?? '',
      phone: user?.phone ?? '',
      is_meal_prep_volunteer: user?.is_meal_prep_volunteer ?? false,
      is_tournament_organizer: user?.is_tournament_organizer ?? false,
    },
  })

  const clothingSize = watch('clothing_size')
  const isMealPrep = watch('is_meal_prep_volunteer')
  const isTournOrg = watch('is_tournament_organizer')

  const onSubmit = async (data: ProfileForm) => {
    if (!user) return
    setSaving(true)
    try {
      await usersApi.update(user.id, data)
      await refreshUser()
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } finally {
      setSaving(false)
    }
  }

  const handleAvatarChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !user) return

    setAvatarPreview(URL.createObjectURL(file))
    setAvatarLoading(true)
    setAvatarError('')
    try {
      await usersApi.uploadAvatar(user.id, file)
      await refreshUser()
    } catch {
      // Without this the optimistic preview stays on screen for an image that
      // was never saved, and you'd find the old avatar back days later. Upload
      // used to be effectively unfailable; the 12 MB cap and the narrowed format
      // list are what make this reachable.
      setAvatarPreview(null)
      setAvatarError(t('profile.avatarRejected'))
    } finally {
      setAvatarLoading(false)
    }
  }

  const handleAvatarRotate = async () => {
    if (!user) return
    setAvatarPreview(null)
    setAvatarLoading(true)
    try {
      await usersApi.rotateAvatar(user.id)
      await refreshUser()
    } finally {
      setAvatarLoading(false)
    }
  }

  const [pwSaved, setPwSaved] = useState(false)
  const [pwError, setPwError] = useState('')
  const {
    register: registerPw,
    handleSubmit: handleSubmitPw,
    watch: watchPw,
    reset: resetPw,
    formState: { errors: pwErrors, isSubmitting: pwSubmitting },
  } = useForm<PasswordChangeForm>()

  const onSubmitPasswordChange = async (data: PasswordChangeForm) => {
    if (!user) return
    setPwError('')
    try {
      await usersApi.changePassword(user.id, {
        current_password: data.current_password,
        new_password: data.new_password,
      })
      resetPw()
      setPwSaved(true)
      setTimeout(() => setPwSaved(false), 3000)
    } catch (e: any) {
      if (e.response?.status === 400) {
        setPwError(t('profile.currentPasswordIncorrect'))
      } else {
        setPwError(t('profile.passwordChangeFailed'))
      }
    }
  }

  return (
    <main className="max-w-4xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="mb-12">
        <div className="font-mono-label text-accent mb-3">{t('profile.tagline')}</div>
        <h1 className="text-5xl lg:text-6xl font-black tracking-tighter text-foreground leading-none mb-2">
          {t('profile.heroLine1')}
          <br />
          <span className="text-accent">{t('profile.heroLine2')}</span>
        </h1>
        {user?.profile_complete ? (
          <Badge variant="success">{t('profile.profileComplete')}</Badge>
        ) : (
          <Badge variant="warning">{t('profile.profileIncomplete')}</Badge>
        )}
      </div>

      {/* Single-column, in the order the crew asked for: upcoming events and
          avatar first (identity), then contact/account/social, then the
          heavier My Setup block, then the rest. Phone/clothing size/roles
          are all on the same ProfileForm (react-hook-form tracks values via
          `register`, not by which DOM element wraps the input) but there's
          no single <form> tag around them any more — Change Password sits
          between them in this order with its own <form>, and forms can't
          nest, so Save Profile below triggers handleSubmit(onSubmit)
          directly on click instead. */}
      <div className="space-y-6">
        {/* 01 — Upcoming events */}
        {upcomingEvents.length > 0 && (
          <div className="border border-border bg-card p-6 space-y-3">
            <p className="font-mono-label text-muted-foreground flex items-center gap-1.5">
              <CalendarDays size={12} strokeWidth={1.5} /> {t('profile.upcomingEvents')}
            </p>
            <div className="space-y-2">
              {upcomingEvents.map((e) => (
                <div key={e.id} className="border-t border-border pt-2 first:border-t-0 first:pt-0">
                  <p className="text-sm font-semibold text-foreground truncate">{e.title}</p>
                  {e.my_arrival_date && e.my_departure_date && (
                    <p className="font-mono-label text-accent text-[10px] mt-0.5">
                      {formatDate(e.my_arrival_date)} → {formatDate(e.my_departure_date)}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 02 — Avatar */}
        <div className="border border-border bg-card p-6">
          <p className="font-mono-label text-muted-foreground mb-4">{t('profile.avatar')}</p>

          {/* Avatar preview */}
          <div className="w-full max-w-xs aspect-square bg-muted border border-border mb-4 overflow-hidden relative">
            {(avatarPreview ?? user?.avatar_url) ? (
              <img
                src={avatarPreview ?? user?.avatar_url ?? ''}
                alt={user?.username}
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center">
                <span className="text-6xl font-black text-muted-foreground">
                  {user?.username?.[0]?.toUpperCase()}
                </span>
              </div>
            )}
            {avatarLoading && (
              <div className="absolute inset-0 bg-background/80 flex items-center justify-center">
                <span className="font-mono-label text-muted-foreground animate-pulse">
                  {t('profile.uploading')}
                </span>
              </div>
            )}
          </div>

          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            className="hidden"
            onChange={handleAvatarChange}
          />
          <div className="flex gap-2 max-w-xs">
            <Button
              variant="outline"
              size="sm"
              className="flex-1 min-w-0"
              onClick={() => fileRef.current?.click()}
              disabled={avatarLoading}
            >
              <Camera size={14} strokeWidth={1.5} className="flex-shrink-0" />
              <span className="truncate">
                {avatarLoading ? t('profile.uploading') : t('profile.changePhoto')}
              </span>
            </Button>
            {user?.avatar_url && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleAvatarRotate}
                disabled={avatarLoading}
                title={t('profile.rotatePhoto')}
              >
                <RotateCw size={14} strokeWidth={1.5} />
              </Button>
            )}
          </div>
          {avatarError && (
            <p className="font-mono-label text-red-400 text-[10px] mt-2">{avatarError}</p>
          )}
        </div>

        {/* 03 — T-Shirt size (opt-out feature — merch_size_enabled) */}
        {merchSizeEnabled && (
          <div className="border border-border bg-card p-6">
            <div className="border-b border-border pb-3 mb-4">
              <p className="font-mono-label text-accent">{t('profile.merchSizeStep')}</p>
              <p className="text-xs text-muted-foreground mt-1">{t('profile.merchSizeDesc')}</p>
            </div>
            <div className="grid grid-cols-7 gap-1 max-w-xl">
              {CLOTHING_SIZES.map((size) => (
                <button
                  key={size}
                  type="button"
                  onClick={() => setValue('clothing_size', size)}
                  className={`py-3 text-sm font-bold font-mono transition-all duration-150 border ${
                    clothingSize === size
                      ? 'bg-accent text-accent-foreground border-accent'
                      : 'bg-transparent text-muted-foreground border-border hover:border-foreground hover:text-foreground'
                  }`}
                >
                  {size}
                </button>
              ))}
            </div>
            <input type="hidden" {...register('clothing_size', { required: true })} />
            {!clothingSize && (
              <p className="font-mono-label text-accent/70 mt-2 text-[10px]">{t('profile.selectASize')}</p>
            )}
          </div>
        )}

        {/* 04 — Contributions / roles */}
        <div className="border border-border bg-card p-6">
          <div className="border-b border-border pb-3 mb-4">
            <p className="font-mono-label text-accent">{t('profile.contributionsStep')}</p>
            <p className="text-xs text-muted-foreground mt-1">{t('profile.contributionsDesc')}</p>
          </div>
          <div className="space-y-3">
            {[
              {
                key: 'is_meal_prep_volunteer' as const,
                active: isMealPrep,
                label: t('profile.mealPrepLabel'),
                desc: t('profile.mealPrepDesc'),
              },
              {
                key: 'is_tournament_organizer' as const,
                active: isTournOrg,
                label: t('profile.organizerLabel'),
                desc: t('profile.organizerDesc'),
              },
            ].map(({ key, active, label, desc }) => (
              <button
                key={key}
                type="button"
                onClick={() => setValue(key, !active)}
                className={`w-full flex items-center justify-between p-4 border text-left transition-all duration-150 ${
                  active
                    ? 'border-accent bg-accent/5'
                    : 'border-border hover:border-border-hover'
                }`}
              >
                <div>
                  <p className={`font-mono-label ${active ? 'text-accent' : 'text-foreground'}`}>
                    {label}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">{desc}</p>
                </div>
                <div
                  className={`w-5 h-5 border flex items-center justify-center flex-shrink-0 transition-colors ${
                    active ? 'border-accent bg-accent' : 'border-border'
                  }`}
                >
                  {active && <Check size={12} strokeWidth={3} className="text-accent-foreground" />}
                </div>
                <input type="hidden" {...register(key)} />
              </button>
            ))}
          </div>
        </div>

        {/* 05 — Phone */}
        <div className="border border-border bg-card p-6">
          <div className="border-b border-border pb-3 mb-4">
            <p className="font-mono-label text-accent flex items-center gap-1.5">
              <Phone size={12} strokeWidth={1.5} /> {t('profile.phoneLabel')}
            </p>
            <p className="text-xs text-muted-foreground mt-1">{t('profile.phoneHint')}</p>
          </div>
          <Input
            type="tel"
            autoComplete="tel"
            placeholder="+33 6 12 34 56 78"
            className="max-w-sm"
            {...register('phone')}
          />
        </div>

        {/* 06 — Account info */}
        <div className="border border-border bg-card p-6 space-y-3">
          <p className="font-mono-label text-muted-foreground">{t('profile.account')}</p>
          <div>
            <p className="font-mono-label text-muted-foreground text-[10px]">{t('profile.username')}</p>
            {editingUsername ? (
              <div className="mt-1">
                <div className="flex items-center gap-1.5">
                  <Input
                    value={usernameDraft}
                    onChange={(e) => setUsernameDraft(e.target.value)}
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') { e.preventDefault(); saveUsername() }
                      if (e.key === 'Escape') setEditingUsername(false)
                    }}
                    className="h-9 max-w-xs"
                  />
                  <button
                    type="button"
                    onClick={saveUsername}
                    disabled={usernameSaving}
                    className="p-2 text-accent hover:text-foreground transition-colors disabled:opacity-50"
                    title={t('common.save')}
                  >
                    <Check size={14} strokeWidth={2} />
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditingUsername(false)}
                    disabled={usernameSaving}
                    className="p-2 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
                    title={t('common.cancel')}
                  >
                    <X size={14} strokeWidth={2} />
                  </button>
                </div>
                {usernameError && (
                  <p className="font-mono-label text-red-500 text-[10px] mt-1">{usernameError}</p>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <p className="font-semibold text-foreground">{user?.username}</p>
                <button
                  type="button"
                  onClick={startEditUsername}
                  className="text-muted-foreground hover:text-accent transition-colors"
                  title={t('profile.editUsername')}
                >
                  <Pencil size={12} strokeWidth={1.5} />
                </button>
              </div>
            )}
          </div>
          <div>
            <p className="font-mono-label text-muted-foreground text-[10px]">{t('profile.email')}</p>
            <p className="font-semibold text-foreground text-sm">{user?.email}</p>
          </div>
          <div>
            <p className="font-mono-label text-muted-foreground text-[10px]">{t('profile.role')}</p>
            <div className="flex items-center gap-2 mt-1">
              {user?.role === 'admin' && <Shield size={14} className="text-accent" strokeWidth={1.5} />}
              <Badge variant={user?.role === 'admin' ? 'accent' : user?.role === 'treasurer' ? 'warning' : 'default'}>
                {t(`nav.role.${user?.role}`)}
              </Badge>
            </div>
          </div>
        </div>

        {/* 07 — Discord link */}
        {discordEnabled && (
          <div className="border border-border bg-card p-6 space-y-3">
            <p className="font-mono-label text-muted-foreground flex items-center gap-1.5">
              <Link2 size={12} strokeWidth={1.5} /> {t('profile.discordTitle')}
            </p>

            {discordNotice === 'linked' && (
              <p className="font-mono-label text-green-400 text-[10px]">{t('profile.discordLinked')}</p>
            )}
            {discordNotice === 'already_linked' && (
              <p className="font-mono-label text-red-400 text-[10px]">{t('profile.discordAlreadyLinked')}</p>
            )}
            {(discordNotice === 'error' || discordNotice === 'unlink_failed') && (
              <p className="font-mono-label text-red-400 text-[10px]">{t('discord.signInFailed')}</p>
            )}

            {user?.discord_username ? (
              <>
                <p className="text-sm text-foreground">
                  {t('profile.discordLinkedAs')}{' '}
                  <span className="font-semibold">{user.discord_username}</span>
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="max-w-xs"
                  onClick={unlinkDiscord}
                  disabled={discordBusy || user.has_password === false}
                >
                  <Unlink size={14} strokeWidth={1.5} /> {t('profile.discordUnlink')}
                </Button>
                {user.has_password === false && (
                  <p className="text-[10px] text-muted-foreground leading-relaxed">
                    {t('profile.discordUnlinkBlocked')}
                  </p>
                )}
              </>
            ) : (
              <>
                <p className="text-xs text-muted-foreground">{t('profile.discordLinkHint')}</p>
                <button
                  type="button"
                  onClick={linkDiscord}
                  disabled={discordBusy}
                  className="w-full max-w-xs h-10 flex items-center justify-center gap-2 bg-[#5865F2] text-white font-mono-label hover:bg-[#4752c4] transition-colors disabled:opacity-50"
                >
                  {discordBusy ? t('discord.redirecting') : t('profile.discordLink')}
                </button>
              </>
            )}
          </div>
        )}

        {/* 07b — Steam link */}
        {steamEnabled && (
          <div className="border border-border bg-card p-6 space-y-3">
            <p className="font-mono-label text-muted-foreground flex items-center gap-1.5">
              <Link2 size={12} strokeWidth={1.5} /> {t('profile.steamTitle')}
            </p>

            {steamNotice === 'linked' && (
              <p className="font-mono-label text-green-400 text-[10px]">{t('profile.steamLinked')}</p>
            )}
            {steamNotice === 'already_linked' && (
              <p className="font-mono-label text-red-400 text-[10px]">{t('profile.steamAlreadyLinked')}</p>
            )}
            {(steamNotice === 'error' || steamNotice === 'unlink_failed') && (
              <p className="font-mono-label text-red-400 text-[10px]">{t('profile.steamSignInFailed')}</p>
            )}

            {user?.steam_username ? (
              <>
                <p className="text-sm text-foreground">
                  {t('profile.steamLinkedAs')}{' '}
                  <span className="font-semibold">{user.steam_username}</span>
                </p>
                <Button variant="outline" size="sm" className="max-w-xs" onClick={unlinkSteam} disabled={steamBusy}>
                  <Unlink size={14} strokeWidth={1.5} /> {t('profile.steamUnlink')}
                </Button>
              </>
            ) : (
              <>
                <p className="text-xs text-muted-foreground">{t('profile.steamLinkHint')}</p>
                <button
                  type="button"
                  onClick={linkSteam}
                  disabled={steamBusy}
                  className="w-full max-w-xs h-10 flex items-center justify-center gap-2 bg-[#171a21] text-white font-mono-label hover:bg-[#2a3f5a] transition-colors disabled:opacity-50"
                >
                  {steamBusy ? t('discord.redirecting') : t('profile.steamLink')}
                </button>
              </>
            )}
          </div>
        )}

        {/* 07c — Riot ID (typed, not OAuth) — what LoL LAN stats match players by */}
        {(gamesEnabled || lolStatsEnabled) && <RiotIdCard />}

        {/* 08 — My Setup */}
        {setupEnabled && <MySetupCard />}

        {/* 09 — Games (library / wishlist) */}
        {gamesEnabled && <GamesLibraryCard />}

        {/* 10 — Change password */}
        <div className="border border-border bg-card p-6">
          <p className="font-mono-label text-muted-foreground mb-4 flex items-center gap-1.5">
            <KeyRound size={12} strokeWidth={1.5} /> {t('profile.changePasswordTitle')}
          </p>
          <form onSubmit={handleSubmitPw(onSubmitPasswordChange)} className="space-y-3 max-w-sm">
            <Input
              label={t('profile.currentPasswordLabel')}
              type="password"
              autoComplete="current-password"
              {...registerPw('current_password', { required: t('profile.currentPasswordRequired') })}
              error={pwErrors.current_password?.message}
            />
            <Input
              label={t('profile.newPasswordLabel')}
              type="password"
              autoComplete="new-password"
              {...registerPw('new_password', {
                required: t('profile.newPasswordRequired'),
                minLength: { value: 6, message: t('register.passwordMinLength') },
                validate: (v) =>
                  new TextEncoder().encode(v).length <= 72 || t('register.passwordMaxLength'),
              })}
              error={pwErrors.new_password?.message}
            />
            <Input
              label={t('profile.confirmNewPasswordLabel')}
              type="password"
              autoComplete="new-password"
              {...registerPw('confirm_new_password', {
                required: t('profile.confirmNewPasswordRequired'),
                validate: (v) => v === watchPw('new_password') || t('register.passwordsNoMatch'),
              })}
              error={pwErrors.confirm_new_password?.message}
            />
            {pwError && (
              <p className="font-mono-label text-red-500">{pwError}</p>
            )}
            <Button type="submit" variant="outline" size="sm" className="w-full" disabled={pwSubmitting}>
              {pwSubmitting ? t('profile.saving') : pwSaved ? (
                <><Check size={14} /> {t('profile.passwordChanged')}</>
              ) : (
                t('profile.changePasswordButton')
              )}
            </Button>
          </form>
        </div>

        {/* 11 — Badges */}
        {badges.length > 0 && (
          <div className="space-y-3">
            <p className="font-mono-label text-accent">{t('recap.badgesTitle')}</p>
            <BadgeList badges={badges} />
          </div>
        )}

        {/* 12 — Save */}
        <div className="flex items-center gap-4">
          <Button type="button" onClick={handleSubmit(onSubmit)} disabled={saving} size="lg">
            {saving ? t('profile.saving') : saved ? (
              <><Check size={14} /> {t('profile.saved')}</>
            ) : (
              t('profile.saveProfile')
            )}
          </Button>
          {saved && (
            <span className="font-mono-label text-green-400">
              {t('profile.profileUpdated')}
            </span>
          )}
        </div>
      </div>
    </main>
  )
}
