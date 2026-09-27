import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react'
import { eventsApi } from '../lib/api'
import { isUpcoming, daysUntil, isChatWindowOpen } from '../lib/eventDates'
import { useAuth } from './AuthContext'
import { useAppConfig } from './AppConfigContext'
import type { LanEvent } from '../types'

const UPCOMING_BANNER_MAX_DAYS = 30

interface UpcomingEventContextType {
  /** The soonest event within 30 days, or null — powers the Hub's countdown
   *  banner. */
  nextEvent: LanEvent | null
  /** `nextEvent`, but only when its Craving Chat is actually reachable right
   *  now (feature on, RSVP'd "in", inside the 30-before/15-after window) —
   *  drives the Navbar's temporary chat icon, which only exists while this
   *  is non-null. Kept here (not recomputed separately in Navbar) so the Hub
   *  banner and the Navbar icon can never disagree about which event is "the"
   *  upcoming one, and so navigating between pages doesn't re-fetch events
   *  on every single route change (Navbar remounts per route — see Layout in
   *  App.tsx — this context lives above the router outlet instead). */
  chatEvent: LanEvent | null
  refreshUpcomingEvent: () => Promise<void>
}

const UpcomingEventContext = createContext<UpcomingEventContextType | null>(null)

export function UpcomingEventProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const { cravingChatEnabled } = useAppConfig()
  const [nextEvent, setNextEvent] = useState<LanEvent | null>(null)

  const refresh = useCallback(async () => {
    try {
      const events = await eventsApi.getAll()
      const upcoming = events
        .filter((e) => isUpcoming(e.end_date))
        .sort((a, b) => a.start_date.localeCompare(b.start_date))
      const soonest = upcoming[0]
      setNextEvent(soonest && daysUntil(soonest.start_date) <= UPCOMING_BANNER_MAX_DAYS ? soonest : null)
    } catch {
      // A hiccup here must never block the rest of the app — worst case, no
      // banner/icon shows until the next successful refresh.
      setNextEvent(null)
    }
  }, [])

  useEffect(() => {
    if (!user) { setNextEvent(null); return }
    refresh()
  }, [user, refresh])

  const chatEvent =
    nextEvent && cravingChatEnabled && nextEvent.my_rsvp === 'in' && isChatWindowOpen(nextEvent.start_date, nextEvent.end_date)
      ? nextEvent
      : null

  return (
    <UpcomingEventContext.Provider value={{ nextEvent, chatEvent, refreshUpcomingEvent: refresh }}>
      {children}
    </UpcomingEventContext.Provider>
  )
}

export const useUpcomingEvent = () => {
  const ctx = useContext(UpcomingEventContext)
  if (!ctx) throw new Error('useUpcomingEvent must be inside UpcomingEventProvider')
  return ctx
}
