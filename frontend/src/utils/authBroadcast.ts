/**
 * ROUND_34 / M-18：认证状态广播的单一实现（SSOT）。
 *
 * 缺陷背景：stores/auth.ts 里的 broadcastAuthSync 会同时发 CustomEvent 与
 * BroadcastChannel，但**全仓生产代码没有调用点**；api/request.ts 里另有一个
 * 同名函数只发 CustomEvent。结果 tokenChannel.onmessage 永不触发，ISS-008
 * 声称的跨标签页 token 同步实际未接通（sessionStorage 不触发 storage 事件）。
 *
 * 这里把两份实现收敛到一处，供 store（登录/登出/续期）与请求层（401 刷新
 * 成功/清空状态）共同调用；不依赖 store / api，避免循环引用。
 */

export const AUTH_SYNC_EVENT = 'auth-sync'
export const AUTH_SYNC_CHANNEL = 'auth_token_sync'

export interface AuthSyncPayload {
  token?: string
  refreshToken?: string
  user?: unknown
}

export function broadcastAuthSync(next: AuthSyncPayload): void {
  if (typeof window === 'undefined') return

  // 同标签页：CustomEvent 由 installAuthSyncListener 同步到内存状态
  window.dispatchEvent(new CustomEvent<AuthSyncPayload>(AUTH_SYNC_EVENT, { detail: next }))

  // 跨标签页：token 存 sessionStorage，不触发 storage 事件，只能靠 BroadcastChannel
  if (typeof BroadcastChannel !== 'undefined' && next.token !== undefined) {
    try {
      const channel = new BroadcastChannel(AUTH_SYNC_CHANNEL)
      channel.postMessage(next.token || '')
      channel.close()
    } catch {
      // BroadcastChannel 不可用时静默降级：同标签页同步仍由上面的 CustomEvent 保证
    }
  }
}
