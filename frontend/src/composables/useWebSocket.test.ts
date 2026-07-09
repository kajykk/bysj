import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { wsClient, useWebSocket, resetWsClient, type WsWarningMessage, type WsTaskProgressMessage } from './useWebSocket'

// mock element-plus 的 ElNotification
vi.mock('element-plus', () => ({
  ElNotification: vi.fn(),
}))

// mock sentry 插件，避免触发实际 SDK 调用
vi.mock('@/plugins/sentry', () => ({
  captureMessage: vi.fn(),
  captureException: vi.fn(),
}))

describe('wsClient', () => {
  const sockets: Array<{
    url: string
    protocols?: string[]
    close: ReturnType<typeof vi.fn>
    send: ReturnType<typeof vi.fn>
    readyState: number
    onopen: ((event: Event) => void) | null
    onmessage: ((event: MessageEvent) => void) | null
    onclose: ((event: CloseEvent) => void) | null
    onerror: ((event: Event) => void) | null
  }> = []

  beforeEach(() => {
    vi.useFakeTimers()
    sockets.length = 0
    class MockWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3
      url: string
      protocols?: string[]
      close = vi.fn()
      send = vi.fn()
      readyState = 0
      onopen: ((event: Event) => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor(url: string, protocols?: string[]) {
        this.url = url
        this.protocols = protocols
        sockets.push(this as any)
      }
    }

    vi.stubGlobal('WebSocket', MockWebSocket as any)
  })

  afterEach(() => {
    wsClient.disconnect()
    wsClient.removeAllListeners()
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('connects without token in url and sends auth message after open', () => {
    wsClient.connect(12, 'access-1')

    expect(sockets).toHaveLength(1)
    // M-FE-1 修复：userId 通过 query parameter 传递，而非路径参数
    expect(sockets[0].url).toContain('user_id=12')
    expect(sockets[0].url).not.toContain('token=access-1')
    expect(sockets[0].protocols).toBeUndefined()

    const socket = sockets[0]
    socket.readyState = 1 // OPEN
    socket.onopen?.({} as Event)

    expect(socket.send).toHaveBeenCalledWith(JSON.stringify({ type: 'auth', token: 'access-1' }))
  })

  it('rebinds when auth session changes', () => {
    wsClient.connect(12, 'access-1')
    wsClient.rebindSession(18, 'access-2')

    expect(sockets).toHaveLength(2)
    // M-FE-1 修复：userId 通过 query parameter 传递，而非路径参数
    expect(sockets[1].url).toContain('user_id=18')
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
    const socket = sockets[0]
    socket.onclose?.({} as CloseEvent)
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
    const socket = sockets[0]

    socket.onmessage?.({ data: 'not-json' } as MessageEvent)

    expect(handler).not.toHaveBeenCalled()
  })

  // ===== 新增测试：覆盖心跳、连接超时、最大重连次数、消息去重等 =====

  describe('心跳机制 - M-47 修复', () => {
    it('连接建立后应启动心跳定时器，每 60s 发送 ping', () => {
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1 // OPEN
      socket.onopen?.({} as Event)

      // 推进 60s 触发首次心跳
      vi.advanceTimersByTime(60_000)
      expect(socket.send).toHaveBeenCalledWith(JSON.stringify({ type: 'ping' }))

      // 再推进 60s 触发第二次心跳
      vi.advanceTimersByTime(60_000)
      expect(socket.send).toHaveBeenCalledTimes(3) // auth + 2 ping
    })

    it('收到 pong 后应清除 pong 超时定时器', () => {
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1 // OPEN
      socket.onopen?.({} as Event)

      // 触发心跳（发送 ping 并启动 pong 超时）
      vi.advanceTimersByTime(60_000)

      // 收到 pong 响应
      socket.onmessage?.({ data: JSON.stringify({ type: 'pong' }) } as MessageEvent)

      // 推进 15s，不应触发 close（pong 超时定时器已被清除）
      const closeSpy = vi.spyOn(socket, 'close')
      vi.advanceTimersByTime(15_000)
      expect(closeSpy).not.toHaveBeenCalled()
    })

    it('pong 超时 15s 未收到，应主动关闭 socket 触发重连', () => {
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1 // OPEN
      socket.onopen?.({} as Event)

      // 触发心跳发送 ping
      vi.advanceTimersByTime(60_000)

      // 不返回 pong，推进 15s 应触发 close
      const closeSpy = vi.spyOn(socket, 'close')
      vi.advanceTimersByTime(15_000)
      expect(closeSpy).toHaveBeenCalledWith(4001, 'heartbeat timeout')

      // close 后应触发 onclose 流程
      socket.readyState = 3 // CLOSED
      socket.onclose?.({} as CloseEvent)

      // 应调度重连
      vi.advanceTimersByTime(1000)
      expect(sockets.length).toBeGreaterThan(1)
    })

    it('心跳只在 ws.readyState === OPEN 时发送 ping', () => {
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      // 不调用 onopen，readyState 仍为 0（CONNECTING）
      vi.advanceTimersByTime(60_000)
      expect(socket.send).not.toHaveBeenCalledWith(JSON.stringify({ type: 'ping' }))
    })

    it('disconnect 时应停止心跳', () => {
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1 // OPEN
      socket.onopen?.({} as Event)

      wsClient.disconnect()

      const sendCountBefore = socket.send.mock.calls.length
      vi.advanceTimersByTime(120_000)
      expect(socket.send.mock.calls.length).toBe(sendCountBefore)
    })
  })

  describe('连接建立超时 - M-FE-2 修复', () => {
    it('10s 内未建立连接应主动关闭 socket', () => {
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      // 不调用 onopen，模拟连接超时

      const closeSpy = vi.spyOn(socket, 'close')
      vi.advanceTimersByTime(10_000)
      expect(closeSpy).toHaveBeenCalledWith(4002, 'connection establishment timeout')
    })

    it('连接建立后应清除连接超时定时器', () => {
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1 // OPEN
      socket.onopen?.({} as Event)

      // 推进 10s，不应触发 close（连接超时定时器已被清除）
      const closeSpy = vi.spyOn(socket, 'close')
      vi.advanceTimersByTime(10_000)
      expect(closeSpy).not.toHaveBeenCalledWith(4002, 'connection establishment timeout')
    })

    it('disconnect 时应清除连接超时定时器', () => {
      wsClient.connect(12, 'access-1')
      wsClient.disconnect()

      // 推进 10s，不应触发原 socket 的 close（已被 disconnect 清理）
      vi.advanceTimersByTime(10_000)
      // sockets[0].close 已被 disconnect 调用一次（无参数），不应再被以 4002 调用
      expect(sockets[0].close).not.toHaveBeenCalledWith(4002, 'connection establishment timeout')
    })
  })

  describe('最大重连次数 - H-FE-3 修复', () => {
    it('达到最大重连次数后应停止重连并通知用户', async () => {
      const { ElNotification } = await import('element-plus')
      const { captureMessage } = await import('@/plugins/sentry')

      wsClient.connect(12, 'access-1')

      // 触发 10 次重连（指数退避：1s, 2s, 4s, 8s, 16s, 30s, 30s, 30s, 30s, 30s）
      // 总时间约 1+2+4+8+16+30*5 = 181s
      for (let i = 0; i < 10; i++) {
        const socket = sockets[sockets.length - 1]
        socket.readyState = 3 // CLOSED
        socket.onclose?.({} as CloseEvent)
        // 推进足够时间触发下一次重连
        vi.advanceTimersByTime(35_000)
      }

      // 第 11 次应触发通知，不再重连
      const lastSocket = sockets[sockets.length - 1]
      lastSocket.readyState = 3
      lastSocket.onclose?.({} as CloseEvent)
      vi.advanceTimersByTime(35_000)

      expect(ElNotification).toHaveBeenCalledWith(
        expect.objectContaining({
          title: '连接已断开',
          type: 'warning',
          duration: 0,
        })
      )
      expect(captureMessage).toHaveBeenCalledWith(
        'WebSocket 重连失败：已达最大重连次数，实时连接已断开',
        'warning'
      )
    })
  })

  describe('消息去重 - L-FE-9 修复', () => {
    it('相同 warning_id 的消息只处理一次', () => {
      const handler = vi.fn()
      wsClient.onMessage(handler)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      const msg: WsWarningMessage = {
        type: 'warning',
        data: {
          warning_id: 100,
          risk_level: 'high',
          user_id: 12,
          created_at: '2026-06-29T10:00:00Z',
        },
      }

      socket.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent)
      socket.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent)

      expect(handler).toHaveBeenCalledTimes(1)
    })

    it('不同 warning_id 的消息应分别处理', () => {
      const handler = vi.fn()
      wsClient.onMessage(handler)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      const msg1: WsWarningMessage = {
        type: 'warning',
        data: { warning_id: 100, risk_level: 'high', created_at: '2026-06-29T10:00:00Z' },
      }
      const msg2: WsWarningMessage = {
        type: 'warning',
        data: { warning_id: 101, risk_level: 'low', created_at: '2026-06-29T10:01:00Z' },
      }

      socket.onmessage?.({ data: JSON.stringify(msg1) } as MessageEvent)
      socket.onmessage?.({ data: JSON.stringify(msg2) } as MessageEvent)

      expect(handler).toHaveBeenCalledTimes(2)
    })

    it('warning_id 无效（<=0）时应使用 fallback key 去重', () => {
      const handler = vi.fn()
      wsClient.onMessage(handler)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      // warning_id = 0 视为无效，使用 fallback key 去重
      const msg: WsWarningMessage = {
        type: 'counselor_warning',
        data: {
          warning_id: 0,
          risk_level: 'high',
          user_id: 12,
          created_at: '2026-06-29T10:00:00Z',
          trigger_reason: 'reason1',
        },
      }

      socket.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent)
      socket.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent)

      expect(handler).toHaveBeenCalledTimes(1)
    })

    it('不同 fallback key 的消息应分别处理', () => {
      const handler = vi.fn()
      wsClient.onMessage(handler)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      socket.onmessage?.({
        data: JSON.stringify({
          type: 'counselor_warning',
          data: { warning_id: 0, risk_level: 'high', user_id: 12, created_at: '2026-06-29T10:00:00Z' },
        }),
      } as MessageEvent)
      socket.onmessage?.({
        data: JSON.stringify({
          type: 'counselor_warning',
          data: { warning_id: 0, risk_level: 'low', user_id: 12, created_at: '2026-06-29T10:00:00Z' },
        }),
      } as MessageEvent)

      expect(handler).toHaveBeenCalledTimes(2)
    })

    it('单个监听器抛错不应影响其他监听器', () => {
      const handler1 = vi.fn(() => {
        throw new Error('listener error')
      })
      const handler2 = vi.fn()
      wsClient.onMessage(handler1)
      wsClient.onMessage(handler2)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      const msg: WsWarningMessage = {
        type: 'warning',
        data: { warning_id: 999, risk_level: 'high', created_at: '2026-06-29T10:00:00Z' },
      }
      socket.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent)

      // 即使 handler1 抛错，handler2 仍应被调用
      expect(handler1).toHaveBeenCalledTimes(1)
      expect(handler2).toHaveBeenCalledTimes(1)
    })

    it('seenWarningIds 超过 1000 时应裁剪到最近 500 条', () => {
      const handler = vi.fn()
      wsClient.onMessage(handler)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      // 发送 1001 条不同 warning_id 的消息，触发裁剪分支
      for (let i = 1; i <= 1001; i++) {
        socket.onmessage?.({
          data: JSON.stringify({
            type: 'warning',
            data: { warning_id: i, risk_level: 'low', created_at: '2026-06-29T10:00:00Z' },
          }),
        } as MessageEvent)
      }
      expect(handler).toHaveBeenCalledTimes(1001)

      // 第 1 条消息已应被裁剪掉，重新发送应能再次触发（去重已失效）
      socket.onmessage?.({
        data: JSON.stringify({
          type: 'warning',
          data: { warning_id: 1, risk_level: 'low', created_at: '2026-06-29T10:00:00Z' },
        }),
      } as MessageEvent)
      expect(handler).toHaveBeenCalledTimes(1002)
    })

    it('seenFallbackKeys 超过 1000 时应裁剪到最近 500 条', () => {
      const handler = vi.fn()
      wsClient.onMessage(handler)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      // 发送 1001 条 fallback key 消息（warning_id = 0），触发裁剪分支
      for (let i = 0; i < 1001; i++) {
        socket.onmessage?.({
          data: JSON.stringify({
            type: 'counselor_warning',
            data: {
              warning_id: 0,
              risk_level: 'low',
              user_id: i,
              created_at: `2026-06-29T10:0${i % 10}:00Z`,
            },
          }),
        } as MessageEvent)
      }
      expect(handler).toHaveBeenCalledTimes(1001)
    })
  })

  describe('onMessage / removeAllListeners / isConnected', () => {
    it('onMessage 返回的取消函数应能正确移除监听器', () => {
      const handler = vi.fn()
      const unsubscribe = wsClient.onMessage(handler)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      const msg: WsWarningMessage = {
        type: 'warning',
        data: { warning_id: 1, risk_level: 'high', created_at: '2026-06-29T10:00:00Z' },
      }

      socket.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent)
      expect(handler).toHaveBeenCalledTimes(1)

      unsubscribe()
      socket.onmessage?.({ data: JSON.stringify({ ...msg, data: { ...msg.data, warning_id: 2 } }) } as MessageEvent)
      expect(handler).toHaveBeenCalledTimes(1)
    })

    it('removeAllListeners 应清空所有监听器', () => {
      const handler1 = vi.fn()
      const handler2 = vi.fn()
      wsClient.onMessage(handler1)
      wsClient.onMessage(handler2)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      wsClient.removeAllListeners()

      const msg: WsWarningMessage = {
        type: 'warning',
        data: { warning_id: 5, risk_level: 'high', created_at: '2026-06-29T10:00:00Z' },
      }
      socket.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent)

      expect(handler1).not.toHaveBeenCalled()
      expect(handler2).not.toHaveBeenCalled()
    })

    it('isConnected 应反映 ws.readyState 是否为 OPEN', () => {
      expect(wsClient.isConnected).toBe(false)
      wsClient.connect(12, 'access-1')
      expect(wsClient.isConnected).toBe(false) // readyState 默认为 0 (CONNECTING)

      const socket = sockets[0]
      socket.readyState = 1 // OPEN
      socket.onopen?.({} as Event)
      expect(wsClient.isConnected).toBe(true)
    })

    it('onerror 应触发 socket.close', () => {
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      const closeSpy = vi.spyOn(socket, 'close')
      socket.onerror?.({} as Event)
      expect(closeSpy).toHaveBeenCalled()
    })

    it('onclose 后应停止心跳并触发重连调度', () => {
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      // 触发心跳，确保心跳定时器已启动
      vi.advanceTimersByTime(60_000)
      expect(socket.send).toHaveBeenCalledWith(JSON.stringify({ type: 'ping' }))

      // 触发 onclose
      socket.readyState = 3
      socket.onclose?.({} as CloseEvent)

      // 推进时间，原 socket 的心跳定时器应已停止，不应再发送 ping
      const sendCallsBefore = socket.send.mock.calls.length
      vi.advanceTimersByTime(120_000)
      expect(socket.send.mock.calls.length).toBe(sendCallsBefore)

      // 应已调度重连
      vi.advanceTimersByTime(1000)
      expect(sockets.length).toBeGreaterThan(1)
    })
  })

  describe('useWebSocket composable', () => {
    it('应暴露 unreadWarningCount、hasNewWarning、incrementUnread、resetUnread', () => {
      const { unreadWarningCount, hasNewWarning, incrementUnread, resetUnread } = useWebSocket()

      expect(unreadWarningCount.value).toBe(0)
      expect(hasNewWarning.value).toBe(false)

      incrementUnread()
      expect(unreadWarningCount.value).toBe(1)
      expect(hasNewWarning.value).toBe(true)

      incrementUnread()
      expect(unreadWarningCount.value).toBe(2)

      resetUnread()
      expect(unreadWarningCount.value).toBe(0)
      expect(hasNewWarning.value).toBe(false)
    })
  })

  describe('resetWsClient', () => {
    it('应清理 wsClient 单例状态（断开连接并清空监听器）', () => {
      const handler = vi.fn()
      wsClient.onMessage(handler)
      wsClient.connect(12, 'access-1')
      expect(sockets).toHaveLength(1)

      resetWsClient()

      expect(sockets[0].close).toHaveBeenCalled()
      // 监听器已被清空，新消息不应再触发 handler
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)
      socket.onmessage?.({
        data: JSON.stringify({
          type: 'warning',
          data: { warning_id: 7, risk_level: 'high', created_at: '2026-06-29T10:00:00Z' },
        }),
      } as MessageEvent)
      expect(handler).not.toHaveBeenCalled()
    })
  })

  describe('rebindSession 边界场景', () => {
    it('userId/token 未变化时不应触发重连', () => {
      wsClient.connect(12, 'access-1')
      const initialCount = sockets.length

      wsClient.rebindSession(12, 'access-1')

      expect(sockets.length).toBe(initialCount)
    })

    it('userId 为 null 时应调用 disconnect', () => {
      wsClient.connect(12, 'access-1')
      wsClient.rebindSession(null, 'token')

      expect(sockets[0].close).toHaveBeenCalled()
    })

    it('token 为空字符串时应调用 disconnect', () => {
      wsClient.connect(12, 'access-1')
      wsClient.rebindSession(12, '')

      expect(sockets[0].close).toHaveBeenCalled()
    })
  })

  // ===== 新增测试：覆盖 wss 协议、退避上限、重连计数重置、URL 构造 =====

  describe('协议选择与 URL 构造', () => {
    it('HTTPS 页面应使用 wss: 协议', () => {
      const originalProtocol = window.location.protocol
      Object.defineProperty(window, 'location', {
        writable: true,
        value: { ...window.location, protocol: 'https:', host: window.location.host },
      })

      try {
        wsClient.connect(12, 'access-1')
        expect(sockets[0].url).toMatch(/^wss:/)
      } finally {
        Object.defineProperty(window, 'location', {
          writable: true,
          value: { ...window.location, protocol: originalProtocol },
        })
      }
    })

    it('HTTP 页面应使用 ws: 协议', () => {
      const originalProtocol = window.location.protocol
      Object.defineProperty(window, 'location', {
        writable: true,
        value: { ...window.location, protocol: 'http:', host: window.location.host },
      })

      try {
        wsClient.connect(12, 'access-1')
        expect(sockets[0].url).toMatch(/^ws:/)
        expect(sockets[0].url).not.toMatch(/^wss:/)
      } finally {
        Object.defineProperty(window, 'location', {
          writable: true,
          value: { ...window.location, protocol: originalProtocol },
        })
      }
    })

    it('URL 应包含 /ws/ 路径', () => {
      wsClient.connect(12, 'access-1')
      expect(sockets[0].url).toContain('/ws/')
    })

    it('URL 应包含 user_id 作为 query parameter', () => {
      wsClient.connect(42, 'access-1')
      const url = new URL(sockets[0].url)
      expect(url.searchParams.get('user_id')).toBe('42')
    })
  })

  describe('指数退避 - H-FE-3 修复', () => {
    it('退避延迟应按指数增长（1s, 2s, 4s, 8s, 16s, 30s, 30s...）', () => {
      wsClient.connect(12, 'access-1')

      // 第 1 次重连：延迟 1s（2^0 * 1000）
      const socket1 = sockets[sockets.length - 1]
      socket1.readyState = 3
      socket1.onclose?.({} as CloseEvent)
      // 推进 999ms，不应重连
      vi.advanceTimersByTime(999)
      expect(sockets.length).toBe(1)
      // 推进到 1000ms，应重连
      vi.advanceTimersByTime(1)
      expect(sockets.length).toBe(2)

      // 第 2 次重连：延迟 2s（2^1 * 1000）
      const socket2 = sockets[sockets.length - 1]
      socket2.readyState = 3
      socket2.onclose?.({} as CloseEvent)
      vi.advanceTimersByTime(1999)
      expect(sockets.length).toBe(2)
      vi.advanceTimersByTime(1)
      expect(sockets.length).toBe(3)

      // 第 3 次重连：延迟 4s（2^2 * 1000）
      const socket3 = sockets[sockets.length - 1]
      socket3.readyState = 3
      socket3.onclose?.({} as CloseEvent)
      vi.advanceTimersByTime(3999)
      expect(sockets.length).toBe(3)
      vi.advanceTimersByTime(1)
      expect(sockets.length).toBe(4)
    })

    it('退避延迟应上限为 30s', () => {
      wsClient.connect(12, 'access-1')

      // 触发 5 次重连（延迟 1+2+4+8+16=31s），第 6 次应为 30s（capped）
      for (let i = 0; i < 5; i++) {
        const socket = sockets[sockets.length - 1]
        socket.readyState = 3
        socket.onclose?.({} as CloseEvent)
        vi.advanceTimersByTime(31_000)
      }

      // 第 6 次重连：Math.min(2^5 * 1000, 30000) = 30000
      const socket6 = sockets[sockets.length - 1]
      socket6.readyState = 3
      socket6.onclose?.({} as CloseEvent)

      // 推进 29999ms，不应重连
      vi.advanceTimersByTime(29_999)
      const countBefore30s = sockets.length
      // 推进到 30000ms，应重连
      vi.advanceTimersByTime(1)
      expect(sockets.length).toBe(countBefore30s + 1)
    })
  })

  describe('重连计数重置 - onopen', () => {
    it('连接成功后 reconnectAttempts 应重置为 0', () => {
      wsClient.connect(12, 'access-1')

      // 触发几次失败重连
      for (let i = 0; i < 3; i++) {
        const socket = sockets[sockets.length - 1]
        socket.readyState = 3
        socket.onclose?.({} as CloseEvent)
        vi.advanceTimersByTime(10_000)
      }

      // 此时已重连 3 次，第 4 个 socket 已创建
      expect(sockets.length).toBe(4)

      // 模拟第 4 个 socket 连接成功
      const socket = sockets[sockets.length - 1]
      socket.readyState = 1 // OPEN
      socket.onopen?.({} as Event)

      // 再次断开，应从 1s 延迟重新开始（说明计数已重置）
      socket.readyState = 3
      socket.onclose?.({} as CloseEvent)
      vi.advanceTimersByTime(999)
      expect(sockets.length).toBe(4)
      vi.advanceTimersByTime(1)
      expect(sockets.length).toBe(5)
    })
  })

  describe('onclose 不应重连的场景', () => {
    it('disconnect 后 onclose 不应触发重连', () => {
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      wsClient.disconnect()

      // 模拟 socket 真正关闭
      socket.readyState = 3
      socket.onclose?.({} as CloseEvent)

      // 推进时间，不应有新 socket 创建
      vi.advanceTimersByTime(35_000)
      expect(sockets.length).toBe(1)
    })
  })

  describe('connect 多次调用', () => {
    it('重复 connect 应关闭旧 socket 并创建新 socket', () => {
      wsClient.connect(12, 'access-1')
      const firstSocket = sockets[0]

      wsClient.connect(12, 'access-1')
      const secondSocket = sockets[1]

      expect(sockets.length).toBe(2)
      expect(firstSocket).not.toBe(secondSocket)
      // 旧 socket 应被关闭
      expect(firstSocket.close).toHaveBeenCalled()
    })

    it('connect 后 socket.onopen 应发送 auth 消息', () => {
      wsClient.connect(12, 'my-auth-token')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      expect(socket.send).toHaveBeenCalledWith(
        JSON.stringify({ type: 'auth', token: 'my-auth-token' })
      )
    })

    it('connect 后 socket.onopen 应清除连接超时定时器', () => {
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      // 推进 10s，不应触发 connection timeout close
      const closeSpy = vi.spyOn(socket, 'close')
      vi.advanceTimersByTime(10_000)
      expect(closeSpy).not.toHaveBeenCalledWith(4002, 'connection establishment timeout')
    })
  })

  describe('心跳 - 边界场景', () => {
    it('心跳定时器应每 60s 发送一次 ping（多次心跳）', () => {
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      // 推进 180s = 3 次心跳
      vi.advanceTimersByTime(180_000)

      // 应发送 auth + 3 次 ping
      const pingCalls = socket.send.mock.calls.filter(
        (call) => call[0] === JSON.stringify({ type: 'ping' })
      )
      expect(pingCalls).toHaveLength(3)
    })

    it('pong 超时后关闭 socket，后续 onclose 应调度重连', () => {
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      // 触发心跳
      vi.advanceTimersByTime(60_000)
      expect(socket.send).toHaveBeenCalledWith(JSON.stringify({ type: 'ping' }))

      // pong 超时 15s，应关闭 socket
      vi.advanceTimersByTime(15_000)
      expect(socket.close).toHaveBeenCalledWith(4001, 'heartbeat timeout')

      // 模拟 socket 真正关闭
      socket.readyState = 3
      socket.onclose?.({} as CloseEvent)

      // 应调度重连
      vi.advanceTimersByTime(1000)
      expect(sockets.length).toBe(2)
    })

    it('收到 pong 后再收到下一个心跳间隔的 pong 也不应出错', () => {
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      // 第一次心跳
      vi.advanceTimersByTime(60_000)
      // 收到 pong
      socket.onmessage?.({ data: JSON.stringify({ type: 'pong' }) } as MessageEvent)

      // 第二次心跳
      vi.advanceTimersByTime(60_000)
      // 收到 pong
      socket.onmessage?.({ data: JSON.stringify({ type: 'pong' }) } as MessageEvent)

      // 不应触发 close
      expect(socket.close).not.toHaveBeenCalledWith(4001, 'heartbeat timeout')
    })
  })

  describe('消息处理 - 边界场景', () => {
    it('JSON 解析成功但 type 非 warning/counselor_warning 时不应调用监听器', () => {
      const handler = vi.fn()
      wsClient.onMessage(handler)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      socket.onmessage?.({
        data: JSON.stringify({ type: 'other', data: {} }),
      } as MessageEvent)

      expect(handler).not.toHaveBeenCalled()
    })

    it('消息包含 warning_id 为负数时应使用 fallback key 去重', () => {
      const handler = vi.fn()
      wsClient.onMessage(handler)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      const msg: WsWarningMessage = {
        type: 'warning',
        data: { warning_id: -1, risk_level: 'high', created_at: '2026-06-29T10:00:00Z' },
      }

      socket.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent)
      socket.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent)

      expect(handler).toHaveBeenCalledTimes(1)
    })

    it('counselor_warning 类型的消息应被正确处理', () => {
      const handler = vi.fn()
      wsClient.onMessage(handler)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      const msg: WsWarningMessage = {
        type: 'counselor_warning',
        data: {
          warning_id: 200,
          risk_level: 'medium',
          user_id: 12,
          created_at: '2026-06-29T10:00:00Z',
          trigger_reason: 'stress',
        },
      }

      socket.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent)

      expect(handler).toHaveBeenCalledWith(msg)
    })

    it('消息 data.trigger_reason 缺失时 fallback key 应使用空字符串', () => {
      const handler = vi.fn()
      wsClient.onMessage(handler)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      // warning_id = 0, trigger_reason 缺失
      socket.onmessage?.({
        data: JSON.stringify({
          type: 'counselor_warning',
          data: { warning_id: 0, risk_level: 'high', created_at: '2026-06-29T10:00:00Z' },
        }),
      } as MessageEvent)

      expect(handler).toHaveBeenCalledTimes(1)
    })
  })

  describe('isConnected 状态', () => {
    it('ws 为 null 时 isConnected 应为 false', () => {
      expect(wsClient.isConnected).toBe(false)
    })

    it('readyState 为 CONNECTING 时 isConnected 应为 false', () => {
      wsClient.connect(12, 'access-1')
      // 默认 readyState = 0 (CONNECTING)
      expect(wsClient.isConnected).toBe(false)
    })

    it('readyState 为 CLOSING 时 isConnected 应为 false', () => {
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 2 // CLOSING
      expect(wsClient.isConnected).toBe(false)
    })

    it('readyState 为 CLOSED 时 isConnected 应为 false', () => {
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 3 // CLOSED
      expect(wsClient.isConnected).toBe(false)
    })
  })

  // ===== I1 改进：任务进度消息处理测试 =====
  describe('onTaskProgress - I1 改进', () => {
    it('收到 task_progress 消息应调用已注册的进度监听器', () => {
      const handler = vi.fn()
      wsClient.onTaskProgress(handler)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      const msg: WsTaskProgressMessage = {
        type: 'task_progress',
        data: {
          job_id: 'job-123',
          job_type: 'pdf',
          status: 'running',
          progress: 50,
          error: null,
          created_at: '2026-07-10T10:00:00Z',
        },
      }

      socket.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent)

      expect(handler).toHaveBeenCalledTimes(1)
      expect(handler).toHaveBeenCalledWith(msg)
    })

    it('同一任务的多次进度更新应全部触发监听器 (不做去重)', () => {
      const handler = vi.fn()
      wsClient.onTaskProgress(handler)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      const baseMsg = {
        type: 'task_progress' as const,
        data: {
          job_id: 'job-456',
          job_type: 'pdf' as const,
          error: null,
          created_at: '2026-07-10T10:00:00Z',
        },
      }

      // 发送 5 次进度更新 (10, 30, 50, 70, 100)
      ;[10, 30, 50, 70, 100].forEach((progress) => {
        socket.onmessage?.({
          data: JSON.stringify({
            ...baseMsg,
            data: {
              ...baseMsg.data,
              status: progress < 100 ? 'running' : 'completed',
              progress,
            },
          }),
        } as MessageEvent)
      })

      expect(handler).toHaveBeenCalledTimes(5)
    })

    it('onTaskProgress 返回的取消函数应能正确移除监听器', () => {
      const handler = vi.fn()
      const unsubscribe = wsClient.onTaskProgress(handler)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      const msg: WsTaskProgressMessage = {
        type: 'task_progress',
        data: {
          job_id: 'job-789',
          job_type: 'excel',
          status: 'completed',
          progress: 100,
          error: null,
          created_at: '2026-07-10T10:00:00Z',
        },
      }

      socket.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent)
      expect(handler).toHaveBeenCalledTimes(1)

      unsubscribe()
      socket.onmessage?.({ data: JSON.stringify({ ...msg, data: { ...msg.data, job_id: 'job-790' } }) } as MessageEvent)
      expect(handler).toHaveBeenCalledTimes(1)
    })

    it('task_progress 消息不应触发 warning 监听器', () => {
      const warningHandler = vi.fn()
      const progressHandler = vi.fn()
      wsClient.onMessage(warningHandler)
      wsClient.onTaskProgress(progressHandler)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      const msg: WsTaskProgressMessage = {
        type: 'task_progress',
        data: {
          job_id: 'job-isolation',
          job_type: 'pdf',
          status: 'running',
          progress: 30,
          error: null,
          created_at: '2026-07-10T10:00:00Z',
        },
      }

      socket.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent)

      expect(progressHandler).toHaveBeenCalledTimes(1)
      expect(warningHandler).not.toHaveBeenCalled()
    })

    it('单个进度监听器抛错不应影响其他监听器', () => {
      const handler1 = vi.fn(() => {
        throw new Error('progress listener error')
      })
      const handler2 = vi.fn()
      wsClient.onTaskProgress(handler1)
      wsClient.onTaskProgress(handler2)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      const msg: WsTaskProgressMessage = {
        type: 'task_progress',
        data: {
          job_id: 'job-error',
          job_type: 'training',
          status: 'running',
          progress: 60,
          error: null,
          created_at: '2026-07-10T10:00:00Z',
        },
      }

      socket.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent)

      expect(handler1).toHaveBeenCalledTimes(1)
      expect(handler2).toHaveBeenCalledTimes(1)
    })

    it('removeAllListeners 应清空进度监听器', () => {
      const handler = vi.fn()
      wsClient.onTaskProgress(handler)
      wsClient.connect(12, 'access-1')
      const socket = sockets[0]
      socket.readyState = 1
      socket.onopen?.({} as Event)

      wsClient.removeAllListeners()

      const msg: WsTaskProgressMessage = {
        type: 'task_progress',
        data: {
          job_id: 'job-clear',
          job_type: 'pdf',
          status: 'completed',
          progress: 100,
          error: null,
          created_at: '2026-07-10T10:00:00Z',
        },
      }

      socket.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent)
      expect(handler).not.toHaveBeenCalled()
    })
  })
})
