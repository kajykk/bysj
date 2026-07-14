/**
 * UserIntervention 共享工具：常量、纯函数。
 * 从原 UserInterventionPage.vue 提取，保持行为一致。
 */

/** 主导模态 → i18n key 后缀映射 */
export const MODALITY_LABEL_KEYS: Record<string, string> = {
  structured: 'modalityStructured',
  text: 'modalityText',
  physiological: 'modalityPhysiological',
  fused: 'modalityFused',
  questionnaire: 'modalityQuestionnaire'
}

/** 任务调度 → i18n key 后缀映射 */
export const SCHEDULE_LABEL_KEYS: Record<string, string> = {
  daily: 'scheduleDaily',
  weekly: 'scheduleWeekly',
  once: 'scheduleOnce'
}

/** 历史计划状态 → i18n key 后缀映射 */
export const HISTORY_STATUS_LABEL_KEYS: Record<string, string> = {
  active: 'statusActive',
  completed: 'statusCompleted',
  cancelled: 'statusCancelled'
}

/** 任务今日状态 → i18n key 后缀映射 */
export const TASK_STATUS_LABEL_KEYS: Record<string, string> = {
  pending: 'taskStatusPending',
  completed: 'taskStatusCompleted',
  missed: 'taskStatusMissed',
  skipped: 'taskStatusSkipped',
  postponed: 'taskStatusPostponed'
}

/** 风险等级 → el-tag type 映射 */
export const riskLevelTag = (level: number): 'info' | 'success' | 'warning' | 'danger' => {
  const map: Record<number, 'info' | 'success' | 'warning' | 'danger'> = {
    0: 'info',
    1: 'success',
    2: 'warning',
    3: 'danger',
    4: 'danger'
  }
  return map[level] || 'info'
}

/** 任务今日状态 → el-tag type 映射 */
export const taskStatusTag = (status: string): 'info' | 'success' | 'warning' | 'danger' => {
  const map: Record<string, 'info' | 'success' | 'warning' | 'danger'> = {
    pending: 'info',
    completed: 'success',
    missed: 'danger',
    skipped: 'warning',
    postponed: 'warning'
  }
  return map[status] || 'info'
}

/** 历史计划状态 → el-tag type 映射 */
export const historyStatusTag = (status: string): 'success' | 'info' | 'warning' => {
  if (status === 'active') return 'success'
  if (status === 'completed') return 'info'
  return 'warning'
}

// ISS-016 修复：改用本地日期，避免 toISOString 返回 UTC 日期导致东八区 0-8 点跨日错位
// 'sv-SE' locale 输出 YYYY-MM-DD 格式的本地日期
/** 获取今日本地日期 YYYY-MM-DD */
export const getTodayDate = (): string => new Date().toLocaleDateString('sv-SE')
