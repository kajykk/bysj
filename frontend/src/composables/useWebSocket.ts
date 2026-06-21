import { computed, ref } from 'vue'

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
  private listeners: Array<(msg: WsWarningMessage) => void> = []
  private shouldReconnect = false
  private connectionSeq = 0
  private seenWarningIds = new Set<number>()
  private seenFallbackKeys = new Set<string>()

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
    const url = new URL(`${wsProtocol}//${host}/ws/${this.userId}`)

    const socket = new WebSocket(url.toString())
    this.ws = socket

    socket.onopen = () => {
      if (seq !== this.connectionSeq) return
      socket.send(JSON.stringify({ type: 'auth', token: this.authToken }))
      this.reconnectAttempts = 0
    }

    socket.onmessage = (event) => {
      if (seq !== this.connectionSeq) return
      try {
        const msg = JSON.parse(event.data)
        if ((msg.type === 'warning' || msg.type === 'counselor_warning') && this._dedupeMessage(msg as WsWarningMessage)) {
          this.listeners.forEach((cb) => cb(msg as WsWarningMessage))
        }
      } catch {
        // ignore non-JSON messages
      }
    }

    socket.onclose = () => {
      if (seq !== this.connectionSeq) return
      this.ws = null
      if (this.shouldReconnect) {
        this._scheduleReconnect()
      }
    }

    socket.onerror = () => {
      if (seq !== this.connectionSeq) return
      socket.close()
    }
  }

  private _scheduleReconnect() {
    if (!this.shouldReconnect || this.reconnectAttempts >= this.maxReconnectAttempts || !this.userId || !this.authToken) return
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
    this.connectionSeq++
    this.ws?.close()
    this.ws = null
    this.userId = null
    this.authToken = ''
    this.seenWarningIds.clear()
    this.seenFallbackKeys.clear()
    // P1-D-9 修复：清空 listeners 数组，防止未清理的监听器回调残留导致内存泄漏
    this.listeners = []
  }

  onMessage(cb: (msg: WsWarningMessage) => void) {
    this.listeners.push(cb)
    return () => {
      this.listeners = this.listeners.filter((l) => l !== cb)
    }
  }

  get isConnected() {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

export const wsClient = new WebSocketClient()

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
