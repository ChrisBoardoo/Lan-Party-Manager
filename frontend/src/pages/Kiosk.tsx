import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import QRCode from 'react-qr-code'
import { kioskApi } from '../lib/api'
import type { KioskSummary, KioskMatch, KioskStanding, KioskChampion, KioskTrophy, KioskMedia } from '../types'
import { playAnnouncementChime, playChampionFanfare } from '../lib/kioskSound'
import Confetti from '../components/kiosk/Confetti'
import LoveWall, { type ReactionBurst } from '../components/kiosk/LoveWall'
import LiveDrop from '../components/kiosk/LiveDrop'
import { asUtc } from '../lib/kioskTime'
import { wifiQrPayload } from '../lib/wifiQr'
import TrophyIcon from '../components/trophies/TrophyIcon'

const POLL_MS = 10_000
const SCENE_MS = 12_000
const CELEBRATION_MS = 15_000
const FLASH_MS = 9_000
// Trophy ceremony: a drumroll beat on the trophy's name, then the winner.
const CEREMONY_MS = 15_000
const SUSPENSE_MS = 3_500
// The #LoveWall stays up longer than a text scene: its reveal alone takes ~3s.
const WALL_SCENE_MS = 24_000
// A drop holds the screen this long. Drops start at most once per cooldown;
// whatever gets posted in between is grouped into the next one.
const DROP_MS = 9_000
const DROP_COOLDOWN_MS = 45_000
// Only this recent a post drops. An item that is new to the payload but older
// (a past photo that just became the crowd favourite, a post made while the
// kiosk was offline) simply joins the wall.
const DROP_MAX_AGE_MS = 3 * 60_000
// Reaction emojis float over their tile for a while after the poll that saw them.
const BURST_MS = 6_000
const MAX_FLOATS = 6

// A locked block time is wall-clock the organizer picked — show it literally.
const hhmm = (iso: string) => iso.slice(11, 16)

function useClock() {
  const [, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(id)
  }, [])
}

export default function Kiosk() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const { t } = useTranslation()

  const [summary, setSummary] = useState<KioskSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sceneIndex, setSceneIndex] = useState(0)

  // Countdown clock-skew handling: remember the remaining time at poll and the
  // wall-clock instant we polled, then decrement locally.
  const polledAtRef = useRef(0)
  const countdownAtPollRef = useRef<number | null>(null)

  // "New since we connected" tracking — don't celebrate/flash the backlog on
  // first load, only things that appear while the kiosk is running.
  const seenAnnouncementsRef = useRef<Set<number> | null>(null)
  const lastChampionIdRef = useRef<number | null | undefined>(undefined)
  // Trophy editions already on screen. Anything new is queued for a ceremony —
  // an admin revealing several in a row gets them one after the other.
  const seenTrophiesRef = useRef<Set<number> | null>(null)
  const ceremonyQueueRef = useRef<KioskTrophy[]>([])
  const [ceremony, setCeremony] = useState<{ trophy: KioskTrophy; until: number } | null>(null)

  // #LoveWall: each item's reaction counts at the last poll (null until the
  // first poll, adopted silently), posts waiting for their drop, the drop on
  // screen, and the reaction emojis waiting to float.
  const seenMediaRef = useRef<Map<number, Record<string, number>> | null>(null)
  const dropQueueRef = useRef<KioskMedia[]>([])
  const lastDropAtRef = useRef(0)
  const burstSeqRef = useRef(0)
  const preloadedRef = useRef(new Set<string>())
  const [drop, setDrop] = useState<{ id: number; more: number; until: number } | null>(null)
  const [bursts, setBursts] = useState<ReactionBurst[]>([])

  const [celebrateUntil, setCelebrateUntil] = useState(0)
  const [flash, setFlash] = useState<{ message: string; level: string; until: number } | null>(null)

  useClock()

  // ── Poll the summary ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!token) {
      setError('missing-token')
      return
    }
    let cancelled = false
    const poll = async () => {
      try {
        const data = await kioskApi.getSummary(token)
        if (cancelled) return
        setError(null)

        // Countdown baseline.
        if (data.countdown) {
          countdownAtPollRef.current = asUtc(data.countdown.target) - asUtc(data.server_time)
          polledAtRef.current = Date.now()
        } else {
          countdownAtPollRef.current = null
        }

        // Announcements → flash on anything new.
        const ids = new Set(data.announcements.map((a) => a.id))
        if (seenAnnouncementsRef.current === null) {
          seenAnnouncementsRef.current = ids // first load: adopt silently
        } else {
          const fresh = data.announcements.find((a) => !seenAnnouncementsRef.current!.has(a.id))
          if (fresh) {
            setFlash({ message: fresh.message, level: fresh.level, until: Date.now() + FLASH_MS })
            playAnnouncementChime()
          }
          seenAnnouncementsRef.current = ids
        }

        // Trophies → queue a ceremony for every newly revealed edition. An
        // un-reveal drops the id, so revealing it again replays the ceremony.
        const trophyIds = new Set(data.trophies.map((tr) => tr.edition_id))
        if (seenTrophiesRef.current === null) {
          seenTrophiesRef.current = trophyIds // first load: adopt silently
        } else {
          const seen = seenTrophiesRef.current
          ceremonyQueueRef.current.push(...data.trophies.filter((tr) => !seen.has(tr.edition_id)))
          seenTrophiesRef.current = trophyIds
        }

        // #LoveWall → queue a drop for each fresh post, float the emojis of each
        // new reaction.
        const prevMedia = seenMediaRef.current
        if (prevMedia !== null) {
          const serverNow = asUtc(data.server_time)
          const fresh = data.media.filter(
            (m) => !prevMedia.has(m.id) && !!m.created_at && serverNow - asUtc(m.created_at) < DROP_MAX_AGE_MS,
          )
          if (data.live_drop) dropQueueRef.current.push(...fresh)
          else dropQueueRef.current = []

          const now = Date.now()
          const freshBursts: ReactionBurst[] = []
          for (const m of data.media) {
            const before = prevMedia.get(m.id)
            if (!before) continue
            const emojis = m.reactions.flatMap((r) =>
              Array<string>(Math.max(0, r.count - (before[r.emoji] ?? 0))).fill(r.emoji),
            )
            if (emojis.length) {
              freshBursts.push({ key: ++burstSeqRef.current, mediaId: m.id, emojis: emojis.slice(0, MAX_FLOATS), until: now + BURST_MS })
            }
          }
          setBursts((prev) => [...prev.filter((b) => b.until > now), ...freshBursts])
        }
        seenMediaRef.current = new Map(
          data.media.map((m) => [m.id, Object.fromEntries(m.reactions.map((r) => [r.emoji, r.count]))]),
        )
        // Warm the browser cache, so a tile's reveal never waits on a download.
        for (const m of data.media) {
          if (m.file_type === 'image' && !preloadedRef.current.has(m.url)) {
            preloadedRef.current.add(m.url)
            new Image().src = m.url
          }
        }

        // Champion → celebrate when a new one is decided.
        const champId = data.champion?.tournament_id ?? null
        if (lastChampionIdRef.current === undefined) {
          lastChampionIdRef.current = champId // first load: adopt silently
        } else if (champId !== null && champId !== lastChampionIdRef.current) {
          setCelebrateUntil(Date.now() + CELEBRATION_MS)
          playChampionFanfare()
          lastChampionIdRef.current = champId
        } else {
          lastChampionIdRef.current = champId
        }

        setSummary(data)
      } catch (e: any) {
        if (cancelled) return
        setError(e?.message?.includes('401') ? 'bad-token' : 'unreachable')
      }
    }
    poll()
    const id = setInterval(poll, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [token])

  // ── Build the available scenes from whatever data we have ─────────────────
  const scenes = useMemo(() => {
    if (!summary) return [] as string[]
    const s: string[] = []
    if (summary.event || summary.countdown) s.push('hero')
    if (summary.matches.length) s.push('matches')
    if (summary.standings.length) s.push('standings')
    if (summary.arrivals.attendees.length) s.push('arrivals')
    if (summary.up_next.length) s.push('upnext')
    if (summary.gear && (summary.gear.bringing.length || summary.gear.needs.length)) s.push('gear')
    if (summary.media.length) s.push('lovewall')
    if (summary.champion) s.push('champion')
    if (summary.trophies.length) s.push('trophies')
    if (summary.wifi || summary.join_url) s.push('join')
    return s
  }, [summary])

  // ── Rotate scenes ─────────────────────────────────────────────────────────
  const sceneMs = scenes[sceneIndex] === 'lovewall' ? WALL_SCENE_MS : SCENE_MS
  useEffect(() => {
    if (scenes.length <= 1) return
    const id = setTimeout(() => setSceneIndex((i) => (i + 1) % scenes.length), sceneMs)
    return () => clearTimeout(id)
  }, [scenes.length, sceneIndex, sceneMs])

  useEffect(() => {
    if (sceneIndex >= scenes.length) setSceneIndex(0)
  }, [scenes.length, sceneIndex])

  // Advance the ceremony queue on the 1s clock: the current one plays out its
  // full time, then the next revealed trophy (if any) takes the stage.
  useEffect(() => {
    if (ceremony && ceremony.until > Date.now()) return
    const next = ceremonyQueueRef.current.shift()
    if (next) setCeremony({ trophy: next, until: Date.now() + CEREMONY_MS })
    else if (ceremony) setCeremony(null)
  })

  // Expire the celebration / flash timers via the 1s clock re-render.
  const celebrating = celebrateUntil > Date.now() && !!summary?.champion
  const flashing = flash && flash.until > Date.now() ? flash : null

  // #LoveWall drop, on the 1s clock: the next queued post takes the screen once
  // nothing louder (announcement, trophy ceremony, champion) is on and the
  // cooldown is over. Everything queued meanwhile is grouped into it.
  useEffect(() => {
    if (drop) {
      if (drop.until <= Date.now()) setDrop(null)
      return
    }
    if (!summary || !dropQueueRef.current.length) return
    if (ceremony || flashing || celebrating) return
    if (Date.now() - lastDropAtRef.current < DROP_COOLDOWN_MS) return
    // Anything deleted since it was queued is skipped — moderation beats the queue.
    const live = new Set(summary.media.map((m) => m.id))
    const queued = dropQueueRef.current.filter((m) => live.has(m.id))
    dropQueueRef.current = []
    if (!queued.length) return
    const newest = queued.reduce((a, b) => (b.id > a.id ? b : a))
    setDrop({ id: newest.id, more: queued.length - 1, until: Date.now() + DROP_MS })
    lastDropAtRef.current = Date.now()
  })

  // ── Render ────────────────────────────────────────────────────────────────
  if (error === 'missing-token' || error === 'bad-token') {
    return (
      <KioskShell>
        <div className="text-center">
          <div className="font-mono-label text-accent mb-4">{t('kiosk.title')}</div>
          <h1 className="text-4xl font-black tracking-tighter mb-3">{t('kiosk.invalidTitle')}</h1>
          <p className="text-muted-foreground max-w-xl mx-auto">{t('kiosk.invalidBody')}</p>
        </div>
      </KioskShell>
    )
  }

  if (!summary) {
    return (
      <KioskShell>
        <div className="font-mono-label text-muted-foreground kiosk-pulse">
          {error === 'unreachable' ? t('kiosk.reconnecting') : t('common.loading')}
        </div>
      </KioskShell>
    )
  }

  const activeScene = celebrating ? 'champion' : scenes[sceneIndex] ?? 'idle'
  // Read from the live payload, so a post deleted mid-drop leaves the screen.
  const dropItem = drop ? summary.media.find((m) => m.id === drop.id) : undefined

  return (
    <KioskShell>
      {/* Ambient header — always visible so the room always has context. */}
      <KioskHeader summary={summary} live={summary.arrivals.online} />

      <div key={activeScene + (celebrating ? '-celebrate' : '')} className="kiosk-scene flex-1 flex items-center justify-center px-[6vw] py-[3vh] relative">
        {activeScene === 'hero' && <HeroScene summary={summary} countdownMs={liveCountdown(polledAtRef, countdownAtPollRef)} />}
        {activeScene === 'matches' && <MatchesScene matches={summary.matches} />}
        {activeScene === 'standings' && <StandingsScene standings={summary.standings} />}
        {activeScene === 'arrivals' && <ArrivalsScene summary={summary} />}
        {activeScene === 'upnext' && <UpNextScene summary={summary} />}
        {activeScene === 'gear' && summary.gear && <GearScene gear={summary.gear} />}
        {activeScene === 'lovewall' && (
          <LoveWall
            media={summary.media}
            mediaTotal={summary.media_total}
            reactionsTotal={summary.media_reactions_total}
            serverTime={summary.server_time}
            joinBase={summary.join_url || window.location.origin}
            bursts={bursts.filter((b) => b.until > Date.now())}
          />
        )}
        {activeScene === 'join' && <JoinScene summary={summary} />}
        {activeScene === 'trophies' && <TrophiesScene trophies={summary.trophies} />}
        {activeScene === 'champion' && summary.champion && (
          <ChampionScene champion={summary.champion} celebrating={celebrating} />
        )}
        {activeScene === 'idle' && (
          <div className="font-mono-label text-muted-foreground kiosk-pulse">{t('kiosk.idle')}</div>
        )}
      </div>

      <SceneDots count={scenes.length} active={celebrating ? scenes.indexOf('champion') : sceneIndex} />

      {drop && dropItem && (
        <LiveDrop key={dropItem.id} item={dropItem} more={drop.more} serverTime={summary.server_time} />
      )}
      {ceremony && <TrophyCeremony key={ceremony.trophy.edition_id} trophy={ceremony.trophy} />}
      {flashing && <AnnouncementFlash message={flashing.message} level={flashing.level} />}
    </KioskShell>
  )
}

// ── Countdown helper (reads refs live each render) ────────────────────────────
function liveCountdown(polledAt: React.MutableRefObject<number>, atPoll: React.MutableRefObject<number | null>): number | null {
  if (atPoll.current === null) return null
  return atPoll.current - (Date.now() - polledAt.current)
}

// ── Chrome ────────────────────────────────────────────────────────────────────
function KioskShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 bg-background text-foreground flex flex-col overflow-hidden">
      {children}
    </div>
  )
}

function KioskHeader({ summary, live }: { summary: KioskSummary; live: number }) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center justify-between px-[4vw] pt-[3vh] shrink-0">
      <div className="font-mono-label text-accent text-[1.4vw] tracking-widest">
        {summary.event ? summary.event.title : t('kiosk.title')}
      </div>
      <div className="flex items-center gap-[2vw] font-mono-label text-[1.2vw]">
        <span className="flex items-center gap-2">
          <span className="w-[0.9vw] h-[0.9vw] bg-green-400 rounded-full kiosk-pulse" />
          {t('kiosk.online', { count: live })}
        </span>
        {summary.event && (
          <span className="text-muted-foreground">
            {t('kiosk.attending', { count: summary.arrivals.expected })}
          </span>
        )}
      </div>
    </div>
  )
}

function SceneDots({ count, active }: { count: number; active: number }) {
  if (count <= 1) return null
  return (
    <div className="flex items-center justify-center gap-3 pb-[3vh] shrink-0">
      {Array.from({ length: count }).map((_, i) => (
        <span
          key={i}
          className={`h-[0.5vh] transition-all duration-500 ${i === active ? 'w-[3vw] bg-accent' : 'w-[1vw] bg-border'}`}
        />
      ))}
    </div>
  )
}

// ── Scenes ──────────────────────────────────────────────────────────────────
function Countdown({ ms }: { ms: number }) {
  const clamped = Math.max(0, ms)
  const s = Math.floor(clamped / 1000)
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  const big = d > 0 ? `${d}d ${pad(h)}:${pad(m)}:${pad(sec)}` : `${pad(h)}:${pad(m)}:${pad(sec)}`
  return <div className="font-mono-label text-accent text-[8vw] leading-none tracking-tight tabular-nums">{big}</div>
}

function HeroScene({ summary, countdownMs }: { summary: KioskSummary; countdownMs: number | null }) {
  const { t } = useTranslation()
  return (
    <div className="text-center">
      {summary.countdown ? (
        <>
          <div className="font-mono-label text-muted-foreground text-[1.6vw] mb-[2vh] tracking-widest">
            {t('kiosk.countingDownTo')}
          </div>
          <h1 className="text-[6vw] font-black tracking-tighter leading-none mb-[4vh]">
            {summary.countdown.label}
          </h1>
          {countdownMs !== null && <Countdown ms={countdownMs} />}
        </>
      ) : (
        <>
          <h1 className="text-[7vw] font-black tracking-tighter leading-none">
            {summary.event?.title ?? t('kiosk.title')}
          </h1>
          {summary.event?.location && (
            <div className="font-mono-label text-muted-foreground text-[1.6vw] mt-[3vh]">
              {summary.event.location}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function TeamChip({ name, color, score, dim }: { name: string | null; color: string | null; score: number; dim?: boolean }) {
  const { t } = useTranslation()
  return (
    <div className={`flex-1 flex flex-col items-center gap-[2vh] ${dim ? 'opacity-60' : ''}`}>
      <span className="w-[3vw] h-[3vw]" style={{ backgroundColor: color || '#262626' }} />
      <span className="text-[2.6vw] font-black tracking-tight text-center leading-none">
        {name || t('kiosk.tbd')}
      </span>
      <span className="text-[6vw] font-black tabular-nums leading-none">{score}</span>
    </div>
  )
}

function MatchesScene({ matches }: { matches: KioskMatch[] }) {
  const { t } = useTranslation()
  const feature = matches[0]
  const rest = matches.slice(1, 5)
  return (
    <div className="w-full max-w-[80vw]">
      <div className="font-mono-label text-accent text-[1.4vw] mb-[3vh] tracking-widest">
        {feature.status === 'in_progress' ? t('kiosk.nowPlaying') : t('kiosk.upNextMatch')}
        <span className="text-muted-foreground ml-4">
          {feature.tournament} · {t(`roundLabels.${feature.round}`, feature.round)}
        </span>
      </div>
      <div className="flex items-center gap-[4vw] mb-[5vh]">
        <TeamChip {...feature.team_a} />
        <span className="text-[3vw] font-black text-muted-foreground">{t('kiosk.vs')}</span>
        <TeamChip {...feature.team_b} />
      </div>
      {rest.length > 0 && (
        <div className="border-t border-border pt-[2vh] space-y-[1.4vh]">
          {rest.map((m, i) => (
            <div key={i} className="flex items-center justify-between text-[1.4vw]">
              <span className="font-mono-label text-muted-foreground">
                {m.tournament} · {t(`roundLabels.${m.round}`, m.round)}
              </span>
              <span className="font-black">
                {m.team_a.name || t('kiosk.tbd')} <span className="text-muted-foreground mx-3">{t('kiosk.vs')}</span> {m.team_b.name || t('kiosk.tbd')}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function StandingsScene({ standings }: { standings: KioskStanding[] }) {
  const { t } = useTranslation()
  return (
    <div className="w-full max-w-[70vw]">
      <div className="font-mono-label text-accent text-[1.4vw] mb-[3vh] tracking-widest">{t('kiosk.standings')}</div>
      <div className="space-y-[1.2vh]">
        {standings.map((s) => (
          <div key={s.rank} className="flex items-center gap-[2vw] text-[2vw]">
            <span className="font-mono-label text-muted-foreground w-[3vw] tabular-nums">{s.rank}</span>
            <span className="w-[1.6vw] h-[1.6vw] shrink-0" style={{ backgroundColor: s.color || '#262626' }} />
            <span className="flex-1 font-black truncate">{s.team_name}</span>
            <span className="font-mono-label text-muted-foreground text-[1.3vw] tabular-nums">
              {s.wins}{t('kiosk.winShort')} · {s.losses}{t('kiosk.lossShort')}{s.draws ? ` · ${s.draws}${t('kiosk.drawShort')}` : ''}
            </span>
            <span className="font-black text-accent w-[5vw] text-right tabular-nums">{s.points}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function ArrivalsScene({ summary }: { summary: KioskSummary }) {
  const { t } = useTranslation()
  return (
    <div className="w-full max-w-[80vw] text-center">
      <div className="font-mono-label text-accent text-[1.4vw] mb-[1vh] tracking-widest">{t('kiosk.whosHere')}</div>
      <div className="text-[2.4vw] font-black mb-[4vh]">
        {t('kiosk.onlineOfExpected', { online: summary.arrivals.online, total: summary.arrivals.expected })}
      </div>
      <div className="flex flex-wrap justify-center gap-[1.6vw]">
        {summary.arrivals.attendees.map((a) => (
          <div key={a.username} className={`flex flex-col items-center gap-[0.8vh] ${a.online ? '' : 'opacity-40'}`}>
            <div className="relative">
              {a.avatar_url ? (
                <img src={a.avatar_url} alt="" className="w-[5vw] h-[5vw] object-cover" />
              ) : (
                <div className="w-[5vw] h-[5vw] bg-muted flex items-center justify-center font-black text-[2vw]">
                  {a.username.charAt(0).toUpperCase()}
                </div>
              )}
              {a.online && <span className="absolute -bottom-1 -right-1 w-[1.2vw] h-[1.2vw] bg-green-400 border-2 border-background rounded-full" />}
            </div>
            <span className="font-mono-label text-[1vw] truncate max-w-[6vw]">{a.username}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function UpNextScene({ summary }: { summary: KioskSummary }) {
  const { t } = useTranslation()
  return (
    <div className="w-full max-w-[70vw]">
      <div className="font-mono-label text-accent text-[1.4vw] mb-[3vh] tracking-widest">{t('kiosk.scheduled')}</div>
      <div className="space-y-[2vh]">
        {summary.up_next.map((b, i) => (
          <div key={i} className="flex items-baseline gap-[2vw] border-b border-border pb-[1.6vh]">
            <span className="font-mono-label text-accent text-[2vw] tabular-nums">{hhmm(b.locked_start)}</span>
            <span className="text-[2.6vw] font-black flex-1 truncate">{b.game}</span>
            <span className="font-mono-label text-muted-foreground text-[1.3vw] tabular-nums">
              {hhmm(b.locked_start)}–{hhmm(b.locked_end)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function GearScene({ gear }: { gear: NonNullable<KioskSummary['gear']> }) {
  const { t } = useTranslation()
  return (
    <div className="w-full max-w-[80vw]">
      <div className="font-mono-label text-accent text-[1.4vw] mb-[3vh] tracking-widest">{t('kiosk.gearHeading')}</div>
      <div className="flex flex-wrap gap-[1.2vw] mb-[4vh]">
        {gear.bringing.map((g, i) => (
          <div key={i} className="border border-border px-[1.4vw] py-[1.2vh]">
            <div className="text-[1.8vw] font-black leading-none">{g.name}</div>
            {g.by && <div className="font-mono-label text-muted-foreground text-[1vw] mt-[0.6vh]">{g.by}</div>}
          </div>
        ))}
      </div>
      {gear.needs.length > 0 && (
        <div>
          <div className="font-mono-label text-accent text-[1.2vw] mb-[1.5vh] tracking-widest kiosk-pulse">{t('kiosk.gearStillNeeded')}</div>
          <div className="text-[2.4vw] font-black leading-tight">{gear.needs.join(' · ')}</div>
        </div>
      )}
    </div>
  )
}

// "Join the LAN": guest WiFi + the app + straight to the photo upload. Each QR
// is sized off the viewport so it stays scannable from a few metres away, and
// the WiFi credentials are also printed large — laptops can't scan a QR.
function JoinScene({ summary }: { summary: KioskSummary }) {
  const { t } = useTranslation()
  const base = summary.join_url || window.location.origin
  const blocks: { key: string; value: string; label: string; detail?: React.ReactNode }[] = []
  if (summary.wifi) {
    blocks.push({
      key: 'wifi',
      value: wifiQrPayload(summary.wifi),
      label: `📶 ${t('kiosk.joinWifi')}`,
      detail: (
        <>
          <div className="text-[2.4vw] font-black leading-tight break-all">{summary.wifi.ssid}</div>
          <div className="font-mono text-[1.8vw] text-accent mt-[1vh] break-all">
            {summary.wifi.password
              ? <><span className="font-mono-label text-muted-foreground text-[1vw] mr-3">{t('kiosk.joinPassword')}</span>{summary.wifi.password}</>
              : <span className="font-mono-label text-muted-foreground text-[1.2vw]">{t('kiosk.joinOpenNetwork')}</span>}
          </div>
        </>
      ),
    })
  }
  blocks.push({ key: 'app', value: base, label: `📱 ${t('kiosk.joinApp')}` })
  blocks.push({ key: 'photo', value: `${base}/media`, label: `📸 ${t('kiosk.joinPhoto')}` })

  return (
    <div className="w-full">
      <div className="font-mono-label text-accent text-[1.4vw] mb-[5vh] tracking-widest text-center">{t('kiosk.joinTitle')}</div>
      <div className="flex items-start justify-center gap-[5vw]">
        {blocks.map((b) => (
          <div key={b.key} className="flex flex-col items-center text-center max-w-[26vw]">
            <div className="bg-white p-[1.2vh]" style={{ width: 'min(30vh, 22vw)' }}>
              <QRCode value={b.value} size={256} style={{ width: '100%', height: 'auto' }} viewBox="0 0 256 256" />
            </div>
            <div className="font-mono-label text-[1.4vw] mt-[2.5vh] mb-[1vh]">{b.label}</div>
            {b.detail}
          </div>
        ))}
      </div>
    </div>
  )
}

function ChampionScene({ champion, celebrating }: { champion: KioskChampion; celebrating: boolean }) {
  const { t } = useTranslation()
  return (
    <div className="text-center relative w-full h-full flex flex-col items-center justify-center">
      <Confetti run={celebrating} />
      <div className="text-[8vw] leading-none mb-[2vh]">🏆</div>
      <div className="font-mono-label text-accent text-[1.6vw] mb-[2vh] tracking-widest">{t('kiosk.champion')}</div>
      <div className="flex items-center justify-center gap-[1.5vw] mb-[2vh]">
        <span className="w-[2.6vw] h-[2.6vw]" style={{ backgroundColor: champion.color || '#FF3D00' }} />
        <h1 className="text-[6vw] font-black tracking-tighter leading-none">{champion.team_name}</h1>
      </div>
      {champion.members.length > 0 && (
        <div className="font-mono-label text-muted-foreground text-[1.6vw]">{champion.members.join(' · ')}</div>
      )}
      <div className="font-mono-label text-muted-foreground text-[1.2vw] mt-[3vh]">{champion.game_name}</div>
    </div>
  )
}

// The LAN's roll of honour so far — every revealed trophy and its winner(s).
function TrophiesScene({ trophies }: { trophies: KioskTrophy[] }) {
  const { t } = useTranslation()
  return (
    <div className="w-full max-w-[80vw]">
      <div className="font-mono-label text-accent text-[1.4vw] mb-[4vh] tracking-widest">{t('kiosk.trophiesHeading')}</div>
      <div className="grid grid-cols-2 gap-x-[4vw] gap-y-[3vh]">
        {trophies.map((tr) => (
          <div key={tr.edition_id} className="flex items-center gap-[1.5vw]">
            <TrophyIcon trophy={tr} className="w-[5vw] h-[5vw] text-[4vw]" />
            <div className="min-w-0">
              <div className="font-mono-label text-muted-foreground text-[1.1vw] truncate">{tr.name}</div>
              <div className="text-[2.4vw] font-black leading-tight truncate">
                {tr.winners.map((w) => w.username).join(' · ')}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// Full-screen reveal: the trophy's name first, a beat of suspense, then the
// winner(s) with confetti and the fanfare. Keyed by edition id, so each queued
// trophy starts from the suspense phase.
function TrophyCeremony({ trophy }: { trophy: KioskTrophy }) {
  const { t } = useTranslation()
  const [revealed, setRevealed] = useState(false)

  useEffect(() => {
    playAnnouncementChime()
    const id = setTimeout(() => {
      setRevealed(true)
      playChampionFanfare()
    }, SUSPENSE_MS)
    return () => clearTimeout(id)
  }, [])

  return (
    <div className="kiosk-flash fixed inset-0 z-40 bg-background flex flex-col items-center justify-center px-[6vw] text-center">
      <Confetti run={revealed} />
      <TrophyIcon trophy={trophy} className="w-[12vw] h-[12vw] text-[10vw] mb-[3vh]" />
      <div className="font-mono-label text-accent text-[1.6vw] tracking-widest mb-[1.5vh]">{t('kiosk.trophyAwardedTo')}</div>
      <h1 className="text-[5vw] font-black tracking-tighter leading-none mb-[5vh]">{trophy.name}</h1>
      {!revealed ? (
        <div className="text-[6vw] leading-none kiosk-pulse" aria-hidden="true">🥁</div>
      ) : (
        <div className="kiosk-scene flex flex-wrap items-start justify-center gap-[4vw]">
          {trophy.winners.map((w) => (
            <div key={w.username} className="flex flex-col items-center max-w-[40vw]">
              {w.avatar_url ? (
                <img src={w.avatar_url} alt="" className="w-[9vw] h-[9vw] object-cover mb-[2vh]" />
              ) : (
                <div className="w-[9vw] h-[9vw] bg-muted flex items-center justify-center font-black text-[4vw] mb-[2vh]">
                  {w.username.charAt(0).toUpperCase()}
                </div>
              )}
              <div className="text-[5vw] font-black tracking-tighter leading-none text-accent">{w.username}</div>
              {w.citation && (
                <div className="text-[1.6vw] text-muted-foreground italic mt-[2vh]">« {w.citation} »</div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function AnnouncementFlash({ message, level }: { message: string; level: string }) {
  const { t } = useTranslation()
  const alert = level === 'alert'
  return (
    <div
      className={`kiosk-flash fixed inset-0 z-50 flex flex-col items-center justify-center px-[8vw] ${alert ? 'bg-accent text-accent-foreground' : 'bg-foreground text-background'}`}
    >
      <div className="font-mono-label text-[1.6vw] mb-[3vh] tracking-widest opacity-70">
        {alert ? t('kiosk.alert') : t('kiosk.announcement')}
      </div>
      <div className="text-[5vw] font-black tracking-tighter text-center leading-tight">{message}</div>
    </div>
  )
}
