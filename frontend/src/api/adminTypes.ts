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

/** AUDIT-2026-10-01（决策三 P2）：/admin/audit-logs 的合规统计块（GDPR/等保 2.0 场景） */
export interface AuditCompliance {
  /** 按当前筛选条件聚合的 action_type 计数 */
  action_breakdown: Record<string, number>
  earliest_log: string | null
  latest_log: string | null
  /** 与后端 archive_logs 的保留策略一致 */
  retention_days: number
}

/**
 * GET /admin/audit-logs 响应 data。
 * 注意：与标准分页结构不同，多出 compliance 块——因此不用 requestPageData（会丢弃附加字段），
 * 走 requestData 取完整结构。
 */
export interface AuditLogsResult {
  items: OperationLogItem[]
  total: number
  page: number
  page_size: number
  compliance: AuditCompliance
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
