import { HubBlockId, HubBlockState, HubZone } from '../types'

// The Hub's customizable blocks, in their default arrangement — which is the
// Hub as it was before the "Customize" mode existed (crew decision: most
// members will never change it). The header, the contextual banners (next LAN,
// trophy vote, booster, "complete your profile") and the admin invite reminder
// stay fixed around them.
//
// zone: 'full' = a full-width row; 'main' / 'side' = the 2/3 and 1/3 columns.
// Consecutive main/side blocks share one two-column section, each column
// stacking its own blocks — so a tall roster doesn't stretch the sidebar.
export const DEFAULT_HUB_LAYOUT: HubBlockState[] = [
  { id: 'contract', zone: 'full', hidden: false },
  { id: 'stats', zone: 'full', hidden: false },
  { id: 'roster', zone: 'main', hidden: false },
  { id: 'chat', zone: 'main', hidden: false },
  { id: 'activity', zone: 'side', hidden: false },
  { id: 'xp', zone: 'side', hidden: false },
  { id: 'minigames', zone: 'side', hidden: false },
  { id: 'hallOfFame', zone: 'side', hidden: false },
  { id: 'recentMedia', zone: 'side', hidden: false },
  { id: 'shortcuts', zone: 'full', hidden: false },
]

const KNOWN = new Set<string>(DEFAULT_HUB_LAYOUT.map((b) => b.id))
const ZONES = new Set<string>(['full', 'main', 'side'])

/** A saved layout made usable against the blocks this version knows: unknown
 *  ids (a block removed since) are dropped, duplicates and bad zones ignored,
 *  and blocks the saved layout doesn't mention (added since) are inserted
 *  right after the block that precedes them by default. null = default. */
export function mergeHubLayout(saved: { id: string; zone: string; hidden?: boolean }[] | null | undefined): HubBlockState[] {
  if (!saved) return DEFAULT_HUB_LAYOUT.map((b) => ({ ...b }))
  const out: HubBlockState[] = []
  const seen = new Set<string>()
  for (const b of saved) {
    if (!KNOWN.has(b.id) || seen.has(b.id) || !ZONES.has(b.zone)) continue
    seen.add(b.id)
    out.push({ id: b.id as HubBlockId, zone: b.zone as HubZone, hidden: !!b.hidden })
  }
  DEFAULT_HUB_LAYOUT.forEach((d, i) => {
    if (seen.has(d.id)) return
    const prev = i > 0 ? out.findIndex((b) => b.id === DEFAULT_HUB_LAYOUT[i - 1].id) : -1
    out.splice(prev + 1, 0, { ...d })
    seen.add(d.id)
  })
  return out
}

export type HubSection =
  | { kind: 'full'; key: string; id: HubBlockId }
  | { kind: 'columns'; key: string; main: HubBlockId[]; side: HubBlockId[] }

/** The layout as rendered: hidden blocks and blocks with nothing to show
 *  (`isShown` false: feature off, no open chat…) are left out, then runs of
 *  consecutive main/side blocks are grouped into one two-column section. */
export function hubSections(layout: HubBlockState[], isShown: (id: HubBlockId) => boolean): HubSection[] {
  const sections: HubSection[] = []
  for (const b of layout) {
    if (b.hidden || !isShown(b.id)) continue
    if (b.zone === 'full') {
      sections.push({ kind: 'full', key: b.id, id: b.id })
      continue
    }
    let last = sections[sections.length - 1]
    if (!last || last.kind !== 'columns') {
      last = { kind: 'columns', key: `cols-${b.id}`, main: [], side: [] }
      sections.push(last)
    }
    last[b.zone].push(b.id)
  }
  return sections
}

/** Moves the block at `from` to `to`, shifting the ones in between. */
export function moveHubBlock(layout: HubBlockState[], from: number, to: number): HubBlockState[] {
  if (from === to || from < 0 || to < 0 || from >= layout.length || to >= layout.length) return layout
  const next = [...layout]
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  return next
}

export function isDefaultHubLayout(layout: HubBlockState[]): boolean {
  return layout.length === DEFAULT_HUB_LAYOUT.length
    && layout.every((b, i) => {
      const d = DEFAULT_HUB_LAYOUT[i]
      return b.id === d.id && b.zone === d.zone && b.hidden === d.hidden
    })
}

// Last layout seen for this account, so the Hub opens in the member's own
// arrangement instead of flashing the default until /me/hub-layout answers.
// A per-browser cache only — the account (backend) stays the source of truth.
const cacheKey = (userId: number) => `lpm.hubLayout.${userId}`

export function readCachedHubLayout(userId: number | undefined): HubBlockState[] | null {
  if (!userId) return null
  try {
    const raw = localStorage.getItem(cacheKey(userId))
    return raw ? mergeHubLayout(JSON.parse(raw)) : null
  } catch {
    return null
  }
}

export function writeCachedHubLayout(userId: number | undefined, layout: HubBlockState[] | null) {
  if (!userId) return
  try {
    if (layout) localStorage.setItem(cacheKey(userId), JSON.stringify(layout))
    else localStorage.removeItem(cacheKey(userId))
  } catch {
    // Private mode / blocked storage: the Hub just loads like before.
  }
}
