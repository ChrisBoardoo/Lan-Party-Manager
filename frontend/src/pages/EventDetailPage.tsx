import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import { useAppConfig } from '../contexts/AppConfigContext'
import { eventsApi, mediaApi, tournamentsApi, expensesApi, settingsApi, usersApi, prizesApi } from '../lib/api'
import { LanEvent, MediaItem, Tournament, Expense, Prize } from '../types'
import { formatDate } from '../lib/formatDate'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import EventCountdown from '../components/ui/EventCountdown'
import ExternalLink from '../components/ui/ExternalLink'
import AttendeeRoster from '../components/AttendeeRoster'
import Lightbox from '../components/ui/Lightbox'
import CreateTournamentModal from '../components/CreateTournamentModal'
import SponsorStrip from '../components/SponsorStrip'
import SponsorsAdminCard from '../components/SponsorsAdminCard'
import PrizeGrid from '../components/PrizeGrid'
import GearSection from '../components/GearSection'
import GroceriesSection from '../components/GroceriesSection'
import ChecklistSection from '../components/ChecklistSection'
import WifiCard from '../components/WifiCard'
import EventTrophiesSection from '../components/trophies/EventTrophiesSection'
import {
  ArrowLeft, CalendarDays, MapPin, Clock, ImagePlus, Trophy, DollarSign,
  Plus, Play, MessageCircle, Gift, Package, ShoppingCart, Sparkles, ChevronRight, ListChecks,
} from 'lucide-react'

function isUpcoming(end: string) {
  return new Date(end) >= new Date(new Date().toDateString())
}

const CATEGORY_COLORS: Record<string, string> = {
  food: 'warning',
  drinks: 'accent',
  equipment: 'default',
  accommodation: 'success',
  transport: 'muted',
  games: 'danger',
  prizes: 'accent',
  general: 'muted',
}

export default function EventDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { currency, treasuryEnabled, prizesEnabled, gearEnabled, groceriesEnabled, recapEnabled, sponsorsEnabled, checklistEnabled, trophiesEnabled } = useAppConfig()
  const { t } = useTranslation()
  const eventId = Number(id)
  const isAdmin = user?.role === 'admin'
  const canCreateTournament = user?.is_tournament_organizer || user?.role === 'admin' || user?.role === 'treasurer'

  const [event, setEvent] = useState<LanEvent | null>(null)
  const [media, setMedia] = useState<MediaItem[]>([])
  const [tournaments, setTournaments] = useState<Tournament[]>([])
  const [expenses, setExpenses] = useState<Expense[]>([])
  const [prizes, setPrizes] = useState<Prize[]>([])
  const [discordInvite, setDiscordInvite] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [viewer, setViewer] = useState<{ items: MediaItem[]; index: number } | null>(null)
  const [showTournamentModal, setShowTournamentModal] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  // Only the event itself decides "not found". The side panels are optional:
  // a feature-gated endpoint answers 404 to non-admins when its feature is off
  // (require_feature), so folding them into one Promise.all would let a hidden
  // Treasury report the whole event as missing.
  const load = () => {
    eventsApi.get(eventId)
      .then(setEvent)
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false))

    mediaApi.getAll(eventId).then(setMedia).catch(() => setMedia([]))
    tournamentsApi.getAll(eventId).then(setTournaments).catch(() => setTournaments([]))
    settingsApi.getDiscordInvite().then((d) => setDiscordInvite(d.discord_invite_url)).catch(() => {})
  }

  useEffect(() => { load() }, [eventId])

  useEffect(() => {
    if (!prizesEnabled) { setPrizes([]); return }
    prizesApi.getForEvent(eventId).then(setPrizes).catch(() => {})
  }, [eventId, prizesEnabled])

  useEffect(() => {
    if (!treasuryEnabled) { setExpenses([]); return }
    expensesApi.getAll(eventId).then(setExpenses).catch(() => setExpenses([]))
  }, [eventId, treasuryEnabled])

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      await mediaApi.upload(file, undefined, eventId)
      load()
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  // Keeps the gallery grid and the open lightbox in step after a reaction or
  // caption edit — same shape as Media.tsx.
  const handleItemUpdated = (updated: MediaItem) => {
    const swap = (i: MediaItem) => (i.id === updated.id ? updated : i)
    setMedia((prev) => prev.map(swap))
    setViewer((v) => (v ? { ...v, items: v.items.map(swap) } : v))
  }

  const handleDeactivateAttendee = async (userId: number, username: string) => {
    if (!confirm(t('players.deactivateConfirm', { username }))) return
    await usersApi.deactivate(userId)
    load()
  }

  const totalExpenses = expenses.reduce((sum, ex) => sum + ex.amount, 0)

  if (loading) {
    return (
      <main className="max-w-4xl mx-auto px-6 py-12">
        <div className="h-64 bg-muted animate-pulse" />
      </main>
    )
  }

  if (notFound || !event) {
    return (
      <main className="max-w-4xl mx-auto px-6 py-12 text-center">
        <p className="font-mono-label text-muted-foreground">{t('eventDetail.notFound')}</p>
      </main>
    )
  }

  const upcoming = isUpcoming(event.end_date)

  return (
    <main className="max-w-4xl mx-auto px-6 py-12">
      <button
        onClick={() => navigate('/events')}
        className="flex items-center gap-2 font-mono-label text-muted-foreground hover:text-foreground transition-colors mb-8"
      >
        <ArrowLeft size={12} /> {t('common.back')}
      </button>

      {/* Recap */}
      <div className="border border-border bg-card mb-6">
        {event.cover_image_url && (
          <div className="w-full h-48 sm:h-64 overflow-hidden border-b border-border">
            <img src={event.cover_image_url} alt={event.title} className="w-full h-full object-cover" />
          </div>
        )}
        <div className="p-6">
          <div className="flex items-center gap-2 flex-wrap mb-3">
            <Badge variant={upcoming ? 'accent' : 'muted'}>
              {upcoming ? t('events.card.upcoming') : t('events.card.past')}
            </Badge>
            {upcoming && <EventCountdown startDate={event.start_date} />}
          </div>
          <h1 className="text-3xl sm:text-4xl font-black tracking-tight text-foreground mb-4">{event.title}</h1>
          <div className="flex flex-wrap items-center gap-4 mb-3">
            <div className="flex items-center gap-2">
              <Clock size={12} strokeWidth={1.5} className="text-muted-foreground" />
              <span className="font-mono-label text-foreground">
                {formatDate(event.start_date)}
                {event.start_date !== event.end_date && <> → {formatDate(event.end_date)}</>}
              </span>
            </div>
            {event.location && (
              <div className="flex items-center gap-2">
                <MapPin size={12} strokeWidth={1.5} className="text-muted-foreground" />
                <span className="font-mono-label text-muted-foreground">{event.location}</span>
              </div>
            )}
          </div>
          {event.description && (
            <p className="text-sm text-muted-foreground leading-relaxed border-t border-border pt-3 mt-3">
              {event.description}
            </p>
          )}
          {discordInvite && (
            <ExternalLink
              href={discordInvite}
              className="inline-flex items-center gap-2 font-mono-label text-accent hover:text-accent/80 transition-colors mt-4"
            >
              <MessageCircle size={12} strokeWidth={1.5} /> {t('eventDetail.joinDiscord')}
            </ExternalLink>
          )}
        </div>
      </div>

      {/* Guest WiFi — only for the current event's attendees (and admins) */}
      {(event.my_rsvp === 'in' || isAdmin) && upcoming && <WifiCard eventId={eventId} />}

      {/* Attendees */}
      <div className="border border-border bg-card p-6 mb-6">
        <p className="font-mono-label text-accent mb-1">{t('eventDetail.attendeesTitle')}</p>
        <AttendeeRoster
          event={event}
          isAdmin={isAdmin}
          currentUserId={user?.id}
          onDeactivate={handleDeactivateAttendee}
          defaultExpanded
        />
      </div>

      {/* Media */}
      <div className="border border-border bg-card p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <p className="font-mono-label text-accent">{t('eventDetail.mediaTitle')}</p>
          <input ref={fileRef} type="file" accept="image/*,video/*" className="hidden" onChange={handleUpload} />
          <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} disabled={uploading}>
            <ImagePlus size={12} /> {uploading ? t('eventDetail.uploading') : t('eventDetail.addMedia')}
          </Button>
        </div>
        {media.length === 0 ? (
          <p className="font-mono-label text-muted-foreground text-xs">{t('eventDetail.noMediaYet')}</p>
        ) : (
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-1">
            {media.map((item, i) => (
              <button
                key={item.id}
                onClick={() => setViewer({ items: media, index: i })}
                className="aspect-square border border-border bg-muted overflow-hidden group relative"
              >
                {item.file_type === 'image' ? (
                  <img src={item.url} alt={item.original_name} className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" />
                ) : item.thumbnail_url ? (
                  <img src={item.thumbnail_url} alt={item.original_name} className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <Play size={14} strokeWidth={1.5} className="text-muted-foreground" />
                  </div>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Tournaments */}
      <div className="border border-border bg-card p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <p className="font-mono-label text-accent flex items-center gap-1.5">
            <Trophy size={12} strokeWidth={1.5} /> {t('eventDetail.tournamentsTitle')}
          </p>
          {canCreateTournament && (
            <Button size="sm" variant="outline" onClick={() => setShowTournamentModal(true)}>
              <Plus size={12} /> {t('eventDetail.addTournament')}
            </Button>
          )}
        </div>
        {tournaments.length === 0 ? (
          <p className="font-mono-label text-muted-foreground text-xs">{t('eventDetail.noTournamentsYet')}</p>
        ) : (
          <div className="space-y-2">
            {tournaments.map((tour) => (
              <Link
                key={tour.id}
                to="/tournaments"
                className="flex items-center justify-between px-4 py-3 border border-border hover:border-accent transition-colors"
              >
                <span className="text-sm font-semibold text-foreground">{tour.game_name}</span>
                <Badge variant="muted">{t(`roundLabels.${tour.status}`, tour.status)}</Badge>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Expenses */}
      {treasuryEnabled && (
      <div className="border border-border bg-card p-6">
        <div className="flex items-center justify-between mb-4">
          <p className="font-mono-label text-accent flex items-center gap-1.5">
            <DollarSign size={12} strokeWidth={1.5} /> {t('eventDetail.expensesTitle')}
          </p>
          <span className="font-mono font-black text-foreground tabular-nums">{totalExpenses.toFixed(2)}{currency}</span>
        </div>
        {expenses.length === 0 ? (
          <p className="font-mono-label text-muted-foreground text-xs">{t('eventDetail.noExpensesYet')}</p>
        ) : (
          <div className="space-y-2">
            {expenses.map((ex) => (
              <div key={ex.id} className="flex items-center justify-between px-4 py-2 border-b border-border last:border-0">
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-sm text-foreground truncate">{ex.description}</span>
                  <Badge variant={(CATEGORY_COLORS[ex.category] as any) ?? 'muted'}>
                    {t(`categories.${ex.category}`, ex.category)}
                  </Badge>
                </div>
                <span className="font-mono font-black text-foreground tabular-nums flex-shrink-0">
                  {ex.amount.toFixed(2)}{currency}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
      )}

      {/* Prizes (read-only display; managed on the Prizes page) */}
      {prizesEnabled && (
        <div className="border border-border bg-card p-6 mt-6">
          <p className="font-mono-label text-accent flex items-center gap-1.5 mb-4">
            <Gift size={12} strokeWidth={1.5} /> {t('prizes.eventBlockTitle')}
          </p>
          {prizes.length === 0 ? (
            <p className="font-mono-label text-muted-foreground text-xs">{t('prizes.emptyEvent')}</p>
          ) : (
            <PrizeGrid prizes={prizes} />
          )}
        </div>
      )}

      {/* Trophies — put in play, voted, revealed (the kiosk plays the ceremony) */}
      {trophiesEnabled && <EventTrophiesSection event={event} isAdmin={isAdmin} currentUserId={user?.id} />}

      {/* Post-event recap — only once there's an event to look back on. */}
      {recapEnabled && !upcoming && (
        <Link
          to={`/events/${eventId}/recap`}
          className="mt-6 border border-accent bg-accent/5 p-6 flex items-center justify-between gap-4 hover:bg-accent/10 transition-colors"
        >
          <div>
            <p className="font-mono-label text-accent flex items-center gap-1.5 mb-1">
              <Sparkles size={12} strokeWidth={1.5} /> {t('recap.blockTitle')}
            </p>
            <p className="text-sm text-muted-foreground">{t('recap.blockDesc')}</p>
          </div>
          <ChevronRight size={20} strokeWidth={1.5} className="text-accent shrink-0" />
        </Link>
      )}

      {/* Gear / BYO — who's bringing what */}
      {gearEnabled && (
        <div className="border border-border bg-card p-6 mt-6">
          <p className="font-mono-label text-accent flex items-center gap-1.5 mb-4">
            <Package size={12} strokeWidth={1.5} /> {t('gear.blockTitle')}
          </p>
          <GearSection eventId={eventId} />
        </div>
      )}

      {/* Groceries — the food/drink shopping list */}
      {groceriesEnabled && (
        <div className="border border-border bg-card p-6 mt-6">
          <p className="font-mono-label text-accent flex items-center gap-1.5 mb-4">
            <ShoppingCart size={12} strokeWidth={1.5} /> {t('groceries.blockTitle')}
          </p>
          <GroceriesSection eventId={eventId} attendees={event.attendees} />
        </div>
      )}

      {/* Private packing checklist — visible only to the logged-in viewer. */}
      {checklistEnabled && (
        <div className="border border-border bg-card p-6 mt-6">
          <p className="font-mono-label text-accent flex items-center gap-1.5 mb-4">
            <ListChecks size={12} strokeWidth={1.5} /> {t('checklist.blockTitle')}
          </p>
          <ChecklistSection eventId={eventId} event={event} />
        </div>
      )}

      {/* Sponsors: admin manager + public strip. Gated on sponsorsEnabled too —
          isAdmin alone used to be enough, so the manager kept showing up here
          even after the feature was switched off in Settings. */}
      {isAdmin && sponsorsEnabled && (
        <div className="mt-6">
          <SponsorsAdminCard eventId={eventId} />
        </div>
      )}
      <div className="mt-6">
        <SponsorStrip eventId={eventId} />
      </div>

      {viewer && (
        <Lightbox
          items={viewer.items}
          index={viewer.index}
          onClose={() => setViewer(null)}
          onItemUpdated={handleItemUpdated}
        />
      )}
      {showTournamentModal && (
        <CreateTournamentModal
          presetEventId={eventId}
          onClose={() => setShowTournamentModal(false)}
          onCreate={load}
        />
      )}
    </main>
  )
}
