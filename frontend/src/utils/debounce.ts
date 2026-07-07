import { ref, watch, type Ref } from 'vue'

/**
 * 防抖函数：延迟 delay 毫秒后执行，期间再次调用会重置计时器
 */
export function debounce<T extends (...args: never[]) => void>(fn: T, delay = 300): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout> | null = null
  return (...args: Parameters<T>) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => fn(...args), delay)
  }
}

/**
 * 节流函数：每 delay 毫秒最多执行一次
 */
export function throttle<T extends (...args: never[]) => void>(fn: T, delay = 100): (...args: Parameters<T>) => void {
  let lastTime = 0
  let timer: ReturnType<typeof setTimeout> | null = null
  return (...args: Parameters<T>) => {
    const now = Date.now()
    const remaining = delay - (now - lastTime)
    if (remaining <= 0) {
      if (timer) { clearTimeout(timer); timer = null }
      lastTime = now
      fn(...args)
    } else if (!timer) {
      timer = setTimeout(() => {
        lastTime = Date.now()
        timer = null
        fn(...args)
      }, remaining)
    }
  }
}

/**
 * 创建防抖的 ref（用于 v-model 实时绑定的搜索框）
 */
export function refDebounced<T>(source: Ref<T>, delay = 300): Ref<T> {
  const debounced = ref(source.value) as Ref<T>
  let timer: ReturnType<typeof setTimeout> | null = null
  watch(source, (val) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      debounced.value = val
    }, delay)
  })
  return debounced
}
