import { useEffect, useRef } from 'react'
import { ChatMessage, PinnedMessage } from '../types'

const RECONNECT_MS = 3000

export interface TypingEvent {
  user_id: number
  username: string
}

interface Handlers {
  onMessages: (items: ChatMessage[]) => void
  /** Ephemeral, never persisted — see backend/router_chat.py's
   *  _receive_loop/_broadcast. Fired whenever another attendee's client
   *  pings "I'm typing"; the caller owns expiring it after a short timeout,
   *  since no "stopped typing" frame is ever sent. */
  onTyping: (event: TypingEvent) => void
  /** Fired whenever the event's pinned message changes (pin, unpin, or a
   *  different message getting pinned) — including for the admin who made
   *  the change themselves, so there's no separate "optimistic" path to
   *  keep in sync with this one. */
  onPinned: (message: PinnedMessage | null) => void
}

/**
 * Live push for one event's Craving Chat via `WS /api/chat/{eventId}/ws` —
 * same "poll every 2s, only push new rows" shape as useActivityFeed.ts
 * (backend/router_activity.py), just scoped to a single event's room instead
 * of the global activity feed. Falls back to doing nothing on failure — the
 * chat just stays at whatever the initial REST fetch loaded — and retries
 * the connection rather than giving up, since the room may only just have
 * opened (the backend closes the socket outright if the caller isn't an
 * attendee or the window isn't open yet, so a permanently-refused caller
 * just keeps quietly failing to reconnect instead of erroring loudly).
 *
 * Also the one place this app sends anything *up* a WebSocket rather than
 * only receiving — `sendTyping()` pings the backend, which relays it to
 * every other currently-connected client in the room (see router_chat.py's
 * _receive_loop). Best-effort: silently a no-op while the socket is down or
 * still connecting, same as every other transient failure mode here.
 */
export function useCravingChat(eventId: number | null, handlers: Handlers) {
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!eventId) return
    const token = localStorage.getItem('token')
    if (!token) return

    let socket: WebSocket | null = null
    let reconnectTimer: number | null = null
    let stopped = false

    const connect = () => {
      if (stopped) return
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      // Token in the first frame, not the URL — see useActivityFeed.ts.
      socket = new WebSocket(`${protocol}//${window.location.host}/api/chat/${eventId}/ws`)
      socket.onopen = () => socket?.send(JSON.stringify({ type: 'auth', token }))
      socketRef.current = socket

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'messages' && Array.isArray(data.items) && data.items.length) {
            handlersRef.current.onMessages(data.items)
          } else if (data.type === 'typing' && typeof data.user_id === 'number') {
            handlersRef.current.onTyping({ user_id: data.user_id, username: data.username })
          } else if (data.type === 'pinned') {
            handlersRef.current.onPinned(data.message ?? null)
          }
        } catch {
          // Malformed frame — ignore rather than crash the socket handler.
        }
      }

      socket.onclose = (event) => {
        if (socketRef.current === socket) socketRef.current = null
        // 4401: token refused, retrying can't help — see useActivityFeed.ts.
        if (!stopped && event.code !== 4401) reconnectTimer = window.setTimeout(connect, RECONNECT_MS)
      }
      socket.onerror = () => socket?.close()
    }

    connect()
    return () => {
      stopped = true
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
      socketRef.current = null
      socket?.close()
    }
  }, [eventId])

  const sendTyping = () => {
    const socket = socketRef.current
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'typing' }))
    }
  }

  return { sendTyping }
}
