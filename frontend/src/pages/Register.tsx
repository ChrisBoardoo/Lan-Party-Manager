import { useState, useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { authApi, eventInvitesApi } from '../lib/api'
import { EventInviteValidation } from '../types'
import { formatDate } from '../lib/formatDate'
import Input from '../components/ui/Input'
import Button from '../components/ui/Button'
import LanguageToggle from '../components/ui/LanguageToggle'
import DiscordButton from '../components/ui/DiscordButton'
import { ArrowRight, Shield, Ticket, AlertCircle, CalendarCheck } from 'lucide-react'

interface FormData {
  username: string
  email: string
  password: string
  confirm: string
  arrival_date: string
  departure_date: string
}

export default function Register() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [error, setError] = useState('')
  const discordError = searchParams.get('discord')
  const [code, setCode] = useState(searchParams.get('code')?.toUpperCase() ?? '')
  const [validation, setValidation] = useState<EventInviteValidation | null>(null)
  const [validating, setValidating] = useState(false)
  const [inviteRequired, setInviteRequired] = useState<boolean | null>(null)

  useEffect(() => {
    fetch('/api/auth/invite-required')
      .then((r) => r.json())
      .then((d) => setInviteRequired(d.required))
      .catch(() => setInviteRequired(false))
  }, [])

  useEffect(() => {
    if (!code) {
      setValidation(null)
      return
    }
    setValidating(true)
    const handle = setTimeout(() => {
      eventInvitesApi
        .validate(code)
        .then(setValidation)
        .finally(() => setValidating(false))
    }, 300)
    return () => clearTimeout(handle)
  }, [code])

  const canRegister = inviteRequired === false || (validation?.valid === true && validation.full === false)

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormData>()

  const onSubmit = async (data: FormData) => {
    setError('')
    try {
      await authApi.register({
        username: data.username,
        email: data.email,
        password: data.password,
        invite_code: code || undefined,
        arrival_date: code ? data.arrival_date : undefined,
        departure_date: code ? data.departure_date : undefined,
      })
      navigate('/login', { state: { registered: true } })
    } catch (e: any) {
      setError(e.response?.data?.detail ?? t('register.registrationFailed'))
    }
  }

  return (
    <div className="min-h-screen bg-background flex flex-col lg:flex-row">
      {/* Left — Branding */}
      <div className="lg:w-2/5 min-w-0 flex flex-col justify-between p-8 lg:p-16 border-b lg:border-b-0 lg:border-r border-border bg-card">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Shield size={18} strokeWidth={1.5} className="text-accent" />
            <span className="font-mono-label text-muted-foreground">{t('register.newPlayer')}</span>
          </div>
          <LanguageToggle />
        </div>

        <div>
          <div className="font-mono-label text-accent mb-4">{t('register.tagline')}</div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-black tracking-tighter text-foreground leading-none mb-6 break-words">
            {t('register.heroLine1')}
            <br />
            <span className="text-accent">{t('register.heroLine2')}</span>
          </h1>
          <p className="text-muted-foreground text-sm leading-relaxed">
            {t('register.adminNoticePrefix')}{' '}
            <span className="text-foreground font-semibold">{t('register.adminNoticeRole')}</span>{' '}
            {t('register.adminNoticeSuffix')}
          </p>
        </div>

        <div className="font-mono-label text-muted-foreground text-[11px] space-y-1">
          <p>✓ {t('register.featureAuth')}</p>
          <p>✓ {t('register.featureRoles')}</p>
          <p>✓ {t('register.featurePasswords')}</p>
        </div>
      </div>

      {/* Right — Form */}
      <div className="lg:w-3/5 flex items-center p-8 lg:p-16">
        <div className="max-w-sm w-full mx-auto lg:mx-0">
          <div className="mb-8">
            <h2 className="text-3xl font-black tracking-tight text-foreground mb-1">
              {t('register.heading')}
            </h2>
            <p className="font-mono-label text-muted-foreground">
              {t('register.subheading')}
            </p>
          </div>

          {inviteRequired && (
            <div className="mb-6">
              <label className="font-mono-label text-muted-foreground block mb-1.5">
                {t('register.inviteCodeLabel')}
              </label>
              <input
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                placeholder="ABC123"
                maxLength={8}
                className="w-full h-12 px-4 bg-input border border-border text-foreground text-base font-mono tracking-widest uppercase placeholder:text-muted-foreground focus:border-accent outline-none transition-colors duration-150"
              />
            </div>
          )}

          {/* Invite status banner */}
          {code && (
            <div
              className={`flex items-start gap-3 px-4 py-3 border mb-6 ${
                validating || validation === null
                  ? 'border-border bg-muted/30'
                  : validation.valid && !validation.full
                  ? 'border-green-700 bg-green-950/20'
                  : 'border-red-700 bg-red-950/20'
              }`}
            >
              {validating || validation === null ? (
                <>
                  <Ticket size={14} className="text-muted-foreground mt-0.5 flex-shrink-0" strokeWidth={1.5} />
                  <span className="font-mono-label text-muted-foreground animate-pulse">
                    {t('register.validatingCode')}
                  </span>
                </>
              ) : validation.valid && !validation.full ? (
                <>
                  <Ticket size={14} className="text-green-400 mt-0.5 flex-shrink-0" strokeWidth={1.5} />
                  <div>
                    <p className="font-mono-label text-green-400">{t('register.validCode')}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {validation.event_title} · {validation.event_start && formatDate(validation.event_start)}
                      {validation.event_end && validation.event_end !== validation.event_start && (
                        <> → {formatDate(validation.event_end)}</>
                      )}
                    </p>
                  </div>
                </>
              ) : validation.valid && validation.full ? (
                <>
                  <AlertCircle size={14} className="text-red-400 mt-0.5 flex-shrink-0" strokeWidth={1.5} />
                  <div>
                    <p className="font-mono-label text-red-400">{t('register.eventFull')}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {t('register.eventFullDetail', { event: validation.event_title })}
                    </p>
                  </div>
                </>
              ) : (
                <>
                  <AlertCircle size={14} className="text-red-400 mt-0.5 flex-shrink-0" strokeWidth={1.5} />
                  <div>
                    <p className="font-mono-label text-red-400">{t('register.invalidCode')}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {t('register.invalidCodeDetail')}
                    </p>
                  </div>
                </>
              )}
            </div>
          )}

          {inviteRequired && !code && (
            <div className="flex items-start gap-3 px-4 py-3 border border-border bg-muted/30 mb-6">
              <Shield size={14} className="text-muted-foreground mt-0.5 flex-shrink-0" strokeWidth={1.5} />
              <p className="font-mono-label text-muted-foreground text-[10px]">
                {t('register.codeRequiredNotice')}
              </p>
            </div>
          )}

          {discordError && (
            <div className="border border-red-800 bg-red-950/20 px-4 py-3 mb-6">
              <p className="font-mono-label text-red-400">
                {discordError === 'invite_required'
                  ? t('register.codeRequiredNotice')
                  : t('discord.signInFailed')}
              </p>
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <Input
              label={t('register.usernameLabel')}
              placeholder={t('register.usernamePlaceholder')}
              autoComplete="username"
              {...register('username', {
                required: t('register.usernameRequired'),
                minLength: { value: 3, message: t('register.usernameMinLength') },
                maxLength: { value: 50, message: t('register.usernameMaxLength') },
                pattern: { value: /^[a-zA-Z0-9_-]+$/, message: t('register.usernamePattern') },
              })}
              error={errors.username?.message}
            />
            <Input
              label={t('register.emailLabel')}
              type="email"
              placeholder={t('register.emailPlaceholder')}
              autoComplete="email"
              {...register('email', {
                required: t('register.emailRequired'),
                pattern: { value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/, message: t('register.emailInvalid') },
              })}
              error={errors.email?.message}
            />
            <Input
              label={t('register.passwordLabel')}
              type="password"
              placeholder={t('register.passwordPlaceholder')}
              autoComplete="new-password"
              {...register('password', {
                required: t('register.passwordRequired'),
                minLength: { value: 8, message: t('register.passwordMinLength') },
                validate: (v) =>
                  new TextEncoder().encode(v).length <= 72 || t('register.passwordMaxLength'),
              })}
              error={errors.password?.message}
            />
            <Input
              label={t('register.confirmLabel')}
              type="password"
              placeholder={t('register.confirmPlaceholder')}
              autoComplete="new-password"
              {...register('confirm', {
                required: t('register.confirmRequired'),
                validate: (v) => v === watch('password') || t('register.passwordsNoMatch'),
              })}
              error={errors.confirm?.message}
            />

            {code && validation?.valid && !validation.full && (
              <div className="border border-border bg-card p-4 space-y-3">
                <p className="font-mono-label text-accent flex items-center gap-1.5">
                  <CalendarCheck size={12} strokeWidth={1.5} /> {t('register.yourStay')}
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <Input
                    label={t('register.arrivalDate')}
                    type="date"
                    min={validation.event_start ?? undefined}
                    max={validation.event_end ?? undefined}
                    {...register('arrival_date', { required: t('register.arrivalDateRequired') })}
                    error={errors.arrival_date?.message}
                  />
                  <Input
                    label={t('register.departureDate')}
                    type="date"
                    min={validation.event_start ?? undefined}
                    max={validation.event_end ?? undefined}
                    {...register('departure_date', { required: t('register.departureDateRequired') })}
                    error={errors.departure_date?.message}
                  />
                </div>
              </div>
            )}

            {error && (
              <div className="border border-red-800 bg-red-950/20 px-4 py-3">
                <p className="font-mono-label text-red-400">{error}</p>
              </div>
            )}

            <Button
              type="submit"
              className="w-full"
              disabled={isSubmitting || !canRegister}
            >
              {isSubmitting ? t('register.creating') : (
                <>{t('register.spawnIn')} <ArrowRight size={14} /></>
              )}
            </Button>
          </form>

          <DiscordButton withDivider inviteCode={code || undefined} disabled={!canRegister} />

          <div className="mt-8 pt-6 border-t border-border">
            <p className="font-mono-label text-muted-foreground">
              {t('register.alreadyPlayer')}{' '}
              <Link
                to="/login"
                className="text-accent hover:text-accent/80 transition-colors"
              >
                {t('register.connect')} →
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
