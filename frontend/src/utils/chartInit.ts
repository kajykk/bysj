/**
 * ECharts 容器就绪后初始化工具。
 *
 * 场景：图表容器可见但宽/高为 0（tab 切换动画、布局未稳定等）时直接
 * `echarts.init` 会输出 "Can't get DOM width or height" 警告且首次渲染空白。
 * 本工具在尺寸就绪后才 init。
 *
 * SEC-FIX (P1-6): 返回取消句柄。重试链 (setTimeout) 与 ResizeObserver 兜底
 * 均可被 cancel() 终止——组件在重试窗口内卸载时, 不再对已脱离文档的 DOM
 * 创建"僵尸" ECharts 实例 (实例无人 dispose, canvas/事件监听全量泄漏)。
 *
 * SEC-FIX (P1-7): 重试耗尽后不再永久放弃。注册 ResizeObserver 兜底,
 * 容器尺寸从 0 变为非 0 时补一次 init (BaseChart 等无数据驱动自愈路径的
 * 场景, 原实现重试 5 次 (~600ms) 后图表永久空白)。
 *
 * 测试环境（jsdom 无布局引擎，clientWidth/clientHeight 恒为 0）保持同步 init，
 * 与既有组件行为一致，避免破坏单测断言。
 */
import { echarts, type ECharts } from '@/utils/echarts'

export interface ChartInitOptions {
  theme?: string
  retries?: number
  intervalMs?: number
}

export interface ChartInitHandle {
  instance: ECharts | null
  /** 终止未完成的重试与兜底监听。组件卸载时必须调用。 */
  cancel: () => void
}

const isJsdomTest = import.meta.env.MODE === 'test'

export function initChartWhenReady(
  dom: HTMLElement,
  options: ChartInitOptions = {},
  onReady?: (instance: ECharts) => void
): ChartInitHandle {
  let cancelled = false
  let settled = false
  let timerId: number | null = null
  let observer: ResizeObserver | null = null

  const tryInit = (): ECharts | null => {
    if (cancelled) return null
    if (!isJsdomTest && (dom.clientWidth <= 0 || dom.clientHeight <= 0)) {
      return null
    }
    settled = true
    cleanupWatchers()
    const instance = echarts.init(dom, options.theme)
    onReady?.(instance)
    return instance
  }

  const cleanupWatchers = () => {
    if (timerId !== null) {
      window.clearTimeout(timerId)
      timerId = null
    }
    if (observer) {
      observer.disconnect()
      observer = null
    }
  }

  const cancel = () => {
    if (cancelled) return
    cancelled = true
    cleanupWatchers()
  }

  const instance = tryInit()
  if (instance) return { instance, cancel }

  const retries = options.retries ?? 5
  const intervalMs = options.intervalMs ?? 120
  let retry = 0

  const attempt = () => {
    if (cancelled || settled) return
    if (tryInit()) return
    retry += 1
    if (retry <= retries) {
      timerId = window.setTimeout(attempt, intervalMs)
      return
    }
    // 重试耗尽: 注册 ResizeObserver 兜底, 尺寸就绪 (0 -> 非 0) 时补一次 init
    installObserverFallback()
  }

  const installObserverFallback = () => {
    if (cancelled || settled || typeof ResizeObserver === 'undefined') return
    observer = new ResizeObserver(() => {
      if (cancelled || settled) return
      if (dom.clientWidth > 0 && dom.clientHeight > 0) {
        tryInit()
      }
    })
    observer.observe(dom)
  }

  // 首次 (同步) 调用 attempt: 尺寸未就绪时启动重试链
  attempt()
  return { instance: null, cancel }
}
