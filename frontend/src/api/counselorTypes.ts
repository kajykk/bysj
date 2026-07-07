import type { UserStatus, RiskLevel, WarningStatus } from '@/types/contracts'
import type { UserBindingInfo, WarningItem } from './userTypes'

export interface UserManageItem {
  id: number
  username: string
  nickname?: string
  email?: string
  role?: string
  status?: UserStatus
  risk_level?: RiskLevel | number | null
  risk_score?: number | null
  latest_risk_level?: RiskLevel | number | null
  latest_risk_score?: number | null
  latest_risk_label?: RiskLevel | 'none' | 'critical' | null
  // ISS-057: 后端 get_user_detail 返回的关联数据
  risk_history?: UserRiskHistoryItem[]
  assessments?: UserAssessmentItem[]
  interventions?: UserInterventionItem[]
}

// ISS-057: 风险轨迹行
export interface UserRiskHistoryItem {
  id: number
  risk_level?: number | null
  risk_score?: number | null
  created_at: string
}

// ISS-057: 评估记录行
export interface UserAssessmentItem {
  id: number
  type?: string | null
  score?: number | null
  created_at: string
}

// ISS-057: 干预记录行
export interface UserInterventionItem {
  id: number
  type?: string | null
  status?: string | null
  created_at: string
}

export interface ConsultationItem {
  id: number
  warning_id?: number | null
  warning_status?: WarningStatus | null
  warning_risk_level?: RiskLevel | null
  main_topics?: string | null
  client_status?: string | null
  interventions?: string | null
  next_plan?: string | null
  notes?: string | null
  created_at: string
}

export interface ConsultationGroupItem {
  id: number
  group_name: string
  description?: string
  user_count?: number
}

export interface ReviewItem {
  id: number
  user_id: number
  risk_report_id: number | null
  risk_level: number
  risk_score: number
  review_triggers: string[]
  crisis_override: boolean
  status: string
  priority: string
  assigned_to: number | null
  resolved_by: number | null
  resolution_note: string | null
  created_at: string
  updated_at: string
  resolved_at: string | null
}

export interface ReviewStats {
  total: number
  pending: number
  in_review: number
  resolved: number
  escalated: number
  crisis_count: number
  high_risk_count: number
}

export type { WarningItem, UserBindingInfo }
