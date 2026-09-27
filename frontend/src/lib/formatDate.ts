import i18n from '../i18n'

// Backend timestamps (created_at, last_seen, …) are naive-but-UTC — SQLite
// has no real timezone type, so SQLAlchemy hands back a tz-less datetime and
// it serializes with no "Z"/offset suffix (e.g. "2026-09-14T20:11:25"). Per
// the JS spec, `new Date(...)` on a date-time string with NO timezone marker
// is parsed as LOCAL time, not UTC — so every "time ago" silently shifted by
// the viewer's own UTC offset (caught live: a chat message posted right now
// showed "2h ago" for a UTC+2 viewer). Appending "Z" when the string doesn't
// already carry a marker fixes the one thing that actually needs it — the
// instant in time — no backend change or timezone setting required.
export function parseUtc(iso: string): Date {
  return new Date(/Z$|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`)
}

export function formatDate(d: string) {
  const locale = i18n.language?.startsWith('fr') ? 'fr-FR' : 'en-GB'
  return new Date(d).toLocaleDateString(locale, { day: '2-digit', month: 'short', year: 'numeric' })
}

export function timeAgo(iso: string) {
  const diff = Date.now() - parseUtc(iso).getTime()
  const s = Math.floor(diff / 1000)
  const isFr = i18n.language?.startsWith('fr')

  if (s < 60) return isFr ? `il y a ${s}s` : `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return isFr ? `il y a ${m}min` : `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return isFr ? `il y a ${h}h` : `${h}h ago`
  return formatDate(iso)
}
