import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useCravingChat } from './useCravingChat'

// A minimal WebSocket stand-in: enough to drive connect/message/close from
// the test without a real socket. `instances` lets a test grab whichever
// WebSocket the hook most recently created.
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  static instances: MockWebSocket[] = []

  readyState = MockWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: ((e: { code: number }) => void) | null = null
  onerror: (() => void) | null = null
  sent: string[] = []

  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  // A real close always carries a CloseEvent with a code (1000 = normal);
  // 4401 is the server refusing the token.
  close(code = 1000) {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.({ code })
  }

  // Test helpers — not part of the real WebSocket API.
  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }

  emitMessage(data: unknown) {
    this.onmessage?.({ data: typeof data === 'string' ? data : JSON.stringify(data) })
  }
}

const RECONNECT_MS = 3000

function lastSocket(): MockWebSocket {
  const socket = MockWebSocket.instances[MockWebSocket.instances.length - 1]
  if (!socket) throw new Error('no WebSocket was constructed')
  return socket
}

function handlers() {
  return {
    onMessages: vi.fn(),
    onTyping: vi.fn(),
    onPinned: vi.fn(),
  }
}

beforeEach(() => {
  vi.useFakeTimers()
  MockWebSocket.instances = []
  vi.stubGlobal('WebSocket', MockWebSocket)
  localStorage.setItem('token', 'test-token')
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  localStorage.clear()
})

describe('useCravingChat connection', () => {
  it('does not open a socket when eventId is null', () => {
    renderHook(() => useCravingChat(null, handlers()))
    expect(MockWebSocket.instances).toHaveLength(0)
  })

  it('does not open a socket when there is no auth token', () => {
    localStorage.clear()
    renderHook(() => useCravingChat(1, handlers()))
    expect(MockWebSocket.instances).toHaveLength(0)
  })

  it('opens exactly one socket, scoped to the event, with no token in the URL', () => {
    renderHook(() => useCravingChat(42, handlers()))
    expect(MockWebSocket.instances).toHaveLength(1)
    const url = lastSocket().url
    expect(url).toContain('/api/chat/42/ws')
    // A query string ends up in nginx's and uvicorn's access logs.
    expect(url).not.toContain('token')
  })

  it('authenticates with its first frame once the socket opens', () => {
    renderHook(() => useCravingChat(42, handlers()))
    expect(lastSocket().sent).toEqual([]) // nothing before the socket is open
    act(() => lastSocket().open())
    expect(lastSocket().sent[0]).toBe(JSON.stringify({ type: 'auth', token: 'test-token' }))
  })
})

describe('useCravingChat message dispatch', () => {
  it('forwards a non-empty messages frame to onMessages', () => {
    const h = handlers()
    renderHook(() => useCravingChat(1, h))
    const items = [{ id: 1, content: 'hi' }]
    act(() => lastSocket().emitMessage({ type: 'messages', items }))
    expect(h.onMessages).toHaveBeenCalledWith(items)
  })

  it('ignores an empty messages frame', () => {
    const h = handlers()
    renderHook(() => useCravingChat(1, h))
    act(() => lastSocket().emitMessage({ type: 'messages', items: [] }))
    expect(h.onMessages).not.toHaveBeenCalled()
  })

  it('forwards a typing frame to onTyping', () => {
    const h = handlers()
    renderHook(() => useCravingChat(1, h))
    act(() => lastSocket().emitMessage({ type: 'typing', user_id: 7, username: 'Chris' }))
    expect(h.onTyping).toHaveBeenCalledWith({ user_id: 7, username: 'Chris' })
  })

  it('forwards a pinned frame, including an explicit unpin (null message)', () => {
    const h = handlers()
    renderHook(() => useCravingChat(1, h))
    act(() => lastSocket().emitMessage({ type: 'pinned', message: { id: 5 } }))
    expect(h.onPinned).toHaveBeenLastCalledWith({ id: 5 })
    act(() => lastSocket().emitMessage({ type: 'pinned', message: null }))
    expect(h.onPinned).toHaveBeenLastCalledWith(null)
  })

  it('does not crash the socket handler on a malformed frame', () => {
    const h = handlers()
    renderHook(() => useCravingChat(1, h))
    expect(() => act(() => lastSocket().emitMessage('not json'))).not.toThrow()
    expect(h.onMessages).not.toHaveBeenCalled()
  })
})

describe('useCravingChat reconnection', () => {
  it('reconnects after the socket closes', () => {
    renderHook(() => useCravingChat(1, handlers()))
    expect(MockWebSocket.instances).toHaveLength(1)

    act(() => lastSocket().close())
    expect(MockWebSocket.instances).toHaveLength(1) // not yet — waits for the backoff

    act(() => vi.advanceTimersByTime(RECONNECT_MS))
    expect(MockWebSocket.instances).toHaveLength(2)
  })

  it('does not reconnect when the server refused the token (4401)', () => {
    renderHook(() => useCravingChat(1, handlers()))
    act(() => lastSocket().close(4401))
    act(() => vi.advanceTimersByTime(RECONNECT_MS * 2))
    expect(MockWebSocket.instances).toHaveLength(1) // retrying the same token can't succeed
  })

  it('stops reconnecting once the component unmounts', () => {
    const { unmount } = renderHook(() => useCravingChat(1, handlers()))
    const socket = lastSocket()
    unmount()
    act(() => socket.close())
    act(() => vi.advanceTimersByTime(RECONNECT_MS * 2))
    expect(MockWebSocket.instances).toHaveLength(1) // the one from initial mount only
  })
})

describe('sendTyping', () => {
  it('sends a typing ping while the socket is open', () => {
    const { result } = renderHook(() => useCravingChat(1, handlers()))
    lastSocket().readyState = MockWebSocket.OPEN
    act(() => result.current.sendTyping())
    expect(lastSocket().sent).toEqual([JSON.stringify({ type: 'typing' })])
  })

  it('is a silent no-op while the socket is still connecting', () => {
    const { result } = renderHook(() => useCravingChat(1, handlers()))
    expect(lastSocket().readyState).toBe(MockWebSocket.CONNECTING)
    act(() => result.current.sendTyping())
    expect(lastSocket().sent).toEqual([])
  })
})
