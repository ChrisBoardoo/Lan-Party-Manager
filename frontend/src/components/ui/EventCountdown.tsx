import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Timer } from 'lucide-react'

const LAST_WEEK_MS = 7 * 86400000

interface Props {
  startDate: string
  /** 'compact' (default): static "N days to go" until the last week, then a
   *  ticking HHH-MM-SS. 'full': always a live DD-HH-MM-SS clock — used only
   *  on the Hub, where the countdown is the whole point of the banner and a
   *  static day-count reads as less exciting than an actually ticking clock. */
  format?: 'compact' | 'full'
}

export default function EventCountdown({ startDate, format = 'compact' }: Props) {
  const { t } = useTranslation()
  const target = new Date(`${startDate}T00:00:00`).getTime()
  const [now, setNow] = useState(Date.now())
  const diff = target - now
  const full = format === 'full'
  const withinLastWeek = diff > 0 && diff <= LAST_WEEK_MS

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), full || withinLastWeek ? 1000 : 60000)
    return () => clearInterval(id)
  }, [withinLastWeek, full])

  if (diff <= 0) {
    return (
      <span className="font-mono-label text-accent flex items-center gap-1.5 animate-pulse">
        <Timer size={10} /> {t('events.countdown.happeningNow')}
      </span>
    )
  }

  const totalSeconds = Math.floor(diff / 1000)
  const days = Math.floor(totalSeconds / 86400)

  if (full) {
    const hours = Math.floor((totalSeconds % 86400) / 3600)
    const minutes = Math.floor((totalSeconds % 3600) / 60)
    const seconds = totalSeconds % 60
    return (
      <span className="font-mono-label text-accent flex items-center gap-1.5 tabular-nums">
        <Timer size={10} />
        {String(days).padStart(2, '0')}{t('events.countdown.unitDays')}-
        {String(hours).padStart(2, '0')}{t('events.countdown.unitHours')}-
        {String(minutes).padStart(2, '0')}{t('events.countdown.unitMinutes')}-
        {String(seconds).padStart(2, '0')}{t('events.countdown.unitSeconds')}
      </span>
    )
  }

  if (!withinLastWeek) {
    return (
      <span className="font-mono-label text-accent flex items-center gap-1.5">
        <Timer size={10} /> {t('events.countdown.daysToGo', { count: days })}
      </span>
    )
  }

  const totalHours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  return (
    <span className="font-mono-label text-accent flex items-center gap-1.5 tabular-nums">
      <Timer size={10} />
      {String(totalHours).padStart(3, '0')}-{String(minutes).padStart(2, '0')}-{String(seconds).padStart(2, '0')}
    </span>
  )
}
