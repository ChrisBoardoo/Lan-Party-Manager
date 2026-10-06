import { describe, it, expect } from 'vitest'
import { INVITE_CODE_LENGTH, normalizeInviteCode } from './inviteCode'

// The invite fields once capped input at 8 characters while the backend issued
// 10-character codes: every pasted code came out truncated and "invalid".

describe('normalizeInviteCode', () => {
  it('keeps a full 10-character code', () => {
    expect(normalizeInviteCode('ZNV7GKAXB5')).toBe('ZNV7GKAXB5')
    expect(INVITE_CODE_LENGTH).toBe(10)
  })

  it('uppercases and strips whitespace from a pasted code', () => {
    expect(normalizeInviteCode('  znv7 gkaxb5\n')).toBe('ZNV7GKAXB5')
  })

  it('caps at the code length', () => {
    expect(normalizeInviteCode('ZNV7GKAXB5EXTRA')).toBe('ZNV7GKAXB5')
  })

  it('still accepts a 6-character code from before 1.3.4', () => {
    expect(normalizeInviteCode('abc234')).toBe('ABC234')
  })
})
