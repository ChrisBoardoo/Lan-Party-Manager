import { useEffect, useRef } from 'react'
import { ActivityLogEntry } from '../types'

const RECONNECT_MS = 3000

/**
 * Live push for the Hub activity feed via `GET/WS /api/activity/ws`, instead
 * of each open tab silently going stale until the next full page load (there
 * was no polling here before — the desktop app's own 30s poll is separate,
 * see `desktopapp/src-tauri/src/main.rs`). Falls back to doing nothing on
 * failure — the feed just stays at whatever the initial REST fetch loaded,
 * same as before this existed — and retries the connection rather than
 * giving up permanently, since a self-hosted box or the crew's own reverse
 * proxy may drop it for a few seconds and reconnect fine after.
 */
export function useActivityFeed(enabled: boolean, onNewItems: (items: ActivityLogEntry[]) => void) {
  const onNewItemsRef = useRef(onNewItems)
  onNewItemsRef.current = onNewItems

  useEffect(() => {
    if (!enabled) return
    const token = localStorage.getItem('token')
    if (!token) return

    let socket: WebSocket | null = null
    let reconnectTimer: number | null = null
    let stopped = false

    const connect = () => {
      if (stopped) return
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      // The token goes in the first frame, not the URL: a query string ends up
      // in nginx's and uvicorn's access logs, and from there in every
      // screenshot or paste of those logs.
      socket = new WebSocket(`${protocol}//${window.location.host}/api/activity/ws`)
      socket.onopen = () => socket?.send(JSON.stringify({ type: 'auth', token }))

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'activity' && Array.isArray(data.items) && data.items.length) {
            // Backend sends the new batch oldest-first; the feed itself is
            // newest-first (see router_activity.py's list_activity ordering).
            onNewItemsRef.current([...data.items].reverse())
          }
        } catch {
          // Malformed frame — ignore rather than crash the socket handler.
        }
      }

      socket.onclose = (event) => {
        // 4401 = the server refused the token: retrying with the same one
        // can't succeed, so stop instead of knocking every 3 seconds.
        if (!stopped && event.code !== 4401) reconnectTimer = window.setTimeout(connect, RECONNECT_MS)
      }
      socket.onerror = () => socket?.close()
    }

    connect()
    return () => {
      stopped = true
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [enabled])
}
