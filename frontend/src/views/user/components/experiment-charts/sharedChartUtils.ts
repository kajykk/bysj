/**
 * 实验图表共享工具：类型定义与公共配置。
 * 颜色统一由 @/utils/chartTheme 读取设计令牌，这里不再保留静态色板。
 */

/** 对比实验指标键名 */
export const COMPARE_METRICS = ['accuracy', 'precision', 'recall', 'f1', 'auc'] as const

/** 模型对比单条记录 */
export interface CompareItem {
  model_name: string
  accuracy: number
  precision: number
  recall: number
  f1: number
  auc: number
}

/** 预测样本记录 */
export interface PredictionSample {
  index: number
  true_label: number
  pred_label: number
  score: number
}
