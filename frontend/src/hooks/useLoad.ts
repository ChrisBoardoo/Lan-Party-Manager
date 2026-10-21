import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { apiErrorMessage } from '../lib/apiError'

/**
 * A page's initial load, with the three states every page used to hand-roll
 * — and the one most of them forgot (F-1 of the 2026-10-20 review): when the
 * backend doesn't answer (the Pi rebooting mid-LAN), `loading` never went back
 * to false and the page sat on its skeleton for ever, no message, no retry.
 *
 *   const { data, loading, error, retry } = useLoad(() => api.getAll(), [])
 *
 * `loading` is true until the first result or failure, and again during a
 * `retry()`; `error` is a sentence from apiErrorMessage; `reload()` refetches
 * in the background without the skeleton (after a mutation). A result that
 * lands after the component unmounted, or after a newer load started, is
 * dropped. `deps` restarts the load like useEffect's.
 */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const { t } = useTranslation()
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const loadRef = useRef(load)
  loadRef.current = load
  const generation = useRef(0)

  const run = useCallback(async (showSkeleton: boolean) => {
    const mine = ++generation.current
    if (showSkeleton) setLoading(true)
    setError(null)
    try {
      const result = await loadRef.current()
      if (mine !== generation.current) return
      setData(result)
    } catch (e) {
      if (mine !== generation.current) return
      setError(apiErrorMessage(e, t))
    } finally {
      if (mine === generation.current) setLoading(false)
    }
  }, [t])

  useEffect(() => {
    run(true)
    return () => {
      generation.current++ // anything still in flight is stale now
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  const retry = useCallback(() => run(true), [run])
  const reload = useCallback(() => run(false), [run])
  return { data, loading, error, retry, reload, setData }
}
