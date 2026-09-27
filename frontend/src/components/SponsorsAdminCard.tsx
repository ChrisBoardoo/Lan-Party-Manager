import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { sponsorsApi } from '../lib/api'
import { Sponsor } from '../types'
import Button from './ui/Button'
import ExternalLinkButton from './ui/ExternalLink'
import { Plus, Trash2, Check, X, ImagePlus, Megaphone, ExternalLink } from 'lucide-react'

/** Admin-only per-event sponsor manager, shown on the event detail page. */
export default function SponsorsAdminCard({ eventId }: { eventId: number }) {
  const { t } = useTranslation()
  const [sponsors, setSponsors] = useState<Sponsor[]>([])
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [link, setLink] = useState('')
  const [saving, setSaving] = useState(false)
  const [uploadingId, setUploadingId] = useState<number | null>(null)
  const bannerInputs = useRef<Record<number, HTMLInputElement | null>>({})

  const load = () => { sponsorsApi.getForEvent(eventId).then(setSponsors).catch(() => {}) }
  useEffect(() => { load() }, [eventId])

  const handleAdd = async () => {
    if (!name.trim()) return
    setSaving(true)
    try {
      await sponsorsApi.create({ event_id: eventId, name: name.trim(), link_url: link.trim() || null })
      setName(''); setLink(''); setShowForm(false)
      load()
    } finally {
      setSaving(false)
    }
  }

  const handleBanner = async (id: number, file?: File) => {
    if (!file) return
    setUploadingId(id)
    try {
      await sponsorsApi.uploadBanner(id, file)
      load()
    } finally {
      setUploadingId(null)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm(t('sponsors.deleteConfirm'))) return
    await sponsorsApi.delete(id)
    load()
  }

  return (
    <div className="border border-border bg-card p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <p className="font-mono-label text-accent flex items-center gap-1.5">
          <Megaphone size={12} strokeWidth={1.5} /> {t('sponsors.manageTitle')}
        </p>
        {!showForm && (
          <Button size="sm" variant="outline" onClick={() => setShowForm(true)}>
            <Plus size={12} /> {t('sponsors.add')}
          </Button>
        )}
      </div>

      {showForm && (
        <div className="border border-accent bg-background p-4 mb-4 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="font-mono-label text-muted-foreground block mb-1.5">{t('sponsors.nameLabel')}</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('sponsors.namePlaceholder')}
                className="w-full h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none"
                autoFocus
              />
            </div>
            <div>
              <label className="font-mono-label text-muted-foreground block mb-1.5">{t('sponsors.linkLabel')}</label>
              <input
                value={link}
                onChange={(e) => setLink(e.target.value)}
                placeholder="https://…"
                className="w-full h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={handleAdd} disabled={saving || !name.trim()}>
              <Check size={12} /> {saving ? t('common.saving') : t('sponsors.add')}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => { setShowForm(false); setName(''); setLink('') }}>
              <X size={12} /> {t('common.cancel')}
            </Button>
          </div>
        </div>
      )}

      {sponsors.length === 0 ? (
        <p className="font-mono-label text-muted-foreground text-xs">{t('sponsors.emptyManage')}</p>
      ) : (
        <div className="space-y-2">
          {sponsors.map((s) => (
            <div key={s.id} className="flex items-center gap-3 px-3 py-2 border border-border">
              <div className="w-24 h-10 bg-muted border border-border flex items-center justify-center overflow-hidden flex-shrink-0">
                {s.banner_url ? (
                  s.banner_type === 'video' ? (
                    <video src={s.banner_url} className="w-full h-full object-contain" muted loop autoPlay playsInline />
                  ) : (
                    <img src={s.banner_url} alt={s.name} className="w-full h-full object-contain" />
                  )
                ) : (
                  <span className="font-mono-label text-muted-foreground text-[10px]">{t('sponsors.noBanner')}</span>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-foreground truncate">{s.name}</p>
                {s.link_url && (
                  <ExternalLinkButton href={s.link_url} className="font-mono-label text-muted-foreground text-[10px] flex items-center gap-1 hover:text-accent truncate">
                    <ExternalLink size={9} /> {s.link_url}
                  </ExternalLinkButton>
                )}
              </div>
              <input
                ref={(el) => { bannerInputs.current[s.id] = el }}
                type="file"
                accept="image/png,image/gif,video/webm"
                className="hidden"
                onChange={(e) => handleBanner(s.id, e.target.files?.[0])}
              />
              <Button
                size="sm"
                variant="outline"
                onClick={() => bannerInputs.current[s.id]?.click()}
                disabled={uploadingId === s.id}
              >
                <ImagePlus size={12} /> {uploadingId === s.id ? t('sponsors.uploading') : t('sponsors.banner')}
              </Button>
              <button
                onClick={() => handleDelete(s.id)}
                className="p-1.5 text-muted-foreground hover:text-red-400 transition-colors"
                title={t('common.delete')}
              >
                <Trash2 size={13} strokeWidth={1.5} />
              </button>
            </div>
          ))}
        </div>
      )}

      <p className="font-mono-label text-muted-foreground/60 text-[10px] mt-3">{t('sponsors.formatsHint')}</p>
    </div>
  )
}
