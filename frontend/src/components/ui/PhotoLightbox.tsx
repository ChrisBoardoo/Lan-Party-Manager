import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, ChevronLeft, ChevronRight } from 'lucide-react'

/**
 * A minimal fullscreen viewer for a plain list of captioned images.
 *
 * Purpose-built rather than reusing the media Lightbox: a setup photo is just a
 * url + an optional caption. The media Lightbox wants a full MediaItem
 * (file_size, uploader, mime_type, reactions…), and the first cut of My Setup
 * fed it a *fabricated* one — file_size 0, an empty uploader — which it then
 * displayed verbatim as "0 B" and "By " with no name. An adapter that invents
 * data isn't an adapter; it's the UI reading a lie aloud. This shows only the
 * two facts a setup photo actually has.
 */
export default function PhotoLightbox({
  photos,
  index,
  onClose,
}: {
  photos: { id: number; url: string; caption: string | null }[]
  index: number
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [cur, setCur] = useState(index)
  const touchStartX = useRef<number | null>(null)

  useEffect(() => setCur(index), [index])

  const count = photos.length
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

  const photo = photos[cur]
  if (!photo) return null

  const onTouchStart = (e: React.TouchEvent) => { touchStartX.current = e.changedTouches[0].clientX }
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
      <button
        onClick={onClose}
        aria-label={t('media.close')}
        className="absolute top-3 right-3 sm:top-4 sm:right-4 p-2 text-muted-foreground hover:text-foreground transition-colors z-10"
      >
        <X size={22} strokeWidth={1.5} />
      </button>

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
        <div className="flex-1 flex items-center justify-center overflow-hidden border border-border bg-card">
          <img
            key={photo.id}
            src={photo.url}
            alt={photo.caption || ''}
            className="max-w-full max-h-[80vh] object-contain"
          />
        </div>

        <div className="flex items-center justify-between gap-3 mt-3">
          {photo.caption ? (
            <p className="font-mono-label text-muted-foreground text-sm min-w-0">{photo.caption}</p>
          ) : (
            <span />
          )}
          {hasMany && (
            <span className="font-mono-label text-muted-foreground text-[10px] shrink-0 tabular-nums">
              {cur + 1} / {count}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
