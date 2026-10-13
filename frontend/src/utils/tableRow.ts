/**
 * P2 类型存量收敛：Element Plus 表格插槽行的**收窄 SSOT**。
 *
 * 问题：`el-table` 的作用域插槽里 `row` 的静态类型是 Element Plus 内部的
 * `DefaultRow`（宽松的 `Record<string, any>` 别名），与各页面自己的行类型
 * （`WarningItem` / `SilenceItem` / `ModelRegistryRecord` / …）不兼容。
 * 全仓因此长期挂着 33 处 `DefaultRow is not assignable to parameter of type XxxItem`。
 *
 * 为什么不直接改 Element Plus 泛型：那属于依赖升级/组件重构范畴，风险与收益不成比例；
 * 本轮的目标是把**边界处**的收窄统一到一处 —— 各页若各写一份 `as Xxx`，
 * 又会变成审查报告根因②「同一模式复制 N 份后各自漂移」。
 *
 * 用法（在插槽里）：
 *
 *     <template #default="{ row }">
 *       <el-button @click="openDetail(asRow<WarningItem>(row))" />
 *
 * 契约：本函数**不做运行时校验**（表格行的数据契约由后端 + API 类型保证），
 * 只做类型收窄。若将来要加运行时断言，必须在这里加，而不是各页各加一份。
 */
export function asRow<T>(row: unknown): T {
  return row as T
}
