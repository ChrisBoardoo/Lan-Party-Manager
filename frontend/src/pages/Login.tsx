import { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import Input from '../components/ui/Input'
import Button from '../components/ui/Button'
import LanguageToggle from '../components/ui/LanguageToggle'
import DiscordButton from '../components/ui/DiscordButton'
import { normalizeInviteCode } from '../lib/inviteCode'
import { ArrowRight, Wifi, Ticket } from 'lucide-react'

interface FormData {
  identifier: string
  password: string
}

export default function Login() {
  const { login } = useAuth()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const [error, setError] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const discordError = new URLSearchParams(location.search).get('discord')
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>()

  const onSubmit = async (data: FormData) => {
    setError('')
    try {
      await login(data.identifier, data.password)
      navigate('/')
    } catch (e: any) {
      if (e.response?.status === 403) {
        setError(t('login.accountDeactivated'))
      } else {
        setError(e.response?.data?.detail ?? t('login.loginFailed'))
      }
    }
  }

  const handleInviteCode = () => {
    const code = inviteCode.trim()
    if (!code) return
    navigate(`/register?code=${encodeURIComponent(code)}`)
  }

  const stats = [
    { v: '∞', l: t('login.statMaxPlayers') },
    { v: '∞', l: t('login.statTournaments') },
    { v: '0', l: t('login.statDrama') },
  ]

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <div className="flex justify-end px-6 pt-4">
        <LanguageToggle />
      </div>
      {/* Hero */}
      <div className="flex-1 flex flex-col lg:flex-row">
        {/* Left — Branding */}
        <div className="lg:w-1/2 min-w-0 flex flex-col justify-between p-8 lg:p-16 border-b lg:border-b-0 lg:border-r border-border">
          <div className="flex items-center gap-3">
            <Wifi size={18} strokeWidth={1.5} className="text-accent" />
            <span className="font-mono-label text-muted-foreground">{t('login.systemOnline')}</span>
          </div>

          <div className="min-w-0">
            <div className="mb-6">
              <div className="font-mono-label text-accent mb-4">{t('login.tagline')}</div>
              <h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl 2xl:text-8xl font-black tracking-tighter text-foreground leading-none break-words">
                {t('login.heroLine1')}
                <br />
                <span className="text-accent">{t('login.heroLine2')}</span>
                <br />
                {t('login.heroLine3')}
              </h1>
            </div>
            <p className="text-muted-foreground text-base leading-relaxed max-w-sm">
              {t('login.description')}
            </p>
          </div>

          {/* Decorative stat */}
          <div className="hidden lg:grid grid-cols-3 gap-px bg-border">
            {stats.map(({ v, l }) => (
              <div key={l} className="bg-card p-4">
                <p className="text-3xl font-black text-foreground tracking-tighter">{v}</p>
                <p className="font-mono-label text-muted-foreground mt-1">{l}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Right — Form */}
        <div className="lg:w-1/2 flex flex-col justify-center p-8 lg:p-16">
          <div className="max-w-sm w-full mx-auto lg:mx-0">
            <div className="mb-8">
              <h2 className="text-3xl font-black tracking-tight text-foreground mb-1">
                {t('login.heading')}
              </h2>
              <p className="font-mono-label text-muted-foreground">
                {t('login.subheading')}
              </p>
            </div>

            {location.state?.passwordReset && (
              <div className="border border-green-700 bg-green-950/20 px-4 py-3 mb-4">
                <p className="font-mono-label text-green-400">{t('login.passwordResetSuccess')}</p>
              </div>
            )}

            {discordError && (
              <div className="border border-red-800 bg-red-950/20 px-4 py-3 mb-4">
                <p className="font-mono-label text-red-400">
                  {discordError === 'deactivated'
                    ? t('login.accountDeactivated')
                    : discordError === 'link_required'
                      ? t('discord.linkRequired')
                      : t('discord.signInFailed')}
                </p>
              </div>
            )}

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <Input
                label={t('login.identifier')}
                placeholder={t('login.identifierPlaceholder')}
                autoComplete="username"
                {...register('identifier', { required: t('login.identifierRequired') })}
                error={errors.identifier?.message}
              />
              <div>
                <Input
                  label={t('login.password')}
                  type="password"
                  placeholder="••••••••"
                  autoComplete="current-password"
                  {...register('password', { required: t('login.passwordRequired') })}
                  error={errors.password?.message}
                />
                <Link
                  to="/forgot-password"
                  className="font-mono-label text-muted-foreground hover:text-accent transition-colors text-[10px] block mt-1.5"
                >
                  {t('login.forgotPassword')}
                </Link>
              </div>

              {error && (
                <div className="border border-red-800 bg-red-950/20 px-4 py-3">
                  <p className="font-mono-label text-red-400">{error}</p>
                </div>
              )}

              <Button
                type="submit"
                className="w-full"
                disabled={isSubmitting}
              >
                {isSubmitting ? t('login.connecting') : (
                  <>{t('login.connect')} <ArrowRight size={14} /></>
                )}
              </Button>
            </form>

            <DiscordButton withDivider />

            <div className="mt-8 pt-6 border-t border-border">
              <p className="font-mono-label text-muted-foreground">
                {t('login.firstTime')}{' '}
                <Link
                  to="/register"
                  className="text-accent hover:text-accent/80 transition-colors"
                >
                  {t('login.createAccount')} →
                </Link>
              </p>
            </div>

            <div className="mt-6 pt-6 border-t border-border">
              <p className="font-mono-label text-muted-foreground mb-2 flex items-center gap-1.5">
                <Ticket size={11} strokeWidth={1.5} /> {t('login.gotInviteCode')}
              </p>
              <div className="flex gap-2">
                <input
                  value={inviteCode}
                  onChange={(e) => setInviteCode(normalizeInviteCode(e.target.value))}
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleInviteCode() } }}
                  placeholder="ABCD234XYZ"
                  className="flex-1 h-10 px-3 bg-input border border-border text-foreground text-sm font-mono tracking-widest uppercase focus:border-accent outline-none"
                />
                <Button type="button" variant="outline" size="sm" onClick={handleInviteCode} disabled={!inviteCode.trim()}>
                  {t('login.go')}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
