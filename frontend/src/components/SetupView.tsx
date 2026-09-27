import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SETUP_FIELDS, SetupComponents, SetupCustomField, SetupPhoto } from '../types'
import PhotoLightbox from './ui/PhotoLightbox'

/** Read-only render of a setup — the parts list and the photos.
 *
 *  Shared by the in-app view (a member looking at someone's profile) and the
 *  public share page, so the two can never drift into showing different things.
 *  It takes only the fields both have in common: no user_id, no role, no
 *  presence. The public payload's shape is the floor.
 */
export default function SetupView({
  components,
  customFields,
  photos,
}: {
  components: SetupComponents
  customFields: SetupCustomField[]
  photos: SetupPhoto[]
}) {
  const { t } = useTranslation()
  const [viewerIndex, setViewerIndex] = useState<number | null>(null)

  const filled = SETUP_FIELDS.filter((key) => components[key])
  const rows: { label: string; value: string }[] = [
    ...filled.map((key) => ({ label: t(`setup.field.${key}`), value: components[key] as string })),
    ...customFields.filter((f) => f.value).map((f) => ({ label: f.label, value: f.value as string })),
  ]

  return (
    <>
      {photos.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-8">
          {photos.map((photo, i) => (
            <button
              key={photo.id}
              onClick={() => setViewerIndex(i)}
              className="relative aspect-video overflow-hidden border border-border bg-card group"
            >
              <img
                src={photo.url}
                alt={photo.caption || ''}
                className="w-full h-full object-cover group-hover:opacity-80 transition-opacity"
              />
              {photo.caption && (
                <span className="absolute inset-x-0 bottom-0 bg-background/80 px-2 py-1 text-left">
                  <span className="font-mono-label text-muted-foreground text-[10px] line-clamp-1">
                    {photo.caption}
                  </span>
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {rows.length > 0 ? (
        <div className="border border-border bg-card divide-y divide-border">
          {rows.map((row, i) => (
            <div key={i} className="flex items-baseline gap-4 px-4 py-3">
              <span className="font-mono-label text-muted-foreground text-[10px] w-32 shrink-0">
                {row.label}
              </span>
              <span className="text-foreground text-sm break-words min-w-0">{row.value}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="font-mono-label text-muted-foreground text-sm border border-border bg-card p-5">
          {t('setup.empty')}
        </p>
      )}

      {viewerIndex !== null && (
        <PhotoLightbox photos={photos} index={viewerIndex} onClose={() => setViewerIndex(null)} />
      )}
    </>
  )
}
