import type { LanEvent } from '../types'

// Event start/end dates are date-only ("YYYY-MM-DD", no time-of-day — see
// LanEvent.start_date/end_date), so every export here treats the event as an
// all-day span. Both Google Calendar's `dates=` param and iCal's
// `DTSTART/DTEND;VALUE=DATE` use an EXCLUSIVE end date, so we always pass
// end_date + 1 day.

function parseIsoDate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d))
}

function toCompactDate(d: Date): string {
  const y = d.getUTCFullYear()
  const m = String(d.getUTCMonth() + 1).padStart(2, '0')
  const day = String(d.getUTCDate()).padStart(2, '0')
  return `${y}${m}${day}`
}

function exclusiveEnd(endIso: string): Date {
  const end = parseIsoDate(endIso)
  end.setUTCDate(end.getUTCDate() + 1)
  return end
}

export function buildGoogleCalendarUrl(event: LanEvent): string {
  const start = toCompactDate(parseIsoDate(event.start_date))
  const end = toCompactDate(exclusiveEnd(event.end_date))
  const params = new URLSearchParams({
    action: 'TEMPLATE',
    text: event.title,
    dates: `${start}/${end}`,
  })
  if (event.location) params.set('location', event.location)
  if (event.description) params.set('details', event.description)
  return `https://www.google.com/calendar/render?${params.toString()}`
}

// RFC 5545 §3.3.11 text escaping — backslash, comma and semicolon are
// structural in ICALENDAR values, so a literal one in the source text has to
// be backslash-escaped or it corrupts the property.
function escapeIcsText(value: string): string {
  return value
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r?\n/g, '\\n')
}

// RFC 5545 §3.1 line folding: no content line may exceed 75 octets: continuation
// lines start with a single space. Descriptions can run long, so this keeps the
// file spec-compliant instead of just "usually works".
function foldLine(line: string): string {
  const CRLF_FOLD = '\r\n '
  const MAX = 75
  if (line.length <= MAX) return line
  let result = line.slice(0, MAX)
  let rest = line.slice(MAX)
  while (rest.length > 0) {
    const chunk = rest.slice(0, MAX - 1)
    result += CRLF_FOLD + chunk
    rest = rest.slice(MAX - 1)
  }
  return result
}

function buildIcsContent(event: LanEvent): string {
  const start = toCompactDate(parseIsoDate(event.start_date))
  const end = toCompactDate(exclusiveEnd(event.end_date))
  const stamp = toCompactDate(new Date()) + 'T000000Z'
  const uid = `lpm-event-${event.id}@lanpartymanager`

  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//LAN Party Manager//Event Export//EN',
    'CALSCALE:GREGORIAN',
    'BEGIN:VEVENT',
    `UID:${uid}`,
    `DTSTAMP:${stamp}`,
    `DTSTART;VALUE=DATE:${start}`,
    `DTEND;VALUE=DATE:${end}`,
    `SUMMARY:${escapeIcsText(event.title)}`,
  ]
  if (event.location) lines.push(`LOCATION:${escapeIcsText(event.location)}`)
  if (event.description) lines.push(`DESCRIPTION:${escapeIcsText(event.description)}`)
  lines.push('END:VEVENT', 'END:VCALENDAR')

  return lines.map(foldLine).join('\r\n') + '\r\n'
}

export function downloadIcsFile(event: LanEvent): void {
  const blob = new Blob([buildIcsContent(event)], { type: 'text/calendar;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${event.title.replace(/[^a-z0-9]+/gi, '-').replace(/^-+|-+$/g, '') || 'event'}.ics`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
