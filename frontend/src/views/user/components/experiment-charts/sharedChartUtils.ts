/**
 * 实验图表共享工具：颜色常量、类型定义、公共配置。
 */

/** 图表配色（与原 ExperimentTab 内联配色保持一致） */
export const CHART_COLORS = {
  loss: '#2e6fa8',
  accuracy: '#5a9e3a',
  /** 对比柱状图各指标配色 */
  compareSeries: ['#2e6fa8', '#5a9e3a', '#d4923a', '#d65a5a', '#7a8290'],
} as const

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
