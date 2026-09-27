import { describe, it, expect } from 'vitest'
import type { GameLibraryEntry } from '../types'
import {
  DEFAULT_LIBRARY_FILTERS, applyLibraryFilters, hasActiveFilters, parsePlayerBound,
} from './gameLibraryFilters'

function game(name: string, max_players: number | null, is_favorite = false): GameLibraryEntry {
  return { game_id: name.length, name, genre: null, max_players, is_custom: false, is_favorite }
}

const LIBRARY = [
  game('Terraria', 8, true),
  game('Factorio', null, true),
  game('Among Us', 15),
  game('Chess', 2),
]

const names = (rows: GameLibraryEntry[]) => rows.map((r) => r.name)

describe('applyLibraryFilters', () => {
  it('leaves the library untouched with the default filters', () => {
    expect(names(applyLibraryFilters(LIBRARY, DEFAULT_LIBRARY_FILTERS))).toEqual(names(LIBRARY))
  })

  it('keeps only starred games with favorites_only', () => {
    const f = { ...DEFAULT_LIBRARY_FILTERS, favorites_only: true }
    expect(names(applyLibraryFilters(LIBRARY, f))).toEqual(['Terraria', 'Factorio'])
  })

  it('drops games with no known max player count with playable_only', () => {
    const f = { ...DEFAULT_LIBRARY_FILTERS, playable_only: true }
    expect(names(applyLibraryFilters(LIBRARY, f))).toEqual(['Terraria', 'Among Us', 'Chess'])
  })

  it('combines favorites_only and playable_only', () => {
    const f = { ...DEFAULT_LIBRARY_FILTERS, favorites_only: true, playable_only: true }
    expect(names(applyLibraryFilters(LIBRARY, f))).toEqual(['Terraria'])
  })

  it('bounds the max player count on both sides', () => {
    const f = { ...DEFAULT_LIBRARY_FILTERS, min_players: 4, max_players: 10 }
    expect(names(applyLibraryFilters(LIBRARY, f))).toEqual(['Terraria'])
  })

  it('sorts A→Z and Z→A without mutating the input', () => {
    const before = names(LIBRARY)
    expect(names(applyLibraryFilters(LIBRARY, { ...DEFAULT_LIBRARY_FILTERS, sort: 'asc' })))
      .toEqual(['Among Us', 'Chess', 'Factorio', 'Terraria'])
    expect(names(applyLibraryFilters(LIBRARY, { ...DEFAULT_LIBRARY_FILTERS, sort: 'desc' })))
      .toEqual(['Terraria', 'Factorio', 'Chess', 'Among Us'])
    expect(names(LIBRARY)).toEqual(before)
  })
})

describe('hasActiveFilters', () => {
  it('is false for the defaults', () => {
    expect(hasActiveFilters(DEFAULT_LIBRARY_FILTERS)).toBe(false)
  })

  it.each([
    { sort: 'asc' as const },
    { min_players: 2 },
    { max_players: 8 },
    { playable_only: true },
    { favorites_only: true },
  ])('is true as soon as one filter is set (%o)', (change) => {
    expect(hasActiveFilters({ ...DEFAULT_LIBRARY_FILTERS, ...change })).toBe(true)
  })
})

describe('parsePlayerBound', () => {
  it('reads a number in range', () => {
    expect(parsePlayerBound('4')).toBe(4)
    expect(parsePlayerBound('999')).toBe(999)
  })

  it.each(['', '  ', 'abc', '0', '-3', '1000'])('treats %j as no bound', (text) => {
    expect(parsePlayerBound(text)).toBeNull()
  })
})
