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

export type { WarningItem, UserBindingInfo }
