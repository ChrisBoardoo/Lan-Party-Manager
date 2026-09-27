import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { sponsorsApi } from '../lib/api'
import { useAppConfig } from '../contexts/AppConfigContext'
import { Sponsor } from '../types'
import ExternalLink from './ui/ExternalLink'

/**
 * Banner strip of a LAN event's sponsors. Pass `eventId` to show a specific
 * event's sponsors; omit it on pages that aren't event-scoped (Tournaments
 * list, player profiles) to show the current event's sponsors via /active.
 * Renders nothing when the feature is off or there are no sponsors.
 */
export default function SponsorStrip({ eventId }: { eventId?: number }) {
  const { sponsorsEnabled } = useAppConfig()
  const { t } = useTranslation()
  const [sponsors, setSponsors] = useState<Sponsor[]>([])

  useEffect(() => {
    if (!sponsorsEnabled) return
    let cancelled = false
    const req = eventId != null ? sponsorsApi.getForEvent(eventId) : sponsorsApi.getActive()
    req.then((data) => { if (!cancelled) setSponsors(data) }).catch(() => {})
    return () => { cancelled = true }
  }, [sponsorsEnabled, eventId])

  if (!sponsorsEnabled || sponsors.length === 0) return null

  return (
    <div className="border border-border bg-card p-6">
      <p className="font-mono-label text-muted-foreground mb-4">// {t('sponsors.title')}</p>
      <div className="flex flex-wrap items-center gap-4 sm:gap-6">
        {sponsors.map((s) => {
          const banner = s.banner_type === 'video' ? (
            <video
              src={s.banner_url ?? undefined}
              className="h-12 sm:h-16 w-auto max-w-full object-contain"
              autoPlay
              loop
              muted
              playsInline
            />
          ) : s.banner_url ? (
            <img
              src={s.banner_url}
              alt={s.name}
              className="h-12 sm:h-16 w-auto max-w-full object-contain"
            />
          ) : (
            <span className="font-mono-label text-foreground">{s.name}</span>
          )

          return s.link_url ? (
            <ExternalLink
              key={s.id}
              href={s.link_url}
              title={s.name}
              className="opacity-80 hover:opacity-100 transition-opacity"
            >
              {banner}
            </ExternalLink>
          ) : (
            <div key={s.id} title={s.name} className="opacity-90">{banner}</div>
          )
        })}
      </div>
    </div>
  )
}
