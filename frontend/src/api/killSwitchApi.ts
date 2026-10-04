import request, { requestData } from './request'

/**
 * Kill Switch 状态来源。
 *
 * AUDIT-2026-10-01 (P1-7)：区分「确认未暂停」与「不知道」是本次修复的核心——
 * 没有这个字段时，Redis 挂掉会让运维看到一个「未暂停」，而实际是「无法确认」。
 * - redis: 权威状态（多实例共享）
 * - memory: 仅当前进程内存（Redis 不可用时写入只落到本实例）
 * - unavailable: 无法确认（Redis 不可用），后端按 fail-closed 视为已暂停
 */
export type KillSwitchStateSource = 'redis' | 'memory' | 'unavailable'

export interface KillSwitchState {
  paused: boolean
  reason: string | null
  activated_by: number | null
  activated_at: string | null
  updated_at: string | null
  /** true = 当前状态不是权威状态（Redis 不可用） */
  degraded: boolean
  source: KillSwitchStateSource
}

/**
 * Phase 3 模型预测暂停开关 API。
 *
 * 后端端点全部要求平台管理员权限（require_platform_admin）。
 * 注意：activate/deactivate 在 fail-closed 模式下若 Redis 不可写会返回 503
 * —— 这表示**操作未生效**，绝不能被当作成功处理。
 */
export const killSwitchApi = {
  // 开关状态是安全相关实时值，不走 dedupedGet 缓存
  getStatus: () => requestData<KillSwitchState>(request.get('/model-kill-switch/status')),
  activate: (reason: string) =>
    requestData<KillSwitchState>(request.post('/model-kill-switch/activate', { reason })),
  deactivate: (reason: string) =>
    requestData<KillSwitchState>(request.post('/model-kill-switch/deactivate', { reason })),
}

export type { KillSwitchState as ModelKillSwitchState }
