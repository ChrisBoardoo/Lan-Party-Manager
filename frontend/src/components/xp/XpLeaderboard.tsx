import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronUp, Sparkles } from 'lucide-react'
import type { XpCrewEntry } from '../../types'
import XpCoin from './XpCoin'

const PREVIEW_COUNT = 5

/** The Hub's crew XP ranking — the Hall of Fame's look, for XP instead of titles. */
export default function XpLeaderboard({ entries, currentUserId }: { entries: XpCrewEntry[]; currentUserId?: number }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)

  if (entries.length === 0) return null
  const shown = expanded ? entries : entries.slice(0, PREVIEW_COUNT)

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <Sparkles size={14} strokeWidth={1.5} className="text-accent" />
        <h2 className="text-lg font-black tracking-tight text-foreground">{t('xp.crewTitle')}</h2>
      </div>
      <div className="border border-border bg-card">
        {shown.map((entry, idx) => (
          <Link
            key={entry.user_id}
            to={`/players/${entry.user_id}`}
            className={`flex items-center gap-3 px-4 py-3 border-b border-border last:border-0 hover:bg-muted/50 transition-colors ${
              entry.user_id === currentUserId ? 'bg-accent/5' : ''
            }`}
          >
            <span className={`font-mono font-black text-sm w-5 text-center ${
              idx === 0 ? 'text-yellow-400' : idx === 1 ? 'text-gray-400' : idx === 2 ? 'text-orange-400' : 'text-muted-foreground'
            }`}>
              {idx + 1}
            </span>
            <div className="w-8 h-8 bg-muted border border-border overflow-hidden flex-shrink-0">
              {entry.avatar_url ? (
                <img src={entry.avatar_url} alt={entry.username} className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <span className="text-xs font-black text-muted-foreground">
                    {entry.username[0].toUpperCase()}
                  </span>
                </div>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold text-foreground truncate">{entry.username}</p>
              <p className="font-mono-label text-muted-foreground text-[10px] truncate">
                {t('xp.levelShort', { level: entry.level })} · {t(`xp.title.${entry.title}`, { defaultValue: entry.title })}
              </p>
            </div>
            <span className="font-mono-label text-accent tabular-nums flex-shrink-0">
              {t('xp.total', { total: entry.total.toLocaleString() })}
            </span>
            <XpCoin level={entry.level} size={18} />
          </Link>
        ))}
      </div>
      {entries.length > PREVIEW_COUNT && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1.5 font-mono-label text-muted-foreground hover:text-foreground text-[10px] mt-2"
        >
          {expanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
          {t(expanded ? 'xp.showLess' : 'xp.showAll', { count: entries.length })}
        </button>
      )}
    </div>
  )
}
