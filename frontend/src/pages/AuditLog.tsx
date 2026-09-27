import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import { auditApi } from '../lib/api'
import { AuditLogEntry } from '../types'
import { timeAgo } from '../lib/formatDate'
import { ShieldAlert } from 'lucide-react'

export default function AuditLog() {
  const { user } = useAuth()
  const { t } = useTranslation()
  const [entries, setEntries] = useState<AuditLogEntry[]>([])
  const [loading, setLoading] = useState(true)

  if (user?.role !== 'admin') return <Navigate to="/" replace />

  useEffect(() => {
    auditApi.getAll().then((data) => { setEntries(data); setLoading(false) })
  }, [])

  return (
    <main className="max-w-6xl mx-auto px-6 py-12">
      <div className="mb-12">
        <div className="font-mono-label text-accent mb-3">{t('audit.tagline')}</div>
        <h1 className="text-5xl lg:text-6xl font-black tracking-tighter text-foreground leading-none">
          {t('audit.heroLine1')}
          <br />
          <span className="text-accent">{t('audit.heroLine2')}</span>
        </h1>
        <p className="font-mono-label text-muted-foreground mt-3 text-sm">
          {t('audit.subtitle', { count: entries.length })}
        </p>
      </div>

      {loading ? (
        <div className="space-y-px">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-14 bg-muted animate-pulse" />
          ))}
        </div>
      ) : entries.length === 0 ? (
        <div className="border border-border p-16 text-center">
          <ShieldAlert size={32} strokeWidth={1} className="text-muted-foreground mx-auto mb-4" />
          <p className="font-mono-label text-muted-foreground">{t('audit.noEntriesYet')}</p>
        </div>
      ) : (
        <div className="border border-border bg-card">
          <div className="grid grid-cols-12 gap-3 px-4 py-3 bg-muted border-b border-border">
            <div className="col-span-3 font-mono-label text-muted-foreground">{t('audit.tableAction')}</div>
            <div className="col-span-4 font-mono-label text-muted-foreground">{t('audit.tableDetails')}</div>
            <div className="col-span-3 font-mono-label text-muted-foreground">{t('audit.tableBy')}</div>
            <div className="col-span-2 font-mono-label text-muted-foreground text-right">{t('audit.tableWhen')}</div>
          </div>
          {entries.map((entry) => (
            <div
              key={entry.id}
              className="grid grid-cols-12 gap-3 px-4 py-3 border-b border-border last:border-0 hover:bg-muted/30 transition-colors"
            >
              <div className="col-span-3">
                <span className="font-mono-label text-accent text-xs">
                  {t(`actionLabels.${entry.action}`, entry.action.replace(/_/g, ' ').toUpperCase())}
                </span>
              </div>
              <div className="col-span-4">
                <span className="text-sm text-muted-foreground truncate block">
                  {entry.details ?? '—'}
                </span>
              </div>
              <div className="col-span-3 flex items-center gap-2">
                <div className="w-5 h-5 bg-muted border border-border flex items-center justify-center flex-shrink-0">
                  <span className="text-[9px] font-bold text-muted-foreground">
                    {entry.admin.username[0].toUpperCase()}
                  </span>
                </div>
                <span className="font-mono-label text-muted-foreground text-xs">
                  {entry.admin.username}
                </span>
              </div>
              <div className="col-span-2 text-right">
                <span className="font-mono-label text-muted-foreground text-xs">
                  {timeAgo(entry.created_at)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  )
}
