import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { announcementsApi } from '../lib/api'
import { Announcement } from '../types'
import Button from './ui/Button'
import { Send, Trash2 } from 'lucide-react'

/**
 * Admin composer for PA announcements: post a message (info/alert, optional
 * auto-expiry and Discord fan-out) and manage the active list. Rendered in the
 * Settings page.
 */
export default function AnnouncementsManager() {
  const { t } = useTranslation()
  const [items, setItems] = useState<Announcement[]>([])
  const [message, setMessage] = useState('')
  const [level, setLevel] = useState<'info' | 'alert'>('info')
  const [expiryHours, setExpiryHours] = useState('')
  const [toDiscord, setToDiscord] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = () => announcementsApi.getActive().then(setItems).catch(() => {})
  useEffect(() => { load() }, [])

  const post = async () => {
    if (!message.trim()) return
    setBusy(true)
    try {
      const expires_at = expiryHours
        ? new Date(Date.now() + Number(expiryHours) * 3_600_000).toISOString()
        : undefined
      await announcementsApi.create({ message: message.trim(), level, expires_at, post_to_discord: toDiscord })
      setMessage(''); setLevel('info'); setExpiryHours(''); setToDiscord(false)
      await load()
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id: number) => {
    await announcementsApi.delete(id)
    await load()
  }

  const inputCls = 'h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none'

  return (
    <div className="border border-border bg-card p-4 space-y-4">
      <textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder={t('settings.announcementPlaceholder')}
        maxLength={500}
        rows={2}
        className="w-full px-3 py-2 bg-input border border-border text-foreground text-sm focus:border-accent outline-none resize-none"
      />
      <div className="flex flex-wrap items-center gap-3">
        <select value={level} onChange={(e) => setLevel(e.target.value as 'info' | 'alert')} className={inputCls}>
          <option value="info">{t('settings.announcementLevelInfo')}</option>
          <option value="alert">{t('settings.announcementLevelAlert')}</option>
        </select>
        <input
          type="number" min={0}
          value={expiryHours}
          onChange={(e) => setExpiryHours(e.target.value)}
          placeholder={t('settings.announcementExpiry')}
          className={`${inputCls} w-48`}
        />
        <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
          <input type="checkbox" checked={toDiscord} onChange={(e) => setToDiscord(e.target.checked)} />
          {t('settings.announcementToDiscord')}
        </label>
        <Button size="sm" onClick={post} disabled={busy || !message.trim()} className="ml-auto">
          <Send size={14} /> {t('settings.announcementPost')}
        </Button>
      </div>

      <div className="border-t border-border pt-3">
        <p className="font-mono-label text-muted-foreground mb-2">{t('settings.announcementActive')}</p>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('settings.announcementNone')}</p>
        ) : (
          <div className="space-y-1">
            {items.map((a) => (
              <div key={a.id} className="flex items-center gap-3 px-3 py-2 border border-border bg-background">
                <span className={`font-mono-label text-[10px] flex-shrink-0 ${a.level === 'alert' ? 'text-red-400' : 'text-accent'}`}>
                  {a.level === 'alert' ? t('settings.announcementLevelAlert') : t('settings.announcementLevelInfo')}
                </span>
                <span className="text-sm text-foreground flex-1 min-w-0 truncate">{a.message}</span>
                <button
                  onClick={() => remove(a.id)}
                  className="p-1 text-muted-foreground hover:text-red-400 transition-colors flex-shrink-0"
                  title={t('common.delete')}
                >
                  <Trash2 size={13} strokeWidth={1.5} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
