import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ShoppingCart, Plus, Trash2, Download, Upload } from 'lucide-react'
import { groceriesApi } from '../lib/api'
import type { GroceryEvent, GroceryItem, GroceryImportResult, EventAttendee } from '../types'
import { useAuth } from '../contexts/AuthContext'
import Button from './ui/Button'
import { buildCsv, csvFormatFor, downloadCsv, parseCsv } from '../lib/csv'

const TRUTHY = new Set(['oui', 'yes', 'true', '1', 'x'])

// The per-event groceries ("courses") list: any attendee can add a food/drink
// item, assign who's buying it (a dropdown built from the event's own attendee
// list), and tick it off once bought. No price field on purpose — cost
// splitting stays in Treasury, entered by hand by the treasurer. Self-contained
// (fetches its own data with its own catch) so a disabled/empty groceries
// feature never takes the event page down.
export default function GroceriesSection({ eventId, attendees }: { eventId: number; attendees: EventAttendee[] }) {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [data, setData] = useState<GroceryEvent | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const [category, setCategory] = useState('')
  const [name, setName] = useState('')
  const [quantity, setQuantity] = useState('')
  const [assignedTo, setAssignedTo] = useState('')

  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<GroceryImportResult | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const load = () => groceriesApi.getForEvent(eventId).then(setData).catch(() => setData(null))

  useEffect(() => {
    setLoading(true)
    groceriesApi.getForEvent(eventId).then(setData).catch(() => setData(null)).finally(() => setLoading(false))
  }, [eventId])

  const items = data?.items ?? []

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    try { await fn(); load() } finally { setBusy(false) }
  }

  const addItem = () => {
    if (!name.trim()) return
    run(async () => {
      await groceriesApi.add(eventId, {
        category: category.trim() || null,
        name: name.trim(),
        quantity: quantity.trim() || null,
        assigned_to: assignedTo ? parseInt(assignedTo, 10) : null,
      })
      setCategory(''); setName(''); setQuantity(''); setAssignedTo('')
    })
  }

  const canManage = (item: GroceryItem) => isAdmin || item.created_by === user?.id || item.assigned_to === user?.id

  const reassign = (item: GroceryItem, value: string) => {
    run(() => groceriesApi.update(item.id, { assigned_to: value ? parseInt(value, 10) : null }))
  }

  const toggleBought = (item: GroceryItem) => {
    run(() => groceriesApi.update(item.id, { is_bought: !item.is_bought }))
  }

  // Column order (category, item, quantity, who's buying, bought) is fixed
  // regardless of UI language — the header *text* is localized for
  // readability, but import reads by position, not by matching header
  // strings, so an export made in French still re-imports fine in English.
  // The separator follows the language too (";" in French, see lib/csv.ts);
  // the import detects it, so any export re-imports whichever language reads it.
  const exportCsv = () => {
    const header = [
      t('groceries.categoryHeader'), t('groceries.itemHeader'), t('groceries.quantityHeader'),
      t('groceries.assignedHeader'), t('groceries.boughtHeader'),
    ]
    const rows = [
      header,
      ...items.map((i) => [
        i.category ?? '', i.name, i.quantity ?? '', i.assigned_username ?? '',
        i.is_bought ? t('groceries.csvYes') : t('groceries.csvNo'),
      ]),
    ]
    downloadCsv(buildCsv(rows, csvFormatFor(i18n.language)), `groceries-event-${eventId}.csv`)
  }

  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = '' // allow re-selecting the same file next time
    if (!file) return

    const rows = parseCsv(await file.text())
    const dataRows = rows.slice(1) // skip the header row, whatever it says
    const parsed = dataRows
      .map((r) => ({
        category: (r[0] ?? '').trim() || null,
        name: (r[1] ?? '').trim(),
        quantity: (r[2] ?? '').trim() || null,
        assigned_username: (r[3] ?? '').trim() || null,
        is_bought: TRUTHY.has((r[4] ?? '').trim().toLowerCase()),
      }))
      .filter((row) => row.name.length > 0)
    if (parsed.length === 0) return

    setImporting(true)
    setImportResult(null)
    try {
      const result = await groceriesApi.import(eventId, parsed)
      setImportResult(result)
      load()
    } finally {
      setImporting(false)
    }
  }

  if (loading) {
    return (
      <div className="border border-border bg-card p-8 text-center">
        <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <span className="font-mono-label text-muted-foreground text-xs flex items-center gap-1.5">
          <ShoppingCart size={13} /> {t('groceries.progress', { bought: data?.bought_count ?? 0, total: data?.total_count ?? 0 })}
        </span>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={exportCsv} disabled={items.length === 0}>
            <Download size={13} /> {t('groceries.exportButton')}
          </Button>
          <input
            ref={fileInputRef} type="file" accept=".csv,text/csv" className="hidden"
            onChange={handleImportFile}
          />
          <Button size="sm" variant="outline" onClick={() => fileInputRef.current?.click()} disabled={importing}>
            <Upload size={13} /> {importing ? t('common.loading') : t('groceries.importButton')}
          </Button>
        </div>
      </div>

      {importResult && (
        <p className="text-xs text-muted-foreground">
          {t('groceries.importSummary', { count: importResult.imported })}
          {importResult.unmatched_usernames.length > 0 && (
            <span className="text-accent"> — {t('groceries.importUnmatched', { names: importResult.unmatched_usernames.join(', ') })}</span>
          )}
        </p>
      )}

      {/* List */}
      <div className="border border-border bg-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted">
              <th className="px-4 py-2 text-left font-mono-label text-muted-foreground">{t('groceries.categoryHeader')}</th>
              <th className="px-4 py-2 text-left font-mono-label text-muted-foreground">{t('groceries.itemHeader')}</th>
              <th className="px-4 py-2 text-left font-mono-label text-muted-foreground">{t('groceries.quantityHeader')}</th>
              <th className="px-4 py-2 text-left font-mono-label text-muted-foreground">{t('groceries.assignedHeader')}</th>
              <th className="px-4 py-2 text-center font-mono-label text-muted-foreground">{t('groceries.boughtHeader')}</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-sm text-muted-foreground">{t('groceries.empty')}</td>
              </tr>
            ) : (
              items.map((item) => {
                const manage = canManage(item)
                return (
                  <tr key={item.id} className={`border-b border-border last:border-0 ${item.is_bought ? 'opacity-50' : ''}`}>
                    <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{item.category || '—'}</td>
                    <td className="px-4 py-3 font-medium text-foreground">{item.name}</td>
                    <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{item.quantity || '—'}</td>
                    <td className="px-4 py-3">
                      {manage ? (
                        <select
                          value={item.assigned_to ?? ''}
                          onChange={(e) => reassign(item, e.target.value)}
                          disabled={busy}
                          className="bg-muted border border-border px-2 py-1 text-sm text-foreground focus:border-accent outline-none max-w-[160px]"
                        >
                          <option value="">{t('groceries.unassigned')}</option>
                          {attendees.map((a) => (
                            <option key={a.user_id} value={a.user_id}>{a.username}</option>
                          ))}
                        </select>
                      ) : (
                        <span className="text-muted-foreground">{item.assigned_username ?? t('groceries.unassigned')}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <input
                        type="checkbox"
                        checked={item.is_bought}
                        disabled={!manage || busy}
                        onChange={() => toggleBought(item)}
                        className="accent-accent"
                      />
                    </td>
                    <td className="px-4 py-3 text-right">
                      {manage && (
                        <button onClick={() => run(() => groceriesApi.delete(item.id))} disabled={busy} className="text-muted-foreground hover:text-red-400">
                          <Trash2 size={13} />
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Add an item */}
      <div className="border border-border bg-card p-4">
        <p className="font-mono-label text-foreground text-sm mb-3">{t('groceries.addTitle')}</p>
        <div className="flex flex-wrap gap-2">
          <input
            value={category} onChange={(e) => setCategory(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addItem()}
            placeholder={t('groceries.categoryPlaceholder')} maxLength={60}
            className="w-32 bg-muted border border-border px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-accent outline-none"
          />
          <input
            value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addItem()}
            placeholder={t('groceries.namePlaceholder')} maxLength={120}
            className="flex-1 min-w-[160px] bg-muted border border-border px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-accent outline-none"
          />
          <input
            value={quantity} onChange={(e) => setQuantity(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addItem()}
            placeholder={t('groceries.quantityPlaceholder')} maxLength={40}
            className="w-28 bg-muted border border-border px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-accent outline-none"
          />
          <select
            value={assignedTo} onChange={(e) => setAssignedTo(e.target.value)}
            className="bg-muted border border-border px-3 py-2 text-sm text-foreground focus:border-accent outline-none"
          >
            <option value="">{t('groceries.unassigned')}</option>
            {attendees.map((a) => (
              <option key={a.user_id} value={a.user_id}>{a.username}</option>
            ))}
          </select>
          <Button size="sm" onClick={addItem} disabled={busy || !name.trim()}>
            <Plus size={13} /> {t('groceries.addButton')}
          </Button>
        </div>
      </div>
    </div>
  )
}
