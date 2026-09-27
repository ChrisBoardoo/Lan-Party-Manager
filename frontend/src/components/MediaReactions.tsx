import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { MediaItem, MediaReactionCount } from '../types'
import { mediaApi } from '../lib/api'

// Mirrors REACTION_EMOJI in backend/router_media.py. A fixed set (rather than
// free text) keeps the "best of" scoring meaningful and the row a predictable
// width — if you change one side, change the other.
export const REACTION_EMOJI = ['🔥', '😂', '💀', '❤️', '🏆', '👀'] as const

// Discord-ish: long enough that a tap never reads as a press, short enough
// that "hold to see who" feels immediate.
const LONG_PRESS_MS = 450

// Intl.ListFormat ("A, B and C" / "A, B et C") is ES2021; the project's TS lib
// is ES2020, so it's typed locally rather than bumping the lib for one call.
// Every browser this app supports ships it; the join is a belt-and-braces fallback.
type ListFormatCtor = new (
  locale: string,
  opts?: { style: 'long'; type: 'conjunction' },
) => { format: (items: string[]) => string }

function nameList(users: string[], lang: string) {
  const ListFormat = (Intl as unknown as { ListFormat?: ListFormatCtor }).ListFormat
  if (!ListFormat) return users.join(', ')
  try {
    return new ListFormat(lang, { style: 'long', type: 'conjunction' }).format(users)
  } catch {
    return users.join(', ')
  }
}

/**
 * The emoji toggle row itself, decoupled from what is being reacted to — media
 * items and setups share the same (emoji, count, mine, users) tally shape.
 * With `onToggle` it renders every emoji as a toggle button; without it, only
 * the nonzero tallies, read-only.
 *
 * Hovering a tally (or holding it, on touch) shows who reacted. On touch, a
 * long press must NOT also toggle the reaction — the `longPressed` ref eats
 * the click that browsers fire after touchend.
 */
export function ReactionBar({
  reactions,
  onToggle,
  busy = false,
}: {
  reactions: MediaReactionCount[]
  onToggle?: (emoji: string) => void
  busy?: boolean
}) {
  const { t, i18n } = useTranslation()
  const [tip, setTip] = useState<string | null>(null)
  const pressTimer = useRef<number | null>(null)
  const longPressed = useRef(false)

  const clearPressTimer = () => {
    if (pressTimer.current !== null) {
      window.clearTimeout(pressTimer.current)
      pressTimer.current = null
    }
  }

  const tooltipFor = (tally: MediaReactionCount | undefined) =>
    tally && tally.emoji === tip && tally.users.length > 0 ? (
      <span
        role="tooltip"
        className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2 py-1 bg-card border border-border text-foreground text-xs whitespace-nowrap pointer-events-none z-20"
      >
        {t('common.reactedBy', { names: nameList(tally.users, i18n.language) })}
      </span>
    ) : null

  // Shared by the buttons and the read-only spans. The touch pair implements
  // press-and-hold: show after LONG_PRESS_MS, hide on release.
  const tipHandlers = (tally: MediaReactionCount | undefined) => ({
    onMouseEnter: () => setTip(tally?.emoji ?? null),
    onMouseLeave: () => setTip(null),
    onTouchStart: () => {
      longPressed.current = false
      if (!tally || tally.users.length === 0) return
      pressTimer.current = window.setTimeout(() => {
        longPressed.current = true
        setTip(tally.emoji)
      }, LONG_PRESS_MS)
    },
    onTouchEnd: () => {
      clearPressTimer()
      setTip(null)
    },
    onTouchCancel: () => {
      clearPressTimer()
      setTip(null)
    },
    // A long press on mobile otherwise pops the browser's own menu.
    onContextMenu: (e: React.MouseEvent) => {
      if (tally && tally.users.length > 0) e.preventDefault()
    },
  })

  if (!onToggle) {
    if (reactions.length === 0) return null
    return (
      <div className="flex flex-wrap items-center gap-1.5">
        {reactions.map((r) => (
          <span
            key={r.emoji}
            {...tipHandlers(r)}
            className="relative select-none px-2 py-1 border border-border text-muted-foreground text-sm leading-none"
          >
            {tooltipFor(r)}
            {r.emoji}
            <span className="ml-1.5 font-mono text-xs">{r.count}</span>
          </span>
        ))}
      </div>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {REACTION_EMOJI.map((emoji) => {
        const tally = reactions.find((r) => r.emoji === emoji)
        return (
          <button
            key={emoji}
            type="button"
            {...tipHandlers(tally)}
            onClick={() => {
              if (longPressed.current) {
                longPressed.current = false
                return
              }
              onToggle(emoji)
            }}
            disabled={busy}
            aria-pressed={tally?.mine ?? false}
            className={`relative select-none px-2 py-1 border text-sm leading-none transition-colors disabled:opacity-50 ${
              tally?.mine
                ? 'border-accent text-accent bg-accent/10'
                : 'border-border text-muted-foreground hover:border-border-hover'
            }`}
          >
            {tooltipFor(tally)}
            {emoji}
            {tally && <span className="ml-1.5 font-mono text-xs">{tally.count}</span>}
          </button>
        )
      })}
    </div>
  )
}

interface Props {
  item: MediaItem
  onChange?: (item: MediaItem) => void
}

export default function MediaReactions({ item, onChange }: Props) {
  const [busy, setBusy] = useState(false)

  const toggle = async (emoji: string) => {
    setBusy(true)
    try {
      onChange?.(await mediaApi.react(item.id, emoji))
    } catch {
      // A failed toggle just leaves the row as it was — nothing to recover.
    } finally {
      setBusy(false)
    }
  }

  return <ReactionBar reactions={item.reactions} onToggle={toggle} busy={busy} />
}
