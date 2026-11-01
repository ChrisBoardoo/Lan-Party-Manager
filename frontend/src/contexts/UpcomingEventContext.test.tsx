import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { UpcomingEventProvider, useUpcomingEvent } from './UpcomingEventContext'
import { eventsApi } from '../lib/api'
import type { LanEvent } from '../types'

// On 2026-11-01 /events answered before /public-config: with the default rules
// (30 days before, 15 after) only the October LAN's room was open, so the Hub
// opened it, while the admin's rules pointed at the 2027 LAN. No room is picked
// until the rules are known.

const config = vi.hoisted(() => ({
  current: {
    cravingChatEnabled: true,
    chatRules: { daysBefore: 30, daysAfter: 15, alwaysOpen: false },
    configLoaded: false,
  },
}))

vi.mock('../lib/api', () => ({ eventsApi: { getAll: vi.fn() } }))
vi.mock('./AuthContext', () => ({ useAuth: () => ({ user: { id: 1 } }) }))
vi.mock('./AppConfigContext', () => ({ useAppConfig: () => config.current }))

const lan = (id: number, title: string, start_date: string, end_date: string) =>
  ({ id, title, start_date, end_date, my_rsvp: 'in', attendees: [] }) as unknown as LanEvent

function ChatRoom() {
  const { chatEvent } = useUpcomingEvent()
  return <p>{chatEvent ? chatEvent.title : 'no room'}</p>
}

describe('UpcomingEventContext: the chat room waits for the chat rules', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 10, 1, 12))
    vi.mocked(eventsApi.getAll).mockResolvedValue([
      lan(1, 'October LAN', '2026-10-14', '2026-10-18'),
      lan(2, '2027 LAN', '2027-03-10', '2027-03-14'),
    ])
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('picks no room before /public-config, then the one the rules open', async () => {
    config.current = { ...config.current, configLoaded: false }
    const { rerender } = render(<UpcomingEventProvider><ChatRoom /></UpcomingEventProvider>)
    await act(async () => {})  // /events has answered
    expect(screen.getByText('no room')).toBeInTheDocument()

    config.current = {
      cravingChatEnabled: true,
      chatRules: { daysBefore: 30, daysAfter: 15, alwaysOpen: true },
      configLoaded: true,
    }
    rerender(<UpcomingEventProvider><ChatRoom /></UpcomingEventProvider>)
    expect(screen.getByText('2027 LAN')).toBeInTheDocument()
  })
})
