import { describe, expect, it } from 'vitest'
import {
  featureLabel,
  severityLabel,
  severityFromLevel,
  modalityLabel,
  routeFamilyLabel,
  routeReasonLabel,
  confidenceLabel,
  getFactorDirectionLabel,
  formatArrayText,
  getRiskScoreColor,
  RISK_SCORE_COLORS,
} from '@/utils/riskFormatters'

describe('riskFormatters', () => {
  describe('featureLabel', () => {
    it('结构化特征 snake_case 转 camelCase 命中词条', () => {
      expect(featureLabel('academic_pressure')).toBe('学业压力')
      expect(featureLabel('sleep_duration')).toBe('睡眠时长')
    })

    it('model_disagreement_{n}_points 归一化为 modelDisagreement', () => {
      expect(featureLabel('model_disagreement_43_points')).toBe('模型评分分歧较大')
    })

    it('low_confidence_high_risk_{modality} 归一化为 lowConfidenceHighRisk', () => {
      expect(featureLabel('low_confidence_high_risk_text')).toBe('低置信度高风险评估')
      expect(featureLabel('low_confidence_high_risk_physiological')).toBe('低置信度高风险评估')
    })

    it('single_modality_high_risk 命中词条', () => {
      expect(featureLabel('single_modality_high_risk')).toBe('单一模态高风险，建议人工复核')
    })

    it('中文直通：后端直接下发中文名时不走 i18n', () => {
      expect(featureLabel('持续焦虑')).toBe('持续焦虑')
    })

    it('未知 key 回退原文', () => {
      expect(featureLabel('weird_new_feature')).toBe('weird_new_feature')
    })
  })

  describe('routeReasonLabel', () => {
    it('后端实际下发的 routing_reason 全部命中词条', () => {
      expect(routeReasonLabel('feature_coverage_sufficient')).toBe('特征覆盖充足，使用完整结构化模型')
      expect(routeReasonLabel('feature_coverage_insufficient_text_available')).toBe('结构化特征不足，使用 GAD-7 + 文本轻量模型')
      expect(routeReasonLabel('only_gad7_available')).toBe('仅 GAD-7 可用，使用焦虑经验映射')
      expect(routeReasonLabel('insufficient_information')).toBe('数据不足，无法生成风险预测')
    })

    it('空值回退空串', () => {
      expect(routeReasonLabel(null)).toBe('')
      expect(routeReasonLabel(undefined)).toBe('')
    })

    it('未知 reason 回退原文', () => {
      expect(routeReasonLabel('some_future_reason')).toBe('some_future_reason')
    })
  })

  describe('severity', () => {
    it('severityLabel 空值回退 unknown', () => {
      expect(severityLabel(null)).toBe('未知')
      expect(severityLabel(undefined)).toBe('未知')
    })

    it('severityFromLevel 映射等级，越界回退 unknown', () => {
      expect(severityFromLevel(3)).toBe('较高')
      expect(severityFromLevel(-1)).toBe('未知')
      expect(severityFromLevel(99)).toBe('未知')
    })
  })

  describe('其他标签函数', () => {
    it('routeFamilyLabel', () => {
      expect(routeFamilyLabel('anxiety_only')).toBe('仅焦虑评估')
      expect(routeFamilyLabel(null)).toBe('未知路由')
    })

    it('confidenceLabel', () => {
      expect(confidenceLabel('high')).toBe('高置信度')
      expect(confidenceLabel(null)).toBe('未知置信度')
    })

    it('getFactorDirectionLabel', () => {
      expect(getFactorDirectionLabel('decrease')).toBe('风险下降')
      expect(getFactorDirectionLabel(undefined)).toBe('未知')
    })

    it('modalityLabel', () => {
      expect(modalityLabel('structured')).toBe('结构化')
    })

    it('formatArrayText', () => {
      expect(formatArrayText([])).toBe('暂无')
      expect(formatArrayText(['a', 'b'])).toBe('a, b')
      expect(formatArrayText(['a', 'b'], '、')).toBe('a、b')
    })
  })

  describe('getRiskScoreColor', () => {
    it('阈值边界', () => {
      expect(getRiskScoreColor(0)).toBe(RISK_SCORE_COLORS.low)
      expect(getRiskScoreColor(20)).toBe(RISK_SCORE_COLORS.low)
      expect(getRiskScoreColor(21)).toBe(RISK_SCORE_COLORS.mild)
      expect(getRiskScoreColor(40)).toBe(RISK_SCORE_COLORS.mild)
      expect(getRiskScoreColor(41)).toBe(RISK_SCORE_COLORS.moderate)
      expect(getRiskScoreColor(80)).toBe(RISK_SCORE_COLORS.high)
    })
  })
})