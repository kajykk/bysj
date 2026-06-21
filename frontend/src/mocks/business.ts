import type { AssessmentRecordItem, UserManageItem, WarningItem } from '@/api/userTypes'
import type { PageResult } from '@/types/api'

const WARNING_STATUS_LABELS = ['pending', 'handled', 'ignored'] as const

const sleep = (ms = 300) => new Promise((resolve) => setTimeout(resolve, ms))

export async function mockWarnings(page = 1, pageSize = 10): Promise<PageResult<WarningItem>> {
  await sleep()
  const all: WarningItem[] = Array.from({ length: 23 }).map((_, idx) => {
    const status = WARNING_STATUS_LABELS[idx % WARNING_STATUS_LABELS.length]
    const isRead = status !== 'pending'
    return {
      id: idx + 1,
      title: `预警 #${idx + 1}`,
      content: '检测到近期情绪波动，请关注',
      risk_level: idx % 3 === 0 ? 3 : idx % 3 === 1 ? 2 : 1,
      is_read: isRead,
      status,
      created_at: new Date(Date.now() - idx * 86400000).toISOString(),
      handled_at: isRead ? new Date(Date.now() - idx * 86400000 + 3600000).toISOString() : null,
      handled_by: isRead ? 1 : null,
      handled_note: isRead ? (status === 'ignored' ? '人工忽略' : '自动标记为已读') : null
    }
  })
  const start = (page - 1) * pageSize
  const items = all.slice(start, start + pageSize)
  return { items, total: all.length, page, page_size: pageSize }
}

export async function mockUsers(page = 1, pageSize = 10): Promise<PageResult<UserManageItem>> {
  await sleep()
  const all: UserManageItem[] = Array.from({ length: 36 }).map((_, idx) => ({
    id: idx + 1,
    username: `student_${idx + 1}`,
    nickname: `同学${idx + 1}`,
    email: `student_${idx + 1}@demo.com`,
    status: idx % 4 === 0 ? 'inactive' : 'active'
  }))
  const start = (page - 1) * pageSize
  return { items: all.slice(start, start + pageSize), total: all.length, page, page_size: pageSize }
}

export async function mockAssessments(page = 1, pageSize = 10): Promise<PageResult<AssessmentRecordItem>> {
  await sleep()
  const all: AssessmentRecordItem[] = Array.from({ length: 18 }).map((_, idx) => ({
    id: idx + 1,
    assessment_type: idx % 2 === 0 ? 'structured' : 'text',
    score: 60 + (idx % 40),
    risk_level: idx % 3 === 0 ? 3 : idx % 3 === 1 ? 2 : 1,
    created_at: new Date(Date.now() - idx * 86400000).toISOString(),
    summary: '状态总体可控，建议规律作息并持续记录情绪。'
  }))
  const start = (page - 1) * pageSize
  return { items: all.slice(start, start + pageSize), total: all.length, page, page_size: pageSize }
}
