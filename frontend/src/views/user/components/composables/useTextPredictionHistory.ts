/**
 * R-E3: 文本预测历史记录持久化 composable.
 *
 * 从 TextAssessTab.vue 抽出历史读写、清空与 CSV 导出逻辑，
 * 键按用户会话隔离（SEC-FIX H4 补强）。
 *
 * SEC-FIX-2026-10-09: 存储位置由 localStorage 改为 sessionStorage。
 * 本历史含用户心理自述文本片段（content_preview，前 60 字 × 最多 20 条），
 * 属敏感健康信息。原实现依赖 `clearSensitiveLocalStorage()` 在**登出/登录时**
 * 清理，但绝大多数用户是直接关闭浏览器而不点退出登录 —— 数据因此长期明文
 * 落盘，共享/公用设备上下一位打开浏览器即可读取上一位用户的心理自述。
 * 改到 sessionStorage 后，关闭标签页即清除，无需依赖用户的登出动作；
 * 刷新页面仍保留，历史功能不受影响。
 */

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import type { TextPredictModelResult } from '@/api/modelApi'
import { downloadBlob, csvEscape } from '@/utils/exportUtils'

export type TextPredictionHistoryItem = TextPredictModelResult & {
  time: string
  content_preview: string
  source: 'text' | 'model'
}

const HISTORY_MAX = 20

/**
 * 运行时守卫：校验 localStorage 里读出的历史项是否仍符合当前契约。
 *
 * SEC-FIX-2026-10-05: 原实现只校验 `Array.isArray(parsed)` 就整体赋值。
 * localStorage 里的数据跨版本存活，而代码里的类型会随迭代变化 —— 后端契约
 * 一改（例如 probability 变可空、或字段改名），旧记录读出来就是残缺对象，
 * 模板里 `(undefined * 100).toFixed(2)` 会抛错导致白屏。
 *
 * 键名带 `_v1` 后缀只保证「大版本」隔离，数据体内没有版本字段，因此这里
 * 做逐项字段校验；不通过的整批丢弃并清空，避免把脏数据带进渲染。
 */
function isValidHistoryItem(x: unknown): x is TextPredictionHistoryItem {
  if (!x || typeof x !== 'object') return false
  const o = x as Record<string, unknown>
  // prediction / probability 为必填数值；sentiment_* 后端 Optional，允许缺失/null
  if (typeof o.prediction !== 'number') return false
  if (typeof o.probability !== 'number') return false
  if (typeof o.time !== 'string') return false
  if (typeof o.content_preview !== 'string') return false
  if (o.sentiment_score !== null && o.sentiment_score !== undefined &&
      typeof o.sentiment_score !== 'number') {
    return false
  }
  if (o.sentiment_label !== null && o.sentiment_label !== undefined &&
      typeof o.sentiment_label !== 'string') {
    return false
  }
  return true
}

export function useTextPredictionHistory(historyKey: string) {
  const { t } = useI18n()
  const textPredictionHistory = ref<TextPredictionHistoryItem[]>([])

  const load = () => {
    try {
      const raw = sessionStorage.getItem(historyKey)
      if (!raw) return
      const parsed: unknown = JSON.parse(raw)
      if (!Array.isArray(parsed)) return
      const valid = parsed.filter(isValidHistoryItem)
      if (valid.length !== parsed.length) {
        // 存在契约不匹配的旧记录：丢弃它们而不是让渲染期抛错。
        // 只在确有脏数据时清理，正常路径不写 localStorage。
        if (valid.length === 0) sessionStorage.removeItem(historyKey)
      }
      textPredictionHistory.value = valid as TextPredictionHistoryItem[]
    } catch {
      textPredictionHistory.value = []
    }
  }

  const save = () => {
    sessionStorage.setItem(
      historyKey,
      JSON.stringify(textPredictionHistory.value.slice(0, HISTORY_MAX)),
    )
  }

  const clear = () => {
    textPredictionHistory.value = []
    sessionStorage.removeItem(historyKey)
    ElMessage.success(t('textAssess.historyCleared'))
  }

  const unshift = (item: TextPredictionHistoryItem) => {
    textPredictionHistory.value.unshift(item)
    save()
  }

  const exportCsv = () => {
    if (!textPredictionHistory.value.length) {
      ElMessage.warning(t('textAssess.noHistoryToExport'))
      return
    }
    const headers = [
      t('textAssess.csvHeaderTime'),
      t('textAssess.csvHeaderContentPreview'),
      'prediction(0/1)',
      'probability(%)',
      'sentiment_label',
      'sentiment_score',
      'model_used',
    ]
    const rows = textPredictionHistory.value.map((row) => [
      row.time,
      row.content_preview,
      row.prediction,
      // SEC-FIX-2026-10-05: probability 后端为 Optional（模型回退路径可能
      // 不返回）。无防御时 (null * 100).toFixed(2) 不会报错，而是静默产出
      // "NaN%" 写进 CSV —— 用户拿到一份含 NaN 的分析记录却毫无察觉。
      row.probability != null ? (row.probability * 100).toFixed(2) : '',
      row.sentiment_label,
      row.sentiment_score != null ? row.sentiment_score.toFixed(2) : '',
      row.model_used,
    ])

    const csv = [headers, ...rows]
      .map((line) =>
        line
          .map((cell) => csvEscape(String(cell)))
          .join(','),
      )
      .join('\n')

    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
    downloadBlob(blob, `text_prediction_history_${Date.now()}.csv`)
    ElMessage.success(t('textAssess.historyCsvExported'))
  }

  return { textPredictionHistory, load, save, clear, unshift, exportCsv }
}
