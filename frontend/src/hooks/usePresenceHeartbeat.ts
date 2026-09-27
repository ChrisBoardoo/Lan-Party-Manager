import { useEffect } from 'react'
import { presenceApi } from '../lib/api'

const HEARTBEAT_MS = 45_000

/**
 * While enabled (i.e. a user is logged in), ping the presence endpoint on a
 * timer so the HUB roster can show who's online. Only pings while the tab is
 * visible, and fires an immediate ping when the tab becomes visible again.
 */
export function usePresenceHeartbeat(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return

    const ping = () => {
      if (document.visibilityState === 'visible') {
        presenceApi.ping().catch(() => {})
      }
    }

    ping()
    const id = window.setInterval(ping, HEARTBEAT_MS)
    document.addEventListener('visibilitychange', ping)
    return () => {
      window.clearInterval(id)
      document.removeEventListener('visibilitychange', ping)
    }
  }, [enabled])
}
