import { describe, it, expect } from 'vitest'
import { daysBetween, slotISO, hourLabel, hourOf, nowNaiveISO, dayHeader } from './Planning'

// These are the primitives behind the Planning > Vote day×hour heatmap —
// bounding the grid to a player's RSVP window and mapping cells to/from the
// naive "YYYY-MM-DDTHH:MM:SS" slot strings the backend stores (see
// router_planning.py). A drift here silently shows the wrong grid or votes
// for the wrong slot, without ever throwing.

describe('daysBetween', () => {
  it('is inclusive of both endpoints for a single-day event', () => {
    expect(daysBetween('2026-10-03', '2026-10-03')).toEqual(['2026-10-03'])
  })

  it('lists every day in a multi-day range', () => {
    expect(daysBetween('2026-10-03', '2026-10-05')).toEqual([
      '2026-10-03', '2026-10-04', '2026-10-05',
    ])
  })

  it('crosses a month boundary correctly', () => {
    expect(daysBetween('2026-09-29', '2026-10-01')).toEqual([
      '2026-09-29', '2026-09-30', '2026-10-01',
    ])
  })
})

describe('slotISO / hourOf round-trip', () => {
  it('recovers the same hour it was built from', () => {
    for (const hour of [0, 9, 10, 13, 23]) {
      expect(hourOf(slotISO('2026-10-03', hour))).toBe(hour)
    }
  })

  it('zero-pads single-digit hours in the slot string', () => {
    expect(slotISO('2026-10-03', 9)).toBe('2026-10-03T09:00:00')
  })
})

describe('hourLabel', () => {
  it('zero-pads the hour', () => {
    expect(hourLabel(9)).toBe('09:00')
  })

  it('does not zero-pad a two-digit hour', () => {
    expect(hourLabel(23)).toBe('23:00')
  })

  it('wraps a 24+ value defensively', () => {
    expect(hourLabel(24)).toBe('00:00')
  })
})

describe('nowNaiveISO', () => {
  it('formats a local Date with no timezone marker, matching slotISO shape', () => {
    const d = new Date(2026, 8, 14, 9, 5, 30) // local: 2026-09-14 09:05:30
    expect(nowNaiveISO(d)).toBe('2026-09-14T09:05:00')
  })

  it('zero-pads month, day, hour and minute', () => {
    const d = new Date(2026, 0, 2, 3, 4, 0) // local: 2026-01-02 03:04
    expect(nowNaiveISO(d)).toBe('2026-01-02T03:04:00')
  })
})

describe('dayHeader', () => {
  it('renders a short weekday + day for English', () => {
    // 2026-10-03 is a Saturday.
    expect(dayHeader('2026-10-03')).toMatch(/Sat.*03|03.*Sat/i)
  })
})
