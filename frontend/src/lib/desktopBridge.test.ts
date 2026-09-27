import { describe, it, expect } from 'vitest'
import { isReloadShortcut } from './desktopBridge'

// Every key combo WebView2 treats as "reload" must be caught, or the desktop app
// reloads its shell and drops the member back on the Hub.

const key = (key: string, mods: { ctrlKey?: boolean; metaKey?: boolean; altKey?: boolean } = {}) => ({
  key,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  ...mods,
})

describe('isReloadShortcut', () => {
  it('catches every reload combo', () => {
    expect(isReloadShortcut(key('F5'))).toBe(true)
    expect(isReloadShortcut(key('F5', { ctrlKey: true }))).toBe(true)
    expect(isReloadShortcut(key('r', { ctrlKey: true }))).toBe(true)
    // Shift turns the key into an uppercase R.
    expect(isReloadShortcut(key('R', { ctrlKey: true }))).toBe(true)
  })

  it('leaves ordinary typing and other shortcuts alone', () => {
    expect(isReloadShortcut(key('r'))).toBe(false)
    expect(isReloadShortcut(key('R'))).toBe(false)
    expect(isReloadShortcut(key('v', { ctrlKey: true }))).toBe(false)
    expect(isReloadShortcut(key('F4', { altKey: true }))).toBe(false)
    expect(isReloadShortcut(key('F5', { altKey: true }))).toBe(false)
  })
})
