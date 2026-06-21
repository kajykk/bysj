import request, { requestData } from './request'

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

export interface UserInfo {
  id: number
  username: string
  role: 'user' | 'counselor' | 'admin'
  nickname?: string
  email?: string
}

export interface AuthResponse {
  access_token: string
  refresh_token: string
  user: UserInfo
}

type LogoutPayload = { refresh_token?: string }

export const authApi = {
  login: (payload: LoginPayload) => requestData<AuthResponse>(request.post('/auth/login', payload)),
  register: (payload: RegisterPayload) => requestData<{ id: number; username: string; role: string }>(request.post('/auth/register', payload)),
  refresh: (refreshToken: string) =>
    requestData<{ access_token: string; refresh_token: string; token_type: string }>(
      request.post('/auth/refresh', { refresh_token: refreshToken })
    ),
  logout: (payload: LogoutPayload = {}) =>
    requestData<{ message: string; revoked_count?: number }>(request.post('/auth/logout', payload)),
  changePassword: (payload: { old_password: string; new_password: string }) =>
    requestData<{ message: string }>(request.put('/auth/change-password', payload)),
  requestPasswordReset: (email: string) =>
    requestData<{ message: string }>(request.post('/auth/request-reset', { email })),
  resetPassword: (payload: { email: string; new_password: string; reset_token: string }) =>
    requestData<{ message: string }>(request.post('/auth/reset-password', payload)),
  updateProfile: (payload: { nickname?: string; email?: string }) =>
    requestData<UserInfo>(request.put('/auth/profile', payload)),
}
