import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowDown, ArrowUp, Eye, EyeOff, GripVertical, RotateCcw, X } from 'lucide-react'
import Button from '../ui/Button'
import { HubBlockId, HubBlockState, HubZone } from '../../types'
import { DEFAULT_HUB_LAYOUT, isDefaultHubLayout, moveHubBlock } from '../../lib/hubLayout'

const ZONES: { zone: HubZone; label: string; title: string }[] = [
  { zone: 'side', label: 'hubLayout.zoneSide', title: 'hubLayout.zoneSideTitle' },
  { zone: 'main', label: 'hubLayout.zoneMain', title: 'hubLayout.zoneMainTitle' },
  { zone: 'full', label: 'hubLayout.zoneFull', title: 'hubLayout.zoneFullTitle' },
]

interface Props {
  layout: HubBlockState[]
  onChange: (layout: HubBlockState[]) => void
  /** Feature switched on: blocks of a disabled feature aren't listed (their
   *  place in the layout is kept for the day it's switched back on). */
  isListed: (id: HubBlockId) => boolean
  /** Has something to show right now (an open chat, a mini-game…). */
  isAvailable: (id: HubBlockId) => boolean
  onSave: () => void
  onCancel: () => void
  saving: boolean
}

/** The Hub's "Customize" panel: a drawer on the right, so the Hub itself stays
 *  visible and previews every change live. Reordering by drag & drop, with
 *  up/down buttons for the keyboard (and touch, where HTML5 drag doesn't fire). */
export default function HubLayoutEditor({ layout, onChange, isListed, isAvailable, onSave, onCancel, saving }: Props) {
  const { t } = useTranslation()
  const [dragIndex, setDragIndex] = useState<number | null>(null)

  const update = (index: number, patch: Partial<HubBlockState>) =>
    onChange(layout.map((b, i) => (i === index ? { ...b, ...patch } : b)))

  // Up/down skip the blocks that aren't listed, otherwise a click would look
  // like it did nothing (swapped with an invisible neighbour).
  const neighbour = (index: number, step: 1 | -1) => {
    for (let i = index + step; i >= 0 && i < layout.length; i += step) if (isListed(layout[i].id)) return i
    return -1
  }

  return (
    <aside
      className="fixed right-0 top-14 bottom-0 z-40 w-[22rem] max-w-full bg-card border-l border-border flex flex-col shadow-2xl"
      aria-label={t('hubLayout.title')}
    >
      <div className="flex items-start justify-between gap-3 px-5 pt-5 pb-3 border-b border-border">
        <div>
          <p className="font-mono-label text-accent mb-1">{t('hubLayout.title')}</p>
          <p className="text-xs text-muted-foreground leading-relaxed">{t('hubLayout.hint')}</p>
        </div>
        <button
          type="button"
          onClick={onCancel}
          className="p-1 text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
          title={t('common.cancel')}
          aria-label={t('common.cancel')}
        >
          <X size={16} strokeWidth={1.5} />
        </button>
      </div>

      <ol className="flex-1 overflow-y-auto py-2">
        {layout.map((b, i) => {
          if (!isListed(b.id)) return null
          const up = neighbour(i, -1)
          const down = neighbour(i, 1)
          return (
            // Drag & drop is the mouse shortcut; the ↑/↓ buttons below are the
            // keyboard (and touch) path, hence the rule switched off for the row.
            // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
            <li
              key={b.id}
              draggable
              onDragStart={(e) => {
                setDragIndex(i)
                e.dataTransfer.effectAllowed = 'move'
                // Firefox won't start a drag without some data set.
                e.dataTransfer.setData('text/plain', b.id)
              }}
              onDragEnter={() => {
                if (dragIndex === null || dragIndex === i) return
                onChange(moveHubBlock(layout, dragIndex, i))
                setDragIndex(i)
              }}
              onDragOver={(e) => e.preventDefault()}
              onDragEnd={() => setDragIndex(null)}
              className={`mx-3 my-1 border px-2 py-2 flex items-center gap-2 transition-colors ${
                dragIndex === i ? 'border-accent bg-accent/5' : 'border-border bg-background'
              } ${b.hidden ? 'opacity-60' : ''}`}
            >
              <span className="cursor-grab active:cursor-grabbing text-muted-foreground" title={t('hubLayout.dragHandle')}>
                <GripVertical size={14} strokeWidth={1.5} />
              </span>
              {/* Width selector under the name, not beside it: on one line the
                  longer names ("Raccourcis Arène / Trésorerie") were truncated. */}
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-bold truncate ${b.hidden ? 'text-muted-foreground line-through' : 'text-foreground'}`}>
                  {t(`hubLayout.blocks.${b.id}`)}
                </p>
                <div className="mt-1.5 flex items-center gap-2 min-w-0">
                  <div className="flex border border-border flex-shrink-0" role="group" aria-label={t('hubLayout.width')}>
                    {ZONES.map(({ zone, label, title }) => (
                      <button
                        key={zone}
                        type="button"
                        onClick={() => update(i, { zone })}
                        disabled={b.hidden}
                        aria-pressed={b.zone === zone}
                        title={t(title)}
                        className={`px-1.5 py-0.5 font-mono-label text-[10px] transition-colors disabled:opacity-40 ${
                          b.zone === zone ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:text-foreground'
                        }`}
                      >
                        {t(label)}
                      </button>
                    ))}
                  </div>
                  {!isAvailable(b.id) && !b.hidden && (
                    <p className="font-mono-label text-muted-foreground text-[10px] truncate">{t('hubLayout.unavailable')}</p>
                  )}
                </div>
              </div>
              <button
                type="button"
                onClick={() => update(i, { hidden: !b.hidden })}
                className="p-1 text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
                title={t(b.hidden ? 'hubLayout.show' : 'hubLayout.hide')}
                aria-label={`${t(b.hidden ? 'hubLayout.show' : 'hubLayout.hide')} — ${t(`hubLayout.blocks.${b.id}`)}`}
              >
                {b.hidden ? <EyeOff size={14} strokeWidth={1.5} /> : <Eye size={14} strokeWidth={1.5} />}
              </button>
              <div className="flex flex-col flex-shrink-0">
                <button
                  type="button"
                  onClick={() => onChange(moveHubBlock(layout, i, up))}
                  disabled={up < 0}
                  className="text-muted-foreground hover:text-foreground disabled:opacity-30 transition-colors"
                  title={t('hubLayout.moveUp')}
                  aria-label={`${t('hubLayout.moveUp')} — ${t(`hubLayout.blocks.${b.id}`)}`}
                >
                  <ArrowUp size={12} strokeWidth={1.5} />
                </button>
                <button
                  type="button"
                  onClick={() => onChange(moveHubBlock(layout, i, down))}
                  disabled={down < 0}
                  className="text-muted-foreground hover:text-foreground disabled:opacity-30 transition-colors"
                  title={t('hubLayout.moveDown')}
                  aria-label={`${t('hubLayout.moveDown')} — ${t(`hubLayout.blocks.${b.id}`)}`}
                >
                  <ArrowDown size={12} strokeWidth={1.5} />
                </button>
              </div>
            </li>
          )
        })}
      </ol>

      <div className="border-t border-border px-5 py-4 space-y-3">
        <p className="text-xs text-muted-foreground">{t('hubLayout.syncNote')}</p>
        <button
          type="button"
          onClick={() => onChange(DEFAULT_HUB_LAYOUT.map((b) => ({ ...b })))}
          disabled={isDefaultHubLayout(layout)}
          className="flex items-center gap-1.5 font-mono-label text-muted-foreground hover:text-accent disabled:opacity-40 disabled:hover:text-muted-foreground transition-colors"
        >
          <RotateCcw size={12} strokeWidth={1.5} /> {t('hubLayout.reset')}
        </button>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" className="flex-1" onClick={onCancel} disabled={saving}>
            {t('common.cancel')}
          </Button>
          <Button size="sm" className="flex-1" onClick={onSave} disabled={saving}>
            {t('common.save')}
          </Button>
        </div>
      </div>
    </aside>
  )
}
