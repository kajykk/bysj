import { ref, computed, onMounted, onUnmounted } from 'vue'
import { subscribeResize } from '@/utils/sharedResize'

export type Breakpoint = 'xs' | 'sm' | 'md' | 'lg' | 'xl' | 'xxl'

// ISS-026 修复：校准断点数值，与 variables.scss 中的 $breakpoint-* 令牌保持一致
// 计划要求六档断点：375/390/768/1024/1366/1920
// 映射说明：xs 为默认档（< sm）；sm=375（小屏手机起）；md=768（平板起，确保 isMobile=width<md 涵盖所有手机）；
// lg=1024（小屏桌面起）；xl=1366（桌面起）；xxl=1920（大屏桌面起）。390 在 SCSS 令牌中保留作为设备参考宽度。
const breakpoints: Record<Breakpoint, number> = {
  xs: 0,
  sm: 375,
  md: 768,
  lg: 1024,
  xl: 1366,
  xxl: 1920
}

export function useBreakpoint() {
  const width = ref(typeof window !== 'undefined' ? window.innerWidth : 0)

  const updateWidth = () => {
    if (typeof window !== 'undefined') {
      width.value = window.innerWidth
    }
  }

  // L-FE-2 修复：使用共享 resize 监听，避免每个组件实例独立注册
  let unsubscribe: (() => void) | null = null

  onMounted(() => {
    unsubscribe = subscribeResize(updateWidth)
  })

  onUnmounted(() => {
    unsubscribe?.()
  })

  const current = computed<Breakpoint>(() => {
    if (width.value >= breakpoints.xxl) return 'xxl'
    if (width.value >= breakpoints.xl) return 'xl'
    if (width.value >= breakpoints.lg) return 'lg'
    if (width.value >= breakpoints.md) return 'md'
    if (width.value >= breakpoints.sm) return 'sm'
    return 'xs'
  })

  const isMobile = computed(() => width.value < breakpoints.md)
  const isTablet = computed(() => width.value >= breakpoints.md && width.value < breakpoints.lg)
  const isDesktop = computed(() => width.value >= breakpoints.lg)

  return {
    width,
    current,
    isMobile,
    isTablet,
    isDesktop
  }
}
