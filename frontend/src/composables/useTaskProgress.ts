import { computed, ref } from 'vue'
import { wsClient, type WsTaskProgressMessage } from '@/composables/useWebSocket'

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
let cleanupTimer: ReturnType<typeof setInterval> | null = null

// 已完成/失败任务的保留时间 (ms), 超时后自动清理
const COMPLETED_RETENTION_MS = 30_000
// 清理检查间隔
const CLEANUP_INTERVAL_MS = 10_000

function ensureSubscribed() {
  if (subscribed) return
  subscribed = true
  wsClient.onTaskProgress((msg: WsTaskProgressMessage) => {
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
  })

  // 定期清理过期的已完成/失败任务
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
export function resetTaskProgress() {
  taskProgressMap.value.clear()
  taskProgressMap.value = new Map(taskProgressMap.value)
  subscribed = false
  if (cleanupTimer) {
    clearInterval(cleanupTimer)
    cleanupTimer = null
  }
}
