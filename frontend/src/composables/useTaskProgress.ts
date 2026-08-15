import { computed, ref } from 'vue'
import { wsClient, type WsTaskProgressMessage } from '@/composables/useWebSocket'
import { reportsApi } from '@/api/reportsApi'

export interface TaskProgressItem {
  job_id: string
  job_type: 'pdf' | 'excel' | 'training'
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress: number
  error: string | null
  created_at: string
  updated_at: number
}

const taskProgressMap = ref<Map<string, TaskProgressItem>>(new Map())
let subscribed = false
// SEC-FIX (C3): 保存 WS 监听器的取消函数，登出重置时移除监听器，
// 避免 A 用户登出后 B 用户仍收到 A 的任务进度事件。
let unsubscribeTaskProgress: (() => void) | null = null
let cleanupTimer: ReturnType<typeof setInterval> | null = null
// M-FIX-005: 活动任务 (recoverJobs 恢复的 running/queued) 轮询刷新间隔
const POLL_INTERVAL_MS = 5000
let pollTimer: ReturnType<typeof setInterval> | null = null

// 已完成/失败任务的保留时间 (ms), 超时后自动清理
// P1-1 核心体验：从 30s 增加到 5min，确保用户有足够时间点击下载/重试
const COMPLETED_RETENTION_MS = 300_000
// 清理检查间隔
const CLEANUP_INTERVAL_MS = 10_000

async function refreshJobStatus(jobId: string) {
  try {
    const s = await reportsApi.getPdfJobStatus(jobId)
    const current = taskProgressMap.value.get(jobId)
    if (!current) return
    // 兼容进程内 PdfJobStore (job_id/id) 与 celery 变体 (job_id)
    const status = s.status as TaskProgressItem['status']
    const error = s.error ?? current.error
    taskProgressMap.value.set(jobId, {
      ...current,
      status,
      progress: s.progress,
      error,
      updated_at: Date.now(),
    })
    taskProgressMap.value = new Map(taskProgressMap.value)
  } catch {
    // 404/网络异常：任务已过期或被清理，静默忽略
  }
}

function refreshActiveJobs() {
  for (const item of taskProgressMap.value.values()) {
    if (item.status === 'running' || item.status === 'queued') {
      void refreshJobStatus(item.job_id)
    }
  }
}

// P1-1 核心体验：从后端恢复任务状态，使刷新后可恢复任务进度
async function recoverJobs() {
  try {
    const result = await reportsApi.listPdfJobs()
    const now = Date.now()
    for (const job of result.jobs) {
      // 仅恢复未过期的任务（后端 TTL 1 小时，但可能已清理）
      if (!taskProgressMap.value.has(job.id)) {
        taskProgressMap.value.set(job.id, {
          job_id: job.id,
          job_type: 'pdf' as const,
          status: job.status as TaskProgressItem['status'],
          progress: job.progress,
          // M-FIX-005: 恢复失败任务时保留后端错误信息，而非硬编码 null
          error: job.error ?? null,
          created_at: job.created_at,
          updated_at: now,
        })
      }
    }
    if (result.jobs.length > 0) {
      taskProgressMap.value = new Map(taskProgressMap.value)
      ensureCleanupTimer()
      // M-FIX-005: 恢复出活动任务时立即启动轮询刷新
      refreshActiveJobs()
      ensurePollTimer()
    }
  } catch {
    // 静默失败：后端不可达时不影响前端正常使用
  }
}

// M-FIX-005: 轮询刷新活动任务进度.
// 刷新后 WS 重连/路由切换导致 task_progress 丢失时，恢复的 running/queued 任务
// 通过 HTTP 轮询持续刷新，直到到达终态后自动停止.
function ensurePollTimer() {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    let hasActive = false
    for (const item of taskProgressMap.value.values()) {
      if (item.status === 'running' || item.status === 'queued') {
        hasActive = true
        void refreshJobStatus(item.job_id)
      }
    }
    if (!hasActive && pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }, POLL_INTERVAL_MS)
  // 首次调用时立即刷新一次，缩短等待窗口
  refreshActiveJobs()
}

function ensureSubscribed() {
  if (subscribed) return
  subscribed = true
  // P1-1 核心体验：页面加载时从后端恢复任务状态
  recoverJobs()
  unsubscribeTaskProgress = wsClient.onTaskProgress((msg: WsTaskProgressMessage) => {
    const item: TaskProgressItem = {
      job_id: msg.data.job_id,
      job_type: msg.data.job_type,
      status: msg.data.status,
      progress: msg.data.progress,
      error: msg.data.error,
      created_at: msg.data.created_at,
      updated_at: Date.now(),
    }
    taskProgressMap.value.set(msg.data.job_id, item)
    // 触发响应式更新 (Map.set 不会触发 ref 更新)
    taskProgressMap.value = new Map(taskProgressMap.value)
    // 有新任务时启动清理定时器
    ensureCleanupTimer()
    // M-FIX-005: 任务处于活动状态时启动轮询刷新 (WS 断线/重连时的兜底)
    if (item.status === 'running' || item.status === 'queued') {
      ensurePollTimer()
    }
  })
}

function ensureCleanupTimer() {
  if (cleanupTimer) return
  cleanupTimer = setInterval(() => {
    const now = Date.now()
    let changed = false
    for (const [key, item] of taskProgressMap.value) {
      if (
        (item.status === 'completed' || item.status === 'failed') &&
        now - item.updated_at > COMPLETED_RETENTION_MS
      ) {
        taskProgressMap.value.delete(key)
        changed = true
      }
    }
    if (changed) {
      taskProgressMap.value = new Map(taskProgressMap.value)
    }
    // 无任务时自动停止定时器，避免空转
    if (taskProgressMap.value.size === 0) {
      if (cleanupTimer) {
        clearInterval(cleanupTimer)
        cleanupTimer = null
      }
      if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
      }
    }
  }, CLEANUP_INTERVAL_MS)
}

export function useTaskProgress() {
  ensureSubscribed()

  const activeTasks = computed(() =>
    Array.from(taskProgressMap.value.values()).filter(
      (t) => t.status === 'running' || t.status === 'queued',
    ),
  )

  const completedTasks = computed(() =>
    Array.from(taskProgressMap.value.values()).filter((t) => t.status === 'completed'),
  )

  const failedTasks = computed(() =>
    Array.from(taskProgressMap.value.values()).filter((t) => t.status === 'failed'),
  )

  const hasActiveTasks = computed(() => activeTasks.value.length > 0)

  function removeTask(jobId: string) {
    taskProgressMap.value.delete(jobId)
    taskProgressMap.value = new Map(taskProgressMap.value)
  }

  function getTask(jobId: string): TaskProgressItem | undefined {
    return taskProgressMap.value.get(jobId)
  }

  function clearAll() {
    taskProgressMap.value.clear()
    taskProgressMap.value = new Map(taskProgressMap.value)
  }

  return {
    activeTasks,
    completedTasks,
    failedTasks,
    hasActiveTasks,
    removeTask,
    getTask,
    clearAll,
  }
}

// 供测试使用: 重置内部状态
// SEC-FIX (C3): 登出时调用，清除跨会话残留的任务状态与 WS 监听器
export function resetTaskProgress() {
  taskProgressMap.value.clear()
  taskProgressMap.value = new Map(taskProgressMap.value)
  subscribed = false
  if (unsubscribeTaskProgress) {
    unsubscribeTaskProgress()
    unsubscribeTaskProgress = null
  }
  if (cleanupTimer) {
    clearInterval(cleanupTimer)
    cleanupTimer = null
  }
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}
