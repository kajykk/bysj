import { computed, onScopeDispose, ref } from 'vue'
import { defineStore } from 'pinia'
import { authApi, type UserInfo } from '@/api/auth'
import { refreshAccessToken } from '@/api/request'
import {
  clearStoredAuth,
  getStoredRefreshToken,
  getStoredToken,
  getStoredUser,
  setStoredAuth,
} from '@/utils/authStorage'

interface AuthSyncDetail {
  token?: string
  refreshToken?: string
  user?: UserInfo | null
}

const AUTH_SYNC_EVENT = 'auth-sync'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(getStoredToken())
  const refreshToken = ref<string>(getStoredRefreshToken())
  const user = ref<UserInfo | null>(getStoredUser())

  const isLoggedIn = computed(() => !!token.value)
  const role = computed(() => user.value?.role || '')

  function syncAuth(next: AuthSyncDetail) {
    if (next.token !== undefined) token.value = next.token
    if (next.refreshToken !== undefined) refreshToken.value = next.refreshToken
    if (next.user !== undefined) user.value = next.user
  }

  function persistAuth(next: AuthSyncDetail) {
    setStoredAuth(next)
    syncAuth(next)
  }

  function broadcastAuthSync(next: AuthSyncDetail) {
    if (typeof window === 'undefined') return
    window.dispatchEvent(new CustomEvent<AuthSyncDetail>(AUTH_SYNC_EVENT, { detail: next }))
    // ISS-008: 通过 BroadcastChannel 跨标签页同步 token
    if (typeof BroadcastChannel !== 'undefined' && next.token !== undefined) {
      try {
        const channel = new BroadcastChannel('auth_token_sync')
        channel.postMessage(next.token || '')
        channel.close()
      } catch {
        // BroadcastChannel 不可用时静默降级
      }
    }
  }

  function installAuthSyncListener() {
    if (typeof window === 'undefined') return
    // 同标签页内同步：使用 CustomEvent 广播 auth 变更
    const handler = (event: Event) => {
      const customEvent = event as CustomEvent<AuthSyncDetail>
      if (customEvent.detail) syncAuth(customEvent.detail)
    }
    window.addEventListener(AUTH_SYNC_EVENT, handler)

    // ISS-008 修复：跨标签页 token 同步改用 BroadcastChannel
    // （sessionStorage 不触发 storage 事件，无法跨标签页同步 token）
    let tokenChannel: BroadcastChannel | null = null
    if (typeof BroadcastChannel !== 'undefined') {
      tokenChannel = new BroadcastChannel('auth_token_sync')
      tokenChannel.onmessage = (event: MessageEvent<string>) => {
        const newToken = event.data
        if (newToken) {
          token.value = newToken
        } else {
          token.value = ''
          refreshToken.value = ''
          user.value = null
        }
      }
    }

    // H-16 修复：跨标签页 user 同步 - 监听 storage 事件（user 仍在 localStorage）
    // 注意：storage 事件只在其他标签页触发，不会在修改数据的标签页本身触发
    const AUTH_STORAGE_KEYS = new Set(['user', 'token', 'token_expiry', 'refreshToken'])
    const storageHandler = (event: StorageEvent) => {
      // event.key === null 表示 localStorage 被清空（其他标签页调用 clear()）
      if (event.key === null) {
        syncAuth({ token: '', refreshToken: '', user: null })
        return
      }
      // 仅处理 auth 相关的 key 变更
      if (!AUTH_STORAGE_KEYS.has(event.key)) return
      // ISS-008: token 从 sessionStorage 读取（localStorage 中 token 已清理）
      // user 从 localStorage 读取
      if (event.key === 'user') {
        user.value = getStoredUser()
        // 如果 user 变为 null（其他标签页登出），也清除 token
        if (!user.value) {
          token.value = ''
          refreshToken.value = ''
        }
      }
    }
    window.addEventListener('storage', storageHandler)

    onScopeDispose(() => {
      window.removeEventListener(AUTH_SYNC_EVENT, handler)
      window.removeEventListener('storage', storageHandler)
      tokenChannel?.close()
    })
  }

  async function login(username: string, password: string) {
    const data = await authApi.login({ username, password })
    // 安全修复：refresh_token 由后端 HttpOnly Cookie 管理，前端不存储也不保留在内存
    persistAuth({ token: data.access_token, user: data.user })
    return data
  }

  async function register(payload: {
    username: string
    email: string
    password: string
    role: 'user' | 'counselor'
    nickname?: string
  }): Promise<void> {
    await authApi.register(payload)
  }

  function restore(): void {
    token.value = getStoredToken()
    refreshToken.value = getStoredRefreshToken()
    user.value = getStoredUser()
    // 安全修复：refresh_token 已由后端 HttpOnly Cookie 管理，前端不再存储
    // 因此仅校验 access_token 和 user 是否存在
    if (!token.value || !user.value) {
      clearStoredAuth()
      token.value = ''
      refreshToken.value = ''
      user.value = null
    }
  }

  async function refreshSession(): Promise<boolean> {
    const newToken = await refreshAccessToken()
    if (!newToken) {
      await logout()
      return false
    }
    token.value = newToken
    return true
  }

  async function logout(): Promise<void> {
    const currentRefreshToken = refreshToken.value
    try {
      await authApi.logout(currentRefreshToken ? { refresh_token: currentRefreshToken } : {})
    } finally {
      clearStoredAuth()
      token.value = ''
      refreshToken.value = ''
      user.value = null
    }
  }

  installAuthSyncListener()

  const username = computed(() => user.value?.username || '')

  return { token, refreshToken, user, isLoggedIn, role, username, login, register, restore, refreshSession, logout, persistAuth, broadcastAuthSync }
})
