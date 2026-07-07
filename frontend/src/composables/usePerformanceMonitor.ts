import { ref, shallowRef, onMounted, onUnmounted } from 'vue'
import { getStoredToken } from '@/utils/authStorage'

/**
 * 前端性能监控指标类型
 */
export interface PerformanceMetrics {
  // Core Web Vitals
  fcp?: number // First Contentful Paint
  lcp?: number // Largest Contentful Paint
  inp?: number // Interaction to Next Paint (M-48: 替代已废弃的 FID)
  cls?: number // Cumulative Layout Shift
  ttfb?: number // Time to First Byte

  // 自定义指标
  pageLoadTime?: number // 页面完全加载时间
  domReadyTime?: number // DOM Ready 时间
  resourceCount?: number // 资源数量
  resourceSize?: number // 资源总大小 (bytes)

  // 导航信息
  url: string
  timestamp: number
  userAgent: string
}

/**
 * 性能监控配置选项
 */
export interface PerformanceMonitorOptions {
  /** 上报间隔 (ms)，默认 30000 */
  reportInterval?: number
  /** 是否自动上报 */
  autoReport?: boolean
  /** 上报地址 */
  reportUrl?: string
  /** CLS 采样窗口 (ms)，默认 5000 */
  clsSessionWindow?: number
}

const DEFAULT_OPTIONS: Required<PerformanceMonitorOptions> = {
  reportInterval: 300000,
  autoReport: false,
  // P3-3 修复: 后端 monitoring router 挂载在 /api/v1/monitoring, 原路径缺少 /v1/ 前缀
  reportUrl: '/api/v1/monitoring/frontend-metrics',
  clsSessionWindow: 5000,
}

/**
 * 使用 PerformanceObserver 采集指标
 * L-FE-10 修复：observer 创建失败时返回 noop cleanup（而非 null），
 * 使调用方无需判空，cleanup 数组中 noop 调用无副作用
 */
const observeMetric = (
  entryType: string,
  callback: (entries: PerformanceEntryList) => void
): () => void => {
  const noop = () => {}
  if (!('PerformanceObserver' in window)) return noop

  try {
    const observer = new PerformanceObserver((list) => {
      callback(list.getEntries())
    })
    observer.observe({ entryTypes: [entryType] })
    return () => observer.disconnect()
  } catch {
    return noop
  }
}

/**
 * 前端性能监控 Composable
 *
 * 采集 Core Web Vitals 和自定义性能指标
 * 自动上报到后端 /api/v1/monitoring/frontend-metrics
 *
 * @example
 * ```ts
 * const { metrics, reportMetrics } = usePerformanceMonitor()
 * // metrics 是响应式对象，包含采集到的性能指标
 * // 手动上报: reportMetrics()
 * ```
 */
export function usePerformanceMonitor(options: PerformanceMonitorOptions = {}) {
  const opts = { ...DEFAULT_OPTIONS, ...options }

  // M-FE-23 修复：改用 shallowRef，避免性能指标频繁更新触发深层响应式开销
  // 所有更新需整体替换 .value，而非深层修改字段
  const metrics = shallowRef<PerformanceMetrics>({
    url: window.location.href,
    timestamp: Date.now(),
    userAgent: navigator.userAgent,
  })

  const isCollecting = ref(false)
  let reportTimer: ReturnType<typeof setInterval> | null = null
  const cleanupFns: (() => void)[] = []

  // CLS 计算状态
  interface LayoutShiftEntry extends PerformanceEntry {
    value: number
    hadRecentInput: boolean
  }

  // M-48 修复：定义 PerformanceEventTiming，用于 INP 采集
  interface PerformanceEventTiming extends PerformanceEntry {
    interactionId: number
    duration: number
    processingStart: number
    processingEnd: number
  }

  let clsValue = 0
  let clsSessionEntries: LayoutShiftEntry[] = []
  let clsSessionStartTime = 0

  /**
   * 采集 FCP (First Contentful Paint)
   */
  const collectFCP = () => {
    const cleanup = observeMetric('paint', (entries) => {
      entries.forEach((entry) => {
        if (entry.name === 'first-contentful-paint') {
          // M-FE-23 修复：shallowRef 需整体替换
          metrics.value = { ...metrics.value, fcp: entry.startTime }
        }
      })
    })
    if (cleanup) cleanupFns.push(cleanup)
  }

  /**
   * 采集 LCP (Largest Contentful Paint)
   */
  const collectLCP = () => {
    const cleanup = observeMetric('largest-contentful-paint', (entries) => {
      const lastEntry = entries[entries.length - 1] as PerformanceEntry & { startTime: number }
      if (lastEntry) {
        // M-FE-23 修复：shallowRef 需整体替换
        metrics.value = { ...metrics.value, lcp: lastEntry.startTime }
      }
    })
    if (cleanup) cleanupFns.push(cleanup)
  }

  // M-FE-9 修复：按 interactionId 分组记录每次交互的最大 duration，
  // 避免同一交互的多个事件（pointerdown/click/pointerup）被重复计入导致 INP 高估
  const interactionMaxDuration = new Map<number, number>()

  /**
   * 采集 INP (Interaction to Next Paint)
   *
   * M-48 修复：FID 已被 Chrome 弃用（2024 年 9 月），改用 INP 作为 Core Web Vital。
   * INP 测量页面生命周期内最差的交互延迟（pointerdown、pointerup、click 等）。
   * 取所有 interaction 的最大 duration 作为 INP 值。
   * 仅记录 interactionId > 0 的条目（排除非交互事件）。
   * M-FE-9 修复：按 interactionId 分组，每组取最大 duration，避免同一交互多事件高估。
   */
  const collectINP = () => {
    const cleanup = observeMetric('event', (entries) => {
      entries.forEach((entry) => {
        const eventEntry = entry as PerformanceEventTiming
        // 仅记录有效交互（interactionId > 0）
        if (eventEntry.interactionId) {
          const id = eventEntry.interactionId
          const duration = eventEntry.duration
          // M-FE-9 修复：按 interactionId 分组，取每组最大 duration
          const prev = interactionMaxDuration.get(id)
          if (prev === undefined || duration > prev) {
            interactionMaxDuration.set(id, duration)
          }
          // INP 取所有交互中最大的 duration
          const worst = Math.max(...interactionMaxDuration.values())
          if (!metrics.value.inp || worst > metrics.value.inp) {
            // M-FE-23 修复：shallowRef 需整体替换
            metrics.value = { ...metrics.value, inp: worst }
          }
        }
      })
    })
    if (cleanup) cleanupFns.push(cleanup)
  }

  /**
   * C-FE-5 修复：将当前 clsSessionEntries 累加到 metrics.value.cls。
   * 原实现仅在新会话窗口开始时才更新 metrics.value.cls，
   * 若页面在当前会话窗口内被关闭（常见情况），最终 CLS 累积值不会被写入，
   * reportWithBeacon 上报的是旧值或 undefined。
   */
  const flushClsSession = () => {
    if (clsSessionEntries.length > 0) {
      const sessionCls = clsSessionEntries.reduce((sum, e) => sum + e.value, 0)
      if (sessionCls > clsValue) {
        clsValue = sessionCls
        // M-FE-23 修复：shallowRef 需整体替换
        metrics.value = { ...metrics.value, cls: clsValue }
      }
    }
  }

  /**
   * 采集 CLS (Cumulative Layout Shift)
   * 使用会话窗口模式，最大会话窗口 5 秒，间隔 1 秒
   */
  const collectCLS = () => {
    if (!('PerformanceObserver' in window)) return

    try {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          const layoutShift = entry as LayoutShiftEntry
          if (!layoutShift.hadRecentInput && layoutShift.value) {
            const entryTime = layoutShift.startTime

            // 新会话窗口开始
            if (
              clsSessionEntries.length === 0 ||
              entryTime - clsSessionStartTime > opts.clsSessionWindow
            ) {
              // 计算上一个会话的 CLS
              if (clsSessionEntries.length > 0) {
                const sessionCls = clsSessionEntries.reduce((sum, e) => sum + e.value, 0)
                if (sessionCls > clsValue) {
                  clsValue = sessionCls
                  // M-FE-23 修复：shallowRef 需整体替换
                  metrics.value = { ...metrics.value, cls: clsValue }
                }
              }
              clsSessionEntries = []
              clsSessionStartTime = entryTime
            }

            clsSessionEntries.push(layoutShift)
          }
        }
      })
      observer.observe({ entryTypes: ['layout-shift'] })
      cleanupFns.push(() => observer.disconnect())
    } catch {
      // 浏览器不支持 layout-shift
    }
  }

  /**
   * 采集 TTFB (Time to First Byte)
   */
  const collectTTFB = () => {
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming
    if (navigation) {
      // M-FE-23 修复：shallowRef 需整体替换，合并多个字段一次性更新
      metrics.value = {
        ...metrics.value,
        ttfb: navigation.responseStart - navigation.startTime,
        domReadyTime: navigation.domContentLoadedEventEnd - navigation.startTime,
        pageLoadTime: navigation.loadEventEnd - navigation.startTime,
      }
    }
  }

  /**
   * 采集资源加载信息
   */
  const collectResources = () => {
    const resources = performance.getEntriesByType('resource')
    // M-FE-23 修复：shallowRef 需整体替换，合并多个字段一次性更新
    metrics.value = {
      ...metrics.value,
      resourceCount: resources.length,
      resourceSize: resources.reduce((total, r) => {
        const resource = r as PerformanceResourceTiming
        return total + (resource.transferSize || 0)
      }, 0),
    }
  }

  /**
   * 上报性能指标到后端
   * FM-03 修复：手动添加 Authorization header，确保后端能鉴权。
   * 不使用封装的 request 实例，因为需要 keepalive 支持页面卸载时上报，
   * 且性能上报不应触发 401 token 刷新逻辑。
   */
  const reportMetrics = async (): Promise<boolean> => {
    try {
      const payload = {
        ...metrics.value,
        url: window.location.href,
        timestamp: Date.now(),
      }

      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      }
      // 注入 access token，与 request 拦截器保持一致
      const token = getStoredToken()
      if (token) {
        headers.Authorization = `Bearer ${token}`
      }

      const response = await fetch(opts.reportUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
        // 使用 keepalive 确保页面卸载时也能发送
        keepalive: true,
        // H-FE-4 修复：显式携带 credentials，确保后端鉴权通过（fetch 默认不发送 Cookie）
        credentials: 'include',
      })

      return response.ok
    } catch (error) {
      console.warn('[PerformanceMonitor] 上报失败:', error)
      return false
    }
  }

  /**
   * 使用 Beacon API 上报（页面卸载时）
   */
  const reportWithBeacon = (): boolean => {
    if (!('sendBeacon' in navigator)) return false

    try {
      const payload = JSON.stringify({
        ...metrics.value,
        url: window.location.href,
        timestamp: Date.now(),
      })
      // H-FE-7 修复：用 Blob 包装 payload 并指定 Content-Type 为 application/json
      // 原直接传字符串时 sendBeacon 默认 Content-Type 为 text/plain;charset=UTF-8，后端可能 422 拒绝
      const blob = new Blob([payload], { type: 'application/json' })
      return navigator.sendBeacon(opts.reportUrl, blob)
    } catch {
      return false
    }
  }

  /**
   * 开始采集
   */
  const start = () => {
    if (isCollecting.value) return
    isCollecting.value = true

    collectFCP()
    collectLCP()
    collectINP()
    collectCLS()
    collectTTFB()
    collectResources()

    // 自动上报
    if (opts.autoReport) {
      reportTimer = setInterval(() => {
        reportMetrics()
      }, opts.reportInterval)
    }

    // 页面卸载时使用 Beacon 上报
    const handleBeforeUnload = () => {
      // C-FE-5 修复：卸载前先把当前 CLS 会话窗口的累积值写入 metrics
      flushClsSession()
      reportWithBeacon()
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    cleanupFns.push(() => window.removeEventListener('beforeunload', handleBeforeUnload))

    // 页面可见性变化时上报
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        // C-FE-5 修复：隐藏前先把当前 CLS 会话窗口的累积值写入 metrics
        flushClsSession()
        reportWithBeacon()
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    cleanupFns.push(() => document.removeEventListener('visibilitychange', handleVisibilityChange))
  }

  /**
   * 停止采集
   */
  const stop = () => {
    isCollecting.value = false

    if (reportTimer) {
      clearInterval(reportTimer)
      reportTimer = null
    }

    cleanupFns.forEach((fn) => fn())
    cleanupFns.length = 0
  }

  onMounted(() => {
    start()
  })

  onUnmounted(() => {
    stop()
  })

  return {
    metrics,
    isCollecting,
    reportMetrics,
    reportWithBeacon,
    start,
    stop,
  }
}

export default usePerformanceMonitor
