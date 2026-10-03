import { useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { setupApi } from '../lib/api'
import {
  MAX_SETUP_CUSTOM_FIELDS,
  MAX_SETUP_PHOTOS,
  SETUP_FIELDS,
  Setup,
  SetupComponents,
  SetupFieldKey,
} from '../types'
import Button from './ui/Button'
import Input from './ui/Input'
import QRModal from './ui/QRModal'
import PhotoLightbox from './ui/PhotoLightbox'
import { ReactionBar } from './MediaReactions'
import { Cpu, Plus, X, Camera, Check, Link2, Copy, QrCode, Trash2, Loader2 } from 'lucide-react'

// Narrow to what the backend actually accepts, rather than image/* — offering a
// .bmp the server will refuse is just lying to the file picker.
const ACCEPTED = 'image/jpeg,image/png,image/webp,image/gif'

type ComponentForm = Record<SetupFieldKey, string>

const EMPTY_FORM = Object.fromEntries(SETUP_FIELDS.map((k) => [k, ''])) as ComponentForm

function toForm(components: SetupComponents): ComponentForm {
  return Object.fromEntries(SETUP_FIELDS.map((k) => [k, components[k] ?? ''])) as ComponentForm
}

// ── Share controls ────────────────────────────────────────────────────────────

function ShareControls() {
  const { t } = useTranslation()
  const [token, setToken] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [showQR, setShowQR] = useState(false)

  useEffect(() => {
    // Own effect, own catch — a 404 while the feature is off must never take the
    // profile page down with it.
    setupApi.getShare().then((s) => setToken(s.token)).catch(() => setToken(null))
  }, [])

  const url = token
    ? `${window.location.origin}/setup/shared#token=${encodeURIComponent(token)}`
    : null

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
    <div className="border-t border-border pt-6 mt-6">
      <p className="font-mono-label text-accent flex items-center gap-1.5 mb-2">
        <Link2 size={12} strokeWidth={1.5} /> {t('setup.shareTitle')}
      </p>
      <p className="text-sm text-muted-foreground mb-4">{t('setup.shareDesc')}</p>

      {url ? (
        <>
          <div className="flex items-center gap-2 mb-3">
            <code className="flex-1 bg-input border border-border px-3 py-2 text-xs text-muted-foreground truncate">
              {url}
            </code>
            <button
              onClick={copy}
              aria-label={t('setup.shareCopy')}
              className="p-2 border border-border text-muted-foreground hover:text-accent hover:border-accent transition-colors"
            >
              {copied ? <Check size={14} strokeWidth={1.5} /> : <Copy size={14} strokeWidth={1.5} />}
            </button>
            <button
              onClick={() => setShowQR(true)}
              aria-label={t('setup.shareQR')}
              className="p-2 border border-border text-muted-foreground hover:text-accent hover:border-accent transition-colors"
            >
              <QrCode size={14} strokeWidth={1.5} />
            </button>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => run(setupApi.mintShare)} disabled={busy}>
              {t('setup.shareRotate')}
            </Button>
            <Button size="sm" variant="danger" onClick={() => run(setupApi.revokeShare)} disabled={busy}>
              <Trash2 size={12} strokeWidth={2} /> {t('setup.shareRevoke')}
            </Button>
          </div>
        </>
      ) : (
        <Button size="sm" onClick={() => run(setupApi.mintShare)} disabled={busy}>
          <Link2 size={12} strokeWidth={2} /> {t('setup.shareCreate')}
        </Button>
      )}

      {showQR && url && <QRModal value={url} label={t('setup.shareTitle')} onClose={() => setShowQR(false)} />}
    </div>
  )
}

// ── Photos ────────────────────────────────────────────────────────────────────

function PhotoGrid({ setup, onChange }: { setup: Setup; onChange: (s: Setup) => void }) {
  const { t } = useTranslation()
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [viewerIndex, setViewerIndex] = useState<number | null>(null)
  // Caption drafts, keyed by photo id — committed on blur so a save is one
  // request per edit, not one per keystroke.
  const [captionDrafts, setCaptionDrafts] = useState<Record<number, string>>({})

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError('')
    // try/catch/finally with a surfaced error: the server can legitimately
    // refuse this (too big, wrong format, 6th photo), and a silent no-op would
    // leave the user thinking it worked.
    try {
      onChange(await setupApi.uploadPhoto(file))
    } catch {
      setError(t('setup.photoRejected'))
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const remove = async (photoId: number) => {
    try {
      onChange(await setupApi.deletePhoto(photoId))
    } catch {
      setError(t('setup.photoDeleteFailed'))
    }
  }

  const saveCaption = async (photo: { id: number; caption: string | null }) => {
    const draft = captionDrafts[photo.id]
    if (draft === undefined) return
    const next = draft.trim()
    if (next === (photo.caption ?? '')) return  // unchanged — no request
    try {
      onChange(await setupApi.captionPhoto(photo.id, next || null))
    } catch {
      setError(t('setup.photoCaptionFailed'))
    }
  }

  const full = setup.photos.length >= MAX_SETUP_PHOTOS

  return (
    <div className="mb-6">
      <p className="font-mono-label text-muted-foreground flex items-center gap-1.5 mb-3">
        <Camera size={12} strokeWidth={1.5} /> {t('setup.photos')}
        <span className="text-[10px]">({setup.photos.length}/{MAX_SETUP_PHOTOS})</span>
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {setup.photos.map((photo, i) => (
          <div key={photo.id} className="flex flex-col gap-1.5">
            <div className="relative aspect-video border border-border bg-card group">
              <button
                type="button"
                onClick={() => setViewerIndex(i)}
                className="w-full h-full block"
                aria-label={t('setup.photoOpen')}
              >
                <img src={photo.url} alt={photo.caption || ''} className="w-full h-full object-cover group-hover:opacity-80 transition-opacity" />
              </button>
              <button
                type="button"
                // stopPropagation so removing doesn't also open the viewer.
                onClick={(e) => { e.stopPropagation(); remove(photo.id) }}
                aria-label={t('setup.photoDelete')}
                className="absolute top-1 right-1 p-1 bg-background/80 border border-border text-muted-foreground hover:text-red-400 hover:border-red-400 opacity-0 group-hover:opacity-100 transition-all"
              >
                <X size={12} strokeWidth={1.5} />
              </button>
            </div>
            <input
              type="text"
              maxLength={200}
              defaultValue={photo.caption ?? ''}
              placeholder={t('setup.photoCaptionPlaceholder')}
              onChange={(e) => setCaptionDrafts((prev) => ({ ...prev, [photo.id]: e.target.value }))}
              onBlur={() => saveCaption(photo)}
              onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
              className="w-full bg-input border border-border px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:border-accent outline-none"
            />
          </div>
        ))}

        {/* Hidden at the cap. The server's 400 is the real enforcement; this is
            just not offering something that can't work. */}
        {!full && (
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="aspect-video border border-dashed border-border text-muted-foreground hover:border-accent hover:text-accent transition-colors flex items-center justify-center disabled:opacity-50"
          >
            {uploading ? (
              <Loader2 size={18} strokeWidth={1.5} className="animate-spin" />
            ) : (
              <span className="flex flex-col items-center gap-1">
                <Plus size={18} strokeWidth={1.5} />
                <span className="font-mono-label text-[10px]">{t('setup.photoAdd')}</span>
              </span>
            )}
          </button>
        )}
      </div>

      <input ref={fileRef} type="file" accept={ACCEPTED} className="hidden" onChange={handleFile} />
      {error && <p className="font-mono-label text-red-400 text-[10px] mt-2">{error}</p>}

      {viewerIndex !== null && (
        <PhotoLightbox photos={setup.photos} index={viewerIndex} onClose={() => setViewerIndex(null)} />
      )}
    </div>
  )
}

// ── The card ──────────────────────────────────────────────────────────────────

export default function MySetupCard() {
  const { t } = useTranslation()
  const [setup, setSetup] = useState<Setup | null>(null)
  const [customFields, setCustomFields] = useState<{ label: string; value: string }[]>([])
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  // Its own form and its own save, not the profile's: that form PUTs to
  // /users/{id}, a different resource. One button firing two PUTs would have no
  // atomicity and could half-save.
  const { register, handleSubmit, reset } = useForm<ComponentForm>({ defaultValues: EMPTY_FORM })

  useEffect(() => {
    const load = async () => {
      try {
        const data = await setupApi.getMine()
        setSetup(data)
        // reset(), not defaultValues: RHF captures defaultValues on first render
        // and never re-initializes them from fetched data.
        reset(toForm(data.components))
        setCustomFields(data.custom_fields.map((f) => ({ label: f.label, value: f.value ?? '' })))
      } catch {
        setSetup(null)
      }
    }
    load()
  }, [reset])

  const onSubmit = async (values: ComponentForm) => {
    setSaving(true)
    try {
      const updated = await setupApi.updateMine({
        components: values,
        custom_fields: customFields
          .filter((f) => f.label.trim())
          .map((f) => ({ label: f.label.trim(), value: f.value.trim() || null })),
      })
      setSetup(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } finally {
      setSaving(false)
    }
  }

  if (!setup) return null

  return (
    <section className="mt-8 border border-border bg-card p-6">
      <p className="font-mono-label text-accent flex items-center gap-1.5 mb-2">
        <Cpu size={12} strokeWidth={1.5} /> {t('setup.title')}
      </p>
      <p className="text-sm text-muted-foreground mb-6">{t('setup.desc')}</p>

      {/* What the crew thinks of the rig — read-only here: reacting happens on
          each other's player pages, and your own tally shows up here since
          /players/you redirects to /profile. */}
      {setup.reaction_total > 0 && (
        <div className="mb-6 flex items-center gap-3">
          <span className="font-mono-label text-muted-foreground text-[10px]">
            {t('setup.reactionsTitle')}
          </span>
          <ReactionBar reactions={setup.reactions} />
        </div>
      )}

      <PhotoGrid setup={setup} onChange={setSetup} />

      <form onSubmit={handleSubmit(onSubmit)}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {SETUP_FIELDS.map((key) => (
            <Input
              key={key}
              label={t(`setup.field.${key}`)}
              placeholder={t(`setup.placeholder.${key}`, { defaultValue: '' })}
              {...register(key)}
            />
          ))}
        </div>

        <div className="mt-6">
          <p className="font-mono-label text-muted-foreground mb-3">
            {t('setup.customTitle')}
            <span className="text-[10px] ml-1.5">({customFields.length}/{MAX_SETUP_CUSTOM_FIELDS})</span>
          </p>
          <div className="space-y-3">
            {customFields.map((field, i) => (
              <div key={i} className="flex items-end gap-2">
                <div className="flex-1 min-w-0">
                  <Input
                    label={t('setup.customLabel')}
                    value={field.label}
                    onChange={(e) =>
                      setCustomFields((prev) => prev.map((f, j) => (j === i ? { ...f, label: e.target.value } : f)))
                    }
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <Input
                    label={t('setup.customValue')}
                    value={field.value}
                    onChange={(e) =>
                      setCustomFields((prev) => prev.map((f, j) => (j === i ? { ...f, value: e.target.value } : f)))
                    }
                  />
                </div>
                <button
                  type="button"
                  onClick={() => setCustomFields((prev) => prev.filter((_, j) => j !== i))}
                  aria-label={t('setup.customRemove')}
                  className="p-2 mb-1 text-muted-foreground hover:text-red-400 transition-colors"
                >
                  <X size={16} strokeWidth={1.5} />
                </button>
              </div>
            ))}
          </div>
          {customFields.length < MAX_SETUP_CUSTOM_FIELDS && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="mt-3"
              onClick={() => setCustomFields((prev) => [...prev, { label: '', value: '' }])}
            >
              <Plus size={12} strokeWidth={2} /> {t('setup.customAdd')}
            </Button>
          )}
        </div>

        <div className="mt-6 flex items-center gap-3">
          <Button type="submit" disabled={saving}>
            {saving ? t('common.saving') : t('common.save')}
          </Button>
          {saved && (
            <span className="font-mono-label text-accent flex items-center gap-1.5">
              <Check size={12} strokeWidth={2} /> {t('setup.saved')}
            </span>
          )}
        </div>
      </form>

      <ShareControls />
    </section>
  )
}
