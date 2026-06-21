import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { wsClient } from './useWebSocket'

describe('wsClient', () => {
  const sockets: Array<{ url: string; protocols?: string[]; close: ReturnType<typeof vi.fn> }> = []

  beforeEach(() => {
    vi.useFakeTimers()
    sockets.length = 0
    class MockWebSocket {
      url: string
      protocols?: string[]
      close = vi.fn()
      readyState = 0
      onopen: ((event: Event) => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor(url: string, protocols?: string[]) {
        this.url = url
        this.protocols = protocols
        sockets.push(this)
      }
    }

    vi.stubGlobal('WebSocket', MockWebSocket as any)
  })

  afterEach(() => {
    wsClient.disconnect()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('connects without token in url and sends auth message after open', () => {
    wsClient.connect(12, 'access-1')

    expect(sockets).toHaveLength(1)
    expect(sockets[0].url).toContain('/ws/12')
    expect(sockets[0].url).not.toContain('token=access-1')
    expect(sockets[0].protocols).toBeUndefined()

    const socket = sockets[0] as any
    socket.send = vi.fn()
    socket.onopen?.({} as Event)

    expect(socket.send).toHaveBeenCalledWith(JSON.stringify({ type: 'auth', token: 'access-1' }))
  })

  it('rebinds when auth session changes', () => {
    wsClient.connect(12, 'access-1')
    wsClient.rebindSession(18, 'access-2')

    expect(sockets).toHaveLength(2)
    expect(sockets[1].url).toContain('/ws/18')
    expect(sockets[1].url).not.toContain('token=access-2')
    expect(sockets[1].protocols).toBeUndefined()
  })

  it('disconnects when session becomes invalid', () => {
    wsClient.connect(12, 'access-1')
    wsClient.rebindSession(null, '')

    expect(sockets[0].close).toHaveBeenCalled()
  })

  it('schedules reconnects only while session is valid', () => {
    wsClient.connect(12, 'access-1')
    const socket = sockets[0] as any
    socket.onclose?.()
    vi.advanceTimersByTime(1000)

    expect(sockets.length).toBeGreaterThan(1)
  })

  it('does not reconnect after disconnect', () => {
    wsClient.connect(12, 'access-1')
    wsClient.disconnect()
    vi.advanceTimersByTime(3000)

    expect(sockets[0].close).toHaveBeenCalled()
  })

  it('ignores malformed websocket payloads', () => {
    const handler = vi.fn()
    wsClient.onMessage(handler)
    wsClient.connect(12, 'access-1')
    const socket = sockets[0] as any

    socket.onmessage?.({ data: 'not-json' })

    expect(handler).not.toHaveBeenCalled()
  })
})
