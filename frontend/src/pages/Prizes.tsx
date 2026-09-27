import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import { prizesApi, eventsApi } from '../lib/api'
import { LanEvent, Prize } from '../types'
import Button from '../components/ui/Button'
import PrizeGrid from '../components/PrizeGrid'
import { Plus, Trash2, Check, X, ImagePlus, Gift, Edit2 } from 'lucide-react'

function pickDefaultEvent(events: LanEvent[]): number | null {
  if (events.length === 0) return null
  const today = new Date(new Date().toDateString())
  const upcoming = events
    .filter((e) => new Date(e.end_date) >= today)
    .sort((a, b) => a.start_date.localeCompare(b.start_date))
  if (upcoming.length > 0) return upcoming[0].id
  const past = [...events].sort((a, b) => b.end_date.localeCompare(a.end_date))
  return past[0].id
}

function PrizeAdminCard({
  prize,
  onChange,
}: {
  prize: Prize
  onChange: () => void
}) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(prize.title)
  const [description, setDescription] = useState(prize.description ?? '')
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const save = async () => {
    if (!title.trim()) return
    await prizesApi.update(prize.id, { title: title.trim(), description: description.trim() || null })
    setEditing(false)
    onChange()
  }

  const uploadPhoto = async (file?: File) => {
    if (!file) return
    setUploading(true)
    try {
      await prizesApi.uploadPhoto(prize.id, file)
      onChange()
    } finally {
      setUploading(false)
    }
  }

  const remove = async () => {
    if (!confirm(t('prizes.deleteConfirm'))) return
    await prizesApi.delete(prize.id)
    onChange()
  }

  return (
    <div className="border border-border bg-card overflow-hidden flex flex-col">
      <div className="aspect-video bg-muted border-b border-border flex items-center justify-center overflow-hidden relative group">
        {prize.photo_url ? (
          <img src={prize.photo_url} alt={prize.title} className="w-full h-full object-cover" />
        ) : (
          <Gift size={28} strokeWidth={1} className="text-muted-foreground" />
        )}
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => uploadPhoto(e.target.files?.[0])}
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="absolute bottom-2 right-2 flex items-center gap-1 px-2 py-1 bg-background/90 border border-border font-mono-label text-[10px] text-foreground hover:border-accent transition-colors disabled:opacity-50"
        >
          <ImagePlus size={11} /> {uploading ? t('prizes.uploading') : t('prizes.photo')}
        </button>
      </div>
      <div className="p-4 flex-1">
        {editing ? (
          <div className="space-y-2">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full h-9 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none"
              autoFocus
            />
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 bg-input border border-border text-foreground text-sm focus:border-accent outline-none resize-y"
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={save} disabled={!title.trim()}><Check size={12} /> {t('common.save')}</Button>
              <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setTitle(prize.title); setDescription(prize.description ?? '') }}>
                <X size={12} /> {t('common.cancel')}
              </Button>
            </div>
          </div>
        ) : (
          <>
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-black tracking-tight text-foreground">{prize.title}</p>
              <div className="flex items-center gap-1 flex-shrink-0">
                <button onClick={() => setEditing(true)} className="p-1 text-muted-foreground hover:text-foreground transition-colors" title={t('common.edit')}>
                  <Edit2 size={12} strokeWidth={1.5} />
                </button>
                <button onClick={remove} className="p-1 text-muted-foreground hover:text-red-400 transition-colors" title={t('common.delete')}>
                  <Trash2 size={12} strokeWidth={1.5} />
                </button>
              </div>
            </div>
            {prize.description && (
              <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed whitespace-pre-wrap">{prize.description}</p>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default function Prizes() {
  const { isAdmin } = useAuth()
  const { t } = useTranslation()
  const [events, setEvents] = useState<LanEvent[]>([])
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null)
  const [prizes, setPrizes] = useState<Prize[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    eventsApi.getAll()
      .then((evts) => {
        setEvents(evts)
        setSelectedEventId(pickDefaultEvent(evts))
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const loadPrizes = () => {
    if (selectedEventId == null) { setPrizes([]); return }
    prizesApi.getForEvent(selectedEventId).then(setPrizes).catch(() => {})
  }
  useEffect(() => { loadPrizes() }, [selectedEventId])

  const handleAdd = async () => {
    if (!title.trim() || selectedEventId == null) return
    setSaving(true)
    try {
      await prizesApi.create({ event_id: selectedEventId, title: title.trim(), description: description.trim() || null })
      setTitle(''); setDescription(''); setShowForm(false)
      loadPrizes()
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="max-w-6xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="mb-12">
        <div className="font-mono-label text-accent mb-3">{t('prizes.tagline')}</div>
        <h1 className="text-5xl lg:text-6xl font-black tracking-tighter text-foreground leading-none">
          {t('prizes.heroLine1')}
          <br />
          <span className="text-accent">{t('prizes.heroLine2')}</span>
        </h1>
      </div>

      {/* Event selector + add */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-8">
        {events.length > 0 ? (
          <div className="flex items-center gap-2">
            <label className="font-mono-label text-muted-foreground">{t('prizes.eventLabel')}</label>
            <select
              className="h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none transition-colors"
              value={selectedEventId ?? ''}
              onChange={(e) => setSelectedEventId(Number(e.target.value))}
            >
              {events.map((ev) => (
                <option key={ev.id} value={ev.id} className="bg-muted">{ev.title}</option>
              ))}
            </select>
          </div>
        ) : <div />}
        {isAdmin && selectedEventId != null && !showForm && (
          <Button size="sm" onClick={() => setShowForm(true)}>
            <Plus size={14} /> {t('prizes.add')}
          </Button>
        )}
      </div>

      {/* Add form */}
      {showForm && (
        <div className="border border-accent bg-card p-6 mb-6 space-y-3">
          <p className="font-mono-label text-accent">{t('prizes.newPrize')}</p>
          <div>
            <label className="font-mono-label text-muted-foreground block mb-1.5">{t('prizes.titleLabel')}</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t('prizes.titlePlaceholder')}
              className="w-full h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none"
              autoFocus
            />
          </div>
          <div>
            <label className="font-mono-label text-muted-foreground block mb-1.5">{t('prizes.descriptionLabel')}</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 bg-input border border-border text-foreground text-sm focus:border-accent outline-none resize-y"
            />
          </div>
          <p className="font-mono-label text-muted-foreground/60 text-[10px]">{t('prizes.photoHint')}</p>
          <div className="flex gap-2">
            <Button size="sm" onClick={handleAdd} disabled={saving || !title.trim()}>
              <Check size={12} /> {saving ? t('common.saving') : t('prizes.add')}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => { setShowForm(false); setTitle(''); setDescription('') }}>
              <X size={12} /> {t('common.cancel')}
            </Button>
          </div>
        </div>
      )}

      {/* Prizes */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-56 bg-muted animate-pulse" />)}
        </div>
      ) : events.length === 0 ? (
        <div className="text-center py-20 border border-border">
          <Gift size={32} strokeWidth={1} className="text-muted-foreground mx-auto mb-4" />
          <p className="font-mono-label text-muted-foreground">{t('prizes.noEvents')}</p>
        </div>
      ) : prizes.length === 0 ? (
        <div className="text-center py-20 border border-border">
          <Gift size={32} strokeWidth={1} className="text-muted-foreground mx-auto mb-4" />
          <p className="font-mono-label text-muted-foreground">{t('prizes.emptyEvent')}</p>
        </div>
      ) : isAdmin ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {prizes.map((p) => <PrizeAdminCard key={p.id} prize={p} onChange={loadPrizes} />)}
        </div>
      ) : (
        <PrizeGrid prizes={prizes} />
      )}
    </main>
  )
}
