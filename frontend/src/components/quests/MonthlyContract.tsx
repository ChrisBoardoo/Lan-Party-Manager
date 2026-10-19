import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Check, ChevronRight, ScrollText } from 'lucide-react'
import { useAppConfig } from '../../contexts/AppConfigContext'
import { useToast } from '../../contexts/ToastContext'
import { questsApi } from '../../lib/api'
import type { QuestContract } from '../../types'

// Where each objective gets done.
const WHERE: Record<string, string> = {
  lol_squad: '/games-finder',
  minigame: '/minigames',
  chat_days: '/craving-chat',
  rsvp_next: '/events',
  planning_vote: '/planning',
}

/** Toast once a month, the first time a page sees the contract met. Storage
 *  can be missing or throw (private window): then no toast, never an error. */
function sayMetOnce(month: string, say: () => void) {
  const key = `lpm.quests.met.${month}`
  try {
    if (localStorage.getItem(key)) return
    localStorage.setItem(key, '1')
  } catch {
    return
  }
  say()
}

/**
 * The month's contract (quests.py): two objectives out of three for some XP.
 * Loads itself and stays silent on error — the endpoint is gated by the
 * feature, and a 404 must never blank the page around it.
 */
export default function MonthlyContract({ shopLink = true, className = '' }: { shopLink?: boolean; className?: string }) {
  const { t, i18n } = useTranslation()
  const { questsEnabled } = useAppConfig()
  const { push } = useToast()
  const [contract, setContract] = useState<QuestContract | null>(null)

  useEffect(() => {
    if (!questsEnabled) {
      setContract(null)
      return
    }
    let cancelled = false
    questsApi
      .current()
      .then((c) => {
        if (cancelled) return
        setContract(c)
        if (c.done) sayMetOnce(c.month, () => push(t('quests.metToast', { xp: c.xp })))
      })
      .catch(() => setContract(null))
    return () => {
      cancelled = true
    }
  }, [questsEnabled, push, t])

  if (!contract || contract.objectives.length === 0) return null

  const [year, month] = contract.month.split('-').map(Number)
  const monthName = new Date(year, month - 1, 1).toLocaleDateString(i18n.language, { month: 'long' })

  return (
    <section className={`border bg-card p-6 ${contract.done ? 'border-accent' : 'border-border'} ${className}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-3 mb-1">
        <p className="font-mono-label text-accent flex items-center gap-1.5">
          <ScrollText size={12} strokeWidth={1.5} /> {t('quests.title', { month: monthName })}
        </p>
        <p className="font-mono-label text-[10px] text-muted-foreground">
          {contract.days_left <= 1 ? t('quests.lastDay') : t('quests.daysLeft', { count: contract.days_left })}
        </p>
      </div>
      <p className="text-sm text-foreground mb-5">
        {contract.done
          ? t('quests.met', { xp: contract.xp })
          : t('quests.goal', { count: contract.required, total: contract.objectives.length, xp: contract.xp })}
      </p>

      <ul className="border border-border">
        {contract.objectives.map((o) => (
          <li key={o.code} className="border-b border-border last:border-0">
            <Link
              to={WHERE[o.code] ?? '/'}
              className="flex items-center gap-4 px-4 py-3 hover:bg-muted/40 transition-colors"
            >
              <span
                className={`w-5 h-5 flex-shrink-0 border flex items-center justify-center ${
                  o.done ? 'bg-accent border-accent text-accent-foreground' : 'border-border'
                }`}
                aria-label={o.done ? t('quests.objectiveDone') : undefined}
              >
                {o.done && <Check size={12} strokeWidth={2.5} />}
              </span>
              <span className="flex-1 min-w-0">
                <span className={`block text-sm ${o.done ? 'text-muted-foreground' : 'text-foreground'}`}>
                  {t(`quests.objective.${o.code}`, {
                    count: o.target,
                    event: o.event_title ?? t('quests.nextLan'),
                    defaultValue: o.code,
                  })}
                </span>
                {o.target > 1 && (
                  <span className="mt-1.5 flex items-center gap-3">
                    <span
                      className="h-1 bg-muted flex-1"
                      role="progressbar"
                      aria-valuemin={0}
                      aria-valuemax={o.target}
                      aria-valuenow={o.progress}
                    >
                      <span className="block h-full bg-accent" style={{ width: `${(o.progress / o.target) * 100}%` }} />
                    </span>
                    <span className="font-mono-label text-[10px] text-muted-foreground tabular-nums">
                      {o.progress}/{o.target}
                    </span>
                  </span>
                )}
              </span>
              <ChevronRight size={14} className="text-muted-foreground flex-shrink-0" />
            </Link>
          </li>
        ))}
      </ul>

      {contract.done && shopLink && (
        <Link
          to="/collection"
          className="mt-4 inline-flex items-center gap-1.5 font-mono-label text-[11px] text-accent hover:underline"
        >
          {t('quests.toShop')} <ChevronRight size={12} />
        </Link>
      )}
    </section>
  )
}
