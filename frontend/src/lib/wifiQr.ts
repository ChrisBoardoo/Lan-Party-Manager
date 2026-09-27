import type { WifiConfig } from '../types'

// The de-facto "WIFI:" QR payload that iOS (11+) and Android (10+) camera apps
// join directly: WIFI:T:<WPA|WEP|nopass>;S:<ssid>;P:<password>;H:true;;
//
// SSID and password must have \ ; , : " backslash-escaped. A password with a
// bare ";" otherwise truncates the payload — and that's invisible until someone
// scans it on the day, so it's covered by wifiQr.test.ts.
export function escapeWifiField(value: string): string {
  return value.replace(/([\\;,:"])/g, '\\$1')
}

export function wifiQrPayload(wifi: Pick<WifiConfig, 'ssid' | 'password' | 'security' | 'hidden'>): string {
  const parts = [`T:${wifi.security}`, `S:${escapeWifiField(wifi.ssid)}`]
  if (wifi.security !== 'nopass' && wifi.password) {
    parts.push(`P:${escapeWifiField(wifi.password)}`)
  }
  if (wifi.hidden) parts.push('H:true')
  return `WIFI:${parts.join(';')};;`
}
