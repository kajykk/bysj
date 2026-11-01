/**
 * 图表主题工具
 * ----------------------------------------------------------------
 * 从全局 CSS 设计令牌读取 ECharts 配色，确保图表与 App 整体视觉一致。
 *
 * 背景：此前 ModelPerformanceChart / SystemHealthChart 直接硬编码了旧主色
 * `#3b82c4`（I6 修复前的蓝），与 variables.scss 当前的品牌主色 `#2e6fa8`
 * 不一致，导致图表呈现“另一个蓝”。统一改为读取 --chart-color-* 令牌，
 * 回退值也同步为当前品牌色，SSR/首屏取不到变量时仍能正确渲染。
 *
 * UI-B4：chartPalette 降级为静态兜底；ECharts canvas 无法解析 CSS 变量，
 * 所以读取发生在客户端运行时。html.dark 类切换时通过 MutationObserver
 * 触发重新计算，让图表在明暗主题间保持同一套语义色。
 */
import { computed, ref } from 'vue'
import { CHART_PALETTE, withAlpha } from './chartPalette'

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
  const primary = readChartVar('--chart-color-primary', CHART_PALETTE.primary)
  const success = readChartVar('--chart-color-success', CHART_PALETTE.success)
  return {
    primary,
    success,
    warning: readChartVar('--chart-color-warning', CHART_PALETTE.warning),
    danger: readChartVar('--chart-color-danger', CHART_PALETTE.danger),
    info: readChartVar('--chart-color-info', CHART_PALETTE.info),
    primaryAreaStart: readChartVar('--chart-color-primary-area', withAlpha(primary, 0.25)),
    primaryAreaEnd: readChartVar('--chart-color-primary-area-end', withAlpha(primary, 0.04)),
    successAreaStart: withAlpha(success, 0.25),
    successAreaEnd: withAlpha(success, 0.04),
  }
}

/** 系列色板：token 优先，第 6 色无对应 token 时用静态兜底。 */
export function chartSeriesColors(): string[] {
  const c = chartColors()
  return [c.primary, c.success, c.warning, c.danger, c.info, CHART_PALETTE.primaryLight]
}

const themeVersion = ref(0)

if (typeof window !== 'undefined' && typeof MutationObserver !== 'undefined') {
  new MutationObserver(() => {
    themeVersion.value += 1
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
}

/** 明暗切换计数，供图表 option 的 computed 建立依赖。 */
export const chartThemeVersion = computed(() => themeVersion.value)

/** 响应主题切换的语义色板。 */
export function useChartColors() {
  return computed(() => {
    void themeVersion.value
    return chartColors()
  })
}

/** 响应主题切换的系列色板。 */
export function useChartSeriesColors() {
  return computed(() => {
    void themeVersion.value
    return chartSeriesColors()
  })
}

/**
 * ECharts 全局主题对象：坐标轴、图例、tooltip 与文字色都走设计令牌，
 * 避免 canvas 内出现与页面脱节的默认灰黑。
 */
export function chartEchartsTheme(): Record<string, unknown> {
  const textPrimary = readChartVar('--text-primary', '#2c3340')
  const textRegular = readChartVar('--text-regular', '#5a6470')
  const textSecondary = readChartVar('--text-secondary', '#6a727f')
  const surface = readChartVar('--surface-1', '#ffffff')
  const cardBorder = readChartVar('--card-border', '#e2e7ee')
  const border = readChartVar('--border-color', '#dcdfe6')

  const axis = {
    axisLabel: { color: textSecondary },
    axisLine: { lineStyle: { color: border } },
    axisTick: { lineStyle: { color: border } },
    splitLine: { lineStyle: { color: cardBorder } },
  }

  return {
    color: chartSeriesColors(),
    backgroundColor: 'transparent',
    textStyle: {
      color: textRegular,
      fontFamily: readChartVar('--font-family', 'system-ui, sans-serif'),
    },
    title: { textStyle: { color: textPrimary } },
    legend: { textStyle: { color: textRegular } },
    tooltip: {
      backgroundColor: surface,
      borderColor: cardBorder,
      borderWidth: 1,
      textStyle: { color: textPrimary },
    },
    categoryAxis: axis,
    valueAxis: axis,
    visualMap: { textStyle: { color: textSecondary } },
  }
}
