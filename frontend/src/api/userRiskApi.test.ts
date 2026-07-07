import { beforeEach, describe, expect, it, vi } from 'vitest'

// 模拟 request 模块以隔离测试 userRiskApi
vi.mock('./request', () => ({
  default: {
    get: vi.fn((url: string, config?: unknown) => Promise.resolve({ url, config })),
    post: vi.fn((url: string, data?: unknown, config?: unknown) => Promise.resolve({ url, data, config })),
    put: vi.fn((url: string, data?: unknown, config?: unknown) => Promise.resolve({ url, data, config })),
    delete: vi.fn((url: string, config?: unknown) => Promise.resolve({ url, config }))
  },
  requestData: vi.fn(async (promise: Promise<{ data: unknown }>) => {
    const response = await promise
    return response.data
  }),
  requestPageData: vi.fn(async (promise: Promise<{ data: unknown }>) => {
    const response = await promise
    return response.data
  })
}))

import request, { requestData } from './request'
import { userRiskApi } from './userRiskApi'

describe('api/userRiskApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('getRiskReport', () => {
    it('调用 GET /user/risk/report', async () => {
      const report = {
        risk_level: 2,
        risk_score: 55.5,
        severity: 'moderate',
        trend: 'up',
        main_factors: [],
        advice: ['rest'],
        assessed_at: '2026-06-29T00:00:00Z'
      }
      ;(requestData as any).mockResolvedValueOnce(report)
      const res = await userRiskApi.getRiskReport()
      expect(request.get).toHaveBeenCalledWith('/user/risk/report')
      expect(res).toEqual(report)
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('500'))
      await expect(userRiskApi.getRiskReport()).rejects.toThrow('500')
    })
  })

  describe('getRiskTrend', () => {
    it('默认 days=30 调用 GET /user/risk/trend', async () => {
      (requestData as any).mockResolvedValueOnce({ days: 30, direction: 'stable', points: [] })
      await userRiskApi.getRiskTrend()
      expect(request.get).toHaveBeenCalledWith('/user/risk/trend', { params: { days: 30 } })
    })

    it('显式传入 days 覆盖默认值', async () => {
      (requestData as any).mockResolvedValueOnce({ days: 90, direction: 'up', points: [] })
      await userRiskApi.getRiskTrend(90)
      expect(request.get).toHaveBeenCalledWith('/user/risk/trend', { params: { days: 90 } })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('500'))
      await expect(userRiskApi.getRiskTrend()).rejects.toThrow('500')
    })
  })

  describe('collectStructuredData', () => {
    it('通过 POST /user/data/collect 提交结构化数据', async () => {
      const expected = {
        assessment_id: 12,
        risk_score: 70,
        risk_level: 3,
        severity: 'high',
        risk_factors: [],
        warning_generated: false,
        warning_id: null
      }
      ;(requestData as any).mockResolvedValueOnce(expected)
      const res = await userRiskApi.collectStructuredData({
        assessment_type: 'phq9',
        data_payload: { q1: 3, q2: 2 }
      })

      expect(request.post).toHaveBeenCalledWith('/user/data/collect', {
        assessment_type: 'phq9',
        data_payload: { q1: 3, q2: 2 }
      })
      expect(res).toEqual(expected)
    })

    it('空 data_payload', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await userRiskApi.collectStructuredData({ assessment_type: 'gad7', data_payload: {} })
      expect(request.post).toHaveBeenCalledWith('/user/data/collect', {
        assessment_type: 'gad7',
        data_payload: {}
      })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('422'))
      await expect(
        userRiskApi.collectStructuredData({ assessment_type: 'x', data_payload: {} })
      ).rejects.toThrow('422')
    })
  })

  describe('analyzeText', () => {
    it('通过 POST /user/data/text/analyze 提交文本分析', async () => {
      const expected = { entry_id: 5, sentiment_score: -0.6, sentiment_label: 'negative' }
      ;(requestData as any).mockResolvedValueOnce(expected)
      const res = await userRiskApi.analyzeText({
        entry_type: 'journal',
        content: '今天心情不好',
        emotion_tags: ['sad'],
        mood_score: 3
      })

      expect(request.post).toHaveBeenCalledWith('/user/data/text/analyze', {
        entry_type: 'journal',
        content: '今天心情不好',
        emotion_tags: ['sad'],
        mood_score: 3
      })
      expect(res).toEqual(expected)
    })

    it('仅必填字段时其他为 undefined', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await userRiskApi.analyzeText({ entry_type: 'journal', content: 'x' })
      expect(request.post).toHaveBeenCalledWith('/user/data/text/analyze', {
        entry_type: 'journal',
        content: 'x',
        emotion_tags: undefined,
        mood_score: undefined
      })
    })

    it('空字符串 content', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await userRiskApi.analyzeText({ entry_type: 'journal', content: '' })
      expect(request.post).toHaveBeenCalledWith('/user/data/text/analyze', {
        entry_type: 'journal',
        content: '',
        emotion_tags: undefined,
        mood_score: undefined
      })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('500'))
      await expect(
        userRiskApi.analyzeText({ entry_type: 'journal', content: 'x' })
      ).rejects.toThrow('500')
    })
  })

  describe('recordPhysiological', () => {
    it('通过 POST /user/data/physiological/record 记录生理数据', async () => {
      (requestData as any).mockResolvedValueOnce({ record_id: 42 })
      const res = await userRiskApi.recordPhysiological({ heart_rate: 80, hrv: 50 })
      expect(request.post).toHaveBeenCalledWith('/user/data/physiological/record', {
        heart_rate: 80,
        hrv: 50
      })
      expect(res).toEqual({ record_id: 42 })
    })

    it('空对象 payload', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await userRiskApi.recordPhysiological({})
      expect(request.post).toHaveBeenCalledWith('/user/data/physiological/record', {})
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('422'))
      await expect(userRiskApi.recordPhysiological({})).rejects.toThrow('422')
    })
  })

  describe('predictTextModel', () => {
    it('通过 POST /model/predict/text 提交模型预测', async () => {
      const expected = {
        prediction: 1,
        probability: 0.78,
        sentiment_label: 'negative',
        sentiment_score: -0.5,
        model_used: 'bert'
      }
      ;(requestData as any).mockResolvedValueOnce(expected)
      const res = await userRiskApi.predictTextModel('我感觉很差')

      expect(request.post).toHaveBeenCalledWith('/model/predict/text', { text: '我感觉很差' })
      expect(res).toEqual(expected)
    })

    it('空字符串 text', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await userRiskApi.predictTextModel('')
      expect(request.post).toHaveBeenCalledWith('/model/predict/text', { text: '' })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('503'))
      await expect(userRiskApi.predictTextModel('x')).rejects.toThrow('503')
    })
  })

  describe('getAssessmentDetail', () => {
    it('调用 GET /user/risk/assessments/:id', async () => {
      (requestData as any).mockResolvedValueOnce({ id: 7, score: 50 })
      await userRiskApi.getAssessmentDetail(7)
      expect(request.get).toHaveBeenCalledWith('/user/risk/assessments/7')
    })

    it('id=0 时路径仍按规则拼接', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await userRiskApi.getAssessmentDetail(0)
      expect(request.get).toHaveBeenCalledWith('/user/risk/assessments/0')
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('404'))
      await expect(userRiskApi.getAssessmentDetail(99)).rejects.toThrow('404')
    })
  })
})
