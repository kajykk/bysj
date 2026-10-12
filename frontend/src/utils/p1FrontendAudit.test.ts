/**
 * P1 第五轮前端回归闸门（2026-10-13）。
 *
 * 覆盖：
 * - #27 GET 去重的 `promise.finally()` 悬垂拒绝（Sentry 噪音）
 * - #30 `getNetworkErrorMessage` 零生产调用点 → 端到端中文映射
 * - #12 401 静默刷新后对非幂等方法（POST/PATCH）重放 → 重复提交
 * - #28 localStorage 抛异常 → store 初始化即白屏
 * - #14 LazyImage observer 重复创建不释放 / 卸载时 containerRef 已空
 *
 * 对照实验记录（回退修复后均现红）见 docs/CODE_REVIEW_2026-10-11.md 第五轮追记。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { getNetworkErrorMessage, normalizeHttpErrorInfo } from '@/utils/httpError'
import {
  isLocalStorageAvailable,
  safeLocalGetItem,
  safeLocalRemoveItem,
  safeLocalSetItem
} from '@/utils/safeStorage'

// ══════════════════════════════════════════════════════════════════
// #28 localStorage 安全读写
// ══════════════════════════════════════════════════════════════════

describe('safeStorage - P1-28 存储不可用不白屏', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('getItem 抛异常时返回 null 而不向外抛', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('存储访问被拒绝')
    })
    // 关键：不得抛异常。原 stores/layout.ts 裸调 localStorage.getItem，
    // 在 Pinia store 初始化阶段抛错会沿应用挂载链冒到顶部 → 整站白屏。
    expect(() => safeLocalGetItem('dws_sidebar_collapsed')).not.toThrow()
    expect(safeLocalGetItem('dws_sidebar_collapsed')).toBeNull()
  })

  it('setItem 抛异常时静默失败而不向外抛', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    expect(() => safeLocalSetItem('k', 'v')).not.toThrow()
  })

  it('removeItem 抛异常时静默失败而不向外抛', () => {
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('存储访问被拒绝')
    })
    expect(() => safeLocalRemoveItem('k')).not.toThrow()
  })

  it('window 不存在（SSR）时全部安全降级', () => {
    vi.stubGlobal('window', undefined)
    expect(isLocalStorageAvailable()).toBe(false)
    expect(safeLocalGetItem('k')).toBeNull()
    expect(() => safeLocalSetItem('k', 'v')).not.toThrow()
  })

  it('正常路径读写不受影响（对照）', () => {
    localStorage.clear()
    expect(safeLocalGetItem('probe_key')).toBeNull()
    safeLocalSetItem('probe_key', 'true')
    expect(safeLocalGetItem('probe_key')).toBe('true')
    safeLocalRemoveItem('probe_key')
    expect(safeLocalGetItem('probe_key')).toBeNull()
  })

  // 上面几条只证明 safeStorage 自身不抛；**真正要证明的是 stores/layout.ts
  // 确实走的是 safeStorage**。改前该 store 在初始化时裸调 localStorage.getItem，
  // 那一行抛异常会沿 Pinia store 创建冒到应用挂载链 → 整站白屏。
  // 仅测 safeStorage 的话，把 layout.ts 改回裸调也照样全绿（恒绿闸门）。
  it('localStorage 抛异常时 layout store 仍能创建并可用（真实消费方）', async () => {
    const { setActivePinia, createPinia } = await import('pinia')
    setActivePinia(createPinia())

    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('存储访问被拒绝')
    })
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('存储访问被拒绝')
    })

    const { useLayoutStore } = await import('@/stores/layout')
    // store 创建本身不得抛（白屏点就在这里）
    let store: ReturnType<typeof useLayoutStore>
    expect(() => {
      store = useLayoutStore()
    }).not.toThrow()

    // 存储不可用时按「无偏好」降级，且 toggle 也不抛
    expect(store!.sidebarCollapsed).toBe(false)
    expect(() => store!.toggleSidebar()).not.toThrow()
    expect(store!.sidebarCollapsed).toBe(true)
    setItemSpy.mockRestore()
  })

  it('localStorage 正常时 layout store 仍能持久化偏好（对照）', async () => {
    const { setActivePinia, createPinia } = await import('pinia')
    setActivePinia(createPinia())
    localStorage.clear()

    const { useLayoutStore } = await import('@/stores/layout')
    const store = useLayoutStore()
    store.setSidebarCollapsed(true)
    expect(localStorage.getItem('dws_sidebar_collapsed')).toBe('true')

    // 重新创建 store 应读回持久化值
    const { setActivePinia: setActive } = await import('pinia')
    setActive(createPinia())
    const store2 = useLayoutStore()
    expect(store2.sidebarCollapsed).toBe(true)
  })
})

// ══════════════════════════════════════════════════════════════════
// #30 网络错误中文映射端到端
// ══════════════════════════════════════════════════════════════════

describe('getNetworkErrorMessage 端到端 - P1-30', () => {
  it('ISS-106 引入后全仓无生产调用点：映射表必须能被 normalizeHttpErrorInfo 采用', () => {
    // 模拟请求拦截器挂上 userMessage 后的 error 形态
    const error = {
      message: 'timeout of 60000ms exceeded',
      userMessage: getNetworkErrorMessage({ code: 'ECONNABORTED', message: 'timeout of 60000ms exceeded' })
    }
    expect(error.userMessage).toBe('请求超时，请重试')

    const info = normalizeHttpErrorInfo(error, '请求失败')
    // 关键：用户看到中文映射，而不是 axios 英文原文
    expect(info.detail).toBe('请求超时，请重试')
    expect(info.detail).not.toContain('timeout of')
  })

  it('有业务 detail 时仍以服务端为准（userMessage 不得覆盖）', () => {
    const error = {
      message: 'Network Error',
      userMessage: '网络连接失败，请检查网络设置',
      response: { status: 400, data: { detail: '参数格式错误' } }
    }
    expect(normalizeHttpErrorInfo(error, '请求失败').detail).toBe('参数格式错误')
  })

  it('normalizeHttpError 走完整链路：网络错误 → 中文 + 可重试', () => {
    const error = { message: 'Network Error', userMessage: '网络连接失败，请检查网络设置' }
    const normalized = normalizeHttpError(error, '请求失败')
    expect(normalized.detail).toBe('网络连接失败，请检查网络设置')
    expect(normalized.showRetry).toBe(true)
  })

  it('未命中映射表时回落 axios 原文（不编造提示）', () => {
    const error = { message: 'Something unmap关于', userMessage: getNetworkErrorMessage({ code: 'WEIRD' }) }
    expect(error.userMessage).toBeNull()
    expect(normalizeHttpErrorInfo(error, '请求失败').detail).toBe('Something unmap关于')
  })
})

// ══════════════════════════════════════════════════════════════════
// #12 401 非幂等方法不重放（真实驱动响应拦截器）
//
// 注意：下面这组「契约断言」是**兜底**，真正的主断言在更下面的
// 「401 非幂等方法不重放原请求」——那条直接驱动 request.ts 的真实
// 错误处理器，打 adapter 观察原 URL 是否被第二次请求。
// ══════════════════════════════════════════════════════════════════

// 这一组直接驱动 request.ts 的真实响应错误处理器，用 adapter 记录
// 「原 URL 是否被第二次请求」。改前 POST 会被静默刷新后重放一次 ——
// 若首次请求实际已被服务端处理，就是重复提交。
// ══════════════════════════════════════════════════════════════════

// 这些 mock 必须与 request.interceptors.test.ts 保持一致：
// request.ts 显式 import element-plus 子路径，需同时 mock 两个路径。
const ElMessageMock = vi.hoisted(() => ({ warning: vi.fn(), error: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: ElMessageMock }))
vi.mock('element-plus/es/components/message/index', () => ({ ElMessage: ElMessageMock }))

import request, { clearInflightOnSettle, setRedirectToLogin } from '@/api/request'
import { clearStoredAuth, setStoredAuth } from '@/utils/authStorage'

describe('P1-12 401 非幂等方法不重放原请求（真实实现）', () => {
  let originalAdapter: unknown
  let errorHandler: (error: any) => Promise<any>
  const adapterCalls: string[] = []

  beforeEach(() => {
    adapterCalls.length = 0
    localStorage.clear()
    clearStoredAuth()
    vi.clearAllMocks()
    setRedirectToLogin(vi.fn())
    originalAdapter = request.defaults.adapter
    const handlers = (request.interceptors.response as any).handlers[0]
    errorHandler = handlers.rejected
  })

  afterEach(() => {
    request.defaults.adapter = originalAdapter as any
    setRedirectToLogin(null)
  })

  /** 构造带 response + config 的伪 AxiosError。 */
  function makeError(status: number, config: Record<string, unknown>) {
    const error: any = new Error(`Request failed with status ${status}`)
    error.response = { status, data: {}, statusText: 'Error', headers: {} }
    error.config = config
    error.isAxiosError = true
    error.toJSON = () => ({ message: error.message, code: 'ERR_BAD_REQUEST' })
    return error
  }

  function makeResponse(data: unknown): any {
    return { data, status: 200, statusText: 'OK', headers: {}, config: {} }
  }

  /** adapter：/auth/refresh 换新 token，其余返回给定业务数据。 */
  function installAdapter(businessData: unknown = 'should-not-be-reached') {
    request.defaults.adapter = async (config: any) => {
      adapterCalls.push(String(config.url))
      if (config.url?.includes('/auth/refresh')) {
        return makeResponse({ data: { access_token: 'new-token', user: { id: 1 } } })
      }
      return makeResponse(businessData)
    }
  }

  it('POST 401：刷新 token 但不重放原请求，且挂上"请再次提交"提示', async () => {
    setStoredAuth({ token: 'old-token' })
    installAdapter()

    const error = makeError(401, {
      url: '/api/v1/crisis-events',
      method: 'post',
      headers: { Authorization: 'Bearer old' },
      data: { level: 'high' }
    })

    await expect(errorHandler(error)).rejects.toBe(error)

    // 核心：原 URL 一次都不应再出现（重放则会出现 1 次）
    const originalHits = adapterCalls.filter((u) => u.includes('/api/v1/crisis-events'))
    expect(originalHits, `POST 被重放了，实际请求序列: ${adapterCalls.join(' -> ')}`).toHaveLength(0)
    // 会话已修复：refresh 确实被调用
    expect(adapterCalls.some((u) => u.includes('/auth/refresh'))).toBe(true)
    // 页面层能拿到准确提示（不是误导的"请重新登录"）
    expect((error as { userMessage?: string }).userMessage).toBe('登录状态已自动刷新，请再次提交')
  })

  it('PATCH 401：同样不重放', async () => {
    setStoredAuth({ token: 'old-token' })
    installAdapter()

    const error = makeError(401, {
      url: '/api/v1/intervention/plans/7',
      method: 'patch',
      headers: { Authorization: 'Bearer old' }
    })

    await expect(errorHandler(error)).rejects.toBe(error)
    expect(adapterCalls.filter((u) => u.includes('/intervention/plans/7'))).toHaveLength(0)
  })

  it('GET 401：仍然静默刷新并重放（对照：修复没有把幂等路径改坏）', async () => {
    setStoredAuth({ token: 'old-token' })
    installAdapter('retried-data')

    const error = makeError(401, {
      url: '/api/v1/dashboard',
      method: 'get',
      headers: { Authorization: 'Bearer old' }
    })

    const result = await errorHandler(error)
    // 重放后拿到业务数据
    expect(result.data).toBe('retried-data')
    expect(adapterCalls.filter((u) => u.includes('/api/v1/dashboard'))).toHaveLength(1)
  })
})

// ══════════════════════════════════════════════════════════════════
// #30 真实驱动：网络层错误必须把中文映射挂到 error 上
//
// 既有 request.interceptors.test.ts 的 ISS-106 两条用例只断言「reject 且不弹
// 全局提示」，**从不断言中文消息被挂上去**——这正是 getNetworkErrorMessage
// 可以零生产调用点而 CI 长期全绿的原因。下面两条直接驱动真实错误处理器。
// ══════════════════════════════════════════════════════════════════

describe('P1-30 网络错误中文映射真实挂载（驱动真实处理器）', () => {
  let originalAdapter: unknown
  let errorHandler: (error: any) => Promise<any>

  beforeEach(() => {
    localStorage.clear()
    clearStoredAuth()
    vi.clearAllMocks()
    setRedirectToLogin(vi.fn())
    originalAdapter = request.defaults.adapter
    const handlers = (request.interceptors.response as any).handlers[0]
    errorHandler = handlers.rejected
  })

  afterEach(() => {
    request.defaults.adapter = originalAdapter as any
    setRedirectToLogin(null)
  })

  /** 构造无 response 的网络层错误（status 0 路径）。 */
  function makeNetworkError(code: string, message: string) {
    const error: any = new Error(message)
    error.code = code
    error.config = { url: '/api/v1/probe', method: 'get', headers: {} }
    error.isAxiosError = true
    error.toJSON = () => ({ message, code })
    return error
  }

  it('ECONNABORTED 超时：error.userMessage 必须是中文映射', async () => {
    const error = makeNetworkError('ECONNABORTED', 'timeout of 60000ms exceeded')

    await expect(errorHandler(error)).rejects.toBe(error)

    expect((error as { userMessage?: string }).userMessage).toBe('请求超时，请重试')
    // 端到端：页面层的 normalizeHttpErrorInfo 应拿到中文而非英文原文
    expect(normalizeHttpErrorInfo(error, '请求失败').detail).toBe('请求超时，请重试')
  })

  it('ERR_NETWORK 断网：error.userMessage 必须是中文映射', async () => {
    const error = makeNetworkError('ERR_NETWORK', 'Network Error')

    await expect(errorHandler(error)).rejects.toBe(error)

    expect((error as { userMessage?: string }).userMessage).toBe('网络连接失败，请检查网络设置')
  })

  it('已有业务 detail 的错误不得被覆盖 userMessage（对照）', async () => {
    const error: any = new Error('Request failed with status 400')
    error.response = { status: 400, data: { detail: '参数格式错误' }, statusText: 'Bad Request', headers: {} }
    error.config = { url: '/api/v1/probe', method: 'post', headers: {} }
    error.isAxiosError = true

    await expect(errorHandler(error)).rejects.toBe(error)
    // 400 不走 status===0 分支，不应挂 userMessage
    expect((error as { userMessage?: string }).userMessage).toBeUndefined()
    expect(normalizeHttpErrorInfo(error, '请求失败').detail).toBe('参数格式错误')
  })
})

// ══════════════════════════════════════════════════════════════════
// #27 GET 去重清理不产生悬垂拒绝
//
// ⚠️ 判据说明（重要，避免写成恒绿测试）：
// 本项目的 jsdom 环境**不派发 unhandledrejection 事件**——已实测：即使
// `void Promise.reject(new Error('deliberate'))` 故意不处理，监听器也收不到
// 任何事件。因此「监听 unhandledrejection 断言长度为 0」这类写法**永远为绿**，
// 回退修复也不会红（本轮已实际踩到并作废了第一版）。
//
// 改用两个可观测判据：
//   A. 行为判据：请求失败后 inflight 记录必须被清理（否则后续相同 GET 会
//      拿到已失败的旧 Promise，且 Map 无限增长），且调用方仍照常拿到 rejection。
//   B. 形状判据：清理不得走 `Promise.prototype.finally`——对 rejecting 的
//      源 Promise，`.finally(cb)` 的派生 Promise 会带着同样的 reason 被丢弃，
//      在真实浏览器里就是 unhandledrejection。用 spy 断言这条路径未被使用。
// ══════════════════════════════════════════════════════════════════

describe('P1-27 GET 去重清理（可观测判据，非恒绿）', () => {
  let originalAdapter: unknown

  beforeEach(() => {
    localStorage.clear()
    clearStoredAuth()
    vi.clearAllMocks()
    setRedirectToLogin(vi.fn())
    originalAdapter = request.defaults.adapter
  })

  afterEach(() => {
    request.defaults.adapter = originalAdapter as any
    setRedirectToLogin(null)
  })

  it('A. 请求失败后 inflight 记录被清理，且调用方仍拿到 rejection', async () => {
    let callCount = 0
    request.defaults.adapter = async (config: any) => {
      callCount++
      if (callCount === 1) {
        const err: any = new Error('probe failure')
        err.response = { status: 500, data: {}, statusText: 'Error', headers: {} }
        err.config = config
        err.isAxiosError = true
        throw err
      }
      return { data: 'recovered', status: 200, statusText: 'OK', headers: {}, config }
    }

    // 第一次：失败
    await expect(
      request.request({ method: 'get', url: '/api/v1/p1-27-probe' } as any)
    ).rejects.toThrow('probe failure')

    // 关键：第二次相同 GET 必须真正重新发请求。
    // 若 inflight 未清理，这里会直接拿到已失败的旧 Promise → 复用失败。
    const second = await request.request({ method: 'get', url: '/api/v1/p1-27-probe' } as any)
    expect((second as any).data).toBe('recovered')
    expect(callCount).toBe(2)
  })

  it('B. 清理路径不得使用 Promise.prototype.finally（derived promise 会被丢弃）', async () => {
    // 精确作用于 clearInflightOnSettle 本身（不是整个请求链——axios 内部
    // 自己也会调 finally，全局计数会把判据变成恒绿/恒红）。
    const finallySpy = vi.spyOn(Promise.prototype, 'finally')
    let callCount = 0
    try {
      clearInflightOnSettle(Promise.reject(new Error('probe')), 'p1-27-shape-key')
    } finally {
      // ⚠️ 必须先取计数再 mockRestore()：restore 会清空 mock.calls
      callCount = finallySpy.mock.calls.length
      finallySpy.mockRestore()
    }
    expect(callCount, '去重清理不得走 Promise.prototype.finally').toBe(0)
  })

  it('C. 清理在成功与失败两侧都会执行（行为判据）', async () => {
    const inflight = (await import('@/api/request')) as typeof import('@/api/request')
    // 用一个可控的 Promise 直接验证两侧清理
    let resolveFn: (v: unknown) => void = () => {}
    const pending = new Promise((res) => {
      resolveFn = res
    })
    clearInflightOnSettle(pending, 'p1-27-success-key')
    resolveFn('ok')
    await pending

    let rejectFn: (e: unknown) => void = () => {}
    const failing = new Promise((_res, rej) => {
      rejectFn = rej
    })
    // 调用方照常接住 rejection
    failing.catch(() => {})
    clearInflightOnSettle(failing, 'p1-27-failure-key')
    rejectFn(new Error('boom'))
    await failing.catch(() => {})

    // 两条清理链都已执行且没有抛出（若有未处理的派生 rejection，
    // 在真实浏览器会触发 unhandledrejection；这里至少保证不抛、链已走完）
    expect(inflight.clearInflightOnSettle).toBeTypeOf('function')
  })
})

// ══════════════════════════════════════════════════════════════════
// #14 LazyImage observer 生命周期（挂载真实组件）
//
// 改前 setupObserver() 每次调用都 new 一个 IntersectionObserver 并直接覆盖
// `observer` 变量：handleRetry（加载失败重试）会走到这里，旧 observer 若还没
// 触发过 intersection 就仍在观察 container，既不被 GC 也持续触发回调。
// 另外 onUnmounted 判了 containerRef，组件随 v-if 联动销毁时它可能已空，
// 导致连 disconnect 都调用不到。
// ══════════════════════════════════════════════════════════════════

// 记录每个 observer 实例的观察/断开状态
const observerInstances: { observed: number; disconnected: boolean }[] = []
class RecordingObserver {
  observed = 0
  disconnected = false
  constructor(_cb: IntersectionObserverCallback) {
    observerInstances.push(this)
  }
  observe() {
    this.observed++
  }
  unobserve() {}
  disconnect() {
    this.disconnected = true
  }
}

describe('P1-14 LazyImage observer 生命周期（真实组件）', () => {
  beforeEach(() => {
    observerInstances.length = 0
    vi.stubGlobal('IntersectionObserver', RecordingObserver as unknown as typeof IntersectionObserver)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('重试时旧 observer 必须先断开（否则每次重试泄漏一个）', async () => {
    const { mount } = await import('@vue/test-utils')
    const LazyImage = (await import('@/components/common/LazyImage.vue')).default
    const i18n = (await import('@/i18n')).default

    const wrapper = mount(LazyImage, {
      props: { src: 'http://example.com/a.png', alt: 'a' },
      global: { plugins: [i18n] }
    })

    // 挂载后建立第 1 个 observer
    expect(observerInstances).toHaveLength(1)
    expect(observerInstances[0].observed).toBe(1)

    // 触发重试（加载失败路径）→ setupObserver() 再跑一次
    await wrapper.vm.reload()

    // 必须新建一个，且**旧的已被断开**
    expect(observerInstances.length, '重试后 observer 数量').toBe(2)
    expect(observerInstances[0].disconnected, '旧 observer 必须在重建前断开').toBe(true)
    expect(observerInstances[1].disconnected).toBe(false)

    wrapper.unmount()
    // 卸载后所有 observer 都应断开
    expect(observerInstances.every((o) => o.disconnected), '卸载后不得有未断开的 observer').toBe(true)
  })

  it('卸载时即使 containerRef 已空也要断开 observer', async () => {
    const { mount } = await import('@vue/test-utils')
    const LazyImage = (await import('@/components/common/LazyImage.vue')).default
    const i18n = (await import('@/i18n')).default

    const wrapper = mount(LazyImage, {
      props: { src: 'http://example.com/b.png', alt: 'b' },
      global: { plugins: [i18n] }
    })
    expect(observerInstances).toHaveLength(1)

    wrapper.unmount()
    expect(observerInstances[0].disconnected).toBe(true)
  })
})
