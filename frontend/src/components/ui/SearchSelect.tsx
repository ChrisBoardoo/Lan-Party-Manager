import { useEffect, useMemo, useRef, useState } from 'react'

export interface SearchSelectOption {
  id: string | number
  label: string
  sublabel?: string
}

interface SearchSelectProps {
  options: SearchSelectOption[]
  value: string
  onChange: (text: string) => void
  onSelect: (option: SearchSelectOption) => void
  placeholder?: string
  maxLength?: number
  disabled?: boolean
  /** Label for the "add this as a new entry" row; omit to disable custom entries entirely. */
  addLabel?: (text: string) => string
  onAddCustom?: (text: string) => void
  className?: string
}

// Generic, dependency-free combobox: a plain input + a filtered dropdown over a
// provided option list, with an optional trailing "add custom" row when nothing
// matches exactly. No existing component in the repo covers this (only Input and
// native <select>s), so built from scratch — kept generic to be reusable beyond
// the game catalog it was built for.
export default function SearchSelect({
  options, value, onChange, onSelect, placeholder, maxLength = 120, disabled,
  addLabel, onAddCustom, className = '',
}: SearchSelectProps) {
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)

  const filtered = useMemo(() => {
    const q = value.trim().toLowerCase()
    const pool = q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options
    return pool.slice(0, 8)
  }, [options, value])

  const exactMatch = useMemo(
    () => options.some((o) => o.label.toLowerCase() === value.trim().toLowerCase()),
    [options, value],
  )
  const showAddRow = !!onAddCustom && value.trim().length > 0 && !exactMatch
  const rowCount = filtered.length + (showAddRow ? 1 : 0)

  useEffect(() => { setHighlight(0) }, [value, open])

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  const pick = (option: SearchSelectOption) => { onSelect(option); setOpen(false) }
  const addCustom = () => { onAddCustom?.(value.trim()); setOpen(false) }

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <input
        value={value}
        onChange={(e) => { onChange(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setHighlight((h) => Math.min(h + 1, rowCount - 1)) }
          else if (e.key === 'ArrowUp') { e.preventDefault(); setHighlight((h) => Math.max(h - 1, 0)) }
          else if (e.key === 'Enter') {
            e.preventDefault()
            if (!open || rowCount === 0) return
            if (highlight < filtered.length) pick(filtered[highlight])
            else if (showAddRow) addCustom()
          } else if (e.key === 'Escape') setOpen(false)
        }}
        placeholder={placeholder}
        maxLength={maxLength}
        disabled={disabled}
        className="w-full bg-muted border border-border px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-accent outline-none"
      />
      {open && rowCount > 0 && (
        <div className="absolute z-20 mt-1 w-full max-h-64 overflow-y-auto bg-card border border-border shadow-lg">
          {filtered.map((o, i) => (
            <button
              key={o.id}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pick(o)}
              className={`w-full text-left px-3 py-2 text-sm flex items-center justify-between gap-2 ${
                i === highlight ? 'bg-accent/10 text-foreground' : 'text-foreground hover:bg-muted'
              }`}
            >
              <span>{o.label}</span>
              {o.sublabel && <span className="font-mono-label text-[10px] text-muted-foreground">{o.sublabel}</span>}
            </button>
          ))}
          {showAddRow && (
            <button
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={addCustom}
              className={`w-full text-left px-3 py-2 text-sm font-mono-label ${
                filtered.length === highlight ? 'bg-accent/10 text-accent' : 'text-accent hover:bg-muted'
              }`}
            >
              {addLabel ? addLabel(value.trim()) : `+ ${value.trim()}`}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
