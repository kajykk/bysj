/**
 * 图表主题工具
 * ----------------------------------------------------------------
 * 从全局 CSS 设计令牌读取 ECharts 配色，确保图表与 App 整体视觉一致。
 *
 * 背景：此前 ModelPerformanceChart / SystemHealthChart 直接硬编码了旧主色
 * `#3b82c4`（I6 修复前的蓝），与 variables.scss 当前的品牌主色 `#2e6fa8`
 * 不一致，导致图表呈现“另一个蓝”。统一改为读取 --chart-color-* 令牌，
 * 回退值也同步为当前品牌色，SSR/首屏取不到变量时仍能正确渲染。
 */

/** 读取 CSS 变量；取不到时回退到传入的安全值。 */
export function readChartVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

export interface ChartColors {
  primary: string
  success: string
  warning: string
  danger: string
  info: string
  /** 主色面积图渐变起止 */
  primaryAreaStart: string
  primaryAreaEnd: string
  /** 成功色面积图渐变起止 */
  successAreaStart: string
  successAreaEnd: string
}

/**
 * 解析后的图表色板。必须在客户端（window 存在）调用，
 * 因为 ECharts canvas 无法识别 CSS 变量字符串，必须传入实际颜色值。
 */
export function chartColors(): ChartColors {
  return {
    primary: readChartVar('--chart-color-primary', '#2e6fa8'),
    success: readChartVar('--chart-color-success', '#5a9e3a'),
    warning: readChartVar('--chart-color-warning', '#d4923a'),
    danger: readChartVar('--chart-color-danger', '#d65a5a'),
    info: readChartVar('--chart-color-info', '#7a8290'),
    primaryAreaStart: readChartVar('--chart-color-primary-area', 'rgba(46, 111, 168, 0.25)'),
    primaryAreaEnd: readChartVar('--chart-color-primary-area-end', 'rgba(46, 111, 168, 0.04)'),
    successAreaStart: 'rgba(90, 158, 58, 0.25)',
    successAreaEnd: 'rgba(90, 158, 58, 0.04)',
  }
}
