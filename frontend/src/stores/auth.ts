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
  }

  function installAuthSyncListener() {
    if (typeof window === 'undefined') return
    const handler = (event: Event) => {
      const customEvent = event as CustomEvent<AuthSyncDetail>
      if (customEvent.detail) syncAuth(customEvent.detail)
    }
    window.addEventListener(AUTH_SYNC_EVENT, handler)
    onScopeDispose(() => window.removeEventListener(AUTH_SYNC_EVENT, handler))
  }

  async function login(username: string, password: string) {
    const data = await authApi.login({ username, password })
    persistAuth({ token: data.access_token, refreshToken: data.refresh_token, user: data.user })
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
    if (!token.value || !refreshToken.value || !user.value) {
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
