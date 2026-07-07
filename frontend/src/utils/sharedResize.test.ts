/* R-009 回归测试：覆盖 V-Perf-04 窗口缩放验证用例 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

/**
 * sharedResize 模块单元测试
 *
 * R-009 修复点：6 个图表组件从独立 window.addEventListener('resize', throttle(...))
 * 迁移到共享 subscribeResize（来自 @/utils/sharedResize）。
 *
 * sharedResize 内部维护模块级 subscribers Set 和 dispatchHandler（throttle 包装），
 * 使用 vi.resetModules() + 动态 import 确保每个测试获得新鲜的模块状态
 * （包括 throttle 的 lastTime/timer 内部状态）。
 */

// 动态加载的 subscribeResize 函数（每个 beforeEach 重新加载模块）
let subscribeResize: (cb: () => void) => () => void
// 收集所有 unsubscribe 函数，在 afterEach 中统一清理
const unsubs: Array<() => void> = []

beforeEach(async () => {
  vi.useFakeTimers()
  // 固定系统时间，确保 throttle 首次调用时 remaining ≤ 0（lastTime 初始为 0）
  vi.setSystemTime(new Date(2024, 0, 1))
  // 重置模块注册表，使下一次 import 获得全新的 subscribers Set / dispatchHandler / throttle 状态
  vi.resetModules()
  const mod = await import('@/utils/sharedResize')
  subscribeResize = mod.subscribeResize
  unsubs.length = 0
})

afterEach(() => {
  // 清理所有订阅（移除 subscribers Set 中的条目）
  unsubs.forEach((u) => u())
  unsubs.length = 0
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('sharedResize - R-009 共享 resize 监听', () => {
  it('1. subscribeResize 基本订阅：触发 resize 后 callback 应被调用', () => {
    // R-009 修复点：共享 subscribeResize 替代独立 addEventListener
    const cb = vi.fn()
    const unsub = subscribeResize(cb)
    unsubs.push(unsub)

    window.dispatchEvent(new Event('resize'))

    expect(cb).toHaveBeenCalledTimes(1)
  })

  it('2. 返回的 unsubscribe 函数：调用后 callback 不再接收事件', () => {
    const cb = vi.fn()
    const unsub = subscribeResize(cb)
    // 不放入 unsubs，手动调用以验证行为
    unsub()

    window.dispatchEvent(new Event('resize'))

    expect(cb).not.toHaveBeenCalled()
  })

  it('3. 多订阅者共享监听：一次 resize 应调用所有 callback（单一全局 listener）', () => {
    // R-009 修复点：多个组件共享一个全局 resize listener，而非各自注册
    const cb1 = vi.fn()
    const cb2 = vi.fn()
    const cb3 = vi.fn()
    unsubs.push(subscribeResize(cb1))
    unsubs.push(subscribeResize(cb2))
    unsubs.push(subscribeResize(cb3))

    // 仅触发一次 resize 事件
    window.dispatchEvent(new Event('resize'))

    expect(cb1).toHaveBeenCalledTimes(1)
    expect(cb2).toHaveBeenCalledTimes(1)
    expect(cb3).toHaveBeenCalledTimes(1)
  })

  it('4. unsubscribe 单个订阅者不影响其他', () => {
    const cb1 = vi.fn()
    const cb2 = vi.fn()
    const unsub1 = subscribeResize(cb1)
    unsubs.push(subscribeResize(cb2))

    unsub1()

    window.dispatchEvent(new Event('resize'))

    expect(cb1).not.toHaveBeenCalled()
    expect(cb2).toHaveBeenCalledTimes(1)
  })

  it('5. 节流 100ms：连续快速触发 5 次应被节流（leading + trailing 共 2 次，非 5 次）', () => {
    // R-009 修复点：throttle(dispatch, 100) 限制 resize 高频触发
    const cb = vi.fn()
    unsubs.push(subscribeResize(cb))

    // 第一次触发：throttle leading edge，remaining ≤ 0 → 立即调用
    window.dispatchEvent(new Event('resize'))
    expect(cb).toHaveBeenCalledTimes(1)

    // 后续 4 次快速触发（间隔 10ms），应被节流（trailing timer 已设置）
    for (let i = 0; i < 4; i++) {
      vi.advanceTimersByTime(10)
      window.dispatchEvent(new Event('resize'))
    }
    // trailing edge 尚未触发，仍只有 leading 的 1 次
    expect(cb).toHaveBeenCalledTimes(1)

    // 推进时间超过节流窗口（100ms），trailing edge 应触发一次
    vi.advanceTimersByTime(100)
    expect(cb).toHaveBeenCalledTimes(2)
  })

  it('6. 单个订阅者异常不影响其他（try/catch 隔离）', () => {
    // R-009 修复点：dispatch 使用 try/catch 隔离每个订阅者
    const cb1 = vi.fn(() => {
      throw new Error('subscriber error')
    })
    const cb2 = vi.fn()
    unsubs.push(subscribeResize(cb1))
    unsubs.push(subscribeResize(cb2))

    // 不应因 cb1 抛错而阻止 cb2 执行
    expect(() => window.dispatchEvent(new Event('resize'))).not.toThrow()

    expect(cb1).toHaveBeenCalledTimes(1)
    expect(cb2).toHaveBeenCalledTimes(1)
  })

  it('7. unsubscribe 幂等：多次调用不应报错', () => {
    const cb = vi.fn()
    const unsub = subscribeResize(cb)

    expect(() => {
      unsub()
      unsub()
      unsub()
    }).not.toThrow()
  })

  it('8. 重复订阅同一 callback：Set 语义去重，unsubscribe 一次后不再调用', () => {
    // Set 语义：同一函数引用只存储一次（非 Array 的"添加两次"）
    const cb = vi.fn()
    const unsub1 = subscribeResize(cb)
    const unsub2 = subscribeResize(cb)
    unsubs.push(unsub1, unsub2)

    // Set 去重：一次 resize 只调用一次
    window.dispatchEvent(new Event('resize'))
    expect(cb).toHaveBeenCalledTimes(1)

    // 任一 unsubscribe 都会从 Set 中删除该引用
    unsub1()
    window.dispatchEvent(new Event('resize'))
    expect(cb).toHaveBeenCalledTimes(1) // 仍然只有 1 次，未被再次调用
  })
})
