import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Archive, ArchiveRestore, ImagePlus, Pencil, Plus, Trash2, X, Check } from 'lucide-react'
import { trophiesApi } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import type { Trophy } from '../../types'
import Button from '../ui/Button'
import TrophyIcon from './TrophyIcon'

// Settings > "Trophy cabinet": the instance's trophy definitions. Awarding them
// happens per event, on the event page (EventTrophiesSection).

interface Draft {
  emoji: string
  name: string
  description: string
}

const EMPTY: Draft = { emoji: '', name: '', description: '' }

function TrophyForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial: Draft
  submitLabel: string
  onSubmit: (d: Draft) => Promise<void>
  onCancel?: () => void
}) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState(initial)
  const [saving, setSaving] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!draft.name.trim()) return
    setSaving(true)
    try {
      await onSubmit(draft)
      setDraft(initial)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <div className="flex gap-2">
        <input
          value={draft.emoji}
          onChange={(e) => setDraft({ ...draft, emoji: e.target.value })}
          placeholder="🏆"
          maxLength={16}
          aria-label={t('trophies.emojiLabel')}
          className="w-14 h-10 px-2 text-center bg-input border border-border text-foreground text-lg focus:border-accent outline-none"
        />
        <input
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          placeholder={t('trophies.namePlaceholder')}
          maxLength={60}
          required
          className="flex-1 min-w-0 h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none"
        />
      </div>
      <input
        value={draft.description}
        onChange={(e) => setDraft({ ...draft, description: e.target.value })}
        placeholder={t('trophies.descriptionPlaceholder')}
        maxLength={300}
        className="w-full h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none"
      />
      <div className="flex gap-2">
        <Button size="sm" type="submit" disabled={saving || !draft.name.trim()}>
          {onCancel ? <Check size={12} /> : <Plus size={12} />} {submitLabel}
        </Button>
        {onCancel && (
          <Button size="sm" variant="ghost" type="button" onClick={onCancel}>{t('common.cancel')}</Button>
        )}
      </div>
    </form>
  )
}

function TrophyRow({ trophy, onChange }: { trophy: Trophy; onChange: () => void }) {
  const { t } = useTranslation()
  const { push } = useToast()
  const [editing, setEditing] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const archived = !!trophy.archived_at

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn()
      onChange()
    } catch {
      push(t('trophies.actionFailed'), 'error')
    }
  }

  const pickImage = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) act(() => trophiesApi.uploadImage(trophy.id, file))
    e.target.value = ''
  }

  if (editing) {
    return (
      <div className="px-4 py-4 border-b border-border last:border-0">
        <TrophyForm
          initial={{ emoji: trophy.emoji ?? '', name: trophy.name, description: trophy.description ?? '' }}
          submitLabel={t('common.save')}
          onCancel={() => setEditing(false)}
          onSubmit={async (d) => {
            await act(() => trophiesApi.update(trophy.id, { name: d.name, emoji: d.emoji || null, description: d.description || null }))
            setEditing(false)
          }}
        />
      </div>
    )
  }

  return (
    <div className={`px-4 py-4 border-b border-border last:border-0 flex items-start gap-3 ${archived ? 'opacity-50' : ''}`}>
      <TrophyIcon trophy={trophy} />
      <div className="flex-1 min-w-0">
        <p className="font-bold text-foreground">{trophy.name}</p>
        {trophy.description && <p className="text-xs text-muted-foreground">{trophy.description}</p>}
        <p className="font-mono-label text-muted-foreground text-[10px] mt-1">
          {trophy.awarded_count === 0
            ? t('trophies.neverAwarded')
            : t('trophies.awardedCount', { count: trophy.awarded_count })}
          {trophy.last_award && ` · ${t('trophies.lastAward', trophy.last_award)}`}
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={pickImage} />
        <button onClick={() => fileRef.current?.click()} title={t('trophies.uploadImage')} className="text-muted-foreground hover:text-foreground">
          <ImagePlus size={14} />
        </button>
        {trophy.image_url && (
          <button onClick={() => act(() => trophiesApi.removeImage(trophy.id))} title={t('trophies.removeImage')} className="text-muted-foreground hover:text-foreground">
            <X size={14} />
          </button>
        )}
        <button onClick={() => setEditing(true)} title={t('common.edit')} className="text-muted-foreground hover:text-foreground">
          <Pencil size={14} />
        </button>
        <button
          onClick={() => act(() => trophiesApi.update(trophy.id, { archived: !archived }))}
          title={archived ? t('trophies.unarchive') : t('trophies.archive')}
          className="text-muted-foreground hover:text-foreground"
        >
          {archived ? <ArchiveRestore size={14} /> : <Archive size={14} />}
        </button>
        {trophy.awarded_count === 0 && (
          <button
            onClick={() => confirm(t('trophies.deleteConfirm', { name: trophy.name })) && act(() => trophiesApi.remove(trophy.id))}
            title={t('common.delete')}
            className="text-muted-foreground hover:text-red-400"
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>
    </div>
  )
}

export default function TrophiesAdminCard() {
  const { t } = useTranslation()
  const { push } = useToast()
  const [trophies, setTrophies] = useState<Trophy[] | null>(null)
  const [prefill, setPrefill] = useState<Draft>(EMPTY)
  const [formKey, setFormKey] = useState(0)

  const load = () => trophiesApi.list().then(setTrophies).catch(() => setTrophies([]))
  useEffect(() => { load() }, [])

  // Inspiration only — the crew writes its own. Picking one pre-fills the form.
  const ideas = t('trophies.ideas', { returnObjects: true }) as unknown
  const ideaList = Array.isArray(ideas) ? (ideas as string[]) : []

  const applyIdea = (idea: string) => {
    const [emoji, ...rest] = idea.split(' ')
    setPrefill({ emoji, name: rest.join(' '), description: '' })
    setFormKey((k) => k + 1)
  }

  return (
    <div className="space-y-4">
      <div className="border border-border bg-card p-4">
        <p className="font-mono-label text-foreground mb-3">{t('trophies.newTrophy')}</p>
        <TrophyForm
          key={formKey}
          initial={prefill}
          submitLabel={t('common.create')}
          onSubmit={async (d) => {
            try {
              await trophiesApi.create({ name: d.name, emoji: d.emoji || null, description: d.description || null })
              setPrefill(EMPTY)
              setFormKey((k) => k + 1)
              await load()
            } catch {
              push(t('trophies.actionFailed'), 'error')
            }
          }}
        />
        {ideaList.length > 0 && (
          <div className="mt-4">
            <p className="font-mono-label text-muted-foreground text-[10px] mb-2">{t('trophies.ideasLabel')}</p>
            <div className="flex flex-wrap gap-1.5">
              {ideaList.map((idea) => (
                <button
                  key={idea}
                  type="button"
                  onClick={() => applyIdea(idea)}
                  className="px-2 py-1 border border-border text-xs text-muted-foreground hover:text-foreground hover:border-border-hover transition-colors"
                >
                  {idea}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="border border-border bg-card">
        {trophies === null ? (
          <div className="p-8 text-center">
            <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
          </div>
        ) : trophies.length === 0 ? (
          <p className="p-6 text-center font-mono-label text-muted-foreground">{t('trophies.cabinetEmpty')}</p>
        ) : (
          trophies.map((tr) => <TrophyRow key={tr.id} trophy={tr} onChange={load} />)
        )}
      </div>
    </div>
  )
}
