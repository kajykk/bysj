<template>
  <div>
    <el-card>
      <el-form
        :model="textForm"
        label-width="100px"
        style="max-width: 600px"
      >
        <el-form-item :label="t('textAssess.entryTypeLabel')">
          <el-select
            v-model="textForm.entry_type"
            style="width: 100%"
          >
            <el-option
              :label="t('textAssess.entryTypeDiary')"
              value="diary"
            />
            <el-option
              :label="t('textAssess.entryTypeSocial')"
              value="social"
            />
            <el-option
              :label="t('textAssess.entryTypeVent')"
              value="vent"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('textAssess.contentLabel')">
          <el-input
            v-model="textForm.content"
            type="textarea"
            :rows="6"
            :placeholder="t('textAssess.contentPlaceholder')"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
        <el-form-item :label="t('textAssess.emotionTagsLabel')">
          <el-select
            v-model="textForm.emotion_tags"
            multiple
            allow-create
            style="width: 100%"
            :placeholder="t('textAssess.emotionTagsPlaceholder')"
          >
            <el-option
              :label="t('textAssess.emotionAnxiety')"
              value="anxiety"
            >
              <el-tag
                type="warning"
                size="small"
              >
                {{ t('textAssess.emotionAnxiety') }}
              </el-tag>
            </el-option>
            <el-option
              :label="t('textAssess.emotionDepression')"
              value="depression"
            >
              <el-tag
                type="danger"
                size="small"
              >
                {{ t('textAssess.emotionDepression') }}
              </el-tag>
            </el-option>
            <el-option
              :label="t('textAssess.emotionAnger')"
              value="anger"
            >
              <el-tag
                type="danger"
                size="small"
                effect="light"
              >
                {{ t('textAssess.emotionAnger') }}
              </el-tag>
            </el-option>
            <el-option
              :label="t('textAssess.emotionCalm')"
              value="calm"
            >
              <el-tag
                type="success"
                size="small"
              >
                {{ t('textAssess.emotionCalm') }}
              </el-tag>
            </el-option>
            <el-option
              :label="t('textAssess.emotionHappy')"
              value="happy"
            >
              <el-tag
                type="success"
                size="small"
                effect="light"
              >
                {{ t('textAssess.emotionHappy') }}
              </el-tag>
            </el-option>
            <el-option
              :label="t('textAssess.emotionSad')"
              value="sad"
            >
              <el-tag
                type="info"
                size="small"
              >
                {{ t('textAssess.emotionSad') }}
              </el-tag>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item :label="t('textAssess.moodScoreLabel')">
          <el-rate
            v-model="textForm.mood_score"
            :max="5"
            show-score
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            :loading="textSubmitting"
            :disabled="!textForm.content.trim()"
            @click="submitText"
          >
            {{ t('textAssess.submitBtn') }}
          </el-button>
          <el-button
            v-if="canUse"
            style="margin-left: 8px"
            type="success"
            :loading="textPredictSubmitting"
            :disabled="!textForm.content.trim()"
            @click="submitTextPredict"
          >
            {{ t('textAssess.predictBtn') }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <Transition name="fade-slide">
      <el-card
        v-if="textResult"
        style="margin-top: 16px"
      >
        <template #header>
          <span class="card-title">{{ t('textAssess.analysisTitle') }}</span>
        </template>
        <el-descriptions
          :column="2"
          border
        >
          <el-descriptions-item :label="t('textAssess.sentimentLabel')">
            <el-tag :type="textResult.sentiment_label === 'negative' ? 'danger' : 'success'">
              {{ textResult.sentiment_label === 'negative' ? t('textAssess.sentimentNegative') : t('textAssess.sentimentPositive') }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('textAssess.sentimentScoreLabel')">
            {{ textResult.sentiment_score }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>
    </Transition>

    <Transition name="fade-slide">
      <el-card
        v-if="textPredictResult"
        style="margin-top: 16px"
        class="result-panel"
      >
        <template #header>
          <div class="header-row">
            <span class="card-title">{{ t('textAssess.predictResultTitle') }}</span>
            <el-tag
              type="success"
              effect="light"
            >
              {{ t('textAssess.newTextModelTag') }}
            </el-tag>
          </div>
        </template>
        <el-row
          :gutter="16"
          class="result-grid"
        >
          <el-col :span="12">
            <el-card
              shadow="never"
              class="mini-result-card"
            >
              <template #header>
                <span class="mini-title">{{ t('textAssess.textPredictResultTitle') }}</span>
              </template>
              <el-result
                :icon="textPredictResult.prediction === 1 ? 'warning' : 'success'"
                :title="textPredictResult.prediction === 1 ? t('textAssess.predictHighRisk') : t('textAssess.predictLowRisk')"
              >
                <template #sub-title>
                  <p>{{ t('textAssess.probabilityLabel') }}{{ (textPredictResult.probability * 100).toFixed(2) }}%</p>
                  <p>{{ t('textAssess.sentimentLabelField') }}{{ textPredictResult.sentiment_label || t('textAssess.sentimentLabel') }}</p>
                  <p>{{ t('textAssess.sentimentScoreFieldLabel') }}{{ textPredictResult.sentiment_score.toFixed(2) }}</p>
                  <p>{{ t('textAssess.modelNameFieldLabel') }}{{ textPredictResult.model_used }}</p>
                </template>
              </el-result>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card
              shadow="never"
              class="mini-result-card"
            >
              <template #header>
                <span class="mini-title">{{ t('textAssess.textPredictDetailTitle') }}</span>
              </template>
              <el-descriptions
                :column="1"
                border
                size="small"
              >
                <el-descriptions-item :label="t('textAssess.predictionLabelLabel')">
                  {{ textPredictResult.prediction === 1 ? t('textAssess.predictionHighRisk') : t('textAssess.predictionLowRisk') }}
                </el-descriptions-item>
                <el-descriptions-item :label="t('textAssess.predictionProbabilityLabel')">
                  {{ textPredictResult.probability != null ? (textPredictResult.probability * 100).toFixed(2) + '%' : t('textAssess.sentimentLabel') }}
                </el-descriptions-item>
                <el-descriptions-item :label="t('textAssess.sentimentLabel')">
                  {{ textPredictResult.sentiment_label || t('textAssess.sentimentLabel') }}
                </el-descriptions-item>
                <el-descriptions-item :label="t('textAssess.sentimentScoreLabel')">
                  {{ textPredictResult.sentiment_score != null ? textPredictResult.sentiment_score.toFixed(2) : t('textAssess.sentimentLabel') }}
                </el-descriptions-item>
                <el-descriptions-item :label="t('textAssess.modelNameLabel')">
                  {{ textPredictResult.model_used }}
                </el-descriptions-item>
              </el-descriptions>
            </el-card>
          </el-col>
        </el-row>
      </el-card>
    </Transition>

    <el-card style="margin-top: 16px">
      <template #header>
        <div class="header-row">
          <span class="card-title">{{ t('textAssess.historyTitle') }}</span>
          <div style="display:flex; gap:8px;">
            <el-button
              size="small"
              :disabled="!textPredictionHistory.length"
              @click="exportTextPredictionHistoryCsv"
            >
              {{ t('textAssess.exportHistoryBtn') }}
            </el-button>
            <el-button
              size="small"
              type="danger"
              plain
              :disabled="!textPredictionHistory.length"
              @click="clearTextPredictionHistory"
            >
              {{ t('textAssess.clearHistoryBtn') }}
            </el-button>
          </div>
        </div>
      </template>
      <el-table
        :data="textPredictionHistory"
        size="small"
        stripe
      >
        <el-table-column
          prop="time"
          :label="t('textAssess.colTime')"
          min-width="170"
        />
        <el-table-column
          prop="content_preview"
          :label="t('textAssess.colContentPreview')"
          min-width="220"
        />
        <el-table-column
          :label="t('textAssess.colPredictResult')"
          width="130"
        >
          <template #default="{ row }">
            {{ row.prediction === 1 ? t('textAssess.predictionHighRisk') : t('textAssess.predictionLowRisk') }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('textAssess.colPredictProbability')"
          width="120"
        >
          <template #default="{ row }">
            {{ (row.probability * 100).toFixed(2) }}%
          </template>
        </el-table-column>
        <el-table-column
          prop="model_used"
          :label="t('textAssess.colModelName')"
          min-width="170"
        />
      </el-table>
      <el-empty
        v-if="!textPredictionHistory.length"
        :description="t('textAssess.emptyHistory')"
        :image-size="60"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { userApi } from '@/api/userApi'
import { modelApi, type TextPredictModelResult } from '@/api/modelApi'
import type { TextAnalyzeResult } from '@/api/userRiskApi'
import { useAuthStore } from '@/stores/auth'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { sanitizeCellForExcel } from '@/utils/exportUtils'

interface Props {
  canUse: boolean
}

defineProps<Props>()
const emit = defineEmits<{
  submitted: [data: { text: string }]
}>()

const { t } = useI18n()
const auth = useAuthStore()
let isUnmounted = false

const historyKey = (base: string) => `${base}_u${auth.user?.id ?? 0}`
const TEXT_PREDICTION_HISTORY_KEY = historyKey('text_prediction_history_v1')

const textForm = reactive({
  entry_type: 'diary', content: '', emotion_tags: [] as string[], mood_score: 3
})
const textSubmitting = ref(false)
const textPredictSubmitting = ref(false)
const textResult = ref<TextAnalyzeResult | null>(null)
const textPredictResult = ref<TextPredictModelResult | null>(null)
// ISS-017 修复：历史记录增加 source 字段，区分文本分析伪造记录与真实模型预测记录
const textPredictionHistory = ref<Array<TextPredictModelResult & { time: string; content_preview: string; source: 'text' | 'model' }>>([])

const loadTextPredictionHistory = () => {
  try {
    const raw = localStorage.getItem(TEXT_PREDICTION_HISTORY_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      textPredictionHistory.value = parsed
    }
  } catch {
    textPredictionHistory.value = []
  }
}

const saveTextPredictionHistory = () => {
  localStorage.setItem(TEXT_PREDICTION_HISTORY_KEY, JSON.stringify(textPredictionHistory.value.slice(0, 20)))
}

const clearTextPredictionHistory = () => {
  textPredictionHistory.value = []
  localStorage.removeItem(TEXT_PREDICTION_HISTORY_KEY)
  ElMessage.success(t('textAssess.historyCleared'))
}

const exportTextPredictionHistoryCsv = () => {
  if (!textPredictionHistory.value.length) {
    ElMessage.warning(t('textAssess.noHistoryToExport'))
    return
  }

  const headers = [t('textAssess.csvHeaderTime'), t('textAssess.csvHeaderContentPreview'), 'prediction(0/1)', 'probability(%)', 'sentiment_label', 'sentiment_score', 'model_used']
  const rows = textPredictionHistory.value.map((row) => [
    row.time,
    row.content_preview,
    row.prediction,
    (row.probability * 100).toFixed(2),
    row.sentiment_label,
    row.sentiment_score != null ? row.sentiment_score.toFixed(2) : '',
    row.model_used
  ])

  const csv = [headers, ...rows]
    .map((line) => line.map((cell) => `"${sanitizeCellForExcel(String(cell)).replace(/"/g, '""')}"`).join(','))
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

const submitText = async () => {
  if (!textForm.content.trim()) return
  textSubmitting.value = true
  try {
    textResult.value = await userApi.analyzeText({
      entry_type: textForm.entry_type,
      content: textForm.content,
      emotion_tags: textForm.emotion_tags,
      mood_score: textForm.mood_score
    })

    textPredictionHistory.value.unshift({
      // ISS-017 修复：标记 source: 'text' 表示由文本分析伪造的预测字段，便于后续按来源过滤
      prediction: textResult.value.sentiment_label === 'negative' ? 1 : 0,
      probability: Math.min(Math.max(textResult.value.sentiment_score, 0), 1),
      sentiment_label: textResult.value.sentiment_label,
      sentiment_score: textResult.value.sentiment_score,
      model_used: 'text_analyze',
      time: new Date().toLocaleString(),
      content_preview: textForm.content.trim().slice(0, 60),
      source: 'text'
    })
    saveTextPredictionHistory()

    ElMessage.success(t('textAssess.analyzeSuccess'))

    if (!isUnmounted) {
      emit('submitted', { text: textForm.content.trim() })
    }
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('textAssess.analyzeFailed')).detail)
  } finally {
    textSubmitting.value = false
  }
}

const submitTextPredict = async () => {
  if (!textForm.content.trim()) return
  textPredictSubmitting.value = true
  try {
    textPredictResult.value = await modelApi.predictTextModel(textForm.content)

    textPredictionHistory.value.unshift({
      ...textPredictResult.value,
      time: new Date().toLocaleString(),
      content_preview: textForm.content.trim().slice(0, 60),
      // ISS-017 修复：标记 source: 'model' 表示真实模型预测结果
      source: 'model'
    })
    textPredictionHistory.value = textPredictionHistory.value.map(item => ({
      ...item,
      model_used: item.model_used || 'text_depression_model'
    }))
    saveTextPredictionHistory()

    ElMessage.success(t('textAssess.predictSuccess'))
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('textAssess.predictFailed')).detail)
  } finally {
    textPredictSubmitting.value = false
  }
}

onMounted(() => {
  loadTextPredictionHistory()
})

onUnmounted(() => {
  isUnmounted = true
})
</script>

<style scoped>
.card-title {
  font-weight: 600;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.result-panel {
  border-radius: 16px;
}

.result-grid {
  margin-bottom: 10px;
}

.mini-result-card {
  min-height: 260px;
  border-radius: 14px;
}

.mini-title {
  font-weight: 600;
  color: #2c3340;
}
</style>
