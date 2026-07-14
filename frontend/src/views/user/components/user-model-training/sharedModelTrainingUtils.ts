/**
 * UserModelTraining 共享工具：类型、常量。
 * 从原 UserModelTrainingPage.vue 提取，保持行为一致。
 */

/** 训练日志行 */
export interface TrainingLogRow {
  time: string
  stage: string
  message: string
  level: 'info' | 'warning' | 'success' | 'error'
}

/** 活跃训练任务 */
export interface ActiveJob {
  job_id?: string
  status: string
  progress?: number
  stage?: string
  message: string
}

/** 训练参数表单 */
export interface TrainingForm {
  dataset_name: string
  model_name: string
  epochs: number
  batch_size: number
  learning_rate: number
}

/** ISS-002 修复：轮询间隔（指数退避：初始 5s，最大 30s） */
export const POLL_INITIAL_MS = 5000
export const POLL_MAX_MS = 30000
