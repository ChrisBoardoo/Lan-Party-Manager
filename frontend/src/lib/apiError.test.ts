import { describe, it, expect } from 'vitest'
import type { TFunction } from 'i18next'
import { apiErrorMessage, isApiStatus } from './apiError'

// `t` returns its key: the assertions read which sentence was picked.
const t = ((key: string) => key) as unknown as TFunction

function axiosError(status: number, data?: unknown) {
  return { isAxiosError: true, message: `Request failed with status code ${status}`, response: { status, data } }
}

describe('apiErrorMessage', () => {
  it('uses the server sentence when detail is a string', () => {
    expect(apiErrorMessage(axiosError(409, { detail: 'Username already taken' }), t)).toBe('Username already taken')
  })

  it('reads the first message of a 422 validation list instead of rendering the objects', () => {
    // FastAPI's shape for a pydantic error — what crashed Register with
    // "Objects are not valid as a React child" before 1.4.1.
    const detail = [
      { type: 'value_error', loc: ['body', 'email'], msg: 'The part after the @-sign is reserved', input: 'me@pc.local' },
      { type: 'string_too_short', loc: ['body', 'username'], msg: 'String should have at least 3 characters' },
    ]
    expect(apiErrorMessage(axiosError(422, { detail }), t)).toBe('The part after the @-sign is reserved')
  })

  it('falls back to a generic validation sentence when the list carries no message', () => {
    expect(apiErrorMessage(axiosError(422, { detail: [{ loc: ['body'] }] }), t)).toBe('errors.invalid')
    expect(apiErrorMessage(axiosError(422, {}), t)).toBe('errors.invalid')
  })

  it('names a network failure, which has no response at all', () => {
    expect(apiErrorMessage({ isAxiosError: true, message: 'Network Error' }, t)).toBe('errors.network')
    expect(apiErrorMessage(new Error('Network Error'), t)).toBe('errors.network')
  })

  it('has a sentence per status, and a generic one for the rest', () => {
    expect(apiErrorMessage(axiosError(401), t)).toBe('errors.unauthorized')
    expect(apiErrorMessage(axiosError(403), t)).toBe('errors.forbidden')
    expect(apiErrorMessage(axiosError(404), t)).toBe('errors.notFound')
    expect(apiErrorMessage(axiosError(409), t)).toBe('errors.conflict')
    expect(apiErrorMessage(axiosError(413), t)).toBe('errors.tooLarge')
    expect(apiErrorMessage(axiosError(429), t)).toBe('errors.tooMany')
    expect(apiErrorMessage(axiosError(500), t)).toBe('errors.server')
    expect(apiErrorMessage(axiosError(418), t)).toBe('errors.generic')
    expect(apiErrorMessage('not even an error', t)).toBe('errors.generic')
  })

  it('never returns an empty string for a blank detail', () => {
    expect(apiErrorMessage(axiosError(400, { detail: '   ' }), t)).toBe('errors.generic')
  })
})

describe('isApiStatus', () => {
  it('matches only an axios error with that status', () => {
    expect(isApiStatus(axiosError(403), 403)).toBe(true)
    expect(isApiStatus(axiosError(409), 403)).toBe(false)
    expect(isApiStatus(new Error('x'), 403)).toBe(false)
  })
})
