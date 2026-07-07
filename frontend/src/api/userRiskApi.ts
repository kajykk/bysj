import request, { requestData } from './request'
import type { AssessmentRecordItem } from './userTypes'

export interface ReportFactor {
  feature: string
  importance: number
  direction?: string
  type?: string
}

export interface RiskReport {
  risk_level: number
  risk_score: number
  severity: string
  trend: 'up' | 'down' | 'stable'
  main_factors: ReportFactor[]
  advice: string[]
  assessed_at: string | null
  physiological_score?: number | null
  modality_contributions?: {
    structured?: number | null
    text?: number | null
    physiological?: number | null
  }
  review_required?: boolean
  review_triggers?: string[]
  review_flags?: ReportFactor[]
  crisis_override?: boolean
  risk_factors?: ReportFactor[]
  protective_factors?: ReportFactor[]
}

export interface RiskTrendPoint {
  date: string
  risk_score: number
  risk_level: number
  assessment_type?: string | null
  structured_score?: number | null
  text_score?: number | null
  physiological_score?: number | null
  record_count?: number
}

export interface RiskTrend {
  days: number
  direction: 'up' | 'down' | 'stable'
  points: RiskTrendPoint[]
  physiological_scores?: { date: string; score: number }[]
}

export interface StructuredCollectResult {
  assessment_id: number
  risk_score: number
  risk_level: number
  severity: string
  risk_factors: { feature: string; importance: number; direction: string }[]
  warning_generated: boolean
  warning_id: number | null
}

export interface TextAnalyzeResult {
  entry_id: number
  sentiment_score: number
  sentiment_label: string
}

export interface TextPredictModelResult {
  prediction: number
  probability: number
  sentiment_label: string
  sentiment_score: number
  model_used: string
}

export interface ActiveIntervention {
  plan: {
    id: number | null
    plan_name: string
    risk_level: number
    start_date: string | null
    progress: number
    dominant_modality?: string | null
  }
  tasks: {
    id: number
    task_name: string
    task_type: string
    description: string
    schedule: string
    duration_minutes: number
    today_status: 'pending' | 'completed' | 'missed' | 'skipped' | 'postponed'
    feedback_score: number | null
    feedback_note: string | null
    modality_based_actions?: string[]
  }[]
}

export interface InterventionHistoryItem {
  plan_id: number
  plan_name: string
  status: string
  start_date: string
  end_date: string | null
  completion_rate: number
  risk_change: unknown
  dominant_modality?: string | null
}

export const userRiskApi = {
  getRiskReport: () => requestData<RiskReport>(request.get('/user/risk/report')),
  getRiskTrend: (days = 30) => requestData<RiskTrend>(request.get('/user/risk/trend', { params: { days } })),
  collectStructuredData: (payload: { assessment_type: string; data_payload: Record<string, number | string> }) =>
    requestData<StructuredCollectResult>(request.post('/user/data/collect', payload)),
  analyzeText: (payload: { entry_type: string; content: string; emotion_tags?: string[]; mood_score?: number }) =>
    requestData<TextAnalyzeResult>(request.post('/user/data/text/analyze', payload)),
  recordPhysiological: (payload: Record<string, unknown>) => requestData<{ record_id: number }>(request.post('/user/data/physiological/record', payload)),
  predictTextModel: (text: string) => requestData<TextPredictModelResult>(request.post('/model/predict/text', { text })),
  getAssessmentDetail: (id: number) => requestData<AssessmentRecordItem>(request.get(`/user/risk/assessments/${id}`)),
}
