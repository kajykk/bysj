// L-FE-1 修复：跨目录相对路径（../../../common）脆弱，改用 @common 别名导入
import taskTypes from '@common/task-types.json'

export const TASK_TYPES = taskTypes as readonly string[]
export type TaskType = (typeof TASK_TYPES)[number]
export const TASK_TYPE_SET = new Set<string>(TASK_TYPES)
