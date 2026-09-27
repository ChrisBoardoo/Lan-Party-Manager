import type { GameLibraryEntry, GameLibraryFilters } from '../types'

// The profile library's filter bar, kept pure so the rules are unit-tested
// without rendering GamesLibraryCard. The shape is the API's own
// (PUT /games/me/filters), since the bar is saved on the account.

export const DEFAULT_LIBRARY_FILTERS: GameLibraryFilters = {
  sort: null,
  min_players: null,
  max_players: null,
  playable_only: false,
  favorites_only: false,
}

export function hasActiveFilters(f: GameLibraryFilters): boolean {
  return (
    f.sort !== null || f.min_players !== null || f.max_players !== null || f.playable_only || f.favorites_only
  )
}

// A player-count input's text → the saved bound. Blank, non-numeric and
// anything outside the 1–999 the backend accepts all mean "no bound", so a
// half-typed value can never make the save fail.
export function parsePlayerBound(text: string): number | null {
  const n = parseInt(text, 10)
  return Number.isInteger(n) && n >= 1 && n <= 999 ? n : null
}

export function applyLibraryFilters(rows: GameLibraryEntry[], f: GameLibraryFilters): GameLibraryEntry[] {
  let out = rows
  if (f.favorites_only) out = out.filter((r) => r.is_favorite)
  if (f.playable_only) out = out.filter((r) => r.max_players != null)
  const min = f.min_players
  const max = f.max_players
  if (min != null) out = out.filter((r) => r.max_players != null && r.max_players >= min)
  if (max != null) out = out.filter((r) => r.max_players != null && r.max_players <= max)
  if (f.sort) {
    const dir = f.sort === 'asc' ? 1 : -1
    out = [...out].sort((a, b) => dir * a.name.localeCompare(b.name))
  }
  return out
}
