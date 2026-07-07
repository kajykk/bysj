import { beforeEach, describe, expect, it, vi } from 'vitest'

// 模拟 request 模块，专注验证 auth API 的 URL/方法/参数构造
vi.mock('./request', () => ({
  default: {
    get: vi.fn((url: string, config?: unknown) => Promise.resolve({ url, config })),
    post: vi.fn((url: string, data?: unknown, config?: unknown) => Promise.resolve({ url, data, config })),
    put: vi.fn((url: string, data?: unknown, config?: unknown) => Promise.resolve({ url, data, config })),
    delete: vi.fn((url: string, config?: unknown) => Promise.resolve({ url, config }))
  },
  requestData: vi.fn(async (promise: Promise<{ data: unknown }>) => {
    const response = await promise
    return response.data
  }),
  requestPageData: vi.fn(async (promise: Promise<{ data: unknown }>) => {
    const response = await promise
    return response.data
  })
}))

import request, { requestData } from './request'
import { authApi } from './auth'

describe('api/auth', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('login', () => {
    it('通过 POST /auth/login 登录并解包响应', async () => {
      (request.post as any).mockResolvedValueOnce({ data: { access_token: 'tok', user: { id: 1 } } })
      ;(requestData as any).mockImplementationOnce(async (p: Promise<{ data: unknown }>) => (await p).data)

      const res = await authApi.login({ username: 'alice', password: 'secret' })

      expect(request.post).toHaveBeenCalledWith('/auth/login', { username: 'alice', password: 'secret' })
      expect(res).toEqual({ access_token: 'tok', user: { id: 1 } })
    })

    it('网络错误时抛出异常', async () => {
      (request.post as any).mockRejectedValueOnce(new Error('Network 500'))
      ;(requestData as any).mockImplementationOnce(async (p: Promise<{ data: unknown }>) => (await p).data)

      await expect(authApi.login({ username: 'x', password: 'y' })).rejects.toThrow('Network 500')
    })

    it('边界：空字符串凭据仍按原样传递', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await authApi.login({ username: '', password: '' })
      expect(request.post).toHaveBeenCalledWith('/auth/login', { username: '', password: '' })
    })
  })

  describe('register', () => {
    it('通过 POST /auth/register 注册用户', async () => {
      const expected = { id: 9, username: 'newbie', role: 'user' }
      ;(requestData as any).mockResolvedValueOnce(expected)

      const res = await authApi.register({
        username: 'newbie',
        email: 'n@example.com',
        password: 'p',
        role: 'user'
      })

      expect(request.post).toHaveBeenCalledWith('/auth/register', {
        username: 'newbie',
        email: 'n@example.com',
        password: 'p',
        role: 'user'
      })
      expect(res).toEqual(expected)
    })

    it('携带可选 nickname 字段', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await authApi.register({
        username: 'u',
        email: 'e',
        password: 'p',
        role: 'counselor',
        nickname: 'Dr. Bob'
      })
      expect(request.post).toHaveBeenCalledWith('/auth/register', {
        username: 'u',
        email: 'e',
        password: 'p',
        role: 'counselor',
        nickname: 'Dr. Bob'
      })
    })

    it('注册失败时透传错误', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('HTTP 400'))
      await expect(
        authApi.register({ username: 'u', email: 'e', password: 'p', role: 'user' })
      ).rejects.toThrow('HTTP 400')
    })
  })

  describe('logout', () => {
    it('通过 POST /auth/logout 退出并启用 withCredentials', async () => {
      (requestData as any).mockResolvedValueOnce({ message: 'ok' })
      const res = await authApi.logout({ refresh_token: 'r' })

      expect(request.post).toHaveBeenCalledWith('/auth/logout', { refresh_token: 'r' }, { withCredentials: true })
      expect(res).toEqual({ message: 'ok' })
    })

    it('默认空载荷不传 refresh_token', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await authApi.logout()
      expect(request.post).toHaveBeenCalledWith('/auth/logout', {}, { withCredentials: true })
    })

    it('logout 接口报错时抛出', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('401'))
      await expect(authApi.logout()).rejects.toThrow('401')
    })
  })

  describe('changePassword', () => {
    it('通过 PUT /auth/change-password 修改密码', async () => {
      (requestData as any).mockResolvedValueOnce({ message: 'ok' })
      const res = await authApi.changePassword({ old_password: 'o', new_password: 'n' })

      expect(request.put).toHaveBeenCalledWith('/auth/change-password', { old_password: 'o', new_password: 'n' })
      expect(res).toEqual({ message: 'ok' })
    })

    it('修改密码失败时透传错误', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('400'))
      await expect(
        authApi.changePassword({ old_password: 'o', new_password: 'n' })
      ).rejects.toThrow('400')
    })
  })

  describe('requestPasswordReset', () => {
    it('通过 POST /auth/request-reset 发起重置', async () => {
      (requestData as any).mockResolvedValueOnce({ message: 'sent' })
      const res = await authApi.requestPasswordReset('a@b.com')

      expect(request.post).toHaveBeenCalledWith('/auth/request-reset', { email: 'a@b.com' })
      expect(res).toEqual({ message: 'sent' })
    })

    it('邮箱不存在场景抛错', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('404'))
      await expect(authApi.requestPasswordReset('none@x.com')).rejects.toThrow('404')
    })

    it('边界：空字符串邮箱仍按原样传递', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await authApi.requestPasswordReset('')
      expect(request.post).toHaveBeenCalledWith('/auth/request-reset', { email: '' })
    })
  })

  describe('resetPassword', () => {
    it('通过 POST /auth/reset-password 重置密码', async () => {
      (requestData as any).mockResolvedValueOnce({ message: 'ok' })
      const res = await authApi.resetPassword({
        email: 'a@b.com',
        new_password: 'new',
        reset_token: 'tok'
      })

      expect(request.post).toHaveBeenCalledWith('/auth/reset-password', {
        email: 'a@b.com',
        new_password: 'new',
        reset_token: 'tok'
      })
      expect(res).toEqual({ message: 'ok' })
    })

    it('reset_token 失效时透传错误', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('410'))
      await expect(
        authApi.resetPassword({ email: 'a@b.com', new_password: 'n', reset_token: 'bad' })
      ).rejects.toThrow('410')
    })
  })

  describe('updateProfile', () => {
    it('通过 PUT /auth/profile 更新昵称与邮箱', async () => {
      const expected = { id: 1, username: 'u', role: 'user', nickname: 'NN', email: 'n@e.com' }
      ;(requestData as any).mockResolvedValueOnce(expected)
      const res = await authApi.updateProfile({ nickname: 'NN', email: 'n@e.com' })

      expect(request.put).toHaveBeenCalledWith('/auth/profile', { nickname: 'NN', email: 'n@e.com' })
      expect(res).toEqual(expected)
    })

    it('仅更新 nickname 时 email 字段为 undefined', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await authApi.updateProfile({ nickname: 'X' })
      expect(request.put).toHaveBeenCalledWith('/auth/profile', { nickname: 'X', email: undefined })
    })

    it('仅更新 email 时 nickname 字段为 undefined', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await authApi.updateProfile({ email: 'x@y.com' })
      expect(request.put).toHaveBeenCalledWith('/auth/profile', { nickname: undefined, email: 'x@y.com' })
    })

    it('更新失败时抛出错误', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('500'))
      await expect(authApi.updateProfile({ nickname: 'X' })).rejects.toThrow('500')
    })
  })
})
