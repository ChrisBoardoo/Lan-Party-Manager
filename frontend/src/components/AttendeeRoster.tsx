import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatDate } from '../lib/formatDate'
import { eventsApi } from '../lib/api'
import { LanEvent } from '../types'
import { ChevronDown, ChevronUp, UserMinus } from 'lucide-react'

export default function AttendeeRoster({
  event,
  isAdmin,
  currentUserId,
  onAttendanceChanged,
  defaultExpanded,
}: {
  event: LanEvent
  isAdmin: boolean
  currentUserId?: number
  onAttendanceChanged: () => void
  defaultExpanded?: boolean
}) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(!!defaultExpanded)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [error, setError] = useState('')

  // Takes the member off this event only — their account stays active
  // (deactivating is on their profile). Same endpoint as the treasury's stay
  // editor: works before and after the attendance lock, logged, member notified.
  const removeAttendance = async (userId: number, username: string) => {
    if (!confirm(t('events.roster.removeConfirm', { username, title: event.title }))) return
    setBusyId(userId)
    setError('')
    try {
      await eventsApi.adjustRsvp(event.id, userId, { status: 'out' })
      onAttendanceChanged()
    } catch (e: any) {
      setError(t('events.roster.removeFailed', { detail: e.response?.data?.detail ?? '' }))
    } finally {
      setBusyId(null)
    }
  }

  if (event.attendees.length === 0) return null

  return (
    <div className="border-t border-border pt-3 mt-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 font-mono-label text-muted-foreground hover:text-foreground text-[10px]"
      >
        {expanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
        {t(expanded ? 'events.roster.hideAttendees' : 'events.roster.showAttendees', { count: event.attendees.length })}
      </button>
      {expanded && (
        <div className="mt-3 space-y-2">
          {event.attendees.map((a) => (
            <div key={a.user_id} className="flex items-center gap-2 group/attendee">
              <div className="w-6 h-6 bg-muted border border-border overflow-hidden flex-shrink-0">
                {a.avatar_url ? (
                  <img src={a.avatar_url} alt={a.username} className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <span className="text-[10px] font-black text-muted-foreground">
                      {a.username[0].toUpperCase()}
                    </span>
                  </div>
                )}
              </div>
              <span className="text-sm text-foreground truncate">{a.username}</span>
              {a.arrival_date && a.departure_date && (
                <span className="font-mono-label text-muted-foreground text-[10px] ml-auto flex-shrink-0">
                  {formatDate(a.arrival_date)} → {formatDate(a.departure_date)}
                </span>
              )}
              {isAdmin && a.user_id !== currentUserId && (
                <button
                  onClick={() => removeAttendance(a.user_id, a.username)}
                  disabled={busyId !== null}
                  title={t('events.roster.removeAttendance')}
                  className="flex-shrink-0 p-1 opacity-0 group-hover/attendee:opacity-100 text-muted-foreground hover:text-red-400 transition-opacity disabled:opacity-50"
                >
                  <UserMinus size={12} strokeWidth={1.5} />
                </button>
              )}
            </div>
          ))}
          {error && <p className="font-mono-label text-[10px] text-red-400">{error}</p>}
        </div>
      )}
    </div>
  )
}
