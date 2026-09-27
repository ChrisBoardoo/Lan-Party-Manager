import type { LolPlayerLine } from '../types'
import { buildCsv, formatCsvNumber, type CsvFormat } from './csv'

// Display helpers for the League of Legends "LAN games" block
// (components/LolLanStats.tsx) — pure, so the rules are unit-tested.

export type LolSortKey =
  | 'games' | 'win_rate' | 'kda' | 'avg_kills' | 'avg_deaths' | 'avg_assists' | 'avg_damage'

// Deaths are the one column where less is better: its first click sorts
// ascending, every other column's sorts descending.
export const LOL_SORT_ASCENDING_FIRST: LolSortKey[] = ['avg_deaths']

export function sortLolLines(lines: LolPlayerLine[], key: LolSortKey, dir: 'asc' | 'desc'): LolPlayerLine[] {
  const sign = dir === 'asc' ? 1 : -1
  return [...lines].sort((a, b) => {
    const va = a[key]
    const vb = b[key]
    // No win rate yet (under 3 games) always sinks, whichever the direction.
    if (va == null || vb == null) {
      if (va == null && vb == null) return a.username.localeCompare(b.username)
      return va == null ? 1 : -1
    }
    if (va !== vb) return sign * (va - vb)
    return a.username.localeCompare(b.username)
  })
}

export function formatOneDecimal(n: number): string {
  return n.toFixed(1)
}

// 32400 → "32.4k", 950 → "950".
export function formatDamage(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(Math.round(n))
}

// 1934 → "32:14". Null when the client didn't report a length.
export function formatDuration(seconds: number | null): string {
  if (seconds == null || seconds < 0) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

// ── CSV export ───────────────────────────────────────────────────────────────

// One row per player, in the order shown on screen. Totals and per-game
// averages both: the table shows averages, a spreadsheet wants to re-sum.
// Win % stays empty under 3 games, like the table's "—".
export function lolStatsCsv(lines: LolPlayerLine[], headers: string[], fmt: CsvFormat): string {
  const num = (n: number, digits: number) => formatCsvNumber(n, digits, fmt)
  const rows = lines.map((p) => [
    p.username,
    String(p.games), String(p.wins), String(p.losses),
    p.win_rate == null ? '' : String(Math.round(p.win_rate * 100)),
    String(p.kills), String(p.deaths), String(p.assists), num(p.kda, 2), String(p.damage),
    num(p.avg_kills, 1), num(p.avg_deaths, 1), num(p.avg_assists, 1), String(Math.round(p.avg_damage)),
  ])
  return buildCsv([headers, ...rows], fmt)
}

// "lol-stats_lan-party-2026-2_custom_2026-10-15.csv" — the scope (a LAN's
// title, or "global") and the category filter, so two exports never collide.
export function lolCsvFilename(scope: string | undefined, category: string | null, date: string): string {
  const slug = (scope ?? 'global')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'lan'
  return ['lol-stats', slug, category, date].filter(Boolean).join('_') + '.csv'
}
