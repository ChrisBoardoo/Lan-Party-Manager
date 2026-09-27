import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import { mediaApi, eventsApi } from '../lib/api'
import { useToast } from '../contexts/ToastContext'
import { MediaItem, LanEvent } from '../types'
import { Upload, X, Trash2, Play, ImageIcon, Video, Loader2, Filter, CheckSquare, Square } from 'lucide-react'
import Button from '../components/ui/Button'
import Lightbox, { formatBytes } from '../components/ui/Lightbox'

// ── Media Card ────────────────────────────────────────────────────────────────

function MediaCard({
  item,
  canDelete,
  selected,
  bulkMode,
  onDelete,
  onClick,
  onToggleSelect,
}: {
  item: MediaItem
  canDelete: boolean
  selected: boolean
  bulkMode: boolean
  onDelete: () => void
  onClick: () => void
  onToggleSelect: () => void
}) {
  const { t } = useTranslation()
  const thumb = item.file_type === 'video' && item.thumbnail_url ? item.thumbnail_url : null

  return (
    <div
      className={`group relative border overflow-hidden cursor-pointer aspect-square transition-all ${
        selected ? 'border-accent' : 'border-border bg-card'
      }`}
    >
      {item.file_type === 'image' ? (
        <img
          src={item.url}
          alt={item.original_name}
          className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
          onClick={bulkMode ? onToggleSelect : onClick}
        />
      ) : thumb ? (
        <img
          src={thumb}
          alt={item.original_name}
          className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
          onClick={bulkMode ? onToggleSelect : onClick}
        />
      ) : (
        <div className="w-full h-full bg-muted flex items-center justify-center" onClick={bulkMode ? onToggleSelect : onClick}>
          <Video size={32} strokeWidth={1} className="text-muted-foreground" />
        </div>
      )}

      {item.file_type === 'video' && !bulkMode && (
        <div className="absolute inset-0 flex items-center justify-center" onClick={onClick}>
          <div className="w-12 h-12 border border-foreground/40 flex items-center justify-center bg-background/60 group-hover:border-accent group-hover:text-accent transition-colors duration-150">
            <Play size={18} strokeWidth={1.5} className="ml-0.5" />
          </div>
        </div>
      )}

      {/* Bulk select overlay */}
      {bulkMode && (
        <div
          className="absolute inset-0 flex items-center justify-center bg-background/40"
          onClick={onToggleSelect}
        >
          {selected ? (
            <CheckSquare size={28} className="text-accent" />
          ) : (
            <Square size={28} className="text-foreground/60" />
          )}
        </div>
      )}

      {/* Hover info overlay — pointer-events-none so it never swallows the
          click that should open the lightbox (it holds no interactive elements). */}
      {!bulkMode && (
        <div className="absolute inset-0 bg-background/0 group-hover:bg-background/60 transition-colors duration-200 flex flex-col justify-end p-3 pointer-events-none">
          <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-150">
            <p className="font-mono-label text-foreground text-[10px] truncate">{item.original_name}</p>
            <p className="font-mono-label text-muted-foreground text-[10px]">
              {item.uploader.username} · {formatBytes(item.file_size)}
            </p>
          </div>
        </div>
      )}

      {/* Reaction tally — a read-only count, never buttons. Reacting happens in
          the lightbox: anything interactive here would have to opt out of the
          pointer-events-none overlay above and would compete with the click that
          opens the viewer. */}
      {!bulkMode && item.reaction_total > 0 && (
        <div className="absolute bottom-2 left-2 flex items-center gap-1 bg-background/80 border border-border px-1.5 py-0.5 pointer-events-none">
          {item.reactions.slice(0, 3).map((r) => (
            <span key={r.emoji} className="text-[10px] leading-none">{r.emoji}</span>
          ))}
          <span className="font-mono text-[10px] text-muted-foreground leading-none">{item.reaction_total}</span>
        </div>
      )}

      {/* Delete button */}
      {canDelete && !bulkMode && (
        <button
          onClick={(e) => { e.stopPropagation(); onDelete() }}
          className="absolute top-2 right-2 p-1.5 bg-background/80 border border-border text-muted-foreground hover:text-red-400 hover:border-red-400 opacity-0 group-hover:opacity-100 transition-all duration-150"
          title={t('common.delete')}
        >
          <Trash2 size={12} strokeWidth={1.5} />
        </button>
      )}
    </div>
  )
}

// ── Upload zone ───────────────────────────────────────────────────────────────

const ACCEPTED = 'image/jpeg,image/png,image/gif,image/webp,video/mp4,video/webm,video/quicktime,video/x-msvideo'
const MAX_BYTES = 100 * 1024 * 1024

function UploadButton({ onUploaded, selectedEventId }: { onUploaded: () => void; selectedEventId?: number }) {
  const { t } = useTranslation()
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (file.size > MAX_BYTES) { setError(t('media.fileTooLarge')); return }
    setError(null)
    setUploading(true)
    try {
      await mediaApi.upload(file, undefined, selectedEventId)
      onUploaded()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? t('media.uploadFailed'))
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button onClick={() => fileRef.current?.click()} disabled={uploading}>
        {uploading ? <><Loader2 size={14} className="animate-spin" /> {t('media.uploading')}</> : <><Upload size={14} /> {t('media.upload')}</>}
      </Button>
      {error && <p className="font-mono-label text-red-400 text-[10px]">{error}</p>}
      <input ref={fileRef} type="file" accept={ACCEPTED} className="hidden" onChange={handleFile} />
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Media() {
  const { user, isAdmin } = useAuth()
  const { t } = useTranslation()
  const { push } = useToast()
  const [items, setItems] = useState<MediaItem[]>([])
  const [events, setEvents] = useState<LanEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [viewer, setViewer] = useState<{ items: MediaItem[]; index: number } | null>(null)
  const [filterEventId, setFilterEventId] = useState<number | undefined>(undefined)
  const [bulkMode, setBulkMode] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const load = async () => {
    const [mediaData, eventsData] = await Promise.all([
      mediaApi.getAll(filterEventId),
      eventsApi.getAll(),
    ])
    setItems(mediaData)
    setEvents(eventsData)
    setLoading(false)
  }

  useEffect(() => { load() }, [filterEventId])

  // The lightbox holds its own copy of the list it was opened with (the images
  // or videos slice), so a reaction/caption edit has to land in both.
  const handleItemUpdated = (updated: MediaItem) => {
    const swap = (i: MediaItem) => (i.id === updated.id ? updated : i)
    setItems((prev) => prev.map(swap))
    setViewer((v) => (v ? { ...v, items: v.items.map(swap) } : v))
  }

  const handleDelete = async (item: MediaItem) => {
    if (!confirm(t('media.deleteConfirm', { name: item.original_name }))) return
    await mediaApi.delete(item.id)
    setItems((prev) => prev.filter((i) => i.id !== item.id))
    push(t('media.mediaDeleted'))
  }

  const handleBulkDelete = async () => {
    if (selected.size === 0) return
    if (!confirm(t('media.deleteSelectedConfirm', { count: selected.size }))) return
    setBulkDeleting(true)
    try {
      await mediaApi.bulkDelete([...selected])
      setSelected(new Set())
      setBulkMode(false)
      await load()
    } finally {
      setBulkDeleting(false)
    }
  }

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const images = items.filter((i) => i.file_type === 'image')
  const videos = items.filter((i) => i.file_type === 'video')

  return (
    <main className="max-w-6xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="font-mono-label text-accent mb-3">{t('media.tagline')}</div>
          <h1 className="text-5xl lg:text-6xl font-black tracking-tighter text-foreground leading-none">
            {t('media.heroLine1')}
            <br />
            <span className="text-accent">{t('media.heroLine2')}</span>
          </h1>
          <p className="font-mono-label text-muted-foreground mt-3 text-sm">
            {t('media.fileCount', { count: items.length })}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <UploadButton onUploaded={load} selectedEventId={filterEventId} />
          {isAdmin && items.length > 0 && (
            <button
              onClick={() => { setBulkMode((b) => !b); setSelected(new Set()) }}
              className={`font-mono-label text-xs flex items-center gap-1 transition-colors ${
                bulkMode ? 'text-accent' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <CheckSquare size={11} /> {bulkMode ? t('media.exitBulk') : t('media.bulkSelect')}
            </button>
          )}
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-3 mb-8 flex-wrap">
        {/* Event filter */}
        <div className="flex items-center gap-2">
          <Filter size={12} strokeWidth={1.5} className="text-muted-foreground" />
          <select
            value={filterEventId ?? ''}
            onChange={(e) => {
              setFilterEventId(e.target.value ? Number(e.target.value) : undefined)
              setSelected(new Set())
            }}
            className="h-8 px-3 bg-input border border-border text-foreground text-xs focus:border-accent outline-none"
          >
            <option value="">{t('media.allEvents')}</option>
            {events.map((ev) => (
              <option key={ev.id} value={ev.id}>{ev.title}</option>
            ))}
          </select>
        </div>

        {/* Bulk delete */}
        {bulkMode && selected.size > 0 && (
          <Button
            variant="ghost"
            onClick={handleBulkDelete}
            disabled={bulkDeleting}
          >
            <Trash2 size={12} />
            {bulkDeleting ? t('media.deleting') : t('media.deleteSelected', { count: selected.size })}
          </Button>
        )}
      </div>

      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="aspect-square bg-muted animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="border border-border p-16 text-center">
          <ImageIcon size={32} strokeWidth={1} className="text-muted-foreground mx-auto mb-4" />
          <p className="font-mono-label text-muted-foreground mb-1">{t('media.noMediaYet')}</p>
          <p className="text-sm text-muted-foreground">{t('media.uploadHint')}</p>
        </div>
      ) : (
        <div className="space-y-10">
          {images.length > 0 && (
            <section>
              <div className="flex items-center gap-3 mb-4">
                <ImageIcon size={14} strokeWidth={1.5} className="text-accent" />
                <p className="font-mono-label text-accent">{t('media.photos', { count: images.length })}</p>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                {images.map((item, i) => (
                  <MediaCard
                    key={item.id}
                    item={item}
                    canDelete={isAdmin || item.uploaded_by === user?.id}
                    selected={selected.has(item.id)}
                    bulkMode={bulkMode}
                    onDelete={() => handleDelete(item)}
                    onClick={() => setViewer({ items: images, index: i })}
                    onToggleSelect={() => toggleSelect(item.id)}
                  />
                ))}
              </div>
            </section>
          )}

          {videos.length > 0 && (
            <section>
              <div className="flex items-center gap-3 mb-4">
                <Video size={14} strokeWidth={1.5} className="text-accent" />
                <p className="font-mono-label text-accent">{t('media.videos', { count: videos.length })}</p>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                {videos.map((item, i) => (
                  <MediaCard
                    key={item.id}
                    item={item}
                    canDelete={isAdmin || item.uploaded_by === user?.id}
                    selected={selected.has(item.id)}
                    bulkMode={bulkMode}
                    onDelete={() => handleDelete(item)}
                    onClick={() => setViewer({ items: videos, index: i })}
                    onToggleSelect={() => toggleSelect(item.id)}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {viewer && (
        <Lightbox
          items={viewer.items}
          index={viewer.index}
          onClose={() => setViewer(null)}
          onItemUpdated={handleItemUpdated}
          events={events}
        />
      )}
    </main>
  )
}
