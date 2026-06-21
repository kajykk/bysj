import { ref, computed, onMounted, onUnmounted } from 'vue'

export type Breakpoint = 'xs' | 'sm' | 'md' | 'lg' | 'xl' | 'xxl'

const breakpoints: Record<Breakpoint, number> = {
  xs: 0,
  sm: 576,
  md: 768,
  lg: 992,
  xl: 1200,
  xxl: 1400
}

export function useBreakpoint() {
  const width = ref(window.innerWidth)

  const updateWidth = () => {
    width.value = window.innerWidth
  }

  onMounted(() => {
    window.addEventListener('resize', updateWidth)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', updateWidth)
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
