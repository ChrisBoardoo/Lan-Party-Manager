import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import { useAppConfig } from '../contexts/AppConfigContext'
import { eventsApi, eventInvitesApi, usersApi, gearApi } from '../lib/api'
import { LanEvent, EventInvite } from '../types'
import { formatDate } from '../lib/formatDate'
import Button from '../components/ui/Button'
import Badge from '../components/ui/Badge'
import Input from '../components/ui/Input'
import QRModal from '../components/ui/QRModal'
import EventCountdown from '../components/ui/EventCountdown'
import AttendeeRoster from '../components/AttendeeRoster'
import {
  Plus, X, CalendarDays, MapPin, Clock, Trash2, Users, CheckCircle2, Circle, Check,
  Ticket, QrCode, Copy, ImagePlus, RotateCw, AlertTriangle, Package, Lock,
} from 'lucide-react'

// ── helpers ───────────────────────────────────────────────────────────────────

function eventDays(start: string, end: string) {
  const diff = Math.round((new Date(end).getTime() - new Date(start).getTime()) / 86400000)
  return diff + 1
}

function isUpcoming(end: string) {
  return new Date(end) >= new Date(new Date().toDateString())
}

// ── Event Modal ───────────────────────────────────────────────────────────────

interface EventForm {
  title: string
  description: string
  location: string
  start_date: string
  end_date: string
  capacity: string
}

function EventModal({
  event,
  onClose,
  onSave,
}: {
  event?: LanEvent
  onClose: () => void
  onSave: () => void
}) {
  const { t } = useTranslation()
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<EventForm>({
    defaultValues: event
      ? {
          title: event.title,
          description: event.description ?? '',
          location: event.location ?? '',
          start_date: event.start_date,
          end_date: event.end_date,
          capacity: event.capacity ? String(event.capacity) : '',
        }
      : {},
  })
  const [coverFile, setCoverFile] = useState<File | null>(null)
  const [coverPreview, setCoverPreview] = useState<string | null>(event?.cover_image_url ?? null)
  const coverFileRef = useRef<HTMLInputElement>(null)

  const handleCoverPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setCoverFile(file)
    setCoverPreview(URL.createObjectURL(file))
  }

  const onSubmit = async (data: EventForm) => {
    const payload = {
      title: data.title,
      description: data.description || undefined,
      location: data.location || undefined,
      start_date: data.start_date,
      end_date: data.end_date,
      capacity: data.capacity ? Number(data.capacity) : undefined,
    }
    const saved = event
      ? await eventsApi.update(event.id, payload)
      : await eventsApi.create(payload)
    if (coverFile) {
      await eventsApi.uploadCover(saved.id, coverFile)
    }
    onSave()
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-background/90 z-50 flex items-center justify-center p-4 sm:p-6">
      <div className="bg-card border border-border w-full max-w-md max-h-[calc(100dvh-2rem)] flex flex-col">
        <div className="flex items-center justify-between p-6 border-b border-border flex-shrink-0">
          <p className="font-mono-label text-accent">
            {event ? t('events.modal.editEvent') : t('events.modal.addEvent')}
          </p>
          <button onClick={onClose}>
            <X size={16} className="text-muted-foreground hover:text-foreground" />
          </button>
        </div>
        <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-4 overflow-y-auto">
          <Input
            label={t('events.modal.titleLabel')}
            placeholder={t('events.modal.titlePlaceholder')}
            {...register('title', { required: t('events.modal.titleRequired') })}
            error={errors.title?.message}
          />
          <Input
            label={t('events.modal.locationLabel')}
            placeholder={t('events.modal.locationPlaceholder')}
            {...register('location')}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label={t('events.modal.startDate')}
              type="date"
              {...register('start_date', { required: t('events.modal.startDateRequired') })}
              error={errors.start_date?.message}
            />
            <Input
              label={t('events.modal.endDate')}
              type="date"
              {...register('end_date', { required: t('events.modal.endDateRequired') })}
              error={errors.end_date?.message}
            />
          </div>
          <Input
            label={t('events.modal.capacityLabel')}
            type="number"
            min={1}
            placeholder={t('events.modal.capacityPlaceholder')}
            {...register('capacity')}
          />
          <div>
            <label className="font-mono-label text-muted-foreground block mb-1.5">
              {t('events.modal.descriptionLabel')}
            </label>
            <textarea
              rows={3}
              placeholder={t('events.modal.descriptionPlaceholder')}
              className="w-full px-4 py-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none resize-none"
              {...register('description')}
            />
          </div>
          <div>
            <label className="font-mono-label text-muted-foreground block mb-1.5">
              {t('events.modal.coverLabel')}
            </label>
            {coverPreview && (
              <div className="w-full h-28 mb-2 border border-border overflow-hidden">
                <img src={coverPreview} alt="" className="w-full h-full object-cover" />
              </div>
            )}
            <input
              ref={coverFileRef}
              type="file"
              accept="image/jpeg,image/png,image/gif,image/webp"
              className="hidden"
              onChange={handleCoverPick}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => coverFileRef.current?.click()}
            >
              <Plus size={12} /> {coverPreview ? t('events.modal.changeCover') : t('events.modal.chooseCover')}
            </Button>
          </div>
          <div className="flex gap-3 pt-2">
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? t('common.saving') : <><Plus size={14} /> {event ? t('common.save') : t('events.modal.createEvent')}</>}
            </Button>
            <Button variant="ghost" type="button" onClick={onClose}>{t('common.cancel')}</Button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── RSVP Date Modal ──────────────────────────────────────────────────────────

interface RsvpDatesForm {
  arrival_date: string
  departure_date: string
}

function RsvpDateModal({
  event,
  onClose,
  onConfirm,
}: {
  event: LanEvent
  onClose: () => void
  onConfirm: (dates: RsvpDatesForm) => Promise<void>
}) {
  const { t } = useTranslation()
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RsvpDatesForm>({
    defaultValues: {
      arrival_date: event.my_arrival_date ?? event.start_date,
      departure_date: event.my_departure_date ?? event.end_date,
    },
  })

  const onSubmit = async (data: RsvpDatesForm) => {
    await onConfirm(data)
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-background/90 z-50 flex items-center justify-center p-4 sm:p-6">
      <div className="bg-card border border-border w-full max-w-md max-h-[calc(100dvh-2rem)] flex flex-col">
        <div className="flex items-center justify-between p-6 border-b border-border flex-shrink-0">
          <p className="font-mono-label text-accent">
            {event.my_rsvp === 'in' ? t('events.rsvpModal.editDates') : t('events.rsvpModal.confirmDates')}
          </p>
          <button onClick={onClose}>
            <X size={16} className="text-muted-foreground hover:text-foreground" />
          </button>
        </div>
        <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-4 overflow-y-auto">
          <p className="text-xs text-muted-foreground">
            {t('events.rsvpModal.pickDates', { start: formatDate(event.start_date), end: formatDate(event.end_date) })}
          </p>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label={t('events.rsvpModal.arrivalDate')}
              type="date"
              min={event.start_date}
              max={event.end_date}
              {...register('arrival_date', { required: t('events.rsvpModal.arrivalRequired') })}
              error={errors.arrival_date?.message}
            />
            <Input
              label={t('events.rsvpModal.departureDate')}
              type="date"
              min={event.start_date}
              max={event.end_date}
              {...register('departure_date', { required: t('events.rsvpModal.departureRequired') })}
              error={errors.departure_date?.message}
            />
          </div>
          <div className="flex gap-3 pt-2">
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? t('common.saving') : <><Check size={14} /> {t('common.confirm')}</>}
            </Button>
            <Button variant="ghost" type="button" onClick={onClose}>{t('common.cancel')}</Button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Invite Code Panel (admin) ───────────────────────────────────────────────────

function InviteCodePanel({ event }: { event: LanEvent }) {
  const { t } = useTranslation()
  const [invite, setInvite] = useState<EventInvite | null | undefined>(undefined)
  const [busy, setBusy] = useState(false)
  const [showQR, setShowQR] = useState(false)
  const [copied, setCopied] = useState(false)

  const load = () => eventInvitesApi.get(event.id).then(setInvite)

  useEffect(() => { load() }, [event.id])

  const handleGenerate = async () => {
    setBusy(true)
    try {
      await eventInvitesApi.create(event.id)
      await load()
    } finally {
      setBusy(false)
    }
  }

  const handleRevoke = async () => {
    if (!confirm(t('events.invitePanel.revokeConfirm'))) return
    setBusy(true)
    try {
      await eventInvitesApi.revoke(event.id)
      await load()
    } finally {
      setBusy(false)
    }
  }

  const handleCopy = () => {
    if (!invite) return
    navigator.clipboard.writeText(invite.code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (invite === undefined) return null

  const registerUrl = invite ? `${window.location.origin}/register?code=${invite.code}` : ''

  return (
    <div className="border-t border-border pt-3 mt-3 flex items-center gap-3 flex-wrap">
      <Ticket size={12} strokeWidth={1.5} className="text-muted-foreground flex-shrink-0" />
      {invite ? (
        <>
          <span className="font-mono font-bold text-sm text-foreground tracking-widest">{invite.code}</span>
          <span className="font-mono-label text-muted-foreground text-[10px]">
            {invite.seats_left === null
              ? t('events.invitePanel.unlimitedSeats')
              : t('events.invitePanel.seatsLeft', { count: invite.seats_left })}
          </span>
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 font-mono-label text-muted-foreground hover:text-foreground text-[10px]"
          >
            <Copy size={9} /> {copied ? t('common.copied') : t('common.copy')}
          </button>
          <button
            onClick={() => setShowQR(true)}
            className="flex items-center gap-1 font-mono-label text-muted-foreground hover:text-foreground text-[10px]"
          >
            <QrCode size={9} /> {t('events.invitePanel.qr')}
          </button>
          <button
            onClick={handleGenerate}
            disabled={busy}
            className="font-mono-label text-muted-foreground hover:text-accent text-[10px] underline disabled:opacity-50"
          >
            {t('events.invitePanel.regenerate')}
          </button>
          <button
            onClick={handleRevoke}
            disabled={busy}
            className="font-mono-label text-muted-foreground hover:text-red-400 text-[10px] underline disabled:opacity-50"
          >
            {t('events.invitePanel.revoke')}
          </button>
        </>
      ) : (
        <button
          onClick={handleGenerate}
          disabled={busy}
          className="font-mono-label text-accent hover:text-accent/80 text-[10px] underline disabled:opacity-50"
        >
          {busy ? t('events.invitePanel.generating') : t('events.invitePanel.generateCode')}
        </button>
      )}

      {showQR && invite && (
        <QRModal
          value={registerUrl}
          label={`${event.title} — ${invite.code}`}
          onClose={() => setShowQR(false)}
        />
      )}
    </div>
  )
}

// ── Event Card ────────────────────────────────────────────────────────────────

function EventCard({
  event,
  isAdmin,
  currentUserId,
  onEdit,
  onDelete,
  onRsvpJoin,
  onRsvpLeave,
  onCoverUpload,
  onCoverRotate,
  onDeactivateAttendee,
}: {
  event: LanEvent
  isAdmin: boolean
  currentUserId?: number
  onEdit: () => void
  onDelete: () => void
  onRsvpJoin: (dates: RsvpDatesForm) => Promise<void>
  onRsvpLeave: () => Promise<void>
  onCoverUpload: (file: File) => Promise<void>
  onCoverRotate: () => Promise<void>
  onDeactivateAttendee: (userId: number, username: string) => Promise<void>
}) {
  const { t } = useTranslation()
  const { gearEnabled } = useAppConfig()
  const upcoming = isUpcoming(event.end_date)
  const days = eventDays(event.start_date, event.end_date)
  const [gear, setGear] = useState<{ pledged: number; needed: number } | null>(null)
  const [toggling, setToggling] = useState(false)

  // Lightweight gear summary for the card — only for upcoming events, and with
  // its own catch so a disabled/empty gear feature never affects the card.
  useEffect(() => {
    if (!gearEnabled || !upcoming) { setGear(null); return }
    gearApi.getForEvent(event.id)
      .then((g) => setGear({ pledged: g.pledged_count, needed: g.open_request_count }))
      .catch(() => setGear(null))
  }, [gearEnabled, upcoming, event.id])
  const [showDateModal, setShowDateModal] = useState(false)
  const [coverUploading, setCoverUploading] = useState(false)
  const [coverRotating, setCoverRotating] = useState(false)
  const coverFileRef = useRef<HTMLInputElement>(null)

  const handleCoverChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setCoverUploading(true)
    try {
      await onCoverUpload(file)
    } finally {
      setCoverUploading(false)
      if (coverFileRef.current) coverFileRef.current.value = ''
    }
  }

  const handleCoverRotate = async () => {
    setCoverRotating(true)
    try {
      await onCoverRotate()
    } finally {
      setCoverRotating(false)
    }
  }

  const handlePillClick = async () => {
    if (event.my_rsvp === 'in') {
      setToggling(true)
      try {
        await onRsvpLeave()
      } finally {
        setToggling(false)
      }
    } else {
      setShowDateModal(true)
    }
  }

  const handleJoinConfirm = async (dates: RsvpDatesForm) => {
    setToggling(true)
    try {
      await onRsvpJoin(dates)
    } finally {
      setToggling(false)
    }
  }

  const isFull = event.capacity != null && event.rsvp_count >= event.capacity && event.my_rsvp !== 'in'
  const canManageCover = isAdmin || event.created_by === currentUserId

  return (
    <div
      className={`border bg-card group relative transition-all duration-150 ${
        upcoming ? 'border-accent/40 bg-accent/5' : 'border-border'
      }`}
    >
      {/* cover image */}
      {event.cover_image_url && (
        <Link to={`/events/${event.id}`} className="block w-full h-32 sm:h-40 overflow-hidden border-b border-border">
          <img src={event.cover_image_url} alt={event.title} className="w-full h-full object-cover" />
        </Link>
      )}

      <div className="p-6">
      {/* top row */}
      <div className="flex items-start justify-between mb-4">
        <Link to={`/events/${event.id}`} className="flex items-center gap-3 group/header">
          <div
            className={`w-10 h-10 flex items-center justify-center border flex-shrink-0 ${
              upcoming ? 'border-accent text-accent' : 'border-border text-muted-foreground'
            }`}
          >
            <CalendarDays size={18} strokeWidth={1.5} />
          </div>
          <div>
            <h3 className="font-black text-lg tracking-tight text-foreground leading-none group-hover/header:text-accent transition-colors">
              {event.title}
            </h3>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <Badge variant={upcoming ? 'accent' : 'muted'}>
                {upcoming ? t('events.card.upcoming') : t('events.card.past')}
              </Badge>
              {/* RSVP count */}
              <span className="font-mono-label text-muted-foreground text-[10px] flex items-center gap-1">
                <Users size={9} />
                {event.rsvp_count}{event.capacity ? `/${event.capacity}` : ''} {t('events.card.going')}
              </span>
              {/* Gear summary */}
              {gear && (gear.pledged > 0 || gear.needed > 0) && (
                <span className="font-mono-label text-muted-foreground text-[10px] flex items-center gap-1">
                  <Package size={9} />
                  {t('gear.cardBringing', { count: gear.pledged })}
                  {gear.needed > 0 && <span className="text-accent">· {t('gear.cardNeeded', { count: gear.needed })}</span>}
                </span>
              )}
              {isFull && (
                <Badge variant="danger">{t('events.card.full')}</Badge>
              )}
              {upcoming && <EventCountdown startDate={event.start_date} />}
            </div>
          </div>
        </Link>

        <div className="flex items-center gap-2">
          {/* Locked from the first day: the stay sets everyone's share */}
          {upcoming && event.attendance_locked && (
            <span
              className="flex items-center gap-1 font-mono-label text-muted-foreground text-[10px]"
              title={t('events.card.lockedHint')}
            >
              <Lock size={10} /> {t('events.card.locked')}
            </span>
          )}

          {/* RSVP toggle */}
          {upcoming && !event.attendance_locked && (
            <div className="flex items-center gap-2">
              <button
                onClick={handlePillClick}
                disabled={toggling || isFull}
                className={`flex items-center gap-1.5 px-3 py-1.5 font-mono-label text-xs border transition-colors duration-150 disabled:opacity-50 ${
                  event.my_rsvp === 'in'
                    ? 'border-green-500 text-green-400 bg-green-500/10'
                    : 'border-border text-muted-foreground hover:border-foreground hover:text-foreground'
                }`}
              >
                {event.my_rsvp === 'in' ? (
                  <><CheckCircle2 size={10} /> {t('events.card.imIn')}</>
                ) : (
                  <><Circle size={10} /> {t('events.card.join')}</>
                )}
              </button>
              {event.my_rsvp === 'in' && (
                <button
                  onClick={() => setShowDateModal(true)}
                  className="font-mono-label text-muted-foreground hover:text-accent text-[10px] underline"
                >
                  {t('events.card.editDates')}
                </button>
              )}
            </div>
          )}

          {(isAdmin || canManageCover) && (
            <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              {canManageCover && (
                <>
                  <button
                    onClick={() => coverFileRef.current?.click()}
                    disabled={coverUploading}
                    title={t('events.card.uploadCover')}
                    className="p-1.5 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
                  >
                    <ImagePlus size={12} strokeWidth={1.5} />
                  </button>
                  {event.cover_image_url && (
                    <button
                      onClick={handleCoverRotate}
                      disabled={coverRotating}
                      title={t('events.card.rotateCover')}
                      className="p-1.5 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
                    >
                      <RotateCw size={12} strokeWidth={1.5} />
                    </button>
                  )}
                  <input
                    ref={coverFileRef}
                    type="file"
                    accept="image/jpeg,image/png,image/gif,image/webp"
                    className="hidden"
                    onChange={handleCoverChange}
                  />
                </>
              )}
              {isAdmin && (
                <>
                  <button
                    onClick={onEdit}
                    className="p-1.5 text-muted-foreground hover:text-foreground transition-colors font-mono-label text-[10px]"
                  >
                    {t('common.edit')}
                  </button>
                  <button
                    onClick={onDelete}
                    className="p-1.5 text-muted-foreground hover:text-red-400 transition-colors"
                  >
                    <Trash2 size={12} strokeWidth={1.5} />
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* dates */}
      <div className="flex flex-wrap items-center gap-4 mb-3">
        <div className="flex items-center gap-2">
          <Clock size={12} strokeWidth={1.5} className="text-muted-foreground" />
          <span className="font-mono-label text-foreground">
            {formatDate(event.start_date)}
            {event.start_date !== event.end_date && <> → {formatDate(event.end_date)}</>}
          </span>
        </div>
        <span className="font-mono-label text-accent">
          {t('events.card.days', { count: days })}
        </span>
      </div>

      {event.my_rsvp === 'in' && event.my_arrival_date && event.my_departure_date && (
        <div className="flex items-center gap-2 mb-3">
          <span className="font-mono-label text-green-400 text-[10px]">
            {t('events.card.yourStay')} {formatDate(event.my_arrival_date)} → {formatDate(event.my_departure_date)}
          </span>
        </div>
      )}

      {event.location && (
        <div className="flex items-center gap-2 mb-3">
          <MapPin size={12} strokeWidth={1.5} className="text-muted-foreground" />
          <span className="font-mono-label text-muted-foreground">{event.location}</span>
        </div>
      )}

      {event.description && (
        <p className="text-sm text-muted-foreground leading-relaxed border-t border-border pt-3 mt-3">
          {event.description}
        </p>
      )}

      <AttendeeRoster
        event={event}
        isAdmin={isAdmin}
        currentUserId={currentUserId}
        onDeactivate={onDeactivateAttendee}
      />

      {isAdmin && <InviteCodePanel event={event} />}
      </div>

      {showDateModal && (
        <RsvpDateModal
          event={event}
          onClose={() => setShowDateModal(false)}
          onConfirm={handleJoinConfirm}
        />
      )}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Events() {
  const { user } = useAuth()
  const { t } = useTranslation()
  const isAdmin = user?.role === 'admin'
  const [events, setEvents] = useState<LanEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [editingEvent, setEditingEvent] = useState<LanEvent | undefined>(undefined)

  const load = async () => {
    try {
      const data = await eventsApi.getAll()
      setEvents(data)
      setError(null)
    } catch {
      setError(t('events.loadFailed'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleDelete = async (event: LanEvent) => {
    if (!confirm(t('events.deleteConfirm', { title: event.title }))) return
    await eventsApi.delete(event.id)
    await load()
  }

  const handleRsvpJoin = async (event: LanEvent, dates: RsvpDatesForm) => {
    await eventsApi.rsvpIn(event.id, dates)
    await load()
  }

  const handleRsvpLeave = async (event: LanEvent) => {
    await eventsApi.rsvpOut(event.id)
    await load()
  }

  const handleCoverUpload = async (event: LanEvent, file: File) => {
    await eventsApi.uploadCover(event.id, file)
    await load()
  }

  const handleCoverRotate = async (event: LanEvent) => {
    await eventsApi.rotateCover(event.id)
    await load()
  }

  const handleDeactivateAttendee = async (userId: number, username: string) => {
    if (!confirm(t('players.deactivateConfirm', { username }))) return
    await usersApi.deactivate(userId)
    await load()
  }

  const upcoming = events.filter((e) => isUpcoming(e.end_date))
  const past = events.filter((e) => !isUpcoming(e.end_date)).reverse()

  return (
    <main className="max-w-6xl mx-auto px-6 py-12">
      <div className="flex items-start justify-between mb-12">
        <div>
          <div className="font-mono-label text-accent mb-3">{t('events.tagline')}</div>
          <h1 className="text-5xl lg:text-6xl font-black tracking-tighter text-foreground leading-none">
            {t('events.heroLine1')}
            <br />
            <span className="text-accent">{t('events.heroLine2')}</span>
          </h1>
        </div>
        {isAdmin && (
          <Button onClick={() => { setEditingEvent(undefined); setShowModal(true) }}>
            <Plus size={14} /> {t('events.addEventButton')}
          </Button>
        )}
      </div>

      {loading ? (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-36 bg-muted animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <div className="border border-red-500/40 bg-red-500/10 p-16 text-center">
          <AlertTriangle size={32} strokeWidth={1} className="text-red-400 mx-auto mb-4" />
          <p className="font-mono-label text-red-200 mb-4">{error}</p>
          <Button onClick={() => { setLoading(true); load() }}>{t('common.retry')}</Button>
        </div>
      ) : events.length === 0 ? (
        <div className="border border-border p-16 text-center">
          <CalendarDays size={32} strokeWidth={1} className="text-muted-foreground mx-auto mb-4" />
          <p className="font-mono-label text-muted-foreground mb-1">{t('events.noEventsScheduled')}</p>
          {isAdmin && (
            <p className="text-sm text-muted-foreground">
              {t('events.addEventHint')}
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-10">
          {upcoming.length > 0 && (
            <section>
              <p className="font-mono-label text-accent mb-4">
                {t('events.upcomingSection', { count: upcoming.length })}
              </p>
              <div className="space-y-4">
                {upcoming.map((e) => (
                  <EventCard
                    key={e.id}
                    event={e}
                    isAdmin={isAdmin}
                    currentUserId={user?.id}
                    onEdit={() => { setEditingEvent(e); setShowModal(true) }}
                    onDelete={() => handleDelete(e)}
                    onRsvpJoin={(dates) => handleRsvpJoin(e, dates)}
                    onRsvpLeave={() => handleRsvpLeave(e)}
                    onCoverUpload={(file) => handleCoverUpload(e, file)}
                    onCoverRotate={() => handleCoverRotate(e)}
                    onDeactivateAttendee={handleDeactivateAttendee}
                  />
                ))}
              </div>
            </section>
          )}

          {past.length > 0 && (
            <section>
              <p className="font-mono-label text-muted-foreground mb-4">
                {t('events.pastSection', { count: past.length })}
              </p>
              <div className="space-y-4">
                {past.map((e) => (
                  <EventCard
                    key={e.id}
                    event={e}
                    isAdmin={isAdmin}
                    currentUserId={user?.id}
                    onEdit={() => { setEditingEvent(e); setShowModal(true) }}
                    onDelete={() => handleDelete(e)}
                    onRsvpJoin={(dates) => handleRsvpJoin(e, dates)}
                    onRsvpLeave={() => handleRsvpLeave(e)}
                    onCoverUpload={(file) => handleCoverUpload(e, file)}
                    onCoverRotate={() => handleCoverRotate(e)}
                    onDeactivateAttendee={handleDeactivateAttendee}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {showModal && (
        <EventModal
          event={editingEvent}
          onClose={() => setShowModal(false)}
          onSave={load}
        />
      )}
    </main>
  )
}
