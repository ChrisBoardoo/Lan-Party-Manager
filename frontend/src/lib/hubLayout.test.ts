import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  DEFAULT_HUB_LAYOUT, hubSections, isDefaultHubLayout, mergeHubLayout, moveHubBlock,
  readCachedHubLayout, writeCachedHubLayout,
} from './hubLayout'
import type { HubBlockId } from '../types'

const ids = (layout: { id: string }[]) => layout.map((b) => b.id)
const all = () => true

describe('mergeHubLayout', () => {
  it('gives the default for a member who never customized', () => {
    expect(mergeHubLayout(null)).toEqual(DEFAULT_HUB_LAYOUT)
    expect(isDefaultHubLayout(mergeHubLayout(null))).toBe(true)
  })

  it('returns a copy, never the default itself', () => {
    const merged = mergeHubLayout(null)
    merged[0].hidden = true
    expect(DEFAULT_HUB_LAYOUT[0].hidden).toBe(false)
  })

  it('keeps a full saved layout as saved', () => {
    const saved = [...DEFAULT_HUB_LAYOUT].reverse().map((b) => ({ ...b, zone: 'full', hidden: b.id === 'xp' }))
    const merged = mergeHubLayout(saved)
    expect(ids(merged)).toEqual(ids(saved))
    expect(merged.find((b) => b.id === 'xp')?.hidden).toBe(true)
    expect(merged.every((b) => b.zone === 'full')).toBe(true)
  })

  it('drops unknown ids, duplicates and bad zones', () => {
    const merged = mergeHubLayout([
      { id: 'stats', zone: 'side' },
      { id: 'removedBlock', zone: 'full' },
      { id: 'stats', zone: 'full' },
      { id: 'roster', zone: 'diagonal' },
    ])
    expect(merged.filter((b) => b.id === 'stats')).toEqual([{ id: 'stats', zone: 'side', hidden: false }])
    expect(ids(merged)).not.toContain('removedBlock')
    // roster's bad entry is ignored, so it comes back from the default
    expect(merged.find((b) => b.id === 'roster')?.zone).toBe('main')
    expect(merged).toHaveLength(DEFAULT_HUB_LAYOUT.length)
  })

  it('inserts a block the saved layout misses right after its default predecessor', () => {
    // A layout saved before 'xp' existed, with the side blocks moved to the top.
    const saved = DEFAULT_HUB_LAYOUT.filter((b) => b.id !== 'xp')
    const moved = [...saved.filter((b) => b.zone === 'side'), ...saved.filter((b) => b.zone !== 'side')]
    const merged = mergeHubLayout(moved)
    const at = ids(merged).indexOf('xp')
    expect(merged[at - 1].id).toBe('activity') // xp's default predecessor
    expect(merged[at]).toEqual({ id: 'xp', zone: 'side', hidden: false })
  })

  it('puts a missing first block first', () => {
    const merged = mergeHubLayout(DEFAULT_HUB_LAYOUT.filter((b) => b.id !== 'contract'))
    expect(merged[0].id).toBe('contract')
  })
})

describe('hubSections', () => {
  it('renders the default as before: contract, stats, roster+chat | sidebar, shortcuts', () => {
    expect(hubSections(DEFAULT_HUB_LAYOUT, all)).toEqual([
      { kind: 'full', key: 'contract', id: 'contract' },
      { kind: 'full', key: 'stats', id: 'stats' },
      {
        kind: 'columns', key: 'cols-roster',
        main: ['roster', 'chat'],
        side: ['activity', 'xp', 'minigames', 'hallOfFame', 'recentMedia'],
      },
      { kind: 'full', key: 'shortcuts', id: 'shortcuts' },
    ])
  })

  it('leaves out hidden blocks and blocks with nothing to show', () => {
    const layout = mergeHubLayout(null).map((b) => (b.id === 'stats' ? { ...b, hidden: true } : b))
    const shown = (id: HubBlockId) => id !== 'chat'
    const sections = hubSections(layout, shown)
    expect(sections.some((s) => s.kind === 'full' && s.id === 'stats')).toBe(false)
    const cols = sections.find((s) => s.kind === 'columns')
    expect(cols?.kind === 'columns' && cols.main).toEqual(['roster'])
  })

  it('a full-width block splits the columns in two sections', () => {
    const layout = mergeHubLayout(null).map((b) => (b.id === 'xp' ? { ...b, zone: 'full' as const } : b))
    const kinds = hubSections(layout, all).map((s) => (s.kind === 'full' ? s.id : `${s.main.join('+')}|${s.side.join('+')}`))
    expect(kinds).toEqual([
      'contract', 'stats',
      'roster+chat|activity',
      'xp',
      '|minigames+hallOfFame+recentMedia',
      'shortcuts',
    ])
  })

  it('section keys stay unique', () => {
    const layout = mergeHubLayout(null).map((b, i) => ({ ...b, zone: i % 2 ? ('full' as const) : ('side' as const) }))
    const keys = hubSections(layout, all).map((s) => s.key)
    expect(new Set(keys).size).toBe(keys.length)
  })
})

describe('moveHubBlock', () => {
  it('moves down and up', () => {
    const l = mergeHubLayout(null)
    expect(ids(moveHubBlock(l, 0, 2)).slice(0, 3)).toEqual(['stats', 'roster', 'contract'])
    expect(ids(moveHubBlock(l, 2, 0)).slice(0, 3)).toEqual(['roster', 'contract', 'stats'])
  })

  it('ignores out-of-range moves', () => {
    const l = mergeHubLayout(null)
    expect(moveHubBlock(l, 0, -1)).toBe(l)
    expect(moveHubBlock(l, 0, l.length)).toBe(l)
  })
})

describe('cached layout', () => {
  // lib/ suites run on node (vite.config.ts): an in-memory localStorage instead
  // of paying jsdom's start-up for two tests.
  beforeEach(() => {
    const store = new Map<string, string>()
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => { store.set(k, v) },
      removeItem: (k: string) => { store.delete(k) },
    })
  })

  it('round-trips per account', () => {
    const layout = moveHubBlock(mergeHubLayout(null), 0, 3)
    writeCachedHubLayout(7, layout)
    expect(readCachedHubLayout(7)).toEqual(layout)
    expect(readCachedHubLayout(8)).toBeNull()
  })

  it('clears on reset and survives garbage', () => {
    writeCachedHubLayout(7, mergeHubLayout(null))
    writeCachedHubLayout(7, null)
    expect(readCachedHubLayout(7)).toBeNull()
    localStorage.setItem('lpm.hubLayout.7', '{not json')
    expect(readCachedHubLayout(7)).toBeNull()
    expect(readCachedHubLayout(undefined)).toBeNull()
  })
})
