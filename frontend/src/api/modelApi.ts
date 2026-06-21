import request, { requestData } from './request'
import type { RiskReport, RiskTrend, TextPredictModelResult } from './userRiskApi'

export type { RiskReport, RiskTrend, TextPredictModelResult }

export interface RoutingInfo {
  selected_model_id: string | null
  selected_model_family: string | null
  routing_reason: string | null
  feature_coverage_ratio: number | null
  prediction_confidence_band: string | null
}

export interface DataQualityInfo {
  missing_fields: string[]
  confidence_penalty: number
  quality_level: 'complete' | 'partial' | 'poor'
}

export interface ModelPredictResponse {
  prediction?: number | null
  probability?: number | null
  risk_score?: number | null
  risk_level?: number | null
  model_used?: string | null
  model_version?: string | null
  model_family?: string | null
  fallback_used?: boolean
  fallback_reason?: string | null
  safety_flags: string[]
  requires_human_review: boolean
  crisis_keywords_matched: string[]
  data_quality?: DataQualityInfo | null
  routing_info?: RoutingInfo | null
  warning?: string | null
  experimental_real_score?: number | null
  experimental_real_level?: number | null
  experimental_real_probability?: number | null
  experimental_real_model?: string | null
  experimental_external_score?: number | null
  experimental_external_level?: number | null
  experimental_external_model?: string | null
  experimental_external_available?: boolean
  experimental_external_delta?: number | null
  adjusted_score?: number | null
  adjusted_delta?: number | null
  adjusted_safe_label?: string | null
  adapter_available?: boolean
  adapter_version?: string | null
  v123_raw_score?: number | null
}

export interface ModelStatusItem {
  model_id: string
  path: string
  exists: boolean
  size_kb: number | null
  modified_at: number | null
  lifecycle?: string
}

export interface ModelStatusResult {
  model_dir: string
  items: ModelStatusItem[]
  ready: boolean
}

export interface FusionDetailItem {
  modality_scores: Record<string, { score: number; model: string }>
  weights: { weighted: number; attention: number }
  gate_weights: number[]
  keras_fusion?: number | null
}

export interface FusionPredictRequest {
  features?: Record<string, number | string | boolean>
  text?: string
  physiological?: Record<string, unknown>
}

export interface FusionPredictResult {
  risk_score: number
  risk_level: number
  severity: string
  model_used: string[]
  fusion_detail: FusionDetailItem
  intervention_level: string
  intervention_actions: string[]
  review_required: boolean
  review_triggers: string[]
  crisis_override: boolean
  model_version: string
  risk_factors?: string[]
  protective_factors?: string[]
}

export interface DatasetImportResult {
  dataset_name: string
  source_type: string
  total_samples: number
  splits: { train: number; validation: number; test: number }
  message: string
}

export interface TrainResult {
  job_id?: string
  dataset_name?: string
  model_name?: string
  status: string
  progress?: number
  stage?: string
  message: string
  epochs?: number
  batch_size?: number
  learning_rate?: number
  train_loss?: number[]
  val_loss?: number[]
  val_accuracy?: number[]
  train_history?: { epoch: number; train_loss: number; val_loss: number; val_accuracy: number }[]
  trainer_state?: Record<string, unknown>
  trainer_log_history?: Record<string, unknown>[]
  eval_history?: Record<string, unknown>[]
  eval_result?: Record<string, unknown>
}

export interface EvaluateResult {
  dataset_name: string
  model_name: string
  split: string
  metrics: { accuracy: number; precision: number; recall: number; f1: number; auc: number }
  confusion_matrix: { tn: number; fp: number; fn: number; tp: number }
  prediction_samples: { index: number; true_label: number; pred_label: number; score: number }[]
  eval_history?: { split: string; sample_count: number; accuracy: number; precision: number; recall: number; f1: number; auc: number; confusion_matrix: { tn: number; fp: number; fn: number; tp: number }; prediction_preview: { index: number; true_label: number; pred_label: number; score: number }[] }[]
  message: string
}

export interface CompareResult {
  dataset_name: string
  results: { model_name: string; accuracy: number; precision: number; recall: number; f1: number; auc: number }[]
  message: string
}

export const modelApi = {
  getRiskReport: () => requestData<RiskReport>(request.get('/user/risk/report')),
  getRiskTrend: (days = 30) => requestData<RiskTrend>(request.get('/user/risk/trend', { params: { days } })),
  getModelStatus: () => requestData<ModelStatusResult>(request.get('/model/status')),
  predictTabularModel: (features: Record<string, number | string | boolean>) =>
    requestData<ModelPredictResponse>(request.post('/model/predict/tabular', { features })),
  predictTextModel: (text: string) => requestData<TextPredictModelResult>(request.post('/model/predict/text', { text })),
  predictFusionModel: (payload: FusionPredictRequest) => requestData<FusionPredictResult>(request.post('/model/predict/fusion', payload)),
  importDataset: (payload: { dataset_name: string; source_type?: string; train_ratio?: number; val_ratio?: number; test_ratio?: number }) =>
    requestData<DatasetImportResult>(request.post('/model/experiment/import', payload)),
  trainModel: (payload: { dataset_name: string; model_name: string; epochs?: number; batch_size?: number; learning_rate?: number }) =>
    requestData<TrainResult>(request.post('/model/experiment/train', payload)),
  getTrainingJobs: () => requestData<{ jobs: TrainResult[] }>(request.get('/model/training/jobs')),
  getTrainingJob: (jobId: string) => requestData<TrainResult>(request.get(`/model/training/jobs/${jobId}`)),
  evaluateModel: (payload: { dataset_name: string; model_name: string; split?: 'validation' | 'test' }) =>
    requestData<EvaluateResult>(request.post('/model/experiment/evaluate', payload)),
  compareModels: (payload: { dataset_name: string; model_names: string[] }) =>
    requestData<CompareResult>(request.post('/model/experiment/compare', payload)),
}
