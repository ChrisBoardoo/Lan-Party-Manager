import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { recapApi } from '../lib/api'
import type { Recap } from '../types'
import { useAuth } from '../contexts/AuthContext'
import { useNoindex } from '../hooks/useNoindex'
import { formatDate } from '../lib/formatDate'
import BadgeList from '../components/BadgeList'
import TrophyIcon from '../components/trophies/TrophyIcon'
import Lightbox from '../components/ui/Lightbox'
import Button from '../components/ui/Button'
import QRModal from '../components/ui/QRModal'
import { Trophy, Users, Moon, Camera, Wallet, Link2, Copy, Check, QrCode, Trash2 } from 'lucide-react'

// ── Pieces ────────────────────────────────────────────────────────────────────

function Stat({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub?: string }) {
  return (
    <div className="border border-border bg-card p-5">
      <p className="font-mono-label text-muted-foreground flex items-center gap-1.5 mb-2">
        {icon} {label}
      </p>
      <p className="text-3xl font-black tracking-tighter text-foreground leading-none">{value}</p>
      {sub && <p className="font-mono-label text-muted-foreground text-[10px] mt-1.5">{sub}</p>}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-10">
      <p className="font-mono-label text-accent mb-4">{title}</p>
      {children}
    </section>
  )
}

/** The recap itself. Identical for the authenticated and shared views — the
 *  shared one simply arrives with `money: null`. */
export function RecapView({ recap }: { recap: Recap }) {
  const { t } = useTranslation()
  const [viewerIndex, setViewerIndex] = useState<number | null>(null)

  const { event, attendance, media, money } = recap

  return (
    <>
      {event.cover_image_url && (
        <div className="border border-border bg-card mb-8 overflow-hidden">
          <img src={event.cover_image_url} alt={event.title} className="w-full max-h-64 object-cover" />
        </div>
      )}

      <div className="mb-12">
        <div className="font-mono-label text-accent mb-3">{t('recap.tagline')}</div>
        <h1 className="text-5xl lg:text-6xl font-black tracking-tighter text-foreground leading-none mb-3">
          {event.title}
        </h1>
        <p className="font-mono-label text-muted-foreground">
          {formatDate(event.start_date)} — {formatDate(event.end_date)}
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
        <Stat
          icon={<Moon size={12} strokeWidth={1.5} />}
          label={t('recap.nights')}
          value={String(event.nights)}
          sub={t('recap.personNights', { count: attendance.total_person_nights })}
        />
        <Stat
          icon={<Users size={12} strokeWidth={1.5} />}
          label={t('recap.attendees')}
          value={String(attendance.attendee_count)}
          sub={t('recap.longestStay', { count: attendance.longest_stay })}
        />
        <Stat
          icon={<Camera size={12} strokeWidth={1.5} />}
          label={t('recap.media')}
          value={String(media.total)}
          sub={t('recap.mediaBreakdown', { photos: media.photo_count, videos: media.video_count })}
        />
        {money ? (
          <Stat
            icon={<Wallet size={12} strokeWidth={1.5} />}
            label={t('recap.moneyMoved')}
            value={`${money.total_expenses.toFixed(2)}${money.currency}`}
            sub={t('recap.settledLines', { settled: money.settled_lines, total: money.total_lines })}
          />
        ) : (
          <Stat
            icon={<Trophy size={12} strokeWidth={1.5} />}
            label={t('recap.brackets')}
            value={String(recap.tournaments.length)}
          />
        )}
      </div>

      {recap.mvp && (
        <Section title={t('recap.mvpTitle')}>
          <div className="border border-accent bg-accent/5 p-6 flex items-center gap-4">
            {recap.mvp.avatar_url ? (
              <img src={recap.mvp.avatar_url} alt="" className="w-16 h-16 object-cover border border-border" />
            ) : (
              <div className="w-16 h-16 bg-muted flex items-center justify-center font-black text-2xl text-muted-foreground">
                {recap.mvp.username.charAt(0).toUpperCase()}
              </div>
            )}
            <div>
              <p className="text-2xl font-black tracking-tighter text-foreground">{recap.mvp.username}</p>
              <p className="font-mono-label text-accent">
                {t('recap.mvpWins', { count: recap.mvp.wins })}
              </p>
            </div>
          </div>
        </Section>
      )}

      {recap.tournaments.length > 0 && (
        <Section title={t('recap.tournamentsTitle')}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {recap.tournaments.map((tournament) => (
              <div key={tournament.tournament_id} className="border border-border bg-card p-4">
                <p className="font-mono-label text-foreground mb-1">{tournament.game_name}</p>
                <p className="font-mono-label text-muted-foreground text-[10px] mb-3">
                  {t('recap.matchesPlayed', { count: tournament.match_count })}
                </p>
                {tournament.champion ? (
                  <div className="flex items-center gap-2">
                    {tournament.champion.color && (
                      <span
                        className="w-3 h-3 shrink-0 border border-border"
                        style={{ backgroundColor: tournament.champion.color }}
                      />
                    )}
                    <div className="min-w-0">
                      <p className="text-foreground font-bold truncate">🏆 {tournament.champion.team_name}</p>
                      {tournament.champion.members.length > 0 && (
                        <p className="text-xs text-muted-foreground truncate">
                          {tournament.champion.members.join(' · ')}
                        </p>
                      )}
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">{t('recap.noChampion')}</p>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {recap.trophies.length > 0 && (
        <Section title={t('trophies.recapTitle')}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {recap.trophies.map((tr) => (
              <div key={tr.trophy.id} className="border border-border bg-card p-4 flex items-start gap-3">
                <TrophyIcon trophy={tr.trophy} className="w-12 h-12 text-4xl" />
                <div className="min-w-0">
                  <p className="font-black text-foreground leading-tight">{tr.trophy.name}</p>
                  {tr.winners.map((w) => (
                    <div key={w.user_id} className="mt-1">
                      <p className="font-mono-label text-accent">{w.username}</p>
                      {w.citation && <p className="text-xs text-muted-foreground italic">« {w.citation} »</p>}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {recap.badges.length > 0 && (
        <Section title={t('recap.badgesTitle')}>
          <BadgeList badges={recap.badges} showWinner />
        </Section>
      )}

      {media.top.length > 0 && (
        <Section title={t('recap.bestOfTitle')}>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {media.top.map((item, i) => (
              <button
                key={item.id}
                onClick={() => setViewerIndex(i)}
                className="relative aspect-square overflow-hidden border border-border bg-card group"
              >
                <img
                  src={item.thumbnail_url || item.url}
                  alt={item.caption || item.original_name}
                  className="w-full h-full object-cover group-hover:opacity-80 transition-opacity"
                />
                <span className="absolute bottom-1.5 left-1.5 flex items-center gap-1 bg-background/80 border border-border px-1.5 py-0.5">
                  {item.reactions.slice(0, 3).map((r) => (
                    <span key={r.emoji} className="text-[10px] leading-none">{r.emoji}</span>
                  ))}
                  <span className="font-mono text-[10px] text-muted-foreground leading-none">
                    {item.reaction_total}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </Section>
      )}

      {media.total === 0 && (
        <p className="font-mono-label text-muted-foreground text-sm border border-border bg-card p-5">
          {t('recap.noMediaHint')}
        </p>
      )}

      {/* Read-only: no onItemUpdated, so no reacting or editing from a recap. */}
      {viewerIndex !== null && (
        <Lightbox items={media.top} index={viewerIndex} onClose={() => setViewerIndex(null)} />
      )}
    </>
  )
}

// ── Admin share controls ──────────────────────────────────────────────────────

function ShareControls({ eventId }: { eventId: number }) {
  const { t } = useTranslation()
  const [token, setToken] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [showQR, setShowQR] = useState(false)

  useEffect(() => {
    // Own effect, own catch: a 404 here (feature off) must never take the page.
    recapApi.getShare(eventId).then((s) => setToken(s.token)).catch(() => setToken(null))
  }, [eventId])

  // Token in the fragment, out of access logs and Referer headers.
  const url = token ? `${window.location.origin}/recap/shared#token=${encodeURIComponent(token)}` : null

  const run = async (fn: () => Promise<{ token: string | null }>) => {
    setBusy(true)
    try {
      setToken((await fn()).token)
    } finally {
      setBusy(false)
    }
  }

  const copy = async () => {
    if (!url) return
    await navigator.clipboard.writeText(url)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="border border-border bg-card p-6 mt-10">
      <p className="font-mono-label text-accent flex items-center gap-1.5 mb-2">
        <Link2 size={12} strokeWidth={1.5} /> {t('recap.shareTitle')}
      </p>
      <p className="text-sm text-muted-foreground mb-4">{t('recap.shareDesc')}</p>

      {url ? (
        <>
          <div className="flex items-center gap-2 mb-3">
            <code className="flex-1 bg-input border border-border px-3 py-2 text-xs text-muted-foreground truncate">
              {url}
            </code>
            <button
              onClick={copy}
              aria-label={t('recap.shareCopy')}
              className="p-2 border border-border text-muted-foreground hover:text-accent hover:border-accent transition-colors"
            >
              {copied ? <Check size={14} strokeWidth={1.5} /> : <Copy size={14} strokeWidth={1.5} />}
            </button>
            <button
              onClick={() => setShowQR(true)}
              aria-label={t('recap.shareQR')}
              className="p-2 border border-border text-muted-foreground hover:text-accent hover:border-accent transition-colors"
            >
              <QrCode size={14} strokeWidth={1.5} />
            </button>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => run(() => recapApi.mintShare(eventId))} disabled={busy}>
              {t('recap.shareRotate')}
            </Button>
            <Button variant="danger" onClick={() => run(() => recapApi.revokeShare(eventId))} disabled={busy}>
              <Trash2 size={14} strokeWidth={2} />
              {t('recap.shareRevoke')}
            </Button>
          </div>
        </>
      ) : (
        <Button onClick={() => run(() => recapApi.mintShare(eventId))} disabled={busy}>
          {t('recap.shareCreate')}
        </Button>
      )}

      {showQR && url && (
        <QRModal value={url} label={t('recap.shareTitle')} onClose={() => setShowQR(false)} />
      )}
    </div>
  )
}

// ── Routes ────────────────────────────────────────────────────────────────────

function Shell({ children }: { children: React.ReactNode }) {
  return <main className="max-w-5xl mx-auto px-6 py-12">{children}</main>
}

function NotFound() {
  const { t } = useTranslation()
  return (
    <Shell>
      <p className="font-mono-label text-muted-foreground">{t('recap.notFound')}</p>
    </Shell>
  )
}

function LoadingSkeleton() {
  return (
    <Shell>
      <div className="h-12 w-2/3 bg-muted animate-pulse mb-8" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-28 bg-muted animate-pulse" />
        ))}
      </div>
    </Shell>
  )
}

/** The authenticated recap, at /events/:eventId/recap. */
export default function RecapPage() {
  const { eventId } = useParams<{ eventId: string }>()
  const { user } = useAuth()
  const [recap, setRecap] = useState<Recap | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      // try/catch/finally: a bad id must reach the not-found state below rather
      // than spin on the skeleton forever.
      try {
        setRecap(await recapApi.get(Number(eventId)))
      } catch {
        setRecap(null)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [eventId])

  if (loading) return <LoadingSkeleton />
  if (!recap) return <NotFound />

  return (
    <Shell>
      <RecapView recap={recap} />
      {user?.role === 'admin' && <ShareControls eventId={recap.event.id} />}
    </Shell>
  )
}

/** The public, token-authorized recap at /recap/shared#token=… — no login, and
 *  no Navbar/Layout, exactly like the kiosk. Its payload never carries money. */
export function SharedRecapPage() {
  const [params] = useSearchParams()
  // #token= since 1.3.4; ?token= for links shared before.
  const token = new URLSearchParams(window.location.hash.slice(1)).get('token') ?? params.get('token')
  const [recap, setRecap] = useState<Recap | null>(null)
  const [loading, setLoading] = useState(true)

  // A public URL with the crew's photos on it shouldn't be search-indexed.
  useNoindex()

  useEffect(() => {
    const load = async () => {
      if (!token) {
        setLoading(false)
        return
      }
      try {
        setRecap(await recapApi.getShared(token))
      } catch {
        setRecap(null)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [token])

  if (loading) return <div className="min-h-screen bg-background"><LoadingSkeleton /></div>
  if (!recap) return <div className="min-h-screen bg-background"><NotFound /></div>

  return (
    <div className="min-h-screen bg-background">
      <Shell>
        <RecapView recap={recap} />
      </Shell>
    </div>
  )
}
