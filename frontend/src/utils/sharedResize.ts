import { throttle } from '@/utils/debounce'

// L-FE-2 修复：共享一个全局 resize 监听，避免每个组件实例独立注册造成冗余开销
const subscribers = new Set<() => void>()
let dispatchHandler: (() => void) | null = null

function dispatch() {
  subscribers.forEach((cb) => {
    try {
      cb()
    } catch {
      // 单个订阅者异常不应影响其他订阅者
    }
  })
}

function ensureListener() {
  if (dispatchHandler || typeof window === 'undefined') return
  // 节流：resize 事件高频触发，限制为每 100ms 最多一次
  dispatchHandler = throttle(dispatch, 100)
  window.addEventListener('resize', dispatchHandler)
}

export function subscribeResize(cb: () => void): () => void {
  if (typeof window === 'undefined') return () => {}
  subscribers.add(cb)
  ensureListener()
  return () => {
    subscribers.delete(cb)
  }
}
