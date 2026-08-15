import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import type { StructuredCollectResult } from '@/api/userRiskApi'
import { sanitizeCellForExcel } from '@/utils/exportUtils'
import { historyKeyWithUser } from '@/utils/sensitiveStorage'
import { formatWarningGenerated } from './sharedStepUtils'

export type PredictionHistoryEntry = StructuredCollectResult & { time: string }

export function usePredictionHistory() {
  const { t } = useI18n()
  const auth = useAuthStore()

  // ISS-058 修复：匿名用户（id=0 或未登录）使用会话级随机 ID，避免共享 localStorage 导致历史相互覆盖
  // SEC-FIX (H4 补强): 统一走 sensitiveStorage.historyKeyWithUser 生成 key,
  // 保证 clearSensitiveLocalStorage 的清理模式覆盖所有匿名/登录 key
  const historyKey = (base: string) => historyKeyWithUser(base, auth.user?.id)

  const PREDICTION_HISTORY_KEY = historyKey('prediction_history_v1')

  const predictionHistory = ref<PredictionHistoryEntry[]>([])

  const loadPredictionHistory = () => {
    try {
      const raw = localStorage.getItem(PREDICTION_HISTORY_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) {
        predictionHistory.value = parsed
      }
    } catch {
      predictionHistory.value = []
    }
  }

  const savePredictionHistory = () => {
    localStorage.setItem(PREDICTION_HISTORY_KEY, JSON.stringify(predictionHistory.value.slice(0, 20)))
  }

  const clearPredictionHistory = () => {
    predictionHistory.value = []
    localStorage.removeItem(PREDICTION_HISTORY_KEY)
    ElMessage.success(t('structuredAssess.historyCleared'))
  }

  const exportPredictionHistoryCsv = () => {
    if (!predictionHistory.value.length) {
      ElMessage.warning(t('structuredAssess.noHistoryToExport'))
      return
    }

    const headers = [
      t('structuredAssess.csvHeaderTime'),
      t('structuredAssess.csvHeaderRiskScore'),
      t('structuredAssess.csvHeaderRiskLevel'),
      t('structuredAssess.csvHeaderSeverity'),
      t('structuredAssess.csvHeaderWarningTriggered')
    ]
    const rows = predictionHistory.value.map((row) => [
      row.time,
      row.risk_score,
      row.risk_level,
      row.severity,
      formatWarningGenerated(row.warning_generated, 'csv')
    ])

    const csv = [headers, ...rows]
      .map((line) => line.map((cell) => `"${sanitizeCellForExcel(String(cell)).replace(/"/g, '""')}"`).join(','))
      .join('\n')

    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `prediction_history_${Date.now()}.csv`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    ElMessage.success(t('structuredAssess.historyCsvExported'))
  }

  const addPredictionEntry = (result: StructuredCollectResult) => {
    predictionHistory.value.unshift({
      ...result,
      time: new Date().toLocaleString()
    })
    savePredictionHistory()
  }

  return {
    predictionHistory,
    loadPredictionHistory,
    clearPredictionHistory,
    exportPredictionHistoryCsv,
    addPredictionEntry,
  }
}
