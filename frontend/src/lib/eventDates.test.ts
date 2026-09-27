import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { isUpcoming, daysUntil, isChatWindowOpen, eventInProgress } from './eventDates'

// A fixed "now" so every test is independent of the machine's real clock and
// timezone. Local noon keeps every date comparison well clear of a UTC
// day-boundary flip on any CI runner's timezone.
const NOW = new Date(2026, 8, 14, 12, 0, 0) // 2026-09-14 local

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('isUpcoming', () => {
  it('is true for an event ending today', () => {
    expect(isUpcoming('2026-09-14')).toBe(true)
  })

  it('is true for an event ending in the future', () => {
    expect(isUpcoming('2026-09-20')).toBe(true)
  })

  it('is false for an event that already ended', () => {
    expect(isUpcoming('2026-09-13')).toBe(false)
  })
})

describe('daysUntil', () => {
  it('is 0 for an event starting today', () => {
    expect(daysUntil('2026-09-14')).toBe(0)
  })

  it('counts whole days forward', () => {
    expect(daysUntil('2026-09-17')).toBe(3)
  })

  it('counts whole days in the past as negative', () => {
    expect(daysUntil('2026-09-10')).toBe(-4)
  })

  it('crosses a month boundary correctly', () => {
    expect(daysUntil('2026-10-01')).toBe(17)
  })
})

describe('isChatWindowOpen', () => {
  // Mirrors backend/router_chat.py's _window_open: 30 days before start,
  // 15 days after end. If this drifts from the backend's own window, the
  // frontend would show/hide the chat room at the wrong time even though the
  // backend socket itself enforces the real access boundary — cosmetic, but
  // confusing, and worth pinning down with a test on both sides.
  const start = '2026-10-01'
  const end = '2026-10-03'

  it('is closed more than 30 days before the event starts', () => {
    vi.setSystemTime(new Date(2026, 7, 31, 12, 0, 0)) // 2026-08-31, 31 days before
    expect(isChatWindowOpen(start, end)).toBe(false)
  })

  it('opens exactly 30 days before the event starts', () => {
    vi.setSystemTime(new Date(2026, 8, 1, 12, 0, 0)) // 2026-09-01, 30 days before
    expect(isChatWindowOpen(start, end)).toBe(true)
  })

  it('stays open during the event', () => {
    vi.setSystemTime(new Date(2026, 9, 2, 12, 0, 0))
    expect(isChatWindowOpen(start, end)).toBe(true)
  })

  it('stays open exactly 15 days after the event ends', () => {
    vi.setSystemTime(new Date(2026, 9, 18, 12, 0, 0)) // 2026-10-18, 15 days after end
    expect(isChatWindowOpen(start, end)).toBe(true)
  })

  it('closes more than 15 days after the event ends', () => {
    vi.setSystemTime(new Date(2026, 9, 19, 12, 0, 0)) // 16 days after end
    expect(isChatWindowOpen(start, end)).toBe(false)
  })
})

describe('eventInProgress', () => {
  const lan = (id: number, start_date: string, end_date: string) => ({ id, start_date, end_date })

  it('picks the LAN running today, first and last day included', () => {
    expect(eventInProgress([lan(1, '2026-09-14', '2026-09-18')])?.id).toBe(1)
    expect(eventInProgress([lan(1, '2026-09-10', '2026-09-14')])?.id).toBe(1)
  })

  it('is undefined before a LAN starts and after it ends — the tracker stays global', () => {
    expect(eventInProgress([lan(1, '2026-09-15', '2026-09-18'), lan(2, '2026-09-01', '2026-09-13')])).toBeUndefined()
    expect(eventInProgress([])).toBeUndefined()
  })

  it('prefers the latest-starting LAN when two overlap', () => {
    expect(eventInProgress([lan(1, '2026-09-10', '2026-09-20'), lan(2, '2026-09-13', '2026-09-15')])?.id).toBe(2)
  })
})
