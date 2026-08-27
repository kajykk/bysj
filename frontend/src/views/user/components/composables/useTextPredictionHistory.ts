/**
 * R-E3: 文本预测历史记录持久化 composable.
 *
 * 从 TextAssessTab.vue 抽出 localStorage 读写、清空与 CSV 导出逻辑，
 * 键按用户会话隔离（SEC-FIX H4 补强）。
 */

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import type { TextPredictModelResult } from '@/api/modelApi'
import { sanitizeCellForExcel } from '@/utils/exportUtils'

export type TextPredictionHistoryItem = TextPredictModelResult & {
  time: string
  content_preview: string
  source: 'text' | 'model'
}

const HISTORY_MAX = 20

export function useTextPredictionHistory(historyKey: string) {
  const { t } = useI18n()
  const textPredictionHistory = ref<TextPredictionHistoryItem[]>([])

  const load = () => {
    try {
      const raw = localStorage.getItem(historyKey)
      if (!raw) return
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) {
        textPredictionHistory.value = parsed
      }
    } catch {
      textPredictionHistory.value = []
    }
  }

  const save = () => {
    localStorage.setItem(
      historyKey,
      JSON.stringify(textPredictionHistory.value.slice(0, HISTORY_MAX)),
    )
  }

  const clear = () => {
    textPredictionHistory.value = []
    localStorage.removeItem(historyKey)
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
      (row.probability * 100).toFixed(2),
      row.sentiment_label,
      row.sentiment_score != null ? row.sentiment_score.toFixed(2) : '',
      row.model_used,
    ])

    const csv = [headers, ...rows]
      .map((line) =>
        line
          .map((cell) => `"${sanitizeCellForExcel(String(cell)).replace(/"/g, '""')}"`)
          .join(','),
      )
      .join('\n')

    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `text_prediction_history_${Date.now()}.csv`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    ElMessage.success(t('textAssess.historyCsvExported'))
  }

  return { textPredictionHistory, load, save, clear, unshift, exportCsv }
}
