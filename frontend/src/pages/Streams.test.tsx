import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import i18n from '../i18n'
import { ToastProvider } from '../contexts/ToastContext'
import Streams from './Streams'
import { streamsApi } from '../lib/api'

// A page whose backend doesn't answer (the Pi rebooting mid-LAN) used to sit
// on its skeleton for ever (F-1 of the 2026-10-20 review). With useLoad it
// says so and offers a retry that actually refetches.

vi.mock('../lib/api', () => ({
  streamsApi: { getAll: vi.fn(), getLiveStatus: vi.fn() },
}))
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, role: 'user' }, isAdmin: false }),
}))

describe('Streams: a dead backend ends the skeleton with a message and a retry', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
    vi.mocked(streamsApi.getAll).mockReset()
    vi.mocked(streamsApi.getLiveStatus).mockResolvedValue({})
  })

  it('shows the network sentence, then recovers on retry', async () => {
    vi.mocked(streamsApi.getAll)
      .mockRejectedValueOnce({ isAxiosError: true, message: 'Network Error' })
      .mockResolvedValueOnce([])
    render(<ToastProvider><Streams /></ToastProvider>)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/server isn't answering/)
    expect(document.querySelector('.animate-pulse')).toBeNull()  // the skeleton is gone

    await userEvent.setup().click(screen.getByRole('button', { name: /retry/i }))
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    expect(streamsApi.getAll).toHaveBeenCalledTimes(2)
  })
})
