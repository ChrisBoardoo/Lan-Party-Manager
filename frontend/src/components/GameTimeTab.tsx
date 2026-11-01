import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Check, Download, Gamepad2, Monitor, Timer, Users } from 'lucide-react'
import { eventsApi, gametimeApi } from '../lib/api'
import { isEmbeddedInDesktop } from '../lib/desktopBridge'
import { eventInProgress, todayIso } from '../lib/eventDates'
import { parseUtc } from '../lib/formatDate'
import { barPercent, formatPlayTime, heatGrid } from '../lib/gametime'
import { useLoad } from '../hooks/useLoad'
import type { GametimeEvent, LanEvent } from '../types'
import ExternalLink from './ui/ExternalLink'
import LoadError from './ui/LoadError'

const DESKTOP_DOWNLOAD_URL = 'https://www.lanpartymanager.com/#desktop'
// "Playing now" moves while a LAN runs: refreshed in the background, no skeleton.
const LIVE_REFRESH_MS = 60_000

// Games > Game time (backend/router_gametime.py): what the members' desktop
// apps saw the crew play during one LAN — the LAN running now by default,
// else the latest one. Totals by game as bars that grow on arrival, who's
// playing right now, each member's time, and the LAN's days × hours.
export default function GameTimeTab() {
  const { t } = useTranslation()
  const events = useLoad(() => eventsApi.getAll(), [])
  const [picked, setPicked] = useState<number | null>(null)

  const sorted = useMemo(
    () => [...(events.data ?? [])].sort((a, b) => b.start_date.localeCompare(a.start_date)),
    [events.data],
  )
  const liveId = eventInProgress(sorted)?.id
  const fallbackId = (sorted.find((e) => e.start_date.slice(0, 10) <= todayIso()) ?? sorted[0])?.id
  const eventId = picked ?? liveId ?? fallbackId

  if (events.error) return <LoadError message={events.error} onRetry={events.retry} />

  return (
    <div className="space-y-6">
      <DesktopCard />
      {events.loading ? (
        <div className="h-40 bg-muted animate-pulse" />
      ) : eventId === undefined ? (
        <p className="py-8 text-center font-mono-label text-muted-foreground">{t('games.gametime.noEvent')}</p>
      ) : (
        <>
          <label htmlFor="gametime-lan" className="flex flex-wrap items-center gap-3">
            <span className="font-mono-label text-muted-foreground">{t('games.gametime.lan')}</span>
            <select
              id="gametime-lan"
              value={eventId}
              onChange={(e) => setPicked(Number(e.target.value))}
              className="h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none max-w-full"
            >
              {sorted.map((e: LanEvent) => (
                <option key={e.id} value={e.id}>
                  {e.title}{e.id === liveId ? ` · ${t('games.lol.inProgress')}` : ''}
                </option>
              ))}
            </select>
          </label>
          <EventGameTime key={eventId} eventId={eventId} live={eventId === liveId} />
        </>
      )}
    </div>
  )
}

function EventGameTime({ eventId, live }: { eventId: number; live: boolean }) {
  const { t } = useTranslation()
  const { data, loading, error, retry, reload } = useLoad(() => gametimeApi.event(eventId), [eventId])

  useEffect(() => {
    if (!live) return
    const id = window.setInterval(reload, LIVE_REFRESH_MS)
    return () => window.clearInterval(id)
  }, [live, reload])

  if (error) return <LoadError message={error} onRetry={retry} />
  if (loading || !data) return <div className="h-64 bg-muted animate-pulse" />
  if (data.total_seconds === 0 && data.now_playing.length === 0) {
    return (
      <div className="border border-border bg-card px-4 py-10 text-center space-y-2">
        <p className="font-mono-label text-muted-foreground">{t('games.gametime.empty')}</p>
        <p className="text-xs text-muted-foreground max-w-md mx-auto">{t('games.gametime.emptyHint')}</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <KeyFigures data={data} />
      {data.now_playing.length > 0 && <NowPlaying data={data} />}
      <GameBars data={data} />
      <Members data={data} />
      <HeatMap data={data} />
    </div>
  )
}

function KeyFigures({ data }: { data: GametimeEvent }) {
  const { t } = useTranslation()
  const top = data.games[0]
  const figures = [
    { label: t('games.gametime.total'), value: formatPlayTime(data.total_seconds), sub: null },
    { label: t('games.gametime.gamesCount'), value: String(data.games.length), sub: null },
    { label: t('games.gametime.topGame'), value: top ? formatPlayTime(top.seconds) : '—', sub: top?.game_name ?? null },
    {
      label: t('games.gametime.longest'),
      value: data.longest ? formatPlayTime(data.longest.seconds) : '—',
      sub: data.longest ? `${data.longest.username} · ${data.longest.game_name}` : null,
    },
  ]
  return (
    // Outlines, not `gap-px bg-border`, as in LolLanStats' records.
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-px border border-border">
      {figures.map((f) => (
        <div key={f.label} className="bg-card p-4 outline outline-1 outline-border min-w-0">
          <p className="font-mono-label text-muted-foreground text-[10px]">{f.label}</p>
          <p className="text-2xl font-black text-foreground mt-1">{f.value}</p>
          {f.sub && <p className="text-xs text-muted-foreground mt-0.5 truncate" title={f.sub}>{f.sub}</p>}
        </div>
      ))}
    </div>
  )
}

function NowPlaying({ data }: { data: GametimeEvent }) {
  const { t } = useTranslation()
  return (
    <section className="border border-border bg-card p-4 space-y-3">
      <p className="font-mono-label text-accent flex items-center gap-1.5">
        <span className="w-2 h-2 bg-accent animate-pulse motion-reduce:animate-none" /> {t('games.gametime.nowPlaying')}
      </p>
      <ul className="flex flex-wrap gap-2">
        {data.now_playing.map((p) => (
          <li key={`${p.user_id}-${p.game_name}`} className="flex items-center gap-2 border border-border px-3 py-2 min-w-0 max-w-full">
            <Avatar url={p.avatar_url} name={p.username} />
            <span className="text-sm min-w-0 truncate">
              <Link to={`/players/${p.user_id}`} className="font-bold text-foreground hover:text-accent">{p.username}</Link>
              <span className="text-muted-foreground"> · {p.game_name}</span>
            </span>
            <span className="font-mono-label text-[10px] text-muted-foreground whitespace-nowrap">
              {t('games.gametime.since', { time: formatPlayTime((Date.now() - parseUtc(p.since).getTime()) / 1000) })}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

// A bar that grows from nothing to its width once mounted, each one a little
// after the previous; with reduced motion, it's simply there.
function GrowingBar({ percent, delayMs }: { percent: number; delayMs: number }) {
  const [grown, setGrown] = useState(false)
  useEffect(() => {
    const id = window.requestAnimationFrame(() => setGrown(true))
    return () => window.cancelAnimationFrame(id)
  }, [])
  return (
    <div className="h-2 bg-muted overflow-hidden">
      <div
        className="h-full bg-accent transition-[width] duration-700 ease-out motion-reduce:transition-none"
        style={{ width: grown ? `${percent}%` : '0%', transitionDelay: `${delayMs}ms` }}
      />
    </div>
  )
}

function GameBars({ data }: { data: GametimeEvent }) {
  const { t } = useTranslation()
  const max = data.games[0]?.seconds ?? 0
  return (
    <section className="border border-border bg-card">
      <div className="p-4 border-b border-border">
        <p className="font-mono-label text-accent flex items-center gap-1.5">
          <Gamepad2 size={12} strokeWidth={1.5} /> {t('games.gametime.byGame')}
        </p>
        <p className="text-xs text-muted-foreground mt-1">{t('games.gametime.hint')}</p>
      </div>
      <ol className="p-4 space-y-4">
        {data.games.map((g, i) => (
          <li key={g.game_key} className="space-y-1.5">
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-bold text-foreground truncate min-w-0" title={g.game_name}>{g.game_name}</span>
              <span className="flex items-baseline gap-3 flex-shrink-0">
                <span className="font-mono-label text-[10px] text-muted-foreground hidden sm:inline">
                  {t('games.gametime.players', { count: g.players })}
                </span>
                <span className="font-mono font-black text-accent">{formatPlayTime(g.seconds)}</span>
              </span>
            </div>
            <GrowingBar percent={barPercent(g.seconds, max)} delayMs={i * 80} />
          </li>
        ))}
      </ol>
    </section>
  )
}

function Members({ data }: { data: GametimeEvent }) {
  const { t } = useTranslation()
  const max = data.members[0]?.seconds ?? 0
  return (
    <section className="border border-border bg-card">
      <p className="p-4 border-b border-border font-mono-label text-accent flex items-center gap-1.5">
        <Users size={12} strokeWidth={1.5} /> {t('games.gametime.byMember')}
      </p>
      <ul>
        {data.members.map((m, i) => (
          <li key={m.user_id} className="px-4 py-3 border-b border-border last:border-0 space-y-1.5">
            <div className="flex items-center justify-between gap-3">
              <Link to={`/players/${m.user_id}`} className="flex items-center gap-2 group min-w-0">
                <Avatar url={m.avatar_url} name={m.username} />
                <span className="font-bold text-foreground group-hover:text-accent transition-colors truncate">{m.username}</span>
              </Link>
              <span className="font-mono font-black text-foreground flex-shrink-0">{formatPlayTime(m.seconds)}</span>
            </div>
            <GrowingBar percent={barPercent(m.seconds, max)} delayMs={i * 80} />
            <p className="text-xs text-muted-foreground truncate">
              {m.games.slice(0, 3).map((g) => `${g.game_name} ${formatPlayTime(g.seconds)}`).join(' · ')}
              {m.games.length > 3 && ` · +${m.games.length - 3}`}
            </p>
          </li>
        ))}
      </ul>
    </section>
  )
}

function HeatMap({ data }: { data: GametimeEvent }) {
  const { t, i18n } = useTranslation()
  const grid = useMemo(() => heatGrid(data.heatmap), [data.heatmap])
  if (grid.days.length === 0) return null
  const locale = i18n.language?.startsWith('fr') ? 'fr-FR' : 'en-GB'
  const dayLabel = (day: string) =>
    new Date(`${day}T12:00:00Z`).toLocaleDateString(locale, { weekday: 'short', day: 'numeric', timeZone: 'UTC' })

  return (
    <section className="border border-border bg-card">
      <div className="p-4 border-b border-border">
        <p className="font-mono-label text-accent flex items-center gap-1.5">
          <Timer size={12} strokeWidth={1.5} /> {t('games.gametime.heatmap')}
        </p>
        <p className="text-xs text-muted-foreground mt-1">{t('games.gametime.heatmapHint')}</p>
      </div>
      <div className="p-4">
        <div className="grid gap-px" style={{ gridTemplateColumns: 'auto repeat(24, minmax(0, 1fr))' }}>
          <span />
          {Array.from({ length: 24 }, (_, h) => (
            <span key={h} className="font-mono-label text-[9px] text-muted-foreground text-center">
              {h % 6 === 0 ? h : ''}
            </span>
          ))}
          {grid.days.map((day, d) => (
            <div key={day} className="contents">
              <span className="font-mono-label text-[10px] text-muted-foreground pr-2 whitespace-nowrap self-center">
                {dayLabel(day)}
              </span>
              {grid.rows[d].map((secs, h) => (
                <span
                  key={h}
                  title={`${dayLabel(day)} ${h}h · ${formatPlayTime(secs)}`}
                  className={`aspect-square ${secs > 0 ? 'bg-accent' : 'bg-muted'}`}
                  style={secs > 0 ? { opacity: 0.2 + 0.8 * (secs / grid.max) } : undefined}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function Avatar({ url, name }: { url: string | null; name: string }) {
  return url ? (
    <img src={url} alt="" className="w-6 h-6 object-cover flex-shrink-0" />
  ) : (
    <span className="w-6 h-6 bg-muted flex items-center justify-center font-black text-xs flex-shrink-0">
      {name.charAt(0).toUpperCase()}
    </span>
  )
}

// Inside the desktop app: where its switches are. In a browser: the download.
function DesktopCard() {
  const { t } = useTranslation()
  return (
    <div className="border border-border bg-card p-4 space-y-2">
      <p className="font-mono-label text-muted-foreground flex items-center gap-1.5">
        <Monitor size={12} strokeWidth={1.5} /> {t('games.lol.desktopTitle')}
      </p>
      {isEmbeddedInDesktop() ? (
        <>
          <p className="font-semibold text-foreground flex items-center gap-1.5">
            <Check size={14} strokeWidth={2} className="text-accent" /> {t('games.gametime.desktopReady')}
          </p>
          <p className="text-xs text-muted-foreground">{t('games.gametime.desktopReadyHint')}</p>
        </>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">{t('games.gametime.desktopHint')}</p>
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
