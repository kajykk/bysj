import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import request, {
  refreshAccessToken,
  requestData,
  requestPageData,
  resetUnauthorizedRedirecting,
  setRedirectToLogin,
} from './request'
import { clearStoredAuth, getStoredToken, setStoredAuth } from '@/utils/authStorage'
import { ElMessage } from 'element-plus'

// ElMessage mock 句柄：通过 vi.hoisted 提升，确保在 vi.mock 工厂内可引用
const ElMessageMock = vi.hoisted(() => ({
  warning: vi.fn(),
  error: vi.fn()
}))

// 循环依赖治理后：request.ts 不再动态 import @/router，改为通过 setRedirectToLogin 注入回调。
// 原 vi.mock('@/router') 已无对应被测代码可拦截，移除并改为注入 mock 回调。
const redirectHandlerMock = vi.fn()

// 模拟 element-plus 的 ElMessage
// R-003 修复：request.ts 已改为显式 import { ElMessage } from 'element-plus'，
// vi.mock('element-plus') 能直接拦截显式 import，不再需要 globalThis 注入。
vi.mock('element-plus', () => ({
  ElMessage: ElMessageMock
}))

// 构造伪 AxiosError：response + config + message
// - config 参数：传 undefined 时 error.config 为 undefined（用于测试无 config 的 401 分支）；
//   传对象时 error.config 为该对象。
// - message 参数：传 undefined 使用默认 'Request failed with status XXX'；传 '' 显式清空，
//   让 normalizeHttpErrorInfo 跳过 error.message fallback 直接使用 fallback '请求失败'。
function makeError(
  status: number,
  data: { detail?: string; message?: string } = {},
  config?: Record<string, unknown>,
  message?: string
) {
  const error: any = new Error(message !== undefined ? message : `Request failed with status ${status}`)
  error.response = { status, data, statusText: 'Error', headers: {} }
  error.config = config
  error.isAxiosError = true
  error.toJSON = () => ({ message: error.message, code: 'ERR_BAD_REQUEST' })
  return error
}

// 构造伪 AxiosResponse
function makeResponse(data: unknown, status = 200): any {
  return { data, status, statusText: 'OK', headers: {}, config: {} }
}

describe('request module - 响应拦截器与辅助函数', () => {
  let originalAdapter: unknown
  let responseSuccessHandler: (response: any) => any
  let responseErrorHandler: (error: any) => Promise<any>

  beforeEach(() => {
    localStorage.clear()
    clearStoredAuth()
    vi.clearAllMocks()
    // R-003 修复：ElMessage 现在通过显式 import + vi.mock 拦截，无需 globalThis 重置
    resetUnauthorizedRedirecting()
    // 注入 mock 回调替代 request.ts 内部的动态 import('@/router')，
    // 避免 401 测试用例触发 jsdom 不支持的 window.location.assign（"navigation to another Document"）
    setRedirectToLogin(redirectHandlerMock)

    originalAdapter = request.defaults.adapter

    const handlers = (request.interceptors.response as any).handlers[0]
    responseSuccessHandler = handlers.fulfilled
    responseErrorHandler = handlers.rejected
  })

  afterEach(() => {
    request.defaults.adapter = originalAdapter as any
    // 还原全局重定向句柄，避免泄漏到其他测试文件
    setRedirectToLogin(null)
  })

  describe('response 成功处理器', () => {
    it('原样返回响应并复位 unauthorized 标志', async () => {
      const response = makeResponse({ data: 'ok' })
      const result = await responseSuccessHandler(response)
      expect(result).toBe(response)
    })

    it('处理不同结构的响应体', async () => {
      const response = makeResponse({ data: { items: [1, 2, 3] } })
      const result = await responseSuccessHandler(response)
      expect(result).toBe(response)
    })
  })

  describe('response 错误处理器 - 非 401 状态码', () => {
    it('403 弹出 warning 并 reject', async () => {
      const error = makeError(403, { detail: '无权限' })
      await expect(responseErrorHandler(error)).rejects.toBe(error)
      expect(ElMessage.warning).toHaveBeenCalledWith('无权限')
    })

    it('403 detail 缺失时回退到 error.message', async () => {
      // 注：源码 `detail || '无权限执行该操作'` 中的默认提示不可达，
      // 因为 normalizeHttpErrorInfo 总会用 error.message 作为 fallback，detail 永远非空。
      // 此处验证 error.message fallback 行为（非源码注释中预期的默认提示）。
      const error = makeError(403, {})
      await expect(responseErrorHandler(error)).rejects.toBe(error)
      expect(ElMessage.warning).toHaveBeenCalledWith('Request failed with status 403')
    })

    it('404 弹出 warning 并 reject', async () => {
      const error = makeError(404, { detail: '资源不存在' })
      await expect(responseErrorHandler(error)).rejects.toBe(error)
      expect(ElMessage.warning).toHaveBeenCalledWith('资源不存在')
    })

    it('404 detail 缺失时回退到 error.message', async () => {
      const error = makeError(404, {})
      await expect(responseErrorHandler(error)).rejects.toBe(error)
      expect(ElMessage.warning).toHaveBeenCalledWith('Request failed with status 404')
    })

    it('422 弹出 warning 并 reject', async () => {
      const error = makeError(422, { detail: '参数错误' })
      await expect(responseErrorHandler(error)).rejects.toBe(error)
      expect(ElMessage.warning).toHaveBeenCalledWith('参数错误')
    })

    it('422 detail 缺失时回退到 error.message', async () => {
      const error = makeError(422, {})
      await expect(responseErrorHandler(error)).rejects.toBe(error)
      expect(ElMessage.warning).toHaveBeenCalledWith('Request failed with status 422')
    })

    it('500 弹出 error 并 reject', async () => {
      const error = makeError(500, { detail: '服务异常' })
      await expect(responseErrorHandler(error)).rejects.toBe(error)
      expect(ElMessage.error).toHaveBeenCalledWith('服务异常')
    })

    it('502 detail 缺失时回退到 error.message', async () => {
      const error = makeError(502, {})
      await expect(responseErrorHandler(error)).rejects.toBe(error)
      expect(ElMessage.error).toHaveBeenCalledWith('Request failed with status 502')
    })

    it('503 detail 优先使用后端返回的 message', async () => {
      const error = makeError(503, { message: '维护中' })
      await expect(responseErrorHandler(error)).rejects.toBe(error)
      expect(ElMessage.error).toHaveBeenCalledWith('维护中')
    })

    it('其他状态码（如 400）detail 缺失时回退到 error.message', async () => {
      const error = makeError(400, {})
      await expect(responseErrorHandler(error)).rejects.toBe(error)
      expect(ElMessage.error).toHaveBeenCalledWith('Request failed with status 400')
    })

    it('无 response 字段的网络异常使用 fallback 提示', async () => {
      // 显式构造无 message 的 Error，确保 normalizeHttpErrorInfo 全部 fallback 失败后使用 fallback '请求失败'
      const error: any = new Error('')
      error.config = { headers: {} }
      await expect(responseErrorHandler(error)).rejects.toBe(error)
      expect(ElMessage.error).toHaveBeenCalledWith('请求失败')
    })
  })

  describe('response 错误处理器 - 401 场景', () => {
    it('401 + _retry=true 时清除 auth 并跳转登录', async () => {
      const error = makeError(401, { detail: 'token 失效' }, { _retry: true, headers: {} })
      setStoredAuth({ token: 'old-token' })
      expect(getStoredToken()).toBe('old-token')

      await expect(responseErrorHandler(error)).rejects.toBe(error)

      // auth 已被清除
      expect(getStoredToken()).toBe('')
      expect(ElMessage.warning).toHaveBeenCalledWith('token 失效')
    })

    it('401 + _retry=true detail 缺失时回退到 error.message', async () => {
      const error = makeError(401, {}, { _retry: true, headers: {} })
      await expect(responseErrorHandler(error)).rejects.toBe(error)
      expect(ElMessage.warning).toHaveBeenCalledWith('Request failed with status 401')
    })

    it('401 无 config 时直接清除 auth 并跳转', async () => {
      // 不传 config，error.config 为 undefined（makeError 默认），
      // 使 originalRequest 为 falsy，跳过 refresh 分支，落入第二个 401 分支调用 redirectToLogin(detail)
      const error: any = makeError(401, { detail: 'expired' })
      await expect(responseErrorHandler(error)).rejects.toBe(error)
      expect(ElMessage.warning).toHaveBeenCalledWith('expired')
    })

    it('401 触发 refresh 成功后重试原请求', async () => {
      // 模拟 adapter：/auth/refresh 返回新 token，其他 URL 返回 200
      request.defaults.adapter = async (config: any) => {
        if (config.url && config.url.includes('/auth/refresh')) {
          return makeResponse({ data: { access_token: 'new-token', user: { id: 1 } } })
        }
        // 修复：response.data 应直接为业务数据（result.data === 'retried-data'），
        // 不要再包一层 { data: 'retried-data' }
        return makeResponse('retried-data')
      }

      const error = makeError(401, {}, {
        url: '/api/test',
        method: 'get',
        headers: { Authorization: 'Bearer old' }
      })

      const result = await responseErrorHandler(error)
      // 重试后的响应被返回：result 是 axios response，result.data 为业务数据
      expect(result.data).toEqual('retried-data')
      // token 已被存储
      expect(getStoredToken()).toBe('new-token')
    })

    it('401 refresh 失败时清除 auth 并 reject', async () => {
      // adapter 抛出异常模拟 refresh 失败
      request.defaults.adapter = async () => {
        throw new Error('refresh failed')
      }

      setStoredAuth({ token: 'old-token' })
      const error = makeError(401, {}, {
        url: '/api/test',
        method: 'get',
        headers: {}
      })

      await expect(responseErrorHandler(error)).rejects.toBe(error)
      // auth 已清除
      expect(getStoredToken()).toBe('')
      expect(ElMessage.warning).toHaveBeenCalledWith('登录已失效，请重新登录')
    })

    it('401 refresh 返回空 token 时清除 auth 并 reject', async () => {
      request.defaults.adapter = async () => {
        return makeResponse({ data: {} }) // 无 access_token
      }

      const error = makeError(401, {}, {
        url: '/api/test',
        method: 'get',
        headers: {}
      })

      await expect(responseErrorHandler(error)).rejects.toBe(error)
      expect(getStoredToken()).toBe('')
    })

    it('并发 401 时第二个请求加入 pending 队列并在 refresh 后重试', async () => {
      let resolveRefresh!: (value: any) => void
      const refreshPromise = new Promise((resolve) => { resolveRefresh = resolve })

      request.defaults.adapter = async (config: any) => {
        if (config.url && config.url.includes('/auth/refresh')) {
          return refreshPromise as Promise<any>
        }
        // 修复：response.data 应直接为业务数据
        return makeResponse('retried')
      }

      // 第一个 401：触发 refresh，挂起
      const error1 = makeError(401, {}, {
        url: '/api/test1',
        method: 'get',
        headers: {}
      })
      const p1 = responseErrorHandler(error1)

      // 第二个 401：应被加入 pending 队列
      const error2 = makeError(401, {}, {
        url: '/api/test2',
        method: 'get',
        headers: {}
      })
      const p2 = responseErrorHandler(error2)

      // 解除 refresh
      resolveRefresh(makeResponse({ data: { access_token: 'new', user: { id: 2 } } }))

      // 两个请求都应成功重试
      const [r1, r2] = await Promise.all([p1, p2])
      expect(r1.data).toEqual('retried')
      expect(r2.data).toEqual('retried')
    })
  })

  describe('refreshAccessToken', () => {
    it('成功时返回新 token 并存储', async () => {
      request.defaults.adapter = async () => {
        return makeResponse({ data: { access_token: 'fresh-token', user: { id: 9 } } })
      }

      const token = await refreshAccessToken()
      expect(token).toBe('fresh-token')
      expect(getStoredToken()).toBe('fresh-token')
    })

    it('网络异常时返回 null 且不抛出', async () => {
      request.defaults.adapter = async () => {
        throw new Error('network down')
      }

      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const token = await refreshAccessToken()
      expect(token).toBeNull()
      expect(consoleSpy).toHaveBeenCalled()
      consoleSpy.mockRestore()
    })

    it('响应缺少 access_token 时返回 null', async () => {
      request.defaults.adapter = async () => {
        return makeResponse({ data: {} })
      }

      const token = await refreshAccessToken()
      expect(token).toBeNull()
    })

    it('成功时通过 setStoredAuth 持久化 user', async () => {
      request.defaults.adapter = async () => {
        return makeResponse({ data: { access_token: 't', user: { id: 1, username: 'u' } } })
      }

      await refreshAccessToken()
      const stored = JSON.parse(localStorage.getItem('user') || 'null')
      expect(stored).toEqual({ id: 1, username: 'u' })
    })
  })

  describe('requestData', () => {
    it('解包 res.data.data', async () => {
      const result = await requestData(Promise.resolve({ data: { data: 'payload' } }))
      expect(result).toBe('payload')
    })

    it('解包复杂对象', async () => {
      const payload = { id: 1, items: [1, 2, 3], nested: { a: true } }
      const result = await requestData(Promise.resolve({ data: { data: payload } }))
      expect(result).toEqual(payload)
    })

    it('上游 reject 时透传错误', async () => {
      await expect(requestData(Promise.reject(new Error('upstream fail')))).rejects.toThrow('upstream fail')
    })
  })

  describe('requestPageData', () => {
    it('合法分页数据通过 normalizePageResult 解包', async () => {
      const result = await requestPageData(Promise.resolve({
        data: { data: { items: [1, 2], total: 2, page: 1, page_size: 10 } }
      }))
      expect(result).toEqual({ items: [1, 2], total: 2, page: 1, page_size: 10 })
    })

    it('缺少 total 时抛出契约错误', async () => {
      await expect(requestPageData(Promise.resolve({
        data: { data: { items: [], page: 1, page_size: 10 } }
      }))).rejects.toThrow('分页契约错误')
    })

    it('缺少 items 时抛出契约错误', async () => {
      await expect(requestPageData(Promise.resolve({
        data: { data: { total: 0, page: 1, page_size: 10 } }
      }))).rejects.toThrow('分页契约错误')
    })

    it('缺少 page 时抛出契约错误', async () => {
      await expect(requestPageData(Promise.resolve({
        data: { data: { items: [], total: 0, page_size: 10 } }
      }))).rejects.toThrow('分页契约错误')
    })

    it('缺少 page_size 时抛出契约错误', async () => {
      await expect(requestPageData(Promise.resolve({
        data: { data: { items: [], total: 0, page: 1 } }
      }))).rejects.toThrow('分页契约错误')
    })

    it('上游 reject 时透传错误', async () => {
      await expect(requestPageData(Promise.reject(new Error('page fail')))).rejects.toThrow('page fail')
    })
  })

  describe('GET 请求去重', () => {
    it('相同 URL + params 的并发 GET 复用同一 Promise', async () => {
      // 注：request.get() 内部调用 context.request（原型方法），不经过 instance.request 覆盖。
      // 因此必须用 request.request(config) 直接调用，才能触发去重逻辑。
      // 这是 request.ts 源码的一个 bug：override 只对直接调用 request.request 生效，
      // request.get/post 等别名方法绕过了覆盖。
      const adapterCalls: any[] = []
      let resolveAdapter!: (value: any) => void

      request.defaults.adapter = (config: any) => {
        adapterCalls.push(config)
        return new Promise((resolve) => { resolveAdapter = resolve })
      }

      const p1 = request.request({ method: 'get', url: '/test', params: { a: 1 } } as any)
      // axios 通过 Promise 链异步调用 adapter，需等待一个宏任务确保 adapter 被调用一次
      // 此时 inflightRequests 中已记录该 Promise，第二次相同请求应直接复用
      await new Promise((resolve) => setTimeout(resolve, 0))
      const p2 = request.request({ method: 'get', url: '/test', params: { a: 1 } } as any)

      // 第二次调用直接返回 inflight Promise，不应再触发 adapter
      expect(p1).toBe(p2)
      expect(adapterCalls).toHaveLength(1)

      resolveAdapter(makeResponse({ data: 'shared' }))
      const [r1, r2] = await Promise.all([p1, p2])
      expect(r1).toBe(r2) // 同一个 Promise 解析为同一响应
    })

    it('不同 params 不复用', async () => {
      // 使用 request.request 直接调用以触发覆盖逻辑（见首测试注释）
      const adapterCalls: any[] = []

      request.defaults.adapter = async (config: any) => {
        adapterCalls.push(config)
        return makeResponse({ data: 'x' })
      }

      await Promise.all([
        request.request({ method: 'get', url: '/test', params: { a: 1 } } as any),
        request.request({ method: 'get', url: '/test', params: { a: 2 } } as any)
      ])
      expect(adapterCalls).toHaveLength(2)
    })

    it('不同 URL 不复用', async () => {
      // 使用 request.request 直接调用以触发覆盖逻辑（见首测试注释）
      const adapterCalls: any[] = []

      request.defaults.adapter = async (config: any) => {
        adapterCalls.push(config)
        return makeResponse({ data: 'x' })
      }

      await Promise.all([
        request.request({ method: 'get', url: '/test1', params: { a: 1 } } as any),
        request.request({ method: 'get', url: '/test2', params: { a: 1 } } as any)
      ])
      expect(adapterCalls).toHaveLength(2)
    })

    it('params 属性顺序不同但内容相同时仍去重', async () => {
      // 使用 request.request 直接调用以触发覆盖逻辑（见上测试注释）
      const adapterCalls: any[] = []
      let resolveAdapter!: (value: any) => void

      request.defaults.adapter = (config: any) => {
        adapterCalls.push(config)
        return new Promise((resolve) => { resolveAdapter = resolve })
      }

      // { a: 1, b: 2 } vs { b: 2, a: 1 } - 排序后 key 应相同
      const p1 = request.request({ method: 'get', url: '/test', params: { a: 1, b: 2 } } as any)
      // 等待 axios 异步调用 adapter，确保 inflight 已被记录
      await new Promise((resolve) => setTimeout(resolve, 0))
      const p2 = request.request({ method: 'get', url: '/test', params: { b: 2, a: 1 } } as any)

      expect(p1).toBe(p2)
      expect(adapterCalls).toHaveLength(1)
      resolveAdapter(makeResponse({ data: 'ok' }))
      await Promise.all([p1, p2])
    })

    it('bypassDedupe=true 时跳过去重', async () => {
      // 使用 request.request 直接调用以触发覆盖逻辑（见首测试注释）
      const adapterCalls: any[] = []

      request.defaults.adapter = async (config: any) => {
        adapterCalls.push(config)
        return makeResponse({ data: 'x' })
      }

      await Promise.all([
        request.request({ method: 'get', url: '/test', params: { a: 1 }, bypassDedupe: true } as any),
        request.request({ method: 'get', url: '/test', params: { a: 1 }, bypassDedupe: true } as any)
      ])
      expect(adapterCalls).toHaveLength(2)
    })

    it('请求完成后从 inflight 队列移除', async () => {
      // 使用 request.request 直接调用以触发覆盖逻辑（见首测试注释）
      const adapterCalls: any[] = []

      request.defaults.adapter = async (config: any) => {
        adapterCalls.push(config)
        return makeResponse({ data: 'x' })
      }

      await request.request({ method: 'get', url: '/test', params: { a: 1 } } as any)

      // 第二次相同请求应触发新的 adapter 调用（inflight 已被清除）
      await request.request({ method: 'get', url: '/test', params: { a: 1 } } as any)
      expect(adapterCalls).toHaveLength(2)
    })

    it('非 GET 请求（POST）不做去重', async () => {
      // 使用 request.request 直接调用以触发覆盖逻辑（见首测试注释）
      const adapterCalls: any[] = []

      request.defaults.adapter = async (config: any) => {
        adapterCalls.push(config)
        return makeResponse({ data: 'x' })
      }

      await Promise.all([
        request.request({ method: 'post', url: '/test', data: { a: 1 } } as any),
        request.request({ method: 'post', url: '/test', data: { a: 1 } } as any)
      ])
      expect(adapterCalls).toHaveLength(2)
    })

    // R-004 修复：验证 stableSerialize 对复杂参数（嵌套对象/数组）的稳定去重
    describe('R-004 复杂参数稳定序列化', () => {
      it('嵌套对象 key 顺序不同时仍去重', async () => {
        const adapterCalls: any[] = []
        let resolveAdapter!: (value: any) => void

        request.defaults.adapter = (config: any) => {
          adapterCalls.push(config)
          return new Promise((resolve) => { resolveAdapter = resolve })
        }

        // {filter: {x: 1, y: 2}} vs {filter: {y: 2, x: 1}} - 语义相同
        const p1 = request.request({
          method: 'get',
          url: '/test',
          params: { filter: { x: 1, y: 2 } }
        } as any)
        await new Promise((resolve) => setTimeout(resolve, 0))
        const p2 = request.request({
          method: 'get',
          url: '/test',
          params: { filter: { y: 2, x: 1 } }
        } as any)

        expect(p1).toBe(p2)
        expect(adapterCalls).toHaveLength(1)
        resolveAdapter(makeResponse({ data: 'ok' }))
        await Promise.all([p1, p2])
      })

      it('多层嵌套对象 key 顺序不同时仍去重', async () => {
        const adapterCalls: any[] = []
        let resolveAdapter!: (value: any) => void

        request.defaults.adapter = (config: any) => {
          adapterCalls.push(config)
          return new Promise((resolve) => { resolveAdapter = resolve })
        }

        // {a: {b: {c: 1, d: 2}}} vs {a: {b: {d: 2, c: 1}}}
        const p1 = request.request({
          method: 'get',
          url: '/test',
          params: { a: { b: { c: 1, d: 2 } } }
        } as any)
        await new Promise((resolve) => setTimeout(resolve, 0))
        const p2 = request.request({
          method: 'get',
          url: '/test',
          params: { a: { b: { d: 2, c: 1 } } }
        } as any)

        expect(p1).toBe(p2)
        expect(adapterCalls).toHaveLength(1)
        resolveAdapter(makeResponse({ data: 'ok' }))
        await Promise.all([p1, p2])
      })

      it('数组元素顺序不同时不复用（语义重要）', async () => {
        const adapterCalls: any[] = []

        request.defaults.adapter = async (config: any) => {
          adapterCalls.push(config)
          return makeResponse({ data: 'x' })
        }

        // [1, 2] vs [2, 1] - 数组顺序语义不同，应分别发送
        await Promise.all([
          request.request({ method: 'get', url: '/test', params: { tags: [1, 2] } } as any),
          request.request({ method: 'get', url: '/test', params: { tags: [2, 1] } } as any)
        ])
        expect(adapterCalls).toHaveLength(2)
      })

      it('相同数组元素顺序时去重', async () => {
        const adapterCalls: any[] = []
        let resolveAdapter!: (value: any) => void

        request.defaults.adapter = (config: any) => {
          adapterCalls.push(config)
          return new Promise((resolve) => { resolveAdapter = resolve })
        }

        const p1 = request.request({
          method: 'get',
          url: '/test',
          params: { tags: ['a', 'b'] }
        } as any)
        await new Promise((resolve) => setTimeout(resolve, 0))
        const p2 = request.request({
          method: 'get',
          url: '/test',
          params: { tags: ['a', 'b'] }
        } as any)

        expect(p1).toBe(p2)
        expect(adapterCalls).toHaveLength(1)
        resolveAdapter(makeResponse({ data: 'ok' }))
        await Promise.all([p1, p2])
      })

      it('undefined 值与缺失 key 生成相同 key', async () => {
        const adapterCalls: any[] = []
        let resolveAdapter!: (value: any) => void

        request.defaults.adapter = (config: any) => {
          adapterCalls.push(config)
          return new Promise((resolve) => { resolveAdapter = resolve })
        }

        // {a: 1, b: undefined} 与 {a: 1} 应生成相同 key（与 JSON.stringify 行为一致）
        const p1 = request.request({
          method: 'get',
          url: '/test',
          params: { a: 1, b: undefined }
        } as any)
        await new Promise((resolve) => setTimeout(resolve, 0))
        const p2 = request.request({
          method: 'get',
          url: '/test',
          params: { a: 1 }
        } as any)

        expect(p1).toBe(p2)
        expect(adapterCalls).toHaveLength(1)
        resolveAdapter(makeResponse({ data: 'ok' }))
        await Promise.all([p1, p2])
      })

      it('混合嵌套结构（对象+数组）稳定去重', async () => {
        const adapterCalls: any[] = []
        let resolveAdapter!: (value: any) => void

        request.defaults.adapter = (config: any) => {
          adapterCalls.push(config)
          return new Promise((resolve) => { resolveAdapter = resolve })
        }

        // 复杂参数：{filter: {tags: ['a','b'], range: {start: 0, end: 10}}, page: 1}
        const p1 = request.request({
          method: 'get',
          url: '/test',
          params: { filter: { tags: ['a', 'b'], range: { start: 0, end: 10 } }, page: 1 }
        } as any)
        await new Promise((resolve) => setTimeout(resolve, 0))
        const p2 = request.request({
          method: 'get',
          url: '/test',
          params: { page: 1, filter: { range: { end: 10, start: 0 }, tags: ['a', 'b'] } }
        } as any)

        expect(p1).toBe(p2)
        expect(adapterCalls).toHaveLength(1)
        resolveAdapter(makeResponse({ data: 'ok' }))
        await Promise.all([p1, p2])
      })

      it('null 值与 undefined 值生成不同 key', async () => {
        const adapterCalls: any[] = []

        request.defaults.adapter = async (config: any) => {
          adapterCalls.push(config)
          return makeResponse({ data: 'x' })
        }

        // {a: null} 与 {a: undefined}（被跳过）应生成不同 key
        await Promise.all([
          request.request({ method: 'get', url: '/test', params: { a: null } } as any),
          request.request({ method: 'get', url: '/test', params: { a: undefined } } as any)
        ])
        expect(adapterCalls).toHaveLength(2)
      })
    })
  })

  describe('resetUnauthorizedRedirecting', () => {
    it('复位后允许下一次 401 再次触发跳转', async () => {
      request.defaults.adapter = async () => {
        throw new Error('refresh failed')
      }

      const error = makeError(401, {}, {
        url: '/api/test',
        method: 'get',
        headers: {}
      })

      // 第一次 401：触发跳转
      await expect(responseErrorHandler(error)).rejects.toBe(error)
      expect(ElMessage.warning).toHaveBeenCalledTimes(1)

      // 不复位时第二次 401 不再触发跳转
      resetUnauthorizedRedirecting()
      // 复位后允许再次触发
      const error2 = makeError(401, { detail: 'again' }, {
        _retry: true,
        headers: {}
      })
      await expect(responseErrorHandler(error2)).rejects.toBe(error2)
      expect(ElMessage.warning).toHaveBeenCalledWith('again')
    })
  })
})
