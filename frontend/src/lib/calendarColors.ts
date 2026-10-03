// Palette + color assignment for the Planning > Schedule calendar view
// (md/2.features/calendarview.md). These are the 11 official Google Calendar event
// colors, kept as-is rather than reinterpreted — the whole point was to
// borrow those exact codes. `ScheduleBlock.game` is free text with no linked
// game library, so a game's color is either chosen explicitly at lock time
// (LockEditor) or, absent that, derived deterministically from its name so
// the same game always lands on the same color.

export interface CalendarColorSwatch {
  key: string
  hex: string
  textHex: string   // '#0A0A0A' or '#FAFAFA' — whichever reads on `hex`
}

const RAW_PALETTE: Array<{ key: string; hex: string }> = [
  { key: 'tomato', hex: '#d50000' },
  { key: 'flamingo', hex: '#e67c73' },
  { key: 'tangerine', hex: '#f4511e' },
  { key: 'banana', hex: '#f6bf26' },
  { key: 'sage', hex: '#33b679' },
  { key: 'basil', hex: '#0b8043' },
  { key: 'peacock', hex: '#039be5' },
  { key: 'blueberry', hex: '#3f51b5' },
  { key: 'lavender', hex: '#7986cb' },
  { key: 'grape', hex: '#8e24aa' },
  { key: 'graphite', hex: '#616161' },
]

function relativeLuminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  const [sr, sg, sb] = [r, g, b].map((c) => {
    const v = c / 255
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
  })
  return 0.2126 * sr + 0.7152 * sg + 0.0722 * sb
}

export const CALENDAR_PALETTE: CalendarColorSwatch[] = RAW_PALETTE.map(({ key, hex }) => ({
  key,
  hex,
  textHex: relativeLuminance(hex) > 0.4 ? '#0A0A0A' : '#FAFAFA',
}))

const PALETTE_BY_KEY = new Map(CALENDAR_PALETTE.map((s) => [s.key, s]))

// djb2 — deterministic and stable across sessions/devices for the same input,
// which is the point: two proposers naming the same game both land on it.
function hashString(value: string): number {
  let hash = 5381
  for (let i = 0; i < value.length; i++) {
    hash = ((hash << 5) + hash + value.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

export function defaultColorKeyFor(game: string): string {
  const normalized = game.trim().toLowerCase()
  const index = hashString(normalized) % CALENDAR_PALETTE.length
  return CALENDAR_PALETTE[index].key
}

// Resolves a block's actual swatch: its stored color if it has one, else the
// deterministic default for its game name (covers blocks locked before the
// `color` column existed, or left unset on purpose).
export function swatchFor(colorKey: string | null | undefined, game: string): CalendarColorSwatch {
  const key = colorKey ?? defaultColorKeyFor(game)
  return PALETTE_BY_KEY.get(key) ?? CALENDAR_PALETTE[0]
}
