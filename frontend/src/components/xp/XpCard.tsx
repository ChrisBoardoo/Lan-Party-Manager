import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { useAppConfig } from '../../contexts/AppConfigContext'
import { xpApi } from '../../lib/api'
import type { XpSummary } from '../../types'
import XpCoin from './XpCoin'

/** XP progress as a 0–100 share of the current level's span. */
export function levelProgress(xp: Pick<XpSummary, 'total' | 'level_floor' | 'next_level_at'>): number {
  const span = xp.next_level_at - xp.level_floor
  if (span <= 0) return 100
  return Math.min(100, Math.max(0, Math.round(((xp.total - xp.level_floor) / span) * 100)))
}

/**
 * A member's XP: token, level, progress to the next one, and what it's made of.
 * Loads itself, in its own effect with its own catch — the endpoint is gated by
 * the xp feature, and a member's 404 must never blank the page around it.
 */
export default function XpCard({ userId, isSelf = false }: { userId: number; isSelf?: boolean }) {
  const { t } = useTranslation()
  const { xpEnabled } = useAppConfig()
  const [xp, setXp] = useState<XpSummary | null>(null)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (!xpEnabled) {
      setXp(null)
      return
    }
    xpApi.user(userId).then(setXp).catch(() => setXp(null))
  }, [userId, xpEnabled])

  if (!xp) return null

  const title = t(`xp.title.${xp.title}`, { defaultValue: xp.title })
  const remaining = xp.next_level_at - xp.total

  return (
    <div className="border border-border bg-card p-6">
      <div className="flex items-center gap-5">
        <XpCoin level={xp.level} size={56} title={t('xp.levelShort', { level: xp.level })} />
        <div className="flex-1 min-w-0">
          <p className="font-mono-label text-accent">
            {t('xp.level', { level: xp.level })} · {title}
          </p>
          <p className="text-3xl font-black tracking-tight text-foreground tabular-nums leading-tight">
            {t('xp.total', { total: xp.total.toLocaleString() })}
          </p>
          <div
            className="h-1.5 bg-muted mt-2"
            role="progressbar"
            aria-valuemin={xp.level_floor}
            aria-valuemax={xp.next_level_at}
            aria-valuenow={xp.total}
          >
            <div className="h-full bg-accent" style={{ width: `${levelProgress(xp)}%` }} />
          </div>
          <p className="font-mono-label text-muted-foreground text-[10px] mt-1.5">
            {t('xp.toNext', { count: remaining, level: xp.level + 1 })}
          </p>
        </div>
      </div>

      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 font-mono-label text-muted-foreground hover:text-foreground text-[10px] mt-4"
      >
        {expanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
        {t(expanded ? 'xp.hideDetails' : 'xp.showDetails')}
      </button>

      {expanded && (
        <div className="mt-3 space-y-3">
          {xp.breakdown.length > 0 ? (
            <div className="border border-border">
              {xp.breakdown.map((line) => (
                <div
                  key={line.code}
                  className="flex items-baseline justify-between gap-4 px-4 py-2 border-b border-border last:border-0"
                >
                  <span className="text-sm text-foreground">
                    {t(`xp.source.${line.code}`, { count: line.count, defaultValue: line.code })}
                  </span>
                  <span className="font-mono-label text-accent tabular-nums flex-shrink-0">+{line.xp}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t(isSelf ? 'xp.emptySelf' : 'xp.empty')}</p>
          )}
          <p className="text-xs text-muted-foreground">{t('xp.howTo')}</p>
        </div>
      )}
    </div>
  )
}
