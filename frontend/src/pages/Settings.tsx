import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import { useAppConfig, CURRENCIES } from '../contexts/AppConfigContext'
import AnnouncementsManager from '../components/AnnouncementsManager'
import KioskManager from '../components/KioskManager'
import DeletedUsersHistory from '../components/DeletedUsersHistory'
import TrophiesAdminCard from '../components/trophies/TrophiesAdminCard'
import { settingsApi, backupApi } from '../lib/api'
import { AppSetting } from '../types'
import Button from '../components/ui/Button'
import { formatBytes } from '../components/ui/Lightbox'
import ExternalLinkButton from '../components/ui/ExternalLink'
import { Navigate } from 'react-router-dom'
import QRCode from 'react-qr-code'
import { wifiQrPayload } from '../lib/wifiQr'
import { Save, Download, Upload, Eye, EyeOff, Copy, Check, ExternalLink, Send, CheckCircle2, AlertCircle, AlertTriangle, HardDrive } from 'lucide-react'

const COMPOSE_SNIPPET = `services:
  backend:
    image: crosswax/lanpartymanager-backend:latest
    # No ports: — the frontend's Nginx reaches it over the Docker network.
    volumes:
      - ./data:/app/data
      - ./uploads:/app/uploads
    environment:
      # Empty: a random key is generated on first start, kept in ./data/secret_key
      SECRET_KEY: ""
      DATABASE_URL: sqlite:///./data/lanparty.db
      UPLOAD_DIR: /app/uploads
    restart: unless-stopped

  frontend:
    image: crosswax/lanpartymanager-frontend:latest
    ports:
      - "3001:80"
    volumes:
      - ./uploads:/app/uploads
    depends_on:
      - backend
    restart: unless-stopped`

const DOCKER_HUB_BACKEND  = 'https://hub.docker.com/r/crosswax/lanpartymanager-backend'
const DOCKER_HUB_FRONTEND = 'https://hub.docker.com/r/crosswax/lanpartymanager-frontend'

function SettingRow({
  label,
  description,
  settingKey,
  value,
  onSave,
  isSecret,
  multiline,
}: {
  label: string
  description: string
  settingKey: string
  value: string | null
  onSave: (key: string, value: string) => Promise<void>
  isSecret?: boolean
  multiline?: boolean
}) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [input, setInput] = useState(value ?? '')
  const [saving, setSaving] = useState(false)
  const [showSecret, setShowSecret] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave(settingKey, input)
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  const displayValue = isSecret && value
    ? (showSecret ? value : value.slice(0, 4) + '••••••••••••')
    : (value ?? '—')

  return (
    <div className="px-4 py-4 border-b border-border last:border-0">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <p className="font-mono-label text-foreground mb-0.5">{label}</p>
          <p className="text-xs text-muted-foreground mb-2">{description}</p>
          {!editing ? (
            <div className="flex items-center gap-2">
              {multiline ? (
                <pre className="font-mono text-xs text-muted-foreground bg-muted px-2 py-1.5 whitespace-pre-wrap max-w-xl">
                  {displayValue}
                </pre>
              ) : (
                <code className="font-mono text-xs text-muted-foreground bg-muted px-2 py-1">
                  {displayValue}
                </code>
              )}
              {isSecret && value && (
                <button
                  onClick={() => setShowSecret((s) => !s)}
                  className="text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showSecret ? <EyeOff size={12} /> : <Eye size={12} />}
                </button>
              )}
            </div>
          ) : (
            <div className={`flex items-start gap-2 ${multiline ? 'max-w-xl' : 'max-w-sm'}`}>
              {multiline ? (
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  rows={4}
                  className="flex-1 px-3 py-2 bg-input border border-border text-foreground text-sm focus:border-accent outline-none font-mono resize-y"
                  autoFocus
                />
              ) : (
                <input
                  type={isSecret && !showSecret ? 'password' : 'text'}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={t('settings.enterFieldPlaceholder', { label: label.toLowerCase() })}
                  className="flex-1 h-9 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none font-mono"
                  autoFocus
                />
              )}
              {isSecret && (
                <button
                  type="button"
                  onClick={() => setShowSecret((s) => !s)}
                  className="text-muted-foreground hover:text-foreground"
                >
                  {showSecret ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              )}
              <Button size="sm" onClick={handleSave} disabled={saving}>
                <Save size={12} /> {saving ? '...' : t('common.save')}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => { setInput(value ?? ''); setEditing(false) }}>
                {t('common.cancel')}
              </Button>
            </div>
          )}
        </div>
        {!editing && (
          <button
            onClick={() => setEditing(true)}
            className="font-mono-label text-[10px] text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
          >
            {t('common.edit')}
          </button>
        )}
      </div>
    </div>
  )
}

const CURRENCY_NAMES: Record<string, string> = {
  '€': 'EUR',
  '$': 'USD',
  '£': 'GBP',
}

function CurrencyRow({
  value,
  onSave,
}: {
  value: string | null
  onSave: (key: string, value: string) => Promise<void>
}) {
  const { t } = useTranslation()
  const { refreshConfig } = useAppConfig()
  const [saving, setSaving] = useState(false)
  const current = value || '€'

  const handleChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const next = e.target.value
    if (next === current) return
    setSaving(true)
    try {
      await onSave('currency', next)
      await refreshConfig()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="px-4 py-4">
      <p className="font-mono-label text-foreground mb-0.5">{t('settings.currencyLabel')}</p>
      <p className="text-xs text-muted-foreground mb-3">{t('settings.currencyDesc')}</p>
      <select
        value={current}
        onChange={handleChange}
        disabled={saving}
        className="h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none transition-colors disabled:opacity-50"
      >
        {CURRENCIES.map((c) => (
          <option key={c} value={c} className="bg-muted">
            {c} — {CURRENCY_NAMES[c]}
          </option>
        ))}
      </select>
    </div>
  )
}

// Boolean feature flag stored as the string "true"/"false"; enabled unless
// explicitly "false", matching the backend's get_public_config default.
function FeatureToggleRow({
  settingKey,
  label,
  description,
  value,
  onToggle,
  defaultOff,
}: {
  settingKey: string
  label: string
  description: string
  value: string | null
  onToggle: (key: string, value: string) => Promise<void>
  defaultOff?: boolean
}) {
  const { refreshConfig } = useAppConfig()
  const [saving, setSaving] = useState(false)
  // Default-off flags (opt-in, e.g. Discord SSO) are enabled only when explicitly
  // "true"; the default-on flags stay enabled unless explicitly "false".
  const enabled = defaultOff ? value === 'true' : value !== 'false'

  const handleToggle = async () => {
    setSaving(true)
    try {
      await onToggle(settingKey, enabled ? 'false' : 'true')
      await refreshConfig()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="px-4 py-4 flex items-start justify-between gap-4 border-b border-border last:border-0">
      <div className="flex-1 min-w-0">
        <p className="font-mono-label text-foreground mb-0.5">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <button
        type="button"
        onClick={handleToggle}
        disabled={saving}
        role="switch"
        aria-checked={enabled}
        aria-label={label}
        className={`relative w-11 h-6 flex-shrink-0 border transition-colors duration-150 disabled:opacity-50 ${
          enabled ? 'bg-accent border-accent' : 'bg-input border-border'
        }`}
      >
        <span
          className={`absolute top-0.5 h-4 w-4 bg-background transition-all duration-150 ${
            enabled ? 'left-[22px]' : 'left-0.5'
          }`}
        />
      </button>
    </div>
  )
}

const WIFI_SECURITY_OPTIONS = ['WPA', 'WEP', 'nopass'] as const

function WifiSecurityRow({
  value,
  onSave,
}: {
  value: string | null
  onSave: (key: string, value: string) => Promise<void>
}) {
  const { t } = useTranslation()
  const [saving, setSaving] = useState(false)
  const current = value || 'WPA'

  const handleChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    setSaving(true)
    try {
      await onSave('wifi_security', e.target.value)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="px-4 py-4 border-b border-border">
      <p className="font-mono-label text-foreground mb-0.5">{t('settings.wifiSecurityLabel')}</p>
      <p className="text-xs text-muted-foreground mb-3">{t('settings.wifiSecurityDesc')}</p>
      <select
        value={current}
        onChange={handleChange}
        disabled={saving}
        className="h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none transition-colors disabled:opacity-50"
      >
        {WIFI_SECURITY_OPTIONS.map((s) => (
          <option key={s} value={s} className="bg-muted">
            {t(`settings.wifiSecurity_${s}`)}
          </option>
        ))}
      </select>
    </div>
  )
}

// Live preview of exactly what the kiosk will show — scanning it with a phone
// before the LAN is the only real test that the payload joins the network.
function WifiPreview({ settings }: { settings: AppSetting[] }) {
  const { t } = useTranslation()
  const get = (key: string) => settings.find((s) => s.key === key)?.value ?? null
  const ssid = (get('wifi_ssid') || '').trim()
  const security = (get('wifi_security') || 'WPA') as 'WPA' | 'WEP' | 'nopass'
  const hasBaseUrl = !!get('app_base_url')

  if (!ssid) {
    return <p className="text-xs text-muted-foreground mt-3">{t('settings.wifiEmptyHint')}</p>
  }

  return (
    <div className="border border-border bg-card p-4 mt-4 flex flex-col sm:flex-row items-start gap-4">
      <div className="bg-white p-3 shrink-0">
        <QRCode
          value={wifiQrPayload({ ssid, password: get('wifi_password'), security, hidden: get('wifi_hidden') === 'true' })}
          size={128}
        />
      </div>
      <div className="min-w-0">
        <p className="font-mono-label text-foreground mb-1">{t('settings.wifiPreviewLabel')}</p>
        <p className="text-xs text-muted-foreground">{t('settings.wifiPreviewDesc')}</p>
        {!hasBaseUrl && (
          <p className="flex items-start gap-1.5 mt-3 text-xs text-accent">
            <AlertTriangle size={12} className="shrink-0 mt-0.5" /> {t('settings.wifiNoBaseUrlWarning')}
          </p>
        )}
      </div>
    </div>
  )
}

function DiscordTest({ hasWebhook }: { hasWebhook: boolean }) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState<'announcement' | 'reminder' | null>(null)
  const [result, setResult] = useState<{ ok: boolean; type: string } | null>(null)

  const run = async (type: 'announcement' | 'reminder') => {
    setBusy(type)
    setResult(null)
    try {
      await settingsApi.testDiscord(type)
      setResult({ ok: true, type })
    } catch {
      setResult({ ok: false, type })
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="mt-4 border border-border bg-card p-4">
      <p className="font-mono-label text-foreground mb-1">{t('settings.discordTestLabel')}</p>
      <p className="text-xs text-muted-foreground mb-3">
        {hasWebhook ? t('settings.discordTestDesc') : t('settings.discordTestNoWebhook')}
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" variant="outline" disabled={!hasWebhook || busy !== null} onClick={() => run('announcement')}>
          <Send size={12} /> {busy === 'announcement' ? t('settings.discordTesting') : t('settings.discordTestAnnouncement')}
        </Button>
        <Button size="sm" variant="outline" disabled={!hasWebhook || busy !== null} onClick={() => run('reminder')}>
          <Send size={12} /> {busy === 'reminder' ? t('settings.discordTesting') : t('settings.discordTestReminder')}
        </Button>
        {result && (
          <span className={`flex items-center gap-1.5 font-mono-label text-[10px] ${result.ok ? 'text-green-400' : 'text-red-400'}`}>
            {result.ok ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}
            {result.ok ? t('settings.discordTestSent') : t('settings.discordTestFailed')}
          </span>
        )}
      </div>
    </div>
  )
}

function RestoreBackup() {
  const { t } = useTranslation()
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [status, setStatus] = useState<'idle' | 'restoring' | 'done' | 'error'>('idle')

  const pick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) { setFile(f); setStatus('idle') }
  }

  const run = async () => {
    if (!file) return
    if (!confirm(t('settings.restoreConfirm'))) return
    setStatus('restoring')
    try {
      await backupApi.restore(file)
      setStatus('done')
      // Backend restarts (~a few seconds); the restored DB may invalidate the
      // current session, so reload — a 401 will bounce to the login page.
      setTimeout(() => window.location.reload(), 6000)
    } catch {
      setStatus('error')
    }
  }

  return (
    <div className="border border-border bg-card p-6 mt-4">
      <div className="flex items-start gap-2 mb-4">
        <AlertTriangle size={16} className="text-accent flex-shrink-0 mt-0.5" strokeWidth={1.5} />
        <div>
          <p className="font-mono-label text-foreground mb-1">{t('settings.restoreLabel')}</p>
          <p className="text-xs text-muted-foreground">{t('settings.restoreDesc')}</p>
        </div>
      </div>

      <input
        ref={fileRef}
        type="file"
        accept=".tar.gz,.tgz,application/gzip"
        className="hidden"
        onChange={pick}
        disabled={status === 'restoring' || status === 'done'}
      />

      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="outline"
          size="sm"
          onClick={() => fileRef.current?.click()}
          disabled={status === 'restoring' || status === 'done'}
        >
          <Upload size={12} /> {t('settings.restoreChooseFile')}
        </Button>
        {file && <span className="font-mono text-xs text-muted-foreground truncate max-w-xs">{file.name}</span>}
        {file && status !== 'done' && (
          <Button size="sm" onClick={run} disabled={status === 'restoring'}>
            {status === 'restoring' ? t('settings.restoreRunning') : t('settings.restoreButton')}
          </Button>
        )}
      </div>

      {status === 'done' && (
        <p className="flex items-center gap-1.5 mt-3 font-mono-label text-[10px] text-green-400">
          <CheckCircle2 size={12} /> {t('settings.restoreDone')}
        </p>
      )}
      {status === 'error' && (
        <p className="flex items-center gap-1.5 mt-3 font-mono-label text-[10px] text-red-400">
          <AlertCircle size={12} /> {t('settings.restoreError')}
        </p>
      )}
    </div>
  )
}

interface StorageStats {
  disk_total: number
  disk_used: number
  disk_free: number
  uploads_size: number
}

function StorageStatus() {
  const { t } = useTranslation()
  const [stats, setStats] = useState<StorageStats | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    backupApi.storage().then(setStats).catch(() => setError(true))
  }, [])

  if (error) {
    return (
      <div className="border border-border bg-card p-6">
        <p className="text-sm text-muted-foreground">{t('settings.storageError')}</p>
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="border border-border bg-card p-6 text-center">
        <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
      </div>
    )
  }

  const usedPct = stats.disk_total > 0 ? Math.min(100, (stats.disk_used / stats.disk_total) * 100) : 0
  // Under 10% free — the point where an admin should actually do something
  // about it before uploads start failing mid-event.
  const low = stats.disk_total > 0 && stats.disk_free / stats.disk_total < 0.1

  return (
    <div className="border border-border bg-card p-6">
      <div className="flex items-center justify-between gap-3 mb-3">
        <p className="font-mono-label text-foreground flex items-center gap-1.5">
          <HardDrive size={12} strokeWidth={1.5} /> {t('settings.storageDiskLabel')}
        </p>
        <p className={`font-mono-label text-xs ${low ? 'text-red-400' : 'text-muted-foreground'}`}>
          {t('settings.storageFreeOfTotal', { free: formatBytes(stats.disk_free), total: formatBytes(stats.disk_total) })}
        </p>
      </div>
      <div className="w-full h-2 bg-input border border-border overflow-hidden">
        <div
          className={`h-full transition-all duration-300 ${low ? 'bg-red-400' : 'bg-accent'}`}
          style={{ width: `${usedPct}%` }}
        />
      </div>
      {low && (
        <p className="flex items-center gap-1.5 mt-2 font-mono-label text-[10px] text-red-400">
          <AlertTriangle size={12} /> {t('settings.storageLowWarning')}
        </p>
      )}
      <div className="mt-4 pt-4 border-t border-border flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">{t('settings.storageUploadsLabel')}</p>
        <p className="font-mono-label text-foreground text-xs">{formatBytes(stats.uploads_size)}</p>
      </div>
    </div>
  )
}

export default function Settings() {
  const { user } = useAuth()
  const { prizesEnabled, planningEnabled, trophiesEnabled } = useAppConfig()
  const { t } = useTranslation()
  const [settings, setSettings] = useState<AppSetting[]>([])
  const [loading, setLoading] = useState(true)
  const [backingUp, setBackingUp] = useState(false)

  if (user?.role !== 'admin') return <Navigate to="/" replace />

  const load = async () => {
    const data = await settingsApi.getAll()
    setSettings(data)
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const handleSave = async (key: string, value: string) => {
    await settingsApi.update(key, value || null)
    await load()
  }

  const handleBackup = () => {
    setBackingUp(true)
    backupApi.download()
    setTimeout(() => setBackingUp(false), 3000)
  }

  const SETTING_META: Record<string, { label: string; description: string; isSecret?: boolean }> = {
    twitch_client_id: {
      label: t('settings.twitchClientIdLabel'),
      description: t('settings.twitchClientIdDesc'),
    },
    twitch_client_secret: {
      label: t('settings.twitchClientSecretLabel'),
      description: t('settings.twitchClientSecretDesc'),
      isSecret: true,
    },
  }

  const DISCORD_META: Record<string, { label: string; description: string }> = {
    discord_invite_url: {
      label: t('settings.discordInviteLabel'),
      description: t('settings.discordInviteDesc'),
    },
    discord_webhook_url: {
      label: t('settings.discordWebhookLabel'),
      description: t('settings.discordWebhookDesc'),
    },
    app_timezone: { label: t('settings.appTimezoneLabel'), description: t('settings.appTimezoneDesc') },
    reminder_days_before: { label: t('settings.reminderDaysLabel'), description: t('settings.reminderDaysDesc') },
  }

  const DISCORD_SSO_META: Record<string, { label: string; description: string; isSecret?: boolean }> = {
    discord_oauth_client_id: {
      label: t('settings.discordOauthClientIdLabel'),
      description: t('settings.discordOauthClientIdDesc'),
    },
    discord_oauth_client_secret: {
      label: t('settings.discordOauthClientSecretLabel'),
      description: t('settings.discordOauthClientSecretDesc'),
      isSecret: true,
    },
  }

  const STEAM_LINK_META: Record<string, { label: string; description: string; isSecret?: boolean }> = {
    steam_web_api_key: {
      label: t('settings.steamWebApiKeyLabel'),
      description: t('settings.steamWebApiKeyDesc'),
      isSecret: true,
    },
  }

  const DISCORD_TEMPLATE_META: Record<string, { label: string; description: string; multiline?: boolean }> = {
    discord_tpl_reminder: {
      label: t('settings.discordReminderLabel'),
      description: t('settings.discordReminderDesc'),
      multiline: true,
    },
    discord_tpl_announcement: {
      label: t('settings.discordAnnouncementLabel'),
      description: t('settings.discordAnnouncementDesc'),
      multiline: true,
    },
  }

  const WIFI_META: Record<string, { label: string; description: string; isSecret?: boolean }> = {
    wifi_ssid: { label: t('settings.wifiSsidLabel'), description: t('settings.wifiSsidDesc') },
    wifi_password: { label: t('settings.wifiPasswordLabel'), description: t('settings.wifiPasswordDesc'), isSecret: true },
  }

  const EMAIL_META: Record<string, { label: string; description: string; isSecret?: boolean }> = {
    smtp_host: { label: t('settings.smtpHostLabel'), description: t('settings.smtpHostDesc') },
    smtp_port: { label: t('settings.smtpPortLabel'), description: t('settings.smtpPortDesc') },
    smtp_username: { label: t('settings.smtpUsernameLabel'), description: t('settings.smtpUsernameDesc') },
    smtp_password: { label: t('settings.smtpPasswordLabel'), description: t('settings.smtpPasswordDesc'), isSecret: true },
    smtp_from_address: { label: t('settings.smtpFromLabel'), description: t('settings.smtpFromDesc') },
    smtp_use_tls: { label: t('settings.smtpTlsLabel'), description: t('settings.smtpTlsDesc') },
    app_base_url: { label: t('settings.appBaseUrlLabel'), description: t('settings.appBaseUrlDesc') },
  }

  return (
    <main className="max-w-6xl mx-auto px-6 py-12">
      <div className="mb-12">
        <div className="font-mono-label text-accent mb-3">{t('settings.tagline')}</div>
        <h1 className="text-5xl lg:text-6xl font-black tracking-tighter text-foreground leading-none">
          {t('settings.heroLine1')}
          <br />
          <span className="text-accent">{t('settings.heroLine2')}</span>
        </h1>
      </div>

      {/* Currency */}
      <section className="mb-10">
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-xl font-black tracking-tight text-foreground">{t('settings.currencySectionTitle')}</h2>
          <span className="font-mono-label text-accent text-xs">{t('settings.adminOnlyTag')}</span>
        </div>
        <p className="text-sm text-muted-foreground mb-6">
          {t('settings.currencySectionDesc')}
        </p>
        <div className="border border-border bg-card">
          {loading ? (
            <div className="p-8 text-center">
              <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
            </div>
          ) : (
            <CurrencyRow
              value={settings.find((s) => s.key === 'currency')?.value ?? null}
              onSave={handleSave}
            />
          )}
        </div>
      </section>

      {/* Features */}
      <section className="mb-10">
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-xl font-black tracking-tight text-foreground">{t('settings.featuresSectionTitle')}</h2>
          <span className="font-mono-label text-accent text-xs">{t('settings.adminOnlyTag')}</span>
        </div>
        <p className="text-sm text-muted-foreground mb-6">
          {t('settings.featuresSectionDesc')}
        </p>
        <div className="border border-border bg-card">
          {loading ? (
            <div className="p-8 text-center">
              <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
            </div>
          ) : (
            <>
              <FeatureToggleRow
                settingKey="sponsors_enabled"
                label={t('settings.sponsorsToggleLabel')}
                description={t('settings.sponsorsToggleDesc')}
                value={settings.find((s) => s.key === 'sponsors_enabled')?.value ?? null}
                onToggle={handleSave}
              />
              <FeatureToggleRow
                settingKey="prizes_enabled"
                label={t('settings.prizesToggleLabel')}
                description={t('settings.prizesToggleDesc')}
                value={settings.find((s) => s.key === 'prizes_enabled')?.value ?? null}
                onToggle={handleSave}
              />
              {/* Prizes takes Treasury's place — hide the now-overridden toggle. */}
              {!prizesEnabled && (
                <FeatureToggleRow
                  settingKey="treasury_enabled"
                  label={t('settings.treasuryToggleLabel')}
                  description={t('settings.treasuryToggleDesc')}
                  value={settings.find((s) => s.key === 'treasury_enabled')?.value ?? null}
                  onToggle={handleSave}
                />
              )}
              <FeatureToggleRow
                settingKey="planning_enabled"
                label={t('settings.planningToggleLabel')}
                description={t('settings.planningToggleDesc')}
                value={settings.find((s) => s.key === 'planning_enabled')?.value ?? null}
                onToggle={handleSave}
                defaultOff
              />
              <FeatureToggleRow
                settingKey="gear_enabled"
                label={t('settings.gearToggleLabel')}
                description={t('settings.gearToggleDesc')}
                value={settings.find((s) => s.key === 'gear_enabled')?.value ?? null}
                onToggle={handleSave}
                defaultOff
              />
              <FeatureToggleRow
                settingKey="groceries_enabled"
                label={t('settings.groceriesToggleLabel')}
                description={t('settings.groceriesToggleDesc')}
                value={settings.find((s) => s.key === 'groceries_enabled')?.value ?? null}
                onToggle={handleSave}
                defaultOff
              />
              <FeatureToggleRow
                settingKey="checklist_enabled"
                label={t('settings.checklistToggleLabel')}
                description={t('settings.checklistToggleDesc')}
                value={settings.find((s) => s.key === 'checklist_enabled')?.value ?? null}
                onToggle={handleSave}
                defaultOff
              />
              <FeatureToggleRow
                settingKey="minigames_enabled"
                label={t('settings.minigamesToggleLabel')}
                description={t('settings.minigamesToggleDesc')}
                value={settings.find((s) => s.key === 'minigames_enabled')?.value ?? null}
                onToggle={handleSave}
                defaultOff
              />
              <FeatureToggleRow
                settingKey="games_enabled"
                label={t('settings.gamesToggleLabel')}
                description={t('settings.gamesToggleDesc')}
                value={settings.find((s) => s.key === 'games_enabled')?.value ?? null}
                onToggle={handleSave}
                defaultOff
              />
              <FeatureToggleRow
                settingKey="recap_enabled"
                label={t('settings.recapToggleLabel')}
                description={t('settings.recapToggleDesc')}
                value={settings.find((s) => s.key === 'recap_enabled')?.value ?? null}
                onToggle={handleSave}
                defaultOff
              />
              <FeatureToggleRow
                settingKey="setup_enabled"
                label={t('settings.setupToggleLabel')}
                description={t('settings.setupToggleDesc')}
                value={settings.find((s) => s.key === 'setup_enabled')?.value ?? null}
                onToggle={handleSave}
                defaultOff
              />
              <FeatureToggleRow
                settingKey="streams_enabled"
                label={t('settings.streamsToggleLabel')}
                description={t('settings.streamsToggleDesc')}
                value={settings.find((s) => s.key === 'streams_enabled')?.value ?? null}
                onToggle={handleSave}
              />
              <FeatureToggleRow
                settingKey="merch_size_enabled"
                label={t('settings.merchSizeToggleLabel')}
                description={t('settings.merchSizeToggleDesc')}
                value={settings.find((s) => s.key === 'merch_size_enabled')?.value ?? null}
                onToggle={handleSave}
              />
              <FeatureToggleRow
                settingKey="craving_chat_enabled"
                label={t('settings.cravingChatToggleLabel')}
                description={t('settings.cravingChatToggleDesc')}
                value={settings.find((s) => s.key === 'craving_chat_enabled')?.value ?? null}
                onToggle={handleSave}
              />
              <FeatureToggleRow
                settingKey="trophies_enabled"
                label={t('settings.trophiesToggleLabel')}
                description={t('settings.trophiesToggleDesc')}
                value={settings.find((s) => s.key === 'trophies_enabled')?.value ?? null}
                onToggle={handleSave}
                defaultOff
              />
              <FeatureToggleRow
                settingKey="lol_stats_enabled"
                label={t('settings.lolStatsToggleLabel')}
                description={t('settings.lolStatsToggleDesc')}
                value={settings.find((s) => s.key === 'lol_stats_enabled')?.value ?? null}
                onToggle={handleSave}
                defaultOff
              />
              <FeatureToggleRow
                settingKey="xp_enabled"
                label={t('settings.xpToggleLabel')}
                description={t('settings.xpToggleDesc')}
                value={settings.find((s) => s.key === 'xp_enabled')?.value ?? null}
                onToggle={handleSave}
                defaultOff
              />
              {/* The two planning behaviour toggles only matter once planning is on. */}
              {planningEnabled && (
                <>
                  <FeatureToggleRow
                    settingKey="planning_default_can_propose"
                    label={t('settings.planningProposeToggleLabel')}
                    description={t('settings.planningProposeToggleDesc')}
                    value={settings.find((s) => s.key === 'planning_default_can_propose')?.value ?? null}
                    onToggle={handleSave}
                  />
                  <FeatureToggleRow
                    settingKey="planning_default_can_vote"
                    label={t('settings.planningVoteToggleLabel')}
                    description={t('settings.planningVoteToggleDesc')}
                    value={settings.find((s) => s.key === 'planning_default_can_vote')?.value ?? null}
                    onToggle={handleSave}
                  />
                </>
              )}
            </>
          )}
        </div>
      </section>

      {/* Trophy cabinet — the definitions; awarding happens on each event's page */}
      {trophiesEnabled && (
        <section className="mb-10">
          <div className="flex items-center gap-3 mb-4">
            <h2 className="text-xl font-black tracking-tight text-foreground">{t('settings.trophiesSectionTitle')}</h2>
            <span className="font-mono-label text-accent text-xs">{t('settings.adminOnlyTag')}</span>
          </div>
          <p className="text-sm text-muted-foreground mb-6">{t('settings.trophiesSectionDesc')}</p>
          <TrophiesAdminCard />
        </section>
      )}

      {/* Announcements / PA */}
      <section className="mb-10">
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-xl font-black tracking-tight text-foreground">{t('settings.announcementsSectionTitle')}</h2>
          <span className="font-mono-label text-accent text-xs">{t('settings.adminOnlyTag')}</span>
        </div>
        <p className="text-sm text-muted-foreground mb-6">{t('settings.announcementsSectionDesc')}</p>
        <AnnouncementsManager />
      </section>

      {/* Big Screen / Kiosk */}
      <section className="mb-10">
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-xl font-black tracking-tight text-foreground">{t('settings.kioskSectionTitle')}</h2>
          <span className="font-mono-label text-accent text-xs">{t('settings.adminOnlyTag')}</span>
        </div>
        <p className="text-sm text-muted-foreground mb-6">{t('settings.kioskSectionDesc')}</p>
        <div className="border border-border bg-card mb-4">
          {loading ? (
            <div className="p-8 text-center">
              <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
            </div>
          ) : (
            <>
              <FeatureToggleRow
                settingKey="kiosk_enabled"
                label={t('settings.kioskToggleLabel')}
                description={t('settings.kioskToggleDesc')}
                value={settings.find((s) => s.key === 'kiosk_enabled')?.value ?? null}
                onToggle={handleSave}
                defaultOff
              />
              {settings.find((s) => s.key === 'kiosk_enabled')?.value === 'true' && (
                <FeatureToggleRow
                  settingKey="kiosk_live_drop_enabled"
                  label={t('settings.kioskLiveDropLabel')}
                  description={t('settings.kioskLiveDropDesc')}
                  value={settings.find((s) => s.key === 'kiosk_live_drop_enabled')?.value ?? null}
                  onToggle={handleSave}
                />
              )}
            </>
          )}
        </div>
        {!loading && settings.find((s) => s.key === 'kiosk_enabled')?.value === 'true' && (
          <KioskManager appBaseUrl={settings.find((s) => s.key === 'app_base_url')?.value ?? null} />
        )}
      </section>

      {/* Guest WiFi — the spare network for phones/laptops (PCs are wired) */}
      <section className="mb-10">
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-xl font-black tracking-tight text-foreground">{t('settings.wifiSectionTitle')}</h2>
          <span className="font-mono-label text-accent text-xs">{t('settings.adminOnlyTag')}</span>
        </div>
        <p className="text-sm text-muted-foreground mb-6">{t('settings.wifiSectionDesc')}</p>
        <div className="border border-border bg-card">
          {loading ? (
            <div className="p-8 text-center">
              <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
            </div>
          ) : (
            <>
              {(['wifi_ssid', 'wifi_password'] as const).map((key) => (
                <SettingRow
                  key={key}
                  settingKey={key}
                  label={WIFI_META[key].label}
                  description={WIFI_META[key].description}
                  value={settings.find((s) => s.key === key)?.value ?? null}
                  isSecret={WIFI_META[key].isSecret}
                  onSave={handleSave}
                />
              ))}
              <WifiSecurityRow
                value={settings.find((s) => s.key === 'wifi_security')?.value ?? null}
                onSave={handleSave}
              />
              <FeatureToggleRow
                settingKey="wifi_hidden"
                label={t('settings.wifiHiddenLabel')}
                description={t('settings.wifiHiddenDesc')}
                value={settings.find((s) => s.key === 'wifi_hidden')?.value ?? null}
                onToggle={handleSave}
                defaultOff
              />
            </>
          )}
        </div>
        {!loading && <WifiPreview settings={settings} />}
      </section>

      {/* Twitch API settings */}
      <section className="mb-10">
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-xl font-black tracking-tight text-foreground">{t('settings.twitchSectionTitle')}</h2>
          <span className="font-mono-label text-accent text-xs">{t('settings.adminOnlyTag')}</span>
        </div>
        <p className="text-sm text-muted-foreground mb-6">
          {t('settings.twitchDesc')}{' '}
          <span className="font-mono text-muted-foreground">dev.twitch.tv</span>.
        </p>
        <div className="border border-border bg-card">
          {loading ? (
            <div className="p-8 text-center">
              <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
            </div>
          ) : (
            settings.map((s) => {
              const meta = SETTING_META[s.key]
              if (!meta) return null
              return (
                <SettingRow
                  key={s.key}
                  settingKey={s.key}
                  label={meta.label}
                  description={meta.description}
                  value={s.value}
                  isSecret={meta.isSecret}
                  onSave={handleSave}
                />
              )
            })
          )}
        </div>
      </section>

      {/* Discord notifications */}
      <section className="mb-10">
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-xl font-black tracking-tight text-foreground">{t('settings.discordSectionTitle')}</h2>
          <span className="font-mono-label text-accent text-xs">{t('settings.adminOnlyTag')}</span>
        </div>
        <p className="text-sm text-muted-foreground mb-6">
          {t('settings.discordDesc')}
        </p>
        <div className="border border-border bg-card mb-4">
          {loading ? (
            <div className="p-8 text-center">
              <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
            </div>
          ) : (
            settings.map((s) => {
              const meta = DISCORD_META[s.key]
              if (!meta) return null
              return (
                <SettingRow
                  key={s.key}
                  settingKey={s.key}
                  label={meta.label}
                  description={meta.description}
                  value={s.value}
                  onSave={handleSave}
                />
              )
            })
          )}
        </div>
        <p className="text-xs text-muted-foreground mb-2">
          {t('settings.discordTemplatesIntro')}
        </p>
        <div className="border border-border bg-card">
          {loading ? (
            <div className="p-8 text-center">
              <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
            </div>
          ) : (
            settings.map((s) => {
              const meta = DISCORD_TEMPLATE_META[s.key]
              if (!meta) return null
              return (
                <SettingRow
                  key={s.key}
                  settingKey={s.key}
                  label={meta.label}
                  description={meta.description}
                  value={s.value}
                  multiline={meta.multiline}
                  onSave={handleSave}
                />
              )
            })
          )}
        </div>
        {!loading && (
          <DiscordTest
            hasWebhook={!!settings.find((s) => s.key === 'discord_webhook_url')?.value}
          />
        )}
      </section>

      {/* Discord SSO (sign-in) */}
      <section className="mb-10">
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-xl font-black tracking-tight text-foreground">{t('settings.discordSsoSectionTitle')}</h2>
          <span className="font-mono-label text-accent text-xs">{t('settings.adminOnlyTag')}</span>
        </div>
        <p className="text-sm text-muted-foreground mb-6">
          {t('settings.discordSsoDesc')}{' '}
          <span className="font-mono text-muted-foreground">discord.com/developers</span>.
        </p>
        <div className="border border-border bg-card">
          {loading ? (
            <div className="p-8 text-center">
              <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
            </div>
          ) : (
            <>
              <FeatureToggleRow
                settingKey="discord_oauth_enabled"
                label={t('settings.discordOauthEnabledLabel')}
                description={t('settings.discordOauthEnabledDesc')}
                value={settings.find((s) => s.key === 'discord_oauth_enabled')?.value ?? null}
                onToggle={handleSave}
                defaultOff
              />
              {settings.map((s) => {
                const meta = DISCORD_SSO_META[s.key]
                if (!meta) return null
                return (
                  <SettingRow
                    key={s.key}
                    settingKey={s.key}
                    label={meta.label}
                    description={meta.description}
                    value={s.value}
                    isSecret={meta.isSecret}
                    onSave={handleSave}
                  />
                )
              })}
            </>
          )}
        </div>
        {!loading && (
          <p className="text-xs text-muted-foreground mt-3 leading-relaxed">
            {t('settings.discordSsoRedirectHint')}{' '}
            <span className="font-mono text-foreground break-all">
              {(settings.find((s) => s.key === 'app_base_url')?.value || '').replace(/\/$/, '')}
              /api/auth/discord/callback
            </span>
          </p>
        )}
      </section>

      {/* Steam link */}
      <section className="mb-10">
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-xl font-black tracking-tight text-foreground">{t('settings.steamLinkSectionTitle')}</h2>
          <span className="font-mono-label text-accent text-xs">{t('settings.adminOnlyTag')}</span>
        </div>
        <p className="text-sm text-muted-foreground mb-6">
          {t('settings.steamLinkDesc')}{' '}
          <ExternalLinkButton href="https://steamcommunity.com/dev/apikey" className="font-mono text-accent hover:underline">
            steamcommunity.com/dev/apikey
          </ExternalLinkButton>.
        </p>
        <div className="border border-border bg-card">
          {loading ? (
            <div className="p-8 text-center">
              <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
            </div>
          ) : (
            <>
              <FeatureToggleRow
                settingKey="steam_link_enabled"
                label={t('settings.steamLinkEnabledLabel')}
                description={t('settings.steamLinkEnabledDesc')}
                value={settings.find((s) => s.key === 'steam_link_enabled')?.value ?? null}
                onToggle={handleSave}
                defaultOff
              />
              {settings.map((s) => {
                const meta = STEAM_LINK_META[s.key]
                if (!meta) return null
                return (
                  <SettingRow
                    key={s.key}
                    settingKey={s.key}
                    label={meta.label}
                    description={meta.description}
                    value={s.value}
                    isSecret={meta.isSecret}
                    onSave={handleSave}
                  />
                )
              })}
            </>
          )}
        </div>
        {!loading && (
          <p className="text-xs text-muted-foreground mt-3 leading-relaxed">
            {t('settings.steamLinkRedirectHint')}{' '}
            <span className="font-mono text-foreground break-all">
              {(settings.find((s) => s.key === 'app_base_url')?.value || '').replace(/\/$/, '')}
              /api/auth/steam/callback
            </span>
          </p>
        )}
      </section>

      {/* Password reset email */}
      <section className="mb-10">
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-xl font-black tracking-tight text-foreground">{t('settings.emailSectionTitle')}</h2>
          <span className="font-mono-label text-accent text-xs">{t('settings.adminOnlyTag')}</span>
        </div>
        <p className="text-sm text-muted-foreground mb-6">
          {t('settings.emailDesc')}
        </p>
        <div className="border border-border bg-card">
          {loading ? (
            <div className="p-8 text-center">
              <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
            </div>
          ) : (
            settings.map((s) => {
              const meta = EMAIL_META[s.key]
              if (!meta) return null
              return (
                <SettingRow
                  key={s.key}
                  settingKey={s.key}
                  label={meta.label}
                  description={meta.description}
                  value={s.value}
                  isSecret={meta.isSecret}
                  onSave={handleSave}
                />
              )
            })
          )}
        </div>
      </section>

      {/* Data backup */}
      <section className="mb-10">
        <h2 className="text-xl font-black tracking-tight text-foreground mb-4">{t('settings.backupSectionTitle')}</h2>
        <p className="text-sm text-muted-foreground mb-6">
          {t('settings.backupDesc')}
        </p>
        <div className="border border-border bg-card p-6 flex items-center justify-between">
          <div>
            <p className="font-mono-label text-foreground mb-1">{t('settings.fullBackupLabel')}</p>
            <p className="text-xs text-muted-foreground">
              {t('settings.fullBackupDesc')}
            </p>
          </div>
          <Button onClick={handleBackup} disabled={backingUp}>
            <Download size={14} />
            {backingUp ? t('settings.preparing') : t('settings.downloadBackup')}
          </Button>
        </div>
        <RestoreBackup />
      </section>

      {/* Storage */}
      <section className="mb-10">
        <h2 className="text-xl font-black tracking-tight text-foreground mb-4">{t('settings.storageSectionTitle')}</h2>
        <p className="text-sm text-muted-foreground mb-6">
          {t('settings.storageSectionDesc')}
        </p>
        <StorageStatus />
      </section>

      {/* Deployment */}
      <section className="mb-10">
        <h2 className="text-xl font-black tracking-tight text-foreground mb-4">{t('settings.deploymentSectionTitle')}</h2>
        <p className="text-sm text-muted-foreground mb-6">
          {t('settings.deploymentDescPrefix')}{' '}
          <code className="font-mono text-xs bg-muted px-1.5 py-0.5 text-foreground">docker compose up</code>.
          {' '}{t('settings.deploymentDescSuffix')}
        </p>

        {/* Docker Hub links */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-6">
          {[
            { label: t('settings.backendImage'), repo: 'crosswax/lanpartymanager-backend', url: DOCKER_HUB_BACKEND },
            { label: t('settings.frontendImage'), repo: 'crosswax/lanpartymanager-frontend', url: DOCKER_HUB_FRONTEND },
          ].map(({ label, repo, url }) => (
            <ExternalLinkButton
              key={repo}
              href={url}
              className="border border-border bg-card p-4 flex items-center justify-between group hover:border-accent transition-colors duration-150"
            >
              <div>
                <p className="font-mono-label text-muted-foreground text-[10px] mb-1">{label}</p>
                <p className="font-mono text-sm text-foreground">{repo}</p>
                <p className="font-mono-label text-muted-foreground text-[10px] mt-1">:latest · :1.3.5</p>
              </div>
              <ExternalLink size={12} strokeWidth={1.5} className="text-muted-foreground group-hover:text-accent transition-colors flex-shrink-0" />
            </ExternalLinkButton>
          ))}
        </div>

        {/* Compose snippet */}
        <ComposeBlock />
      </section>

      {/* Removed accounts (deleted — and, eventually, banned) */}
      <section className="mb-10">
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-xl font-black tracking-tight text-foreground">{t('settings.removedUsersSectionTitle')}</h2>
          <span className="font-mono-label text-accent text-xs">{t('settings.adminOnlyTag')}</span>
        </div>
        <p className="text-sm text-muted-foreground mb-6">{t('settings.removedUsersSectionDesc')}</p>
        <DeletedUsersHistory />
      </section>
    </main>
  )
}

function ComposeBlock() {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(COMPOSE_SNIPPET)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="border border-border bg-card">
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-muted">
        <span className="font-mono-label text-muted-foreground text-[10px]">docker-compose.yml</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 font-mono-label text-[10px] text-muted-foreground hover:text-foreground transition-colors"
        >
          {copied ? (
            <><Check size={10} className="text-green-400" /> {t('common.copied')}</>
          ) : (
            <><Copy size={10} /> {t('common.copy')}</>
          )}
        </button>
      </div>
      <pre className="p-4 text-xs font-mono text-foreground overflow-x-auto leading-relaxed">
        <code>{COMPOSE_SNIPPET}</code>
      </pre>
    </div>
  )
}
