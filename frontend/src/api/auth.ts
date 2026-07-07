import request, { requestData } from './request'
// 类型下沉：UserInfo 提取至 @/types/auth 以打破 utils/authStorage 与 api/auth 的类型-only 循环依赖。
// 此处再导出以保持 `import { type UserInfo } from '@/api/auth'` 的公共 API 向后兼容。
export type { UserInfo } from '@/types/auth'
import type { UserInfo } from '@/types/auth'

export interface LoginPayload {
  username: string
  password: string
}

export interface RegisterPayload {
  username: string
  email: string
  password: string
  role: 'user' | 'counselor'
  nickname?: string
}

export interface AuthResponse {
  access_token: string
  refresh_token?: string
  user: UserInfo
}

type LogoutPayload = { refresh_token?: string }

export const authApi = {
  login: (payload: LoginPayload) => requestData<AuthResponse>(request.post('/auth/login', payload)),
  register: (payload: RegisterPayload) => requestData<{ id: number; username: string; role: string }>(request.post('/auth/register', payload)),
  // 注意：token 刷新逻辑在 request.ts 的 refreshAccessToken 中实现，依赖 HttpOnly Cookie
  logout: (payload: LogoutPayload = {}) =>
    requestData<{ message: string; revoked_count?: number }>(
      request.post('/auth/logout', payload, { withCredentials: true })
    ),
  changePassword: (payload: { old_password: string; new_password: string }) =>
    requestData<{ message: string }>(request.put('/auth/change-password', payload)),
  requestPasswordReset: (email: string) =>
    requestData<{ message: string }>(request.post('/auth/request-reset', { email })),
  resetPassword: (payload: { email: string; new_password: string; reset_token: string }) =>
    requestData<{ message: string }>(request.post('/auth/reset-password', payload)),
  updateProfile: (payload: { nickname?: string; email?: string }) =>
    requestData<UserInfo>(request.put('/auth/profile', payload)),
}
