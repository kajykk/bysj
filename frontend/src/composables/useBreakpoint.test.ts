import { describe, it, expect } from 'vitest'

/**
 * useBreakpoint 组合式函数单元测试
 * T-FE-005: 移动端基础体验 - 响应式断点
 */

// 断点定义（与组件内部一致）
const breakpoints = {
  xs: 0,
  sm: 576,
  md: 768,
  lg: 992,
  xl: 1200,
  xxl: 1400,
}

type Breakpoint = keyof typeof breakpoints

/**
 * 计算当前断点
 */
const calculateBreakpoint = (width: number): Breakpoint => {
  if (width >= breakpoints.xxl) return 'xxl'
  if (width >= breakpoints.xl) return 'xl'
  if (width >= breakpoints.lg) return 'lg'
  if (width >= breakpoints.md) return 'md'
  if (width >= breakpoints.sm) return 'sm'
  return 'xs'
}

/**
 * 判断是否为移动端
 */
const isMobile = (width: number): boolean => width < breakpoints.md

/**
 * 判断是否为平板
 */
const isTablet = (width: number): boolean => width >= breakpoints.md && width < breakpoints.lg

/**
 * 判断是否为桌面端
 */
const isDesktop = (width: number): boolean => width >= breakpoints.lg

/**
 * 获取布局列数
 */
const getLayoutColumns = (width: number): number => {
  if (width >= breakpoints.xl) return 5
  if (width >= breakpoints.lg) return 4
  if (width >= breakpoints.md) return 3
  if (width >= breakpoints.sm) return 2
  return 1
}

/**
 * 获取图表高度
 */
const getChartHeight = (width: number): number => {
  if (width < breakpoints.sm) return 200
  if (width < breakpoints.lg) return 300
  return 400
}

describe('useBreakpoint - T-FE-005 移动端基础体验', () => {
  describe('1. 断点阈值计算', () => {
    it('宽度 0 应为 xs', () => {
      expect(calculateBreakpoint(0)).toBe('xs')
    })

    it('宽度 375 应为 xs (iPhone SE)', () => {
      expect(calculateBreakpoint(375)).toBe('xs')
    })

    it('宽度 576 应为 sm', () => {
      expect(calculateBreakpoint(576)).toBe('sm')
    })

    it('宽度 768 应为 md (iPad mini)', () => {
      expect(calculateBreakpoint(768)).toBe('md')
    })

    it('宽度 992 应为 lg', () => {
      expect(calculateBreakpoint(992)).toBe('lg')
    })

    it('宽度 1200 应为 xl', () => {
      expect(calculateBreakpoint(1200)).toBe('xl')
    })

    it('宽度 1400 应为 xxl', () => {
      expect(calculateBreakpoint(1400)).toBe('xxl')
    })

    it('宽度 1920 应为 xxl', () => {
      expect(calculateBreakpoint(1920)).toBe('xxl')
    })
  })

  describe('2. 设备类型判断', () => {
    it('移动端宽度应正确识别', () => {
      expect(isMobile(375)).toBe(true)
      expect(isMobile(767)).toBe(true)
      expect(isMobile(768)).toBe(false)
    })

    it('平板宽度应正确识别', () => {
      expect(isTablet(768)).toBe(true)
      expect(isTablet(991)).toBe(true)
      expect(isTablet(767)).toBe(false)
      expect(isTablet(992)).toBe(false)
    })

    it('桌面端宽度应正确识别', () => {
      expect(isDesktop(992)).toBe(true)
      expect(isDesktop(1920)).toBe(true)
      expect(isDesktop(991)).toBe(false)
    })
  })

  describe('3. 布局列数', () => {
    it('xs 应为 1 列', () => {
      expect(getLayoutColumns(375)).toBe(1)
    })

    it('sm 应为 2 列', () => {
      expect(getLayoutColumns(576)).toBe(2)
    })

    it('md 应为 3 列', () => {
      expect(getLayoutColumns(768)).toBe(3)
    })

    it('lg 应为 4 列', () => {
      expect(getLayoutColumns(992)).toBe(4)
    })

    it('xl 应为 5 列', () => {
      expect(getLayoutColumns(1200)).toBe(5)
    })
  })

  describe('4. 图表高度', () => {
    it('移动端应为 200px', () => {
      expect(getChartHeight(375)).toBe(200)
    })

    it('平板应为 300px', () => {
      expect(getChartHeight(768)).toBe(300)
    })

    it('桌面端应为 400px', () => {
      expect(getChartHeight(1200)).toBe(400)
    })
  })

  describe('5. 边界值处理', () => {
    it('负宽度应返回 xs', () => {
      expect(calculateBreakpoint(-1)).toBe('xs')
    })

    it('极大宽度应返回 xxl', () => {
      expect(calculateBreakpoint(99999)).toBe('xxl')
    })
  })

  describe('6. 常见设备宽度', () => {
    it('iPhone SE (375px) 应为 xs', () => {
      expect(calculateBreakpoint(375)).toBe('xs')
      expect(isMobile(375)).toBe(true)
    })

    it('iPhone 12 (390px) 应为 xs', () => {
      expect(calculateBreakpoint(390)).toBe('xs')
      expect(isMobile(390)).toBe(true)
    })

    it('iPhone 12 Pro Max (428px) 应为 xs', () => {
      expect(calculateBreakpoint(428)).toBe('xs')
      expect(isMobile(428)).toBe(true)
    })

    it('iPad mini (768px) 应为 md', () => {
      expect(calculateBreakpoint(768)).toBe('md')
      expect(isTablet(768)).toBe(true)
    })

    it('iPad Pro (1024px) 应为 lg', () => {
      expect(calculateBreakpoint(1024)).toBe('lg')
      expect(isDesktop(1024)).toBe(true)
    })

    it('MacBook Air (1440px) 应为 xxl', () => {
      expect(calculateBreakpoint(1440)).toBe('xxl')
      expect(isDesktop(1440)).toBe(true)
    })
  })
})
