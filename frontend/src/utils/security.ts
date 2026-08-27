/**
 * HTML 转义工具（图表 tooltip / 动态插值安全）。
 * OPT-P4-001：原实现在 sharedDashboardUtils 与 RiskReportTab 各维护一份，
 * 收敛到 @/utils 统一引用，避免双份漂移。
 */
export const escapeHtml = (value: unknown): string => {
  if (value === null || value === undefined) return ''
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}
