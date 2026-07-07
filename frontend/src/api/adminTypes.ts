export interface TemplateTaskItem {
  task_name: string
  task_type: string
  description?: string | null
  schedule?: 'daily' | 'weekly' | 'monthly' | 'once' | 'manual' | null
  duration_minutes?: number | null
  sort_order?: number | null
  [key: string]: unknown
}

export interface TemplateItem {
  id: number
  template_name: string
  applicable_levels: number[]
  task_list: TemplateTaskItem[]
  estimated_weeks: number | null
  status: string
}

export interface ThresholdItem {
  id: number
  level: number
  level_name: string
  min_score: number
  max_score: number
  color: string
  action_required: string
}

export interface ConfigItem {
  id: number
  config_key: string
  config_value: Record<string, unknown>
  description: string | null
  updated_by: number | null
}

export interface OperationLogItem {
  id: number
  operator_id: number
  operator_role: string
  action_type: string
  target_type: string
  target_id: number | null
  detail: string | null
  ip_address: string | null
  created_at: string | null
}

export interface ModelFeedbackItem {
  id: number
  counselor_id: number
  user_id: number
  assessment_id: number
  agreed: boolean
  reason: string | null
  created_at: string
}

export interface CrisisEventItem {
  id: number
  user_id: number
  report_id: number | null
  trigger_source: string
  crisis_keywords: string[]
  crisis_score: number | null
  input_summary: string | null
  review_task_id: number | null
  status: string
  handled_by: number | null
  handled_action: string | null
  created_at: string
  handled_at: string | null
}
