import type { AssessmentType, BindingStatus, UserStatus } from '@/types/contracts'

export interface WarningItem {
  id: number
  risk_level: number
  title: string
  content: string
  is_read: boolean
  status: string
  created_at: string
  handled_at?: string | null
  handled_by?: number | null
  handled_note?: string | null
  physiological_score?: number | null
  fusion_detail?: Record<string, unknown> | null
}

export interface UserManageItem {
  id: number
  username: string
  nickname?: string
  email?: string
  role?: string
  status?: UserStatus
}

export interface DataHistoryItem {
  id: number
  type: AssessmentType | 'structured' | 'text' | 'physiological' | string
  created_at: string
  data: Record<string, unknown>
}

export interface AssessmentRecordItem {
  id: number
  assessment_type?: AssessmentType | 'structured' | 'text' | 'physiological'
  score?: number
  risk_level?: number
  created_at?: string
  summary?: string
  detail?: string
}

export interface WarningSettingData {
  notify_channels: Record<string, boolean> | null
  threshold_level: number
  quiet_hours_start: string | null
  quiet_hours_end: string | null
}

export interface ContentItem {
  id: number
  title: string
  content_type: string
  category: string
  summary: string
  cover_image_url: string | null
  duration_minutes: number | null
  difficulty: string | null
  view_count?: number
  is_favorited?: boolean
  recommend_reason?: string
  viewed_at?: string | null
}

export interface ContentDetail extends ContentItem {
  content: string
  audio_url: string | null
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

export interface UserBindingInfo {
  binding_id: number
  counselor_id: number
  counselor_name: string
  counselor_email: string | null
  bound_at: string
  status: BindingStatus
  bind_code_status: BindingStatus
}
