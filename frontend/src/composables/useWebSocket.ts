import { computed, ref } from 'vue'
import { ElNotification } from 'element-plus'
import { captureMessage } from '@/plugins/sentry'
import i18n from '@/i18n'

const t = i18n.global.t.bind(i18n.global)

export interface WsWarningMessage {
  type: 'warning' | 'counselor_warning'
  data: {
    warning_id: number
    risk_level: string
    trigger_reason?: string
    user_id?: number
    created_at: string
  }
}

class WebSocketClient {
  private ws: WebSocket | null = null
  private userId: number | null = null
  private authToken = ''
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 10
  // L-FE-8 修复：listeners 改用 Set 存储，移除监听器从 O(n) filter 降为 O(1) delete
  private listeners: Set<(msg: WsWarningMessage) => void> = new Set()
  private shouldReconnect = false
  private connectionSeq = 0
  private seenWarningIds = new Set<number>()
  private seenFallbackKeys = new Set<string>()

  // M-47 修复：心跳机制（ping/pong）检测静默断连
  // 后端 idle timeout 为 300s，客户端每 60s 发送一次 ping 保持连接活跃
  // 若 pong 在 15s 内未收到，认为连接已死，主动关闭并触发重连
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null
  private pongTimeoutTimer: ReturnType<typeof setTimeout> | null = null
  private static readonly HEARTBEAT_INTERVAL_MS = 60_000
  private static readonly PONG_TIMEOUT_MS = 15_000
  // M-FE-2 修复：连接建立超时定时器，10s 内未建立连接则关闭并重连
  private connectionTimeoutTimer: ReturnType<typeof setTimeout> | null = null
  private static readonly CONNECTION_TIMEOUT_MS = 10_000

  private _dedupeMessage(msg: WsWarningMessage) {
    const warningId = Number(msg.data.warning_id)
    if (Number.isFinite(warningId) && warningId > 0) {
      if (this.seenWarningIds.has(warningId)) return false
      this.seenWarningIds.add(warningId)
      // 长会话下防止 Set 无界增长：超过阈值时仅保留最近 500 条
      if (this.seenWarningIds.size > 1000) {
        const recent = Array.from(this.seenWarningIds).slice(-500)
        this.seenWarningIds = new Set(recent)
      }
      return true
    }

    const fallbackKey = `${msg.type}:${msg.data.user_id ?? 'unknown'}:${msg.data.created_at}:${msg.data.risk_level}:${msg.data.trigger_reason ?? ''}`
    if (this.seenFallbackKeys.has(fallbackKey)) return false
    this.seenFallbackKeys.add(fallbackKey)
    // 长会话下防止 Set 无界增长：超过阈值时仅保留最近 500 条
    if (this.seenFallbackKeys.size > 1000) {
      const recent = Array.from(this.seenFallbackKeys).slice(-500)
      this.seenFallbackKeys = new Set(recent)
    }
    return true
  }

  connect(userId: number, token: string) {
    this.userId = userId
    this.authToken = token
    this.shouldReconnect = true
    this._resetReconnectState()
    this._connect()
  }

  rebindSession(userId: number | null, token: string) {
    const changed = this.userId !== userId || this.authToken !== token
    this.userId = userId
    this.authToken = token

    if (!userId || !token) {
      this.disconnect()
      return
    }

    this.shouldReconnect = true
    if (changed) {
      this._resetReconnectState()
      this._connect()
    }
  }

  private _connect() {
    if (!this.userId || !this.authToken || !this.shouldReconnect) return

    const seq = ++this.connectionSeq
    this.ws?.close()

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    // M-FE-1 修复：userId 不再放在 URL 路径中（避免被日志/代理记录），
    // 改为通过 query parameter 传递
    const url = new URL(`${wsProtocol}//${host}/ws/`)
    url.searchParams.set('user_id', String(this.userId))

    const socket = new WebSocket(url.toString())
    this.ws = socket

    // M-FE-2 修复：设置 10s 连接建立超时，超时后关闭 socket 触发重连
    if (this.connectionTimeoutTimer) clearTimeout(this.connectionTimeoutTimer)
    this.connectionTimeoutTimer = setTimeout(() => {
      if (seq !== this.connectionSeq) return
      // 连接超时未建立，主动关闭触发 onclose 重连流程
      if (this.ws && this.ws.readyState !== WebSocket.CLOSED) {
        this.ws.close(4002, 'connection establishment timeout')
      }
    }, WebSocketClient.CONNECTION_TIMEOUT_MS)

    socket.onopen = () => {
      if (seq !== this.connectionSeq) return
      // M-FE-2 修复：连接已建立，清除连接超时定时器
      if (this.connectionTimeoutTimer) {
        clearTimeout(this.connectionTimeoutTimer)
        this.connectionTimeoutTimer = null
      }
      socket.send(JSON.stringify({ type: 'auth', token: this.authToken }))
      this.reconnectAttempts = 0
      // M-47 修复：连接成功后启动心跳
      this._startHeartbeat()
    }

    socket.onmessage = (event) => {
      if (seq !== this.connectionSeq) return
      try {
        const msg = JSON.parse(event.data)
        // M-47 修复：处理 pong 响应，清除超时定时器
        if (msg.type === 'pong') {
          this._clearPongTimeout()
          return
        }
        if ((msg.type === 'warning' || msg.type === 'counselor_warning') && this._dedupeMessage(msg as WsWarningMessage)) {
          // L-FE-9 修复：单个监听器抛错时捕获，避免影响其他监听器；消息已去重，不从 Set 移除
          this.listeners.forEach((cb) => {
            try {
              cb(msg as WsWarningMessage)
            } catch {
              // 监听器内部异常静默处理，不影响后续监听器调用
            }
          })
        }
      } catch {
        // ignore non-JSON messages
      }
    }

    socket.onclose = () => {
      if (seq !== this.connectionSeq) return
      this.ws = null
      // M-47 修复：连接关闭时停止心跳
      this._stopHeartbeat()
      if (this.shouldReconnect) {
        this._scheduleReconnect()
      }
    }

    socket.onerror = () => {
      if (seq !== this.connectionSeq) return
      socket.close()
    }
  }

  // M-47 修复：心跳机制实现
  private _startHeartbeat() {
    this._stopHeartbeat()
    this.heartbeatTimer = setInterval(() => {
      if (this.ws?.readyState !== WebSocket.OPEN) return
      // 发送 ping 并启动 pong 超时等待
      this.ws.send(JSON.stringify({ type: 'ping' }))
      this._schedulePongTimeout()
    }, WebSocketClient.HEARTBEAT_INTERVAL_MS)
  }

  private _stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
    this._clearPongTimeout()
  }

  private _schedulePongTimeout() {
    this._clearPongTimeout()
    this.pongTimeoutTimer = setTimeout(() => {
      // pong 超时未收到，认为连接已死，主动关闭触发重连
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.close(4001, 'heartbeat timeout')
      }
    }, WebSocketClient.PONG_TIMEOUT_MS)
  }

  private _clearPongTimeout() {
    if (this.pongTimeoutTimer) {
      clearTimeout(this.pongTimeoutTimer)
      this.pongTimeoutTimer = null
    }
  }

  private _scheduleReconnect() {
    if (!this.shouldReconnect || !this.userId || !this.authToken) return
    // H-FE-3 修复：达到最大重连次数时提示用户并上报 Sentry
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      ElNotification({
        title: t('webSocket.disconnectedTitle'),
        message: t('webSocket.disconnectedMessage'),
        type: 'warning',
        duration: 0,
      })
      captureMessage('WebSocket 重连失败：已达最大重连次数，实时连接已断开', 'warning')
      return
    }
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000)
    this.reconnectAttempts++
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.reconnectTimer = setTimeout(() => this._connect(), delay)
  }

  private _resetReconnectState() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.reconnectAttempts = 0
  }

  disconnect() {
    this.shouldReconnect = false
    this._resetReconnectState()
    // M-47 修复：断开时停止心跳
    this._stopHeartbeat()
    // M-FE-2 修复：断开时清除连接超时定时器
    if (this.connectionTimeoutTimer) {
      clearTimeout(this.connectionTimeoutTimer)
      this.connectionTimeoutTimer = null
    }
    this.connectionSeq++
    this.ws?.close()
    this.ws = null
    this.userId = null
    this.authToken = ''
    this.seenWarningIds.clear()
    this.seenFallbackKeys.clear()
    // M-27 修复：不清空 listeners 数组，避免重连后监听器丢失
    // 监听器应由注册者通过 onMessage 返回的取消函数负责清理
    // 如需清空所有监听器，请显式调用 removeAllListeners()
  }

  removeAllListeners() {
    this.listeners.clear()
  }

  onMessage(cb: (msg: WsWarningMessage) => void) {
    this.listeners.add(cb)
    return () => {
      this.listeners.delete(cb)
    }
  }

  get isConnected() {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

export const wsClient = new WebSocketClient()

// L-FE-20 修复：供测试调用，重置全局单例状态避免测试间状态污染
export function resetWsClient() {
  wsClient.disconnect()
  wsClient.removeAllListeners()
}

const unreadWarningCount = ref(0)

export function useWebSocket() {
  const hasNewWarning = computed(() => unreadWarningCount.value > 0)

  function incrementUnread() {
    unreadWarningCount.value++
  }

  function resetUnread() {
    unreadWarningCount.value = 0
  }

  return {
    unreadWarningCount,
    hasNewWarning,
    incrementUnread,
    resetUnread,
  }
}
