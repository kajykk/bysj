/**
 * R-E3: 风险趋势图 ECharts option 纯函数构建器.
 *
 * 从 RiskReportTab.vue 的 paintReportTrend（约 85 行）抽出，
 * 便于单测与复用；视觉令牌统一取自 @/utils/chartPalette。
 */

import { echarts } from '@/utils/echarts'
import { CHART_PALETTE, withAlpha } from '@/utils/chartPalette'
import { escapeHtml } from '@/utils/security'
import type { RiskTrend } from '@/api/modelApi'
import type { Composer } from 'vue-i18n'

type Translate = Composer['t']

interface TrendTooltipItem {
  dataIndex: number
  marker: string
  seriesName: string
  value: number | null
}

export function buildReportTrendOption(
  trend: RiskTrend,
  t: Translate,
): Record<string, unknown> {
  const points = Array.isArray(trend.points) ? trend.points : []
  const dates = points.map((p) => p.date)
  const valueOrNull = (value: number | null | undefined) =>
    typeof value === 'number' ? value : null

  const sourceLabelMap: Record<string, string> = {
    fusion: t('riskReport.sourceFusion'),
    structured: t('riskReport.sourceStructured'),
    text: t('riskReport.sourceText'),
    physiological: t('riskReport.sourcePhysiological'),
  }
  const riskLevelMap: Record<number, string> = {
    0: t('riskReport.chartRiskLevel0'),
    1: t('riskReport.chartRiskLevel1'),
    2: t('riskReport.chartRiskLevel2'),
    3: t('riskReport.chartRiskLevel3'),
    4: t('riskReport.chartRiskLevel4'),
  }

  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => {
        const items = Array.isArray(params)
          ? (params as TrendTooltipItem[])
          : []
        const point = points[items[0]?.dataIndex ?? 0]
        if (!point) return ''
        // OPT-P4-001：转义逻辑统一走 @/utils/security
        const safeDate = escapeHtml(point.date)
        const safeAssessmentType = escapeHtml(point.assessment_type)
        const safeRiskLevel = escapeHtml(point.risk_level)
        const safeRecordCount = escapeHtml(point.record_count ?? 1)
        const lines = [
          `<strong>${safeDate}</strong>`,
          `${t('riskReport.chartMainAssessment')}${sourceLabelMap[String(point.assessment_type || '')] || safeAssessmentType || t('riskReport.chartUnknown')}`,
          `${t('riskReport.chartRiskLevel')}${riskLevelMap[point.risk_level] || `${t('riskReport.chartLevelPrefix')}${safeRiskLevel}`}`,
          `${t('riskReport.chartDailyRecords')}${safeRecordCount} ${t('riskReport.chartRecordsUnit')}`,
        ]
        items.forEach((item) => {
          if (item.value !== null && item.value !== undefined) {
            lines.push(`${item.marker}${item.seriesName}：${Number(item.value).toFixed(2)}`)
          }
        })
        return lines.join('<br/>')
      },
    },
    legend: {
      top: 0,
      data: [
        t('riskReport.legendComprehensive'),
        t('riskReport.legendStructured'),
        t('riskReport.legendText'),
        t('riskReport.legendPhysiological'),
      ],
      textStyle: { fontSize: 11 },
    },
    grid: { left: 40, right: 20, top: 42, bottom: 30 },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { fontSize: 11 } },
    graphic: points.length
      ? []
      : [
          {
            type: 'text',
            left: 'center',
            top: 'middle',
            style: {
              text: t('riskReport.noTrendData'),
              fill: CHART_PALETTE.info,
              fontSize: 14,
            },
          },
        ],
    series: [
      {
        name: t('riskReport.legendComprehensive'),
        type: 'line',
        data: points.map((p) => p.risk_score),
        smooth: true,
        // VIS-P4-01：主色渐变/系列色统一取自 chartPalette
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: withAlpha(CHART_PALETTE.primary, 0.3) },
            { offset: 1, color: withAlpha(CHART_PALETTE.primary, 0.02) },
          ]),
        },
        lineStyle: { color: CHART_PALETTE.primary, width: 2 },
        itemStyle: { color: CHART_PALETTE.primary },
      },
      {
        name: t('riskReport.legendStructured'),
        type: 'line',
        data: points.map((p) => valueOrNull(p.structured_score)),
        smooth: true,
        connectNulls: true,
        lineStyle: { color: CHART_PALETTE.success, width: 1.8 },
        itemStyle: { color: CHART_PALETTE.success },
      },
      {
        name: t('riskReport.legendText'),
        type: 'line',
        data: points.map((p) => valueOrNull(p.text_score)),
        smooth: true,
        connectNulls: true,
        lineStyle: { color: CHART_PALETTE.warning, width: 1.8 },
        itemStyle: { color: CHART_PALETTE.warning },
      },
      {
        name: t('riskReport.legendPhysiological'),
        type: 'line',
        data: points.map((p) => valueOrNull(p.physiological_score)),
        smooth: true,
        connectNulls: true,
        lineStyle: { color: CHART_PALETTE.danger, width: 1.8 },
        itemStyle: { color: CHART_PALETTE.danger },
      },
    ],
  }
}
