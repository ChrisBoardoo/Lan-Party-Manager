import type { GametimeHeatCell } from '../types'

// Game time (Games > Game time, backend/router_gametime.py): the small pure
// pieces of the tab, kept here so they're testable without rendering it.

/** "45 min", "4h", "2h33" — the format of the LAN's own scoreboard. */
export function formatPlayTime(seconds: number): string {
  const minutes = Math.floor(Math.max(0, seconds) / 60)
  if (minutes < 60) return `${minutes} min`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m === 0 ? `${h}h` : `${h}h${String(m).padStart(2, '0')}`
}

/** A bar's width, in % of the longest one; a game played at all keeps a sliver. */
export function barPercent(seconds: number, max: number): number {
  if (max <= 0 || seconds <= 0) return 0
  return Math.max(2, Math.round((seconds / max) * 100))
}

export interface HeatGrid {
  days: string[]        // every day from the first played to the last, gaps included
  rows: number[][]      // rows[day][hour] = seconds
  max: number
}

function nextDay(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + 1)
  return d.toISOString().slice(0, 10)
}

/** The server's sparse cells as a full days × 24 hours grid. A day nobody
 *  played stays as an empty row: the night the crew slept shows. */
export function heatGrid(cells: GametimeHeatCell[]): HeatGrid {
  if (cells.length === 0) return { days: [], rows: [], max: 0 }
  const sorted = [...cells].sort((a, b) => a.day.localeCompare(b.day))
  const days: string[] = []
  for (let day = sorted[0].day; day <= sorted[sorted.length - 1].day; day = nextDay(day)) {
    days.push(day)
  }
  const index = new Map(days.map((d, i) => [d, i]))
  const rows = days.map(() => Array<number>(24).fill(0))
  let max = 0
  for (const c of cells) {
    const row = rows[index.get(c.day)!]
    row[c.hour] += c.seconds
    max = Math.max(max, row[c.hour])
  }
  return { days, rows, max }
}
