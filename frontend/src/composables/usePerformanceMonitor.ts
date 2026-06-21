import { ref, onMounted, onUnmounted } from 'vue'

/**
 * 前端性能监控指标类型
 */
export interface PerformanceMetrics {
  // Core Web Vitals
  fcp?: number // First Contentful Paint
  lcp?: number // Largest Contentful Paint
  fid?: number // First Input Delay
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
  reportInterval: 30000,
  autoReport: true,
  reportUrl: '/api/monitoring/frontend-metrics',
  clsSessionWindow: 5000,
}

/**
 * 使用 PerformanceObserver 采集指标
 */
const observeMetric = (
  entryType: string,
  callback: (entries: PerformanceEntryList) => void
): (() => void) | null => {
  if (!('PerformanceObserver' in window)) return null

  try {
    const observer = new PerformanceObserver((list) => {
      callback(list.getEntries())
    })
    observer.observe({ entryTypes: [entryType] })
    return () => observer.disconnect()
  } catch {
    return null
  }
}

/**
 * 前端性能监控 Composable
 *
 * 采集 Core Web Vitals 和自定义性能指标
 * 自动上报到后端 /monitoring/frontend-metrics
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

  const metrics = ref<PerformanceMetrics>({
    url: window.location.href,
    timestamp: Date.now(),
    userAgent: navigator.userAgent,
  })

  const isCollecting = ref(false)
  const reportTimer = ref<ReturnType<typeof setInterval> | null>(null)
  const cleanupFns: (() => void)[] = []

  // CLS 计算状态
  interface LayoutShiftEntry extends PerformanceEntry {
    value: number
    hadRecentInput: boolean
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
          metrics.value.fcp = entry.startTime
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
        metrics.value.lcp = lastEntry.startTime
      }
    })
    if (cleanup) cleanupFns.push(cleanup)
  }

  /**
   * 采集 FID (First Input Delay)
   */
  const collectFID = () => {
    const cleanup = observeMetric('first-input', (entries) => {
      entries.forEach((entry) => {
        const firstInput = entry as PerformanceEventTiming
        if (firstInput.processingStart && firstInput.startTime) {
          metrics.value.fid = firstInput.processingStart - firstInput.startTime
        }
      })
    })
    if (cleanup) cleanupFns.push(cleanup)
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
                  metrics.value.cls = clsValue
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
    onMounted(() => {
      const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming
      if (navigation) {
        metrics.value.ttfb = navigation.responseStart - navigation.startTime
        metrics.value.domReadyTime = navigation.domContentLoadedEventEnd - navigation.startTime
        metrics.value.pageLoadTime = navigation.loadEventEnd - navigation.startTime
      }
    })
  }

  /**
   * 采集资源加载信息
   */
  const collectResources = () => {
    onMounted(() => {
      const resources = performance.getEntriesByType('resource')
      metrics.value.resourceCount = resources.length
      metrics.value.resourceSize = resources.reduce((total, r) => {
        const resource = r as PerformanceResourceTiming
        return total + (resource.transferSize || 0)
      }, 0)
    })
  }

  /**
   * 上报性能指标到后端
   */
  const reportMetrics = async (): Promise<boolean> => {
    try {
      const payload = {
        ...metrics.value,
        url: window.location.href,
        timestamp: Date.now(),
      }

      const response = await fetch(opts.reportUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
        // 使用 keepalive 确保页面卸载时也能发送
        keepalive: true,
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
      return navigator.sendBeacon(opts.reportUrl, payload)
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
    collectFID()
    collectCLS()
    collectTTFB()
    collectResources()

    // 自动上报
    if (opts.autoReport) {
      reportTimer.value = setInterval(() => {
        reportMetrics()
      }, opts.reportInterval)
    }

    // 页面卸载时使用 Beacon 上报
    const handleBeforeUnload = () => {
      reportWithBeacon()
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    cleanupFns.push(() => window.removeEventListener('beforeunload', handleBeforeUnload))

    // 页面可见性变化时上报
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
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

    if (reportTimer.value) {
      clearInterval(reportTimer.value)
      reportTimer.value = null
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
