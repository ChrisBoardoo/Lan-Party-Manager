import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Vote, ChevronRight } from 'lucide-react'
import { trophiesApi } from '../../lib/api'

// Hub nudge while a trophy vote is open and the viewer hasn't voted on all of
// them yet. Only mounted for an attendee of the upcoming/current event.
export default function TrophyVoteBanner({ eventId }: { eventId: number }) {
  const { t } = useTranslation()
  const [pending, setPending] = useState(0)

  useEffect(() => {
    trophiesApi
      .editions(eventId)
      .then((es) => setPending(es.filter((e) => e.status === 'voting' && e.my_vote == null).length))
      .catch(() => setPending(0))
  }, [eventId])

  if (pending === 0) return null

  return (
    <Link
      to={`/events/${eventId}#trophies`}
      className="mb-12 -mt-8 border border-accent bg-accent/10 p-4 flex items-center justify-between gap-4 hover:bg-accent/20 transition-colors"
    >
      <span className="flex items-center gap-3">
        <Vote size={18} strokeWidth={1.5} className="text-accent shrink-0" />
        <span className="font-mono-label text-foreground">{t('trophies.votesOpenBanner', { count: pending })}</span>
      </span>
      <ChevronRight size={16} className="text-accent shrink-0" />
    </Link>
  )
}
