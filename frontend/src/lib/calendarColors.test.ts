import { describe, it, expect } from 'vitest'
import { CALENDAR_PALETTE, defaultColorKeyFor, swatchFor } from './calendarColors'

describe('CALENDAR_PALETTE', () => {
  it('has the 11 official Google Calendar colors, each with a readable text color', () => {
    expect(CALENDAR_PALETTE).toHaveLength(11)
    for (const swatch of CALENDAR_PALETTE) {
      expect(['#0A0A0A', '#FAFAFA']).toContain(swatch.textHex)
    }
  })

  it('picks dark text on a bright swatch and light text on a dark one', () => {
    const banana = CALENDAR_PALETTE.find((s) => s.key === 'banana')! // #f6bf26, bright yellow
    const tomato = CALENDAR_PALETTE.find((s) => s.key === 'tomato')! // #d50000, dark red
    expect(banana.textHex).toBe('#0A0A0A')
    expect(tomato.textHex).toBe('#FAFAFA')
  })
})

describe('defaultColorKeyFor', () => {
  it('is deterministic for the same game name', () => {
    expect(defaultColorKeyFor('Valorant')).toBe(defaultColorKeyFor('Valorant'))
  })

  it('is case- and whitespace-insensitive, so two proposers land on the same color', () => {
    const key = defaultColorKeyFor('Valorant')
    expect(defaultColorKeyFor('valorant')).toBe(key)
    expect(defaultColorKeyFor('  VALORANT  ')).toBe(key)
  })

  it('always returns a key present in the palette', () => {
    const key = defaultColorKeyFor('Some Random Game Name')
    expect(CALENDAR_PALETTE.some((s) => s.key === key)).toBe(true)
  })
})

describe('swatchFor', () => {
  it('uses the stored color when one is set', () => {
    expect(swatchFor('grape', 'Anything').key).toBe('grape')
  })

  it('falls back to the deterministic default when colorKey is null', () => {
    expect(swatchFor(null, 'Valorant').key).toBe(defaultColorKeyFor('Valorant'))
  })

  it('falls back to the deterministic default when colorKey is undefined', () => {
    expect(swatchFor(undefined, 'Valorant').key).toBe(defaultColorKeyFor('Valorant'))
  })

  it('falls back to the first palette entry for an unknown/stale key', () => {
    expect(swatchFor('not-a-real-key', 'Valorant')).toBe(CALENDAR_PALETTE[0])
  })
})
