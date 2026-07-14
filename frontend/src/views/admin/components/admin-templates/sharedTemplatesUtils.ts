/**
 * AdminTemplates 共享工具：常量、类型、纯函数。
 * 从原 AdminTemplatesPage.vue 提取，保持行为一致。
 */
import type { TaskType } from '@/api/taskTypes'
import type { TemplateItem } from '@/api/adminApi'

/** 模板状态 */
export type TemplateStatus = 'active' | 'inactive'

/** 表单状态 */
export interface TemplateFormState {
  template_name: string
  applicable_levels: number[]
  estimated_weeks: number
  status: TemplateStatus
}

/** 默认表单值（对应原 openCreate 中的初始化） */
export const DEFAULT_TEMPLATE_FORM: TemplateFormState = {
  template_name: '',
  applicable_levels: [2],
  estimated_weeks: 4,
  status: 'active',
}

/** 任务项类型（含任意附加字段） */
export type TaskItem = { task_name: string; task_type: TaskType } & Record<string, unknown>

/** Upsert 模板时使用的 payload 类型 */
export interface TemplateUpsertPayload {
  id?: number
  template_name: string
  applicable_levels: number[]
  task_list: TemplateItem['task_list']
  estimated_weeks: number
  status: TemplateStatus
}

/**
 * 构建任务列表 textarea 的占位 JSON。
 * 依赖 i18n 文案，需要传入 t 函数。
 */
export const buildTaskListPlaceholder = (
  t: (key: string, params?: Record<string, unknown>) => string
): string =>
  JSON.stringify(
    [
      {
        task_name: t('adminTemplates.placeholderTaskName'),
        task_type: 'meditation',
        schedule: 'daily',
        duration_minutes: 15,
      },
    ],
    null,
    2
  )

/** 将行任务列表序列化为 textarea 字符串 */
export const serializeTaskList = (
  taskList: TemplateItem['task_list'] | null | undefined
): string => JSON.stringify(taskList || [], null, 2)
