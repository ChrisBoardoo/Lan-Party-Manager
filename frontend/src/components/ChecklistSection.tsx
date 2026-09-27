import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CalendarPlus, Check, Download, Lock, Plus, Sparkles, Trash2 } from 'lucide-react'
import { checklistApi } from '../lib/api'
import { isEmbeddedInDesktop, requestOpenExternal } from '../lib/desktopBridge'
import { buildGoogleCalendarUrl, downloadIcsFile } from '../lib/calendar'
import { CHECKLIST_FIXED_FIELDS, MAX_CHECKLIST_CUSTOM_FIELDS } from '../types'
import type { Checklist, ChecklistSuggestion, LanEvent } from '../types'
import Button from './ui/Button'

// A member's PRIVATE per-event packing checklist — nobody else ever sees these
// rows, not even an admin (mirrors the backend's owner-only routes). Every
// toggle saves the whole state immediately (same simplicity as My Setup's
// whole-state PUT) rather than needing an explicit Save button.
export default function ChecklistSection({ eventId, event }: { eventId: number; event: LanEvent }) {
  const { t } = useTranslation()

  const [data, setData] = useState<Checklist | null>(null)
  const [suggestion, setSuggestion] = useState<ChecklistSuggestion | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [carryoverDismissed, setCarryoverDismissed] = useState(false)
  const [newFieldLabel, setNewFieldLabel] = useState('')

  useEffect(() => {
    setLoading(true)
    Promise.all([
      checklistApi.getForEvent(eventId).then(setData).catch(() => setData(null)),
      checklistApi.suggestions().then(setSuggestion).catch(() => setSuggestion(null)),
    ]).finally(() => setLoading(false))
  }, [eventId])

  if (loading) {
    return (
      <div className="border border-border bg-card p-8 text-center">
        <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
      </div>
    )
  }
  if (!data) return null

  const save = async (items: Checklist['items'], customFields: Checklist['custom_fields']) => {
    setBusy(true)
    try {
      const updated = await checklistApi.save(eventId, {
        items,
        custom_fields: customFields.map((f) => ({ label: f.label, checked: f.checked })),
      })
      setData(updated)
    } finally {
      setBusy(false)
    }
  }

  const toggleFixed = (key: (typeof CHECKLIST_FIXED_FIELDS)[number]) => {
    if (busy) return
    save({ ...data.items, [key]: !data.items[key] }, data.custom_fields)
  }

  const toggleCustom = (id: number) => {
    if (busy) return
    save(data.items, data.custom_fields.map((f) => (f.id === id ? { ...f, checked: !f.checked } : f)))
  }

  const removeCustom = (id: number) => {
    if (busy) return
    save(data.items, data.custom_fields.filter((f) => f.id !== id))
  }

  const addCustom = () => {
    const label = newFieldLabel.trim()
    if (!label || data.custom_fields.length >= MAX_CHECKLIST_CUSTOM_FIELDS || busy) return
    save(data.items, [...data.custom_fields, { id: -Date.now(), label, checked: false }])
    setNewFieldLabel('')
  }

  const confirmCarryover = async () => {
    setBusy(true)
    try {
      const updated = await checklistApi.carryover(eventId)
      setData(updated)
    } finally {
      setBusy(false)
      setCarryoverDismissed(true)
    }
  }

  const showCarryover = !data.started && !carryoverDismissed && !!suggestion
  const atCap = data.custom_fields.length >= MAX_CHECKLIST_CUSTOM_FIELDS

  return (
    <div className="space-y-4">
      {/* Privacy note + progress */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <span className="font-mono-label text-muted-foreground text-xs flex items-center gap-1.5">
          <Lock size={12} /> {t('checklist.privateHint')}
        </span>
        <span className="font-mono-label text-accent text-xs">
          {t('checklist.progress', { checked: data.progress_checked, total: data.progress_total })}
        </span>
      </div>

      {/* Carryover — your usual list from last time */}
      {showCarryover && suggestion && (
        <div className="border border-accent/40 bg-accent/5 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles size={15} className="text-accent" />
            <p className="font-mono-label text-foreground text-sm">{t('checklist.carryoverTitle')}</p>
          </div>
          <p className="text-xs text-muted-foreground mb-3">
            {t('checklist.carryoverHint', { title: suggestion.source_event_title })}
          </p>
          <div className="flex items-center gap-3">
            <Button size="sm" onClick={confirmCarryover} disabled={busy}>
              {t('checklist.carryoverConfirm')}
            </Button>
            <button onClick={() => setCarryoverDismissed(true)} className="font-mono-label text-xs text-muted-foreground hover:text-foreground">
              {t('checklist.carryoverDismiss')}
            </button>
          </div>
        </div>
      )}

      {/* Fixed items */}
      <div className="border border-border bg-card">
        {CHECKLIST_FIXED_FIELDS.map((key) => (
          <label key={key} className="flex items-center gap-3 px-4 py-3 border-b border-border last:border-0 cursor-pointer hover:bg-muted/50">
            <input type="checkbox" checked={data.items[key]} onChange={() => toggleFixed(key)} disabled={busy} />
            <span className="text-sm text-foreground">{t(`checklist.field.${key}`)}</span>
          </label>
        ))}
      </div>

      {/* Custom fields */}
      <div className="border border-border bg-card">
        {data.custom_fields.length > 0 && (
          <div>
            {data.custom_fields.map((f) => (
              <div key={f.id} className="flex items-center justify-between px-4 py-3 border-b border-border last:border-0">
                <label className="flex items-center gap-3 cursor-pointer min-w-0">
                  <input type="checkbox" checked={f.checked} onChange={() => toggleCustom(f.id)} disabled={busy} />
                  <span className="text-sm text-foreground truncate">{f.label}</span>
                </label>
                <button onClick={() => removeCustom(f.id)} disabled={busy} className="text-muted-foreground hover:text-red-400 flex-shrink-0">
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="flex flex-wrap gap-2 p-4">
          <input
            value={newFieldLabel}
            onChange={(e) => setNewFieldLabel(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addCustom()}
            placeholder={atCap ? t('checklist.customFieldMaxReached') : t('checklist.customFieldPlaceholder')}
            maxLength={80}
            disabled={atCap}
            className="flex-1 min-w-[180px] bg-muted border border-border px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-accent outline-none disabled:opacity-50"
          />
          <Button size="sm" variant="outline" onClick={addCustom} disabled={busy || atCap || !newFieldLabel.trim()}>
            <Plus size={13} /> {t('checklist.addCustomField')}
          </Button>
        </div>
      </div>

      {/* Add to calendar — the whole event, not per-item */}
      <div className="border border-border bg-card p-4">
        <p className="font-mono-label text-foreground text-sm mb-3">{t('checklist.addToCalendarTitle')}</p>
        <div className="flex flex-wrap gap-2">
          {isEmbeddedInDesktop() ? (
            <Button size="sm" variant="outline" onClick={() => requestOpenExternal(buildGoogleCalendarUrl(event))}>
              <CalendarPlus size={13} /> {t('checklist.googleCalendar')}
            </Button>
          ) : (
            <a href={buildGoogleCalendarUrl(event)} target="_blank" rel="noopener noreferrer">
              <Button size="sm" variant="outline">
                <CalendarPlus size={13} /> {t('checklist.googleCalendar')}
              </Button>
            </a>
          )}
          <Button size="sm" variant="outline" onClick={() => downloadIcsFile(event)}>
            <Download size={13} /> {t('checklist.downloadIcs')}
          </Button>
        </div>
      </div>

      {data.progress_checked === data.progress_total && (
        <p className="font-mono-label text-accent text-xs flex items-center gap-1.5">
          <Check size={13} /> {t('checklist.allPacked')}
        </p>
      )}
    </div>
  )
}
