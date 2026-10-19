// Shared date helpers for LanEvent-shaped objects — pulled out of the several
// copies that had each grown their own `isUpcoming` (Events.tsx, PlayerProfile.tsx,
// EventDetailPage.tsx) so the Hub's "next event" card uses the exact same
// definition of "upcoming" as the rest of the app instead of a 4th copy.

const DAY_MS = 86400000

export function isUpcoming(endDate: string): boolean {
  return new Date(endDate) >= new Date(new Date().toDateString())
}

export function daysUntil(startDate: string): number {
  const start = new Date(`${startDate}T00:00:00`)
  const today = new Date(new Date().toDateString())
  return Math.round((start.getTime() - today.getTime()) / DAY_MS)
}

/** The Craving Chat window, as an admin set it (Settings → Craving Chat;
 *  served by /public-config). */
export interface ChatWindowRules {
  daysBefore: number
  daysAfter: number
  alwaysOpen: boolean
}

export const DEFAULT_CHAT_RULES: ChatWindowRules = { daysBefore: 30, daysAfter: 15, alwaysOpen: false }

// Mirrors backend/router_chat.py's `_window_open`. Duplicated (not fetched)
// because it only picks which room the UI shows — the backend is the real
// enforcement point for every actual read/write.
// - Default: from `daysBefore` before the event's start to `daysAfter` after its end.
// - Always open: the room is open as soon as the LAN exists; once it's over it
//   stays open until a later LAN exists (`hasLaterEvent`) — never closing sooner
//   than `daysAfter` after the end.
export function isChatWindowOpen(
  startDate: string,
  endDate: string,
  rules: ChatWindowRules = DEFAULT_CHAT_RULES,
  hasLaterEvent = false,
): boolean {
  const today = new Date(new Date().toDateString()).getTime()
  const closes = new Date(`${endDate}T00:00:00`).getTime() + rules.daysAfter * DAY_MS
  if (rules.alwaysOpen) return today <= closes || !hasLaterEvent
  const opens = new Date(`${startDate}T00:00:00`).getTime() - rules.daysBefore * DAY_MS
  return today >= opens && today <= closes
}

// Today as YYYY-MM-DD in the browser's timezone — the same shape as an
// event's start_date/end_date, so the two compare as plain strings.
export function todayIso(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// The LAN running today, whole days from start to end — the latest-starting
// one if two overlap. Same rule as backend/router_lol.py's `_lan_in_progress`
// minus its RSVP check: this only picks what the LoL tracker shows by default,
// the server still decides which LAN a captured game belongs to.
export function eventInProgress<T extends { start_date: string; end_date: string }>(events: T[]): T | undefined {
  const today = todayIso()
  return events
    .filter((e) => e.start_date.slice(0, 10) <= today && e.end_date.slice(0, 10) >= today)
    .sort((a, b) => b.start_date.localeCompare(a.start_date))[0]
}
