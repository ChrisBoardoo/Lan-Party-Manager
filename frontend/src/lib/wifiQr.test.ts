import { describe, it, expect } from 'vitest'
import { escapeWifiField, wifiQrPayload } from './wifiQr'

// A malformed WIFI: payload doesn't throw anywhere — the phone just fails to
// join, in the room, on the day. These pin the format and the escaping.

describe('escapeWifiField', () => {
  it('leaves ordinary text alone', () => {
    expect(escapeWifiField('LAN-Invites 5GHz')).toBe('LAN-Invites 5GHz')
  })

  it('escapes every reserved character', () => {
    expect(escapeWifiField('a;b,c:d"e\\f')).toBe('a\\;b\\,c\\:d\\"e\\\\f')
  })
})

describe('wifiQrPayload', () => {
  it('builds a WPA payload', () => {
    expect(wifiQrPayload({ ssid: 'LAN', password: 'secret', security: 'WPA', hidden: false }))
      .toBe('WIFI:T:WPA;S:LAN;P:secret;;')
  })

  it('escapes a password containing a semicolon', () => {
    expect(wifiQrPayload({ ssid: 'LAN', password: 'Pizza;Froide42', security: 'WPA', hidden: false }))
      .toBe('WIFI:T:WPA;S:LAN;P:Pizza\\;Froide42;;')
  })

  it('omits the password on an open network', () => {
    expect(wifiQrPayload({ ssid: 'Open', password: 'leftover', security: 'nopass', hidden: false }))
      .toBe('WIFI:T:nopass;S:Open;;')
  })

  it('flags a hidden network', () => {
    expect(wifiQrPayload({ ssid: 'Ghost', password: 'pw', security: 'WPA', hidden: true }))
      .toBe('WIFI:T:WPA;S:Ghost;P:pw;H:true;;')
  })
})
