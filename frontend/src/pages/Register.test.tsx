import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import i18n from '../i18n'
import Register from './Register'
import { authApi } from '../lib/api'

// The first page-level test of the app (F-5 of the 2026-10-20 review): a 422
// from the server used to crash the whole page into the ErrorBoundary,
// because FastAPI's `detail` is a list of objects and it was rendered as text.

vi.mock('../lib/api', () => ({
  authApi: { register: vi.fn() },
  eventInvitesApi: { validate: vi.fn() },
}))
// The Discord button talks to the API on mount; it isn't what's under test.
vi.mock('../components/ui/DiscordButton', () => ({ default: () => null }))

function axiosError(status: number, data?: unknown) {
  return { isAxiosError: true, message: `Request failed with status code ${status}`, response: { status, data } }
}

async function fillAndSubmit() {
  const user = userEvent.setup()
  const field = (name: string) => document.querySelector(`input[name="${name}"]`) as HTMLInputElement
  await user.type(field('username'), 'crosswax')
  await user.type(field('email'), 'crosswax@pc.local')
  await user.type(field('password'), 'Str0ngPass!42')
  await user.type(field('confirm'), 'Str0ngPass!42')
  const submit = document.querySelector('button[type="submit"]') as HTMLButtonElement
  await waitFor(() => expect(submit).not.toBeDisabled())
  await user.click(submit)
}

describe('Register: what the server answers is shown, never rendered raw', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
    // The page asks whether an invite code is required; no server here.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ json: async () => ({ required: false }) }))
    vi.mocked(authApi.register).mockReset()
  })

  it('shows the first validation message of a 422 instead of crashing', async () => {
    vi.mocked(authApi.register).mockRejectedValue(axiosError(422, {
      detail: [{ type: 'value_error', loc: ['body', 'email'],
                 msg: 'The part after the @-sign is a special-use or reserved name that cannot be used with email.' }],
    }))
    render(<MemoryRouter><Register /></MemoryRouter>)
    await fillAndSubmit()
    expect(await screen.findByText(/special-use or reserved name/)).toBeInTheDocument()
    expect(authApi.register).toHaveBeenCalledTimes(1)
  })

  it('shows the server sentence of a 409 (username taken)', async () => {
    vi.mocked(authApi.register).mockRejectedValue(axiosError(409, { detail: 'Username already taken' }))
    render(<MemoryRouter><Register /></MemoryRouter>)
    await fillAndSubmit()
    expect(await screen.findByText('Username already taken')).toBeInTheDocument()
  })

  it('says the server is not answering on a network error', async () => {
    vi.mocked(authApi.register).mockRejectedValue({ isAxiosError: true, message: 'Network Error' })
    render(<MemoryRouter><Register /></MemoryRouter>)
    await fillAndSubmit()
    expect(await screen.findByText(/server isn't answering/)).toBeInTheDocument()
  })
})
