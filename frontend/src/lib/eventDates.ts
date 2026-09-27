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

// Mirrors backend/router_chat.py's `_window_open`: the Craving Chat is open
// from 30 days before an event's start to 15 days after its end. Duplicated
// (not fetched) because it only gates which UI to render — the backend is the
// real enforcement point for every actual read/write.
const CHAT_OPENS_DAYS_BEFORE = 30
const CHAT_CLOSES_DAYS_AFTER = 15

export function isChatWindowOpen(startDate: string, endDate: string): boolean {
  const today = new Date(new Date().toDateString())
  const opens = new Date(`${startDate}T00:00:00`).getTime() - CHAT_OPENS_DAYS_BEFORE * DAY_MS
  const closes = new Date(`${endDate}T00:00:00`).getTime() + CHAT_CLOSES_DAYS_AFTER * DAY_MS
  return today.getTime() >= opens && today.getTime() <= closes
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
