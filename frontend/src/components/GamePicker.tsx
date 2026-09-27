import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { tournamentsApi } from '../lib/api'
import type { TournamentGame } from '../types'

export interface GamePick {
  /** Set when a catalog entry was picked; absent for free text (the backend
   *  then looks the name up, or adds it to the catalog as a custom game). */
  game_id?: number
  game_name: string
}

const MAX_SUGGESTIONS = 8

// Tournament game picker: a text field over the shared catalog. The backend
// already orders the catalog (played in tournaments → owned by this event's
// attendees → on its planning → A-Z), so with an empty query the top of the
// list *is* the suggestion list.
export default function GamePicker({
  value,
  onChange,
  eventId,
  error,
}: {
  value: GamePick
  onChange: (pick: GamePick) => void
  eventId?: number
  error?: string
}) {
  const { t } = useTranslation()
  const [games, setGames] = useState<TournamentGame[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    tournamentsApi.games(eventId).then(setGames).catch(() => setGames([]))
  }, [eventId])

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const query = value.game_name.trim().toLowerCase()
  const suggestions = useMemo(
    () => (query ? games.filter((g) => g.name.toLowerCase().includes(query)) : games).slice(0, MAX_SUGGESTIONS),
    [games, query],
  )
  const exact = games.find((g) => g.name.toLowerCase() === query)

  const pick = (g: TournamentGame) => {
    onChange({ game_id: g.id, game_name: g.name })
    setOpen(false)
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || suggestions.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => (i + 1) % suggestions.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => (i - 1 + suggestions.length) % suggestions.length)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      pick(suggestions[active])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const hints = (g: TournamentGame) => {
    const out: string[] = []
    if (g.tournament_count) out.push(t('tournaments.picker.playedCount', { count: g.tournament_count }))
    if (g.owner_count) out.push(t('tournaments.picker.ownerCount', { count: g.owner_count }))
    if (g.planned) out.push(t('tournaments.picker.planned'))
    return out
  }

  return (
    <div className="flex flex-col gap-1.5" ref={boxRef}>
      <label className="font-mono-label text-muted-foreground">{t('tournaments.modal.gameNameLabel')}</label>
      <div className="relative">
        <input
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          value={value.game_name}
          placeholder={t('tournaments.modal.gameNamePlaceholder')}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            // Typing drops a previous catalog pick until one is picked again —
            // unless the text still names a catalog game exactly.
            onChange({ game_name: e.target.value })
            setActive(0)
            setOpen(true)
          }}
          onKeyDown={onKeyDown}
          className="w-full h-12 px-4 bg-input border border-border text-foreground text-base placeholder:text-muted-foreground focus:border-accent outline-none transition-colors duration-150"
        />
        {open && suggestions.length > 0 && (
          <ul role="listbox" className="absolute z-10 left-0 right-0 top-full mt-px bg-card border border-border max-h-72 overflow-y-auto">
            {suggestions.map((g, i) => (
              <li
                key={g.id}
                role="option"
                aria-selected={i === active}
                onMouseDown={(e) => { e.preventDefault(); pick(g) }}
                onMouseEnter={() => setActive(i)}
                className={`px-4 py-2 cursor-pointer flex items-center justify-between gap-3 ${
                  i === active ? 'bg-accent/10' : ''
                }`}
              >
                <span className="min-w-0">
                  <span className="block text-sm text-foreground truncate">{g.name}</span>
                  {g.genre && <span className="block font-mono-label text-muted-foreground text-[10px]">{g.genre}</span>}
                </span>
                <span className="font-mono-label text-accent text-[10px] shrink-0 text-right">
                  {hints(g).join(' · ')}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {error ? (
        <span className="font-mono-label text-red-500">{error}</span>
      ) : query && !value.game_id && !exact ? (
        <span className="font-mono-label text-muted-foreground text-[10px]">{t('tournaments.picker.newGameHint')}</span>
      ) : null}
    </div>
  )
}
