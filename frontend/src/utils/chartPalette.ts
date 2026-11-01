/**
 * 统一图表色板
 * ----------------------------------------------------------------
 * VIS-P4-01 修复：集中管理图表/数据可视化的基础色板，消除
 * UserDashboard/AdminDashboard/CounselorUsersPage/RiskTrendChart/BaseChart 等
 * 组件中重复硬编码的 hex（#2e6fa8/#5a9e3a/#d4923a/#d65a5a 等）。
 *
 * 色值与 variables.scss 中的 --chart-color-* / 语义色令牌保持一致，
 * 运行时仍优先通过 chartTheme.ts 读取 CSS 变量以支持深色模式，
 * 此处作为静态色值与渐变/光晕计算的唯一来源。
 *
 * 本文件是生产代码中唯一允许出现「静态色值镜像」的地方：
 * ECharts canvas 无法解析 CSS 变量，SSR/首屏也可能读不到计算样式，
 * 必须保留一份 hex 兜底。镜像是否漂移由 tokens.contract.test.ts 守护。
 */

/** 基础语义色板（与 variables.scss --chart-color-* 一一对应） */
export const CHART_PALETTE = {
  primary: '#2e6fa8',
  primaryLight: '#82a9cb',
  success: '#5a9e3a',
  warning: '#c07f26',
  danger: '#d65a5a',
  info: '#7a8290',
} as const

/** 标准系列色板（≤6 系列图表/列表着色使用） */
export const CHART_SERIES_COLORS: readonly string[] = [
  CHART_PALETTE.primary,
  CHART_PALETTE.success,
  CHART_PALETTE.warning,
  CHART_PALETTE.danger,
  CHART_PALETTE.info,
  CHART_PALETTE.primaryLight,
]

/** 扩展系列色板（>6 系列或头像着色等需要更多区分度的场景） */
export const EXTENDED_SERIES_COLORS: readonly string[] = [
  ...CHART_SERIES_COLORS,
  '#9254de',
  '#ff85c0',
]

/**
 * 非图表场景的静态兜底色（文字/表面/边框）。
 * 仅用于 getComputedStyle 取不到令牌的极端情况，值必须与浅色主题一致。
 */
export const STATIC_FALLBACK_COLORS = {
  textPrimary: '#2c3340',
  textRegular: '#5a6470',
  textSecondary: '#5a6470',
  surface1: '#ffffff',
  cardBorder: '#e2e7ee',
  borderColor: '#dce1e7',
} as const

/** 将 hex 颜色转为 rgba 字符串，供 ECharts 渐变/光晕等半透明场景使用 */
export function withAlpha(hex: string, alpha: number): string {
  const normalized = hex.replace('#', '')
  const full =
    normalized.length === 3
      ? normalized
          .split('')
          .map((c) => c + c)
          .join('')
      : normalized
  const r = parseInt(full.slice(0, 2), 16)
  const g = parseInt(full.slice(2, 4), 16)
  const b = parseInt(full.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}
