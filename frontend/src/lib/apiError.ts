import axios from 'axios'
import type { TFunction } from 'i18next'

/**
 * The one place that turns a failed API call into a sentence for the user.
 *
 * Before 1.4.1 every page did `e.response?.data?.detail ?? t('…failed')` by
 * hand (F-2/F-5 of the 2026-10-20 review): on a 422 FastAPI's `detail` is a
 * *list* of objects, and rendering it as text threw "Objects are not valid as
 * a React child" — the whole page fell into the ErrorBoundary for an email
 * like `me@pc.local`. A network error (the Pi rebooting mid-LAN) has no
 * `response` at all and surfaced as nothing.
 *
 * Returns, in order: a translated sentence for a network error; the server's
 * own `detail` when it is a string (the backend writes those for people); the
 * first validation message of a 422 list; a translated sentence per status;
 * a generic one otherwise. Never an object, never an empty string.
 */
export function apiErrorMessage(e: unknown, t: TFunction): string {
  if (axios.isAxiosError(e)) {
    if (!e.response) return t('errors.network')
    const { status, data } = e.response
    const detail = (data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail)) {
      const first = detail.find((d) => d && typeof d === 'object' && typeof (d as { msg?: unknown }).msg === 'string')
      if (first) return (first as { msg: string }).msg
      return t('errors.invalid')
    }
    switch (status) {
      case 401:
        return t('errors.unauthorized')
      case 403:
        return t('errors.forbidden')
      case 404:
        return t('errors.notFound')
      case 409:
        return t('errors.conflict')
      case 413:
        return t('errors.tooLarge')
      case 422:
        return t('errors.invalid')
      case 429:
        return t('errors.tooMany')
      default:
        return status >= 500 ? t('errors.server') : t('errors.generic')
    }
  }
  if (e instanceof Error && e.message === 'Network Error') return t('errors.network')
  return t('errors.generic')
}

/** True when the failure is a specific HTTP status — for the few places that
 *  word one status differently (a 409 on a locked RSVP, a 403 on a login). */
export function isApiStatus(e: unknown, status: number): boolean {
  return axios.isAxiosError(e) && e.response?.status === status
}
