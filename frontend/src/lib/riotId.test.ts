import { describe, it, expect } from 'vitest'
import { normalizeRiotId } from './riotId'

// Same cases as backend/tests/test_riot_id.py — the two sides must agree,
// or the profile would accept an id the API then rejects (or the reverse).

describe('normalizeRiotId', () => {
  it('keeps the casing', () => {
    expect(normalizeRiotId('CrossWax#EUW')).toBe('CrossWax#EUW')
  })

  it('trims around the hash', () => {
    expect(normalizeRiotId('  Cross Wax  #  EUW1 ')).toBe('Cross Wax#EUW1')
  })

  it('accepts accents and spaces in the game name', () => {
    expect(normalizeRiotId('Élodie la Fée#FR1')).toBe('Élodie la Fée#FR1')
  })

  it('counts the name by characters, not UTF-16 units', () => {
    // 16 characters but 32 UTF-16 units — Python's len() says 16, so must we.
    const name = '🎮'.repeat(16)
    expect(normalizeRiotId(`${name}#EUW`)).toBe(`${name}#EUW`)
  })

  it.each([
    'CrossWax',
    'CrossWax#',
    '#EUW',
    'ab#EUW',
    `${'a'.repeat(17)}#EUW`,
    'CrossWax#EU',
    'CrossWax#EUWEST',
    'CrossWax#EU-W',
    'Cross#Wax#EUW',
  ])('rejects %j', (raw) => {
    expect(normalizeRiotId(raw)).toBeNull()
  })
})
