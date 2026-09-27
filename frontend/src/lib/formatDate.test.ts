import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import i18n from '../i18n'
import { parseUtc, formatDate, timeAgo } from './formatDate'

describe('parseUtc', () => {
  // Regression test for a real bug: SQLite/SQLAlchemy hand back naive
  // "YYYY-MM-DDTHH:MM:SS" timestamps with no timezone marker. Per the JS
  // spec, `new Date(...)` on such a string parses it as LOCAL time, so a
  // message posted "now" showed as hours old/in the future depending on the
  // viewer's UTC offset. parseUtc must always resolve to the same instant
  // regardless of the runner's local timezone.
  it('treats a marker-less timestamp as UTC, not local time', () => {
    const naive = '2026-09-14T20:11:25'
    const parsed = parseUtc(naive)
    expect(parsed.getTime()).toBe(new Date('2026-09-14T20:11:25Z').getTime())
  })

  it('leaves a Z-suffixed timestamp untouched', () => {
    const withZ = '2026-09-14T20:11:25Z'
    expect(parseUtc(withZ).getTime()).toBe(new Date(withZ).getTime())
  })

  it('leaves a timestamp with an explicit offset untouched', () => {
    const withOffset = '2026-09-14T20:11:25+02:00'
    expect(parseUtc(withOffset).getTime()).toBe(new Date(withOffset).getTime())
  })

  it('recognizes a compact (non-colon) offset too', () => {
    const compactOffset = '2026-09-14T20:11:25+0200'
    expect(parseUtc(compactOffset).getTime()).toBe(new Date(compactOffset).getTime())
  })
})

describe('formatDate', () => {
  afterEach(() => {
    i18n.changeLanguage('en')
  })

  it('formats in English by default', async () => {
    await i18n.changeLanguage('en')
    expect(formatDate('2026-09-14T00:00:00Z')).toBe('14 Sept 2026')
  })

  it('formats in French when the active language is fr', async () => {
    await i18n.changeLanguage('fr')
    // fr-FR renders the month abbreviation with a trailing period.
    expect(formatDate('2026-09-14T00:00:00Z')).toMatch(/14\s+sept\.?\s+2026/i)
  })
})

describe('timeAgo', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-14T12:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
    i18n.changeLanguage('en')
  })

  it('renders seconds for anything under a minute', async () => {
    await i18n.changeLanguage('en')
    expect(timeAgo('2026-09-14T11:59:45Z')).toBe('15s ago')
  })

  it('renders minutes under an hour', async () => {
    await i18n.changeLanguage('en')
    expect(timeAgo('2026-09-14T11:30:00Z')).toBe('30m ago')
  })

  it('renders hours under a day', async () => {
    await i18n.changeLanguage('en')
    expect(timeAgo('2026-09-14T09:00:00Z')).toBe('3h ago')
  })

  it('falls back to a full date at 24h and beyond', async () => {
    await i18n.changeLanguage('en')
    expect(timeAgo('2026-09-12T12:00:00Z')).toBe(formatDate('2026-09-12T12:00:00Z'))
  })

  it('renders French relative units', async () => {
    await i18n.changeLanguage('fr')
    expect(timeAgo('2026-09-14T11:30:00Z')).toBe('il y a 30min')
  })
})
