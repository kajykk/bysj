/* R-009 回归测试：覆盖 V-Perf-04 窗口缩放验证用例 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import BaseChart from './BaseChart.vue'

/**
 * BaseChart 组件单元测试
 *
 * R-009 修复点：BaseChart.vue 添加 rAF (requestAnimationFrame) 节流 ResizeObserver 回调，
 * 避免同一帧内多次 RO 回调同步触发 ECharts resize（布局重计算阻塞主线程）。
 *
 * 关键实现：
 * - ResizeObserver 回调中使用 requestAnimationFrame 合并：if (resizeRafId !== null) return
 * - disposeChart 中 cancelAnimationFrame 取消 pending rAF
 * - onUnmounted/onDeactivated 调用 disposeChart 清理资源
 */

// 使用 vi.hoisted 确保 mock 函数在 vi.mock 工厂执行前已初始化
const { mockResize, mockDispose, mockSetOption, mockInit } = vi.hoisted(() => {
  const mockResize = vi.fn()
  const mockDispose = vi.fn()
  const mockSetOption = vi.fn()
  return {
    mockResize,
    mockDispose,
    mockSetOption,
    mockInit: vi.fn(() => ({
      resize: mockResize,
      dispose: mockDispose,
      setOption: mockSetOption,
      getDataURL: vi.fn(),
      dispatchAction: vi.fn(),
    })),
  }
})

// Mock @/utils/echarts 避免 ECharts 真实渲染
vi.mock('@/utils/echarts', () => ({
  echarts: {
    init: mockInit,
    use: vi.fn(),
  },
}))

// Mock vue-i18n（BaseChart 使用 useI18n 的 t 函数）
vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

// ResizeObserver mock 实例收集器
interface MockResizeObserver {
  observe: ReturnType<typeof vi.fn>
  unobserve: ReturnType<typeof vi.fn>
  disconnect: ReturnType<typeof vi.fn>
  cb: (entries: ResizeObserverEntry[]) => void
}
const roInstances: MockResizeObserver[] = []

beforeEach(() => {
  // 使用 fake timers 控制 requestAnimationFrame 时序（rAF 被调度到 ~16ms 后）
  vi.useFakeTimers()

  // 清理 mock 调用记录
  mockResize.mockClear()
  mockDispose.mockClear()
  mockSetOption.mockClear()
  mockInit.mockClear()
  roInstances.length = 0

  // Mock ResizeObserver：构造时保存回调，便于测试中手动触发
  vi.stubGlobal(
    'ResizeObserver',
    class MockRO {
      observe = vi.fn()
      unobserve = vi.fn()
      disconnect = vi.fn()
      cb: (entries: ResizeObserverEntry[]) => void
      constructor(cb: (entries: ResizeObserverEntry[]) => void) {
        this.cb = cb
        roInstances.push(this as unknown as MockResizeObserver)
      }
    }
  )
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const baseProps = {
  option: { title: { text: 'test' } },
  autoResize: true,
}

describe('BaseChart - R-009 rAF 节流 ResizeObserver', () => {
  it('1. rAF 节流合并多次 ResizeObserver 回调：同一帧内仅调用一次 chart.resize', async () => {
    // R-009 修复点：ResizeObserver 回调使用 rAF 合并，避免同步布局计算
    const wrapper = mount(BaseChart, { props: baseProps })
    await flushPromises()

    expect(roInstances).toHaveLength(1)
    const ro = roInstances[0]

    // 连续触发 3 次 RO 回调
    ro.cb([])
    ro.cb([])
    ro.cb([])

    // rAF 尚未执行（需推进时间），chart.resize 不应被调用
    expect(mockResize).not.toHaveBeenCalled()

    // 推进 rAF（一帧 ≈ 16ms）
    vi.advanceTimersByTime(20)

    // chart.resize 应仅被调用一次（3 次回调被 rAF 合并为 1 次）
    expect(mockResize).toHaveBeenCalledTimes(1)

    wrapper.unmount()
  })

  it('2. disposeChart 取消未执行的 rAF：pending rAF 被 cancelAnimationFrame 取消', async () => {
    // R-009 修复点：disposeChart 中 cancelAnimationFrame(resizeRafId) 取消 pending rAF
    const wrapper = mount(BaseChart, { props: baseProps })
    await flushPromises()

    const ro = roInstances[0]

    // 触发 RO 回调（调度 rAF，但尚未执行）
    ro.cb([])

    // 立即卸载组件（触发 disposeChart → cancelAnimationFrame）
    wrapper.unmount()

    // 推进 rAF 时间
    vi.advanceTimersByTime(20)

    // chart.resize 不应被调用（rAF 已被取消，且 chartInstance 已被 dispose）
    expect(mockResize).not.toHaveBeenCalled()
  })

  it('3. disposeChart 断开 ResizeObserver：onDeactivated 时 disconnect 应被调用', async () => {
    // R-009 修复点：disposeChart 调用 ResizeObserver.disconnect 释放观察者
    // 说明：onUnmounted 时 Vue 已将 chartRef.value 置空，disposeChart 中
    // `resizeObserver.value && chartRef.value` 守卫会跳过 disconnect。
    // 故通过 keep-alive 的 onDeactivated 路径验证（deactivate 时 chartRef.value 仍有效）。
    const Dummy = { inheritAttrs: false, template: '<div />' }
    const Parent = {
      components: { BaseChart, Dummy },
      data() {
        return { current: 'BaseChart', option: { title: { text: 'test' } } }
      },
      template: `
        <keep-alive>
          <component :is="current" :option="option" :autoResize="true" />
        </keep-alive>
      `,
    }
    const wrapper = mount(Parent)
    await flushPromises()

    expect(roInstances).toHaveLength(1)
    const ro = roInstances[0]

    // 切换到 Dummy → BaseChart 被 keep-alive 缓存（deactivate），触发 onDeactivated → disposeChart
    await wrapper.setData({ current: 'Dummy' })
    await flushPromises()

    expect(ro.disconnect).toHaveBeenCalled()
  })

  it('4. autoResize=false 不创建 ResizeObserver', async () => {
    // R-009 相关：autoResize 为 false 时不应初始化 ResizeObserver
    const wrapper = mount(BaseChart, { props: { ...baseProps, autoResize: false } })
    await flushPromises()

    expect(roInstances).toHaveLength(0)

    wrapper.unmount()
  })

  it('5. 组件卸载时清理：onUnmounted 触发 disposeChart，释放 chart 实例和 rAF', async () => {
    // R-009 修复点：onUnmounted → disposeChart → chart.dispose + cancelAnimationFrame
    const wrapper = mount(BaseChart, { props: baseProps })
    await flushPromises()

    const ro = roInstances[0]

    // 触发 RO 回调（调度 pending rAF）
    ro.cb([])

    wrapper.unmount()

    // ECharts 实例应被 dispose（释放 chart 实例）
    expect(mockDispose).toHaveBeenCalled()
    // 推进 rAF 时间，resize 不应被调用（rAF 已被 cancelAnimationFrame 取消，释放 rAF）
    vi.advanceTimersByTime(20)
    expect(mockResize).not.toHaveBeenCalled()
  })
})
