import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Download, Monitor } from 'lucide-react'
import { eventsApi } from '../lib/api'
import { isEmbeddedInDesktop } from '../lib/desktopBridge'
import { eventInProgress } from '../lib/eventDates'
import type { LanEvent } from '../types'
import ExternalLink from './ui/ExternalLink'
import LolLanStats from './LolLanStats'
import RiotIdCard from './RiotIdCard'

// The site's download section rather than the .msi itself: the installer's
// file name carries the version, so a direct link would go stale on every bump.
const DESKTOP_DOWNLOAD_URL = 'https://www.lanpartymanager.com/#desktop'

// Games > League of Legends tracker (the page's first tab when lol_stats is on):
// the two things a member sets up before the LAN — Riot ID, desktop app — then
// the stats of the games their apps sent, all LANs or one (LolLanStats).
export default function LolTrackerTab() {
  const { t } = useTranslation()
  const [events, setEvents] = useState<LanEvent[]>([])
  const [liveId, setLiveId] = useState<number | undefined>(undefined)
  const [eventId, setEventId] = useState<number | undefined>(undefined)
  const [scopeReady, setScopeReady] = useState(false)

  // Global by default; during a LAN, that LAN — so what the crew looks at
  // starts from zero every LAN without anything being reset. The table waits
  // for this choice rather than flashing the global stats first.
  useEffect(() => {
    eventsApi
      .getAll()
      .then((es) => {
        setEvents([...es].sort((a, b) => b.start_date.localeCompare(a.start_date)))
        const live = eventInProgress(es)?.id
        setLiveId(live)
        setEventId(live)
      })
      .catch(() => setEvents([]))
      .finally(() => setScopeReady(true))
  }, [])

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <p className="text-sm text-muted-foreground">{t('games.lol.setupIntro')}</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <RiotIdCard />
          <DesktopAppCard />
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <label className="font-mono-label text-muted-foreground">{t('tournaments.stats.scope')}</label>
        <select
          value={eventId ?? ''}
          onChange={(e) => setEventId(e.target.value ? Number(e.target.value) : undefined)}
          className="h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none"
        >
          <option value="">{t('tournaments.stats.scopeGlobal')}</option>
          {events.map((e) => (
            <option key={e.id} value={e.id}>
              {e.title}{e.id === liveId ? ` · ${t('games.lol.inProgress')}` : ''}
            </option>
          ))}
        </select>
      </div>

      {scopeReady
        ? <LolLanStats eventId={eventId} scopeName={events.find((e) => e.id === eventId)?.title} />
        : <div className="h-40 bg-muted animate-pulse" />}
    </div>
  )
}

// Inside the desktop app there's nothing to install — only the shell's own
// switch to point at. In a browser we can't tell whether it's installed, so
// the card always offers the download.
function DesktopAppCard() {
  const { t } = useTranslation()

  return (
    <div className="border border-border bg-card p-6 space-y-3">
      <p className="font-mono-label text-muted-foreground flex items-center gap-1.5">
        <Monitor size={12} strokeWidth={1.5} /> {t('games.lol.desktopTitle')}
      </p>
      {isEmbeddedInDesktop() ? (
        <>
          <p className="font-semibold text-foreground flex items-center gap-1.5">
            <Check size={14} strokeWidth={2} className="text-accent" /> {t('games.lol.desktopReady')}
          </p>
          <p className="text-xs text-muted-foreground">{t('games.lol.desktopReadyHint')}</p>
        </>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">{t('games.lol.desktopHint')}</p>
          <ExternalLink
            href={DESKTOP_DOWNLOAD_URL}
            className="inline-flex items-center gap-1.5 px-3 py-2 border border-accent text-accent font-mono-label text-xs hover:bg-accent/10 transition-colors"
          >
            <Download size={12} strokeWidth={1.5} /> {t('games.lol.desktopDownload')}
          </ExternalLink>
        </>
      )}
    </div>
  )
}
