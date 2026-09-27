import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Megaphone, AlertTriangle, X } from 'lucide-react'
import { announcementsApi } from '../lib/api'
import { Announcement } from '../types'
import { useAuth } from '../contexts/AuthContext'

const DISMISS_KEY = 'lpm_dismissed_announcements'

function readDismissed(): number[] {
  try {
    return JSON.parse(localStorage.getItem(DISMISS_KEY) || '[]')
  } catch {
    return []
  }
}

/**
 * App-wide PA banner: shows active announcements below the navbar. Dismissal is
 * per-device (localStorage), so hiding one doesn't hide it for the rest of the crew.
 */
export default function AnnouncementBanner() {
  const { user } = useAuth()
  const { t } = useTranslation()
  const [items, setItems] = useState<Announcement[]>([])
  const [dismissed, setDismissed] = useState<number[]>(readDismissed)

  useEffect(() => {
    if (!user) return
    announcementsApi.getActive().then(setItems).catch(() => {})
  }, [user])

  const visible = items.filter((a) => !dismissed.includes(a.id))
  if (visible.length === 0) return null

  const dismiss = (id: number) => {
    const next = [...dismissed, id]
    setDismissed(next)
    try {
      localStorage.setItem(DISMISS_KEY, JSON.stringify(next))
    } catch { /* ignore */ }
  }

  return (
    <div>
      {visible.map((a) => (
        <div
          key={a.id}
          className={`flex items-center gap-3 px-6 py-2.5 border-b ${
            a.level === 'alert'
              ? 'bg-red-500/10 border-red-500/40 text-red-200'
              : 'bg-accent/10 border-accent/40 text-foreground'
          }`}
        >
          {a.level === 'alert' ? (
            <AlertTriangle size={15} strokeWidth={1.5} className="text-red-400 flex-shrink-0" />
          ) : (
            <Megaphone size={15} strokeWidth={1.5} className="text-accent flex-shrink-0" />
          )}
          <span className="text-sm flex-1 min-w-0">{a.message}</span>
          <button
            onClick={() => dismiss(a.id)}
            className="text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
            aria-label={t('common.dismiss')}
            title={t('common.dismiss')}
          >
            <X size={14} strokeWidth={1.5} />
          </button>
        </div>
      ))}
    </div>
  )
}
