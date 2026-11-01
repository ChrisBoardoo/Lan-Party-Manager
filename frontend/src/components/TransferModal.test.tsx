import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import i18n from '../i18n'
import { ToastProvider } from '../contexts/ToastContext'
import TransferModal from './TransferModal'
import { expensesApi, usersApi } from '../lib/api'
import type { ProRataResult, User } from '../types'
import { todayIso } from '../lib/eventDates'

// The treasurer's transfer entry (Trésorerie 2.0): pre-filled from the plan,
// several at once for a catch-up, and two confirmations the server also
// enforces — a transfer dated before the plan recalculates it, a member
// outside the split counts anyway.

vi.mock('../lib/api', () => ({
  expensesApi: { recordTransfers: vi.fn() },
  usersApi: { getAll: vi.fn() },
}))
vi.mock('../contexts/AppConfigContext', () => ({
  useAppConfig: () => ({ currency: '€' }),
}))

const TODAY = todayIso()  // the modal's own local day

const data: ProRataResult = {
  total_expenses: 90,
  event_id: 7,
  event_title: 'LAN',
  event_start: '2026-10-14',
  event_end: '2026-10-18',
  total_nights: 4,
  total_person_nights: 12,
  shares: [
    { user_id: 1, username: 'Marsha', avatar_url: null, nights: 4, percentage: 33.3, amount: 30 },
    { user_id: 2, username: 'HugeP', avatar_url: null, nights: 4, percentage: 33.3, amount: 30 },
    { user_id: 3, username: 'Alfred', avatar_url: null, nights: 4, percentage: 33.4, amount: 30 },
  ],
  settlements: [
    { from_user_id: 1, from_username: 'Marsha', to_user_id: 2, to_username: 'HugeP', amount: 25.5, paid: false },
  ],
  plan: { frozen: true, frozen_on: TODAY },
}

const outsider = { id: 4, username: 'pote', is_active: true, deleted_at: null } as unknown as User

function open() {
  const onSaved = vi.fn()
  const onClose = vi.fn()
  render(<ToastProvider><TransferModal data={data} onClose={onClose} onSaved={onSaved} /></ToastProvider>)
  return { onSaved, onClose }
}

describe('TransferModal', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
    vi.mocked(expensesApi.recordTransfers).mockReset()
    vi.mocked(usersApi.getAll).mockResolvedValue([outsider])
  })

  it('pre-fills the amount with what the plan says, until it is typed', async () => {
    open()
    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText('From'), '1')
    await user.selectOptions(screen.getByLabelText('To'), '2')
    expect(screen.getByLabelText('Amount')).toHaveValue('25.50')
    expect(screen.getByText(/Pre-filled with what Marsha owes HugeP/)).toBeInTheDocument()
  })

  it('saves a batch of transfers in one call', async () => {
    vi.mocked(expensesApi.recordTransfers).mockResolvedValue({ plan_recalculated: false })
    const { onSaved, onClose } = open()
    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText('From'), '1')
    await user.selectOptions(screen.getByLabelText('To'), '2')
    await user.click(screen.getByRole('button', { name: /Add and record another/ }))
    expect(screen.getByText('1 transfer ready to save')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('From'), '3')
    await user.selectOptions(screen.getByLabelText('To'), '2')
    await user.type(screen.getByLabelText('Amount'), '10,5')
    await user.click(screen.getByRole('button', { name: 'Save the 2 transfers' }))
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(expensesApi.recordTransfers).toHaveBeenCalledWith(7, [
      { from_user_id: 1, to_user_id: 2, amount: 25.5, transferred_on: TODAY },
      { from_user_id: 3, to_user_id: 2, amount: 10.5, transferred_on: TODAY },
    ], false)
    expect(onClose).toHaveBeenCalled()
  })

  it('a transfer dated before the plan needs the recalculation acknowledged', async () => {
    vi.mocked(expensesApi.recordTransfers).mockResolvedValue({ plan_recalculated: true })
    open()
    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText('From'), '1')
    await user.selectOptions(screen.getByLabelText('To'), '2')
    fireEvent.change(screen.getByLabelText('Transfer date'), { target: { value: '2026-10-16' } })
    expect(screen.getByText(/settlement plan will be recalculated/)).toBeInTheDocument()
    const save = screen.getByRole('button', { name: 'Save the transfer' })
    expect(save).toBeDisabled()
    await user.click(screen.getByLabelText('Understood'))
    expect(save).toBeEnabled()
    await user.click(save)
    expect(await screen.findByText('Settlement plan recalculated')).toBeInTheDocument()
  })

  it('a member outside the split needs a confirmation, sent along', async () => {
    vi.mocked(expensesApi.recordTransfers).mockResolvedValue({ plan_recalculated: false })
    open()
    const user = userEvent.setup()
    await waitFor(() => expect(screen.getAllByRole('option', { name: /pote/ }).length).toBeGreaterThan(0))
    await user.selectOptions(screen.getByLabelText('From'), '4')
    await user.selectOptions(screen.getByLabelText('To'), '2')
    await user.type(screen.getByLabelText('Amount'), '20')
    expect(screen.getByText(/pote is not in this event's split/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save the transfer' })).toBeDisabled()
    await user.click(screen.getByLabelText('I confirm'))
    await user.click(screen.getByRole('button', { name: 'Save the transfer' }))
    await waitFor(() => expect(expensesApi.recordTransfers).toHaveBeenCalled())
    expect(vi.mocked(expensesApi.recordTransfers).mock.calls[0][2]).toBe(true)
  })

  it('refuses the same member twice and a malformed amount', async () => {
    open()
    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText('From'), '1')
    await user.selectOptions(screen.getByLabelText('To'), '1')
    expect(screen.getByText('Pick two different members.')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('To'), '3')
    await user.type(screen.getByLabelText('Amount'), '1.234')
    expect(screen.getByText(/Invalid amount/)).toBeInTheDocument()
  })

  it('a server refusal ends in a toast and keeps the modal open', async () => {
    vi.mocked(expensesApi.recordTransfers).mockRejectedValue({
      isAxiosError: true, message: 'Request failed', response: { status: 409, data: { detail: 'This transfer was just recorded' } },
    })
    const { onClose } = open()
    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText('From'), '1')
    await user.selectOptions(screen.getByLabelText('To'), '2')
    await user.click(screen.getByRole('button', { name: 'Save the transfer' }))
    expect(await screen.findByText('This transfer was just recorded')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })
})
