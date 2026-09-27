import type { TFunction } from 'i18next'

// Backend times are naive UTC ISO strings; append 'Z' so the browser parses them
// as UTC. We only ever show *durations* (target − server_time), which stay
// correct regardless of the viewer's timezone.
export const asUtc = (iso: string) => Date.parse(iso.endsWith('Z') ? iso : iso + 'Z')

/** "just now" / "12 min ago"… measured against the server's clock, not the
 *  projector's — the kiosk machine's clock is whatever it happens to be. */
export function timeAgo(createdAt: string | null, serverTime: string, t: TFunction): string | null {
  if (!createdAt) return null
  const mins = Math.max(0, Math.floor((asUtc(serverTime) - asUtc(createdAt)) / 60_000))
  if (mins < 1) return t('kiosk.wallJustNow')
  if (mins < 60) return t('kiosk.wallMinutesAgo', { count: mins })
  const hours = Math.floor(mins / 60)
  if (hours < 24) return t('kiosk.wallHoursAgo', { count: hours })
  return t('kiosk.wallDaysAgo', { count: Math.floor(hours / 24) })
}
