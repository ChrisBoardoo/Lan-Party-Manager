import { useTranslation } from 'react-i18next'
import type { BadgeAward } from '../types'

// The API sends codes, not labels — the strings live here so translators own
// them and EN/FR parity stays enforceable. An unknown code (a badge from a newer
// backend) falls back to its code rather than rendering a raw i18n key.
const BADGE_EMOJI: Record<string, string> = {
  champion: '🏆',
  undefeated: '🛡️',
  first_blood: '🩸',
  night_owl: '🦉',
  shutterbug: '📸',
  crowd_pleaser: '😂',
  quartermaster: '📦',
  snack_sponsor: '🍕',
  veteran: '🎖️',
}

interface Props {
  badges: BadgeAward[]
  /** Show who earned it — for the recap, where badges span the whole crew. */
  showWinner?: boolean
}

export default function BadgeList({ badges, showWinner = false }: Props) {
  const { t } = useTranslation()
  if (badges.length === 0) return null

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {badges.map((badge) => {
        const label = t(`badges.${badge.code}.label`, { defaultValue: badge.code })
        const desc = t(`badges.${badge.code}.desc`, { defaultValue: '' })
        return (
          <div
            key={`${badge.code}-${badge.user_id}`}
            className="border border-border bg-card p-4 flex items-start gap-3"
            title={desc}
          >
            <span className="text-2xl leading-none shrink-0" aria-hidden="true">
              {BADGE_EMOJI[badge.code] ?? '⭐'}
            </span>
            <div className="min-w-0">
              <p className="font-mono-label text-accent">
                {label}
                {badge.value != null && <span className="text-muted-foreground ml-1.5">×{badge.value}</span>}
              </p>
              {showWinner && (
                <p className="text-sm text-foreground truncate">{badge.username}</p>
              )}
              {desc && <p className="text-xs text-muted-foreground mt-0.5">{desc}</p>}
            </div>
          </div>
        )
      })}
    </div>
  )
}
