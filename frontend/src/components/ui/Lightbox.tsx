import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LanEvent, MediaItem } from '../../types'
import { formatDate } from '../../lib/formatDate'
import { mediaApi } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'
import MediaReactions from '../MediaReactions'
import { X, ChevronLeft, ChevronRight, Pencil, Check } from 'lucide-react'

export function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * Fullscreen media viewer / slideshow.
 * Pass the list of items and the index that was clicked; when the list has more
 * than one item, prev/next arrows, keyboard ←/→ and touch-swipe are enabled.
 *
 * This is also where reacting and editing live. The gallery cards deliberately
 * carry only a read-only count: their hover overlay is pointer-events-none so it
 * can't swallow the click that opens this viewer, and putting buttons there
 * would fight that.
 */
export default function Lightbox({
  items,
  index,
  onClose,
  onItemUpdated,
  events,
}: {
  items: MediaItem[]
  index: number
  onClose: () => void
  /** Called with the updated item after a reaction/caption/re-tag, so the
   *  caller can keep its own list in sync. Omit for read-only surfaces. */
  onItemUpdated?: (item: MediaItem) => void
  /** Enables re-tagging an item's event. Omit to hide that control. */
  events?: LanEvent[]
}) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [cur, setCur] = useState(index)
  const [editingCaption, setEditingCaption] = useState(false)
  const [draftCaption, setDraftCaption] = useState('')
  const [saving, setSaving] = useState(false)
  const touchStartX = useRef<number | null>(null)

  // Re-seed when the caller opens the viewer at a different item.
  useEffect(() => setCur(index), [index])

  const count = items.length
  const hasMany = count > 1

  const goPrev = useCallback(() => setCur((c) => (c + count - 1) % count), [count])
  const goNext = useCallback(() => setCur((c) => (c + 1) % count), [count])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (hasMany && e.key === 'ArrowLeft') goPrev()
      else if (hasMany && e.key === 'ArrowRight') goNext()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose, goPrev, goNext, hasMany])

  // Leave edit mode when navigating away, so a half-typed caption can't land on
  // the wrong photo.
  useEffect(() => setEditingCaption(false), [cur])

  const item = items[cur]
  if (!item) return null

  const canEdit = !!user && (user.role === 'admin' || user.id === item.uploaded_by)

  const saveCaption = async () => {
    setSaving(true)
    try {
      const trimmed = draftCaption.trim()
      onItemUpdated?.(await mediaApi.update(item.id, { caption: trimmed || null }))
      setEditingCaption(false)
    } finally {
      setSaving(false)
    }
  }

  const retag = async (value: string) => {
    setSaving(true)
    try {
      onItemUpdated?.(await mediaApi.update(item.id, { event_id: value ? Number(value) : null }))
    } finally {
      setSaving(false)
    }
  }

  const onTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.changedTouches[0].clientX
  }
  const onTouchEnd = (e: React.TouchEvent) => {
    if (touchStartX.current === null || !hasMany) return
    const dx = e.changedTouches[0].clientX - touchStartX.current
    if (Math.abs(dx) > 50) (dx > 0 ? goPrev : goNext)()
    touchStartX.current = null
  }

  return (
    <div
      className="fixed inset-0 bg-background/95 z-50 flex flex-col items-center justify-center p-4 sm:p-6"
      onClick={onClose}
    >
      {/* Close (top-right, always reachable) */}
      <button
        onClick={onClose}
        aria-label={t('media.close')}
        className="absolute top-3 right-3 sm:top-4 sm:right-4 p-2 text-muted-foreground hover:text-foreground transition-colors z-10"
      >
        <X size={22} strokeWidth={1.5} />
      </button>

      {/* Prev / Next arrows */}
      {hasMany && (
        <>
          <button
            onClick={(e) => { e.stopPropagation(); goPrev() }}
            aria-label={t('media.prev')}
            className="absolute left-1 sm:left-4 top-1/2 -translate-y-1/2 p-2 sm:p-3 bg-background/60 border border-border text-muted-foreground hover:text-accent hover:border-accent transition-colors z-10"
          >
            <ChevronLeft size={24} strokeWidth={1.5} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); goNext() }}
            aria-label={t('media.next')}
            className="absolute right-1 sm:right-4 top-1/2 -translate-y-1/2 p-2 sm:p-3 bg-background/60 border border-border text-muted-foreground hover:text-accent hover:border-accent transition-colors z-10"
          >
            <ChevronRight size={24} strokeWidth={1.5} />
          </button>
        </>
      )}

      <div
        className="relative max-w-5xl w-full max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
      >
        <div className="flex items-center justify-between mb-3 gap-3 px-10 sm:px-0">
          <div className="min-w-0">
            <p className="font-mono-label text-foreground text-sm truncate">{item.original_name}</p>
            <p className="font-mono-label text-muted-foreground text-[10px] truncate">
              {t('media.by')} {item.uploader.username} · {formatDate(item.created_at)} · {formatBytes(item.file_size)}
            </p>
          </div>
          {hasMany && (
            <span className="font-mono-label text-muted-foreground text-[10px] shrink-0 tabular-nums">
              {cur + 1} / {count}
            </span>
          )}
        </div>

        <div className="flex-1 flex items-center justify-center overflow-hidden border border-border bg-card">
          {item.file_type === 'image' ? (
            // key forces a fresh element per item so the browser doesn't reuse
            // the previous frame while the next image loads.
            <img
              key={item.id}
              src={item.url}
              alt={item.original_name}
              className="max-w-full max-h-[75vh] object-contain"
            />
          ) : (
            // key remounts the <video> on navigation so the previous clip stops
            // and the new one autoplays from the start.
            <video
              key={item.id}
              src={item.url}
              controls
              autoPlay
              className="max-w-full max-h-[75vh]"
            />
          )}
        </div>

        {/* Caption — editable in place by its uploader or an admin. */}
        <div className="mt-3 flex items-start gap-2">
          {editingCaption ? (
            <>
              <input
                autoFocus
                value={draftCaption}
                onChange={(e) => setDraftCaption(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') saveCaption()
                  if (e.key === 'Escape') setEditingCaption(false)
                }}
                maxLength={500}
                placeholder={t('media.captionPlaceholder')}
                className="flex-1 bg-input border border-border px-3 py-1.5 text-sm text-foreground focus:border-accent outline-none"
              />
              <button
                onClick={saveCaption}
                disabled={saving}
                aria-label={t('media.captionSave')}
                className="p-2 text-muted-foreground hover:text-accent transition-colors disabled:opacity-50"
              >
                <Check size={16} strokeWidth={1.5} />
              </button>
            </>
          ) : (
            <>
              <p className="flex-1 font-mono-label text-muted-foreground text-sm">
                {item.caption || (canEdit ? t('media.noCaption') : '')}
              </p>
              {canEdit && onItemUpdated && (
                <button
                  onClick={() => { setDraftCaption(item.caption ?? ''); setEditingCaption(true) }}
                  aria-label={t('media.captionEdit')}
                  className="p-1 text-muted-foreground hover:text-accent transition-colors"
                >
                  <Pencil size={14} strokeWidth={1.5} />
                </button>
              )}
            </>
          )}
        </div>

        {/* Reactions — the crew's vote, and what "best of" is derived from. */}
        {onItemUpdated && (
          <div className="mt-3">
            <MediaReactions item={item} onChange={onItemUpdated} />
          </div>
        )}

        {/* Re-tagging: media event_id is nullable and uploads inherit whatever
            filter was selected, so plenty of photos end up tied to no event and
            invisible to that event's recap. This is how they get put right. */}
        {canEdit && onItemUpdated && events && events.length > 0 && (
          <div className="mt-3 flex items-center gap-2">
            <label className="font-mono-label text-muted-foreground text-[10px]">
              {t('media.eventTag')}
            </label>
            <select
              value={item.event_id ?? ''}
              onChange={(e) => retag(e.target.value)}
              disabled={saving}
              className="bg-input border border-border px-2 py-1 text-xs text-foreground focus:border-accent outline-none disabled:opacity-50"
            >
              <option value="">{t('media.noEvent')}</option>
              {events.map((ev) => (
                <option key={ev.id} value={ev.id}>{ev.title}</option>
              ))}
            </select>
          </div>
        )}
      </div>
    </div>
  )
}
