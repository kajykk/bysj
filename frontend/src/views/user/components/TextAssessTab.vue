<template>
  <div>
    <el-card>
      <el-form
        :model="textForm"
        label-width="100px"
        class="form-max-width"
      >
        <el-form-item :label="t('textAssess.entryTypeLabel')">
          <el-select
            v-model="textForm.entry_type"
            class="full-width"
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
            class="full-width"
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
            class="btn-ml"
            type="success"
            :loading="textPredictSubmitting"
            :disabled="!textForm.content.trim()"
            @click="submitTextPredict"
          >
            {{ t('textAssess.predictBtn') }}
          </el-button>
          <!-- AUDIT-2026-10-01（决策三 P6）：接入 POST /user/data/draft，长文本中断可续填 -->
          <el-button
            class="btn-ml"
            :loading="draftSaving"
            :disabled="!textForm.content.trim()"
            @click="saveDraft"
          >
            {{ t('textAssess.saveDraftBtn') }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <Transition name="fade-slide">
      <el-card
        v-if="textResult"
        class="card-gap"
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
        class="card-gap result-panel"
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
          <!-- BLANK-07 修复：补充响应式断点，窄屏下两张结果卡整行堆叠 -->
          <el-col
            :xs="24"
            :sm="24"
            :md="12"
          >
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
                  <!--
                    SEC-FIX-2026-10-05: sentiment_score 原直接 .toFixed(2)。
                    后端 schemas/model_predict.py:39 该字段是 Optional
                    （模型回退路径可能不返回），为 null 时渲染期抛 TypeError
                    导致整棵子树白屏、用户刚提交的结果卡消失。
                    下方 246/252 行本就做了 != null 防御，此处是遗漏。
                    类型已在 api/userRiskApi.ts 一并修正为 number | null。
                  -->
                  <p>{{ t('textAssess.probabilityLabel') }}{{ (textPredictResult.probability * 100).toFixed(2) }}%</p>
                  <p>{{ t('textAssess.sentimentLabelField') }}{{ textPredictResult.sentiment_label || t('textAssess.sentimentLabel') }}</p>
                  <p>{{ t('textAssess.sentimentScoreFieldLabel') }}{{ textPredictResult.sentiment_score != null ? textPredictResult.sentiment_score.toFixed(2) : '-' }}</p>
                  <p>{{ t('textAssess.modelNameFieldLabel') }}{{ textPredictResult.model_used }}</p>
                </template>
              </el-result>
            </el-card>
          </el-col>
          <el-col
            :xs="24"
            :sm="24"
            :md="12"
          >
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

    <TextPredictionHistoryCard
      :history="textPredictionHistory"
      @clear="clearTextPredictionHistory"
      @export="exportTextPredictionHistoryCsv"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { userApi } from '@/api/userApi'
import { modelApi, type TextPredictModelResult } from '@/api/modelApi'
import type { TextAnalyzeResult } from '@/api/userRiskApi'
import { useAuthStore } from '@/stores/auth'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { historyKeyWithUser } from '@/utils/sensitiveStorage'
import { formatDate } from '@/utils/formatUtils'
import {
  useTextPredictionHistory,
  type TextPredictionHistoryItem,
} from './composables/useTextPredictionHistory'
import TextPredictionHistoryCard from './TextPredictionHistoryCard.vue'

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

// SEC-FIX (H4 补强): 匿名用户不再共享 `_u0` key (互相覆盖/可读),
// 改为会话级隔离, 且与 clearSensitiveLocalStorage 清理模式对齐
const historyKey = (base: string) => historyKeyWithUser(base, auth.user?.id)
// ISS-017 修复：历史记录增加 source 字段，区分文本分析伪造记录与真实模型预测记录
const {
  textPredictionHistory,
  load: loadTextPredictionHistory,
  save,
  unshift: unshiftTextPredictionHistory,
  clear: clearTextPredictionHistory,
  exportCsv: exportTextPredictionHistoryCsv,
} = useTextPredictionHistory(historyKey('text_prediction_history_v1'))

const textForm = reactive({
  entry_type: 'diary', content: '', emotion_tags: [] as string[], mood_score: 3
})
const textSubmitting = ref(false)
const textPredictSubmitting = ref(false)
const textResult = ref<TextAnalyzeResult | null>(null)
const textPredictResult = ref<TextPredictModelResult | null>(null)
// SEC-FIX (M8): 提交成功后清空输入, 避免误触重复提交
const resetTextForm = () => {
  textForm.content = ''
  textForm.emotion_tags = []
  textForm.mood_score = 3
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

    unshiftTextPredictionHistory({
      // ISS-017 修复：标记 source: 'text' 表示由文本分析伪造的预测字段，便于后续按来源过滤
      prediction: textResult.value.sentiment_label === 'negative' ? 1 : 0,
      probability: Math.min(Math.max(textResult.value.sentiment_score, 0), 1),
      sentiment_label: textResult.value.sentiment_label,
      sentiment_score: textResult.value.sentiment_score,
      model_used: 'text_analyze',
      time: formatDate(new Date()),
      content_preview: textForm.content.trim().slice(0, 60),
      source: 'text'
    })

    ElMessage.success(t('textAssess.analyzeSuccess'))

    if (!isUnmounted) {
      emit('submitted', { text: textForm.content.trim() })
    }
    // SEC-FIX (M8): 提交成功后重置输入 (emit 在重置前, 确保父组件拿到原文)
    resetTextForm()
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

    const item: TextPredictionHistoryItem = {
      ...textPredictResult.value,
      time: formatDate(new Date()),
      content_preview: textForm.content.trim().slice(0, 60),
      // ISS-017 修复：标记 source: 'model' 表示真实模型预测结果
      source: 'model'
    }
    unshiftTextPredictionHistory(item)
    textPredictionHistory.value = textPredictionHistory.value.map(entry => ({
      ...entry,
      model_used: entry.model_used || 'text_depression_model'
    }))
    save()

    ElMessage.success(t('textAssess.predictSuccess'))
    // SEC-FIX (M8): 提交成功后重置输入
    resetTextForm()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('textAssess.predictFailed')).detail)
  } finally {
    textPredictSubmitting.value = false
  }
}

// ── AUDIT-2026-10-01（决策三 P6）：文本填报草稿（POST/GET /user/data/draft）──
// draft_type 为前端与后端约定的自由串（1-50 字符），固定用于文本评估场景
const TEXT_DRAFT_TYPE = 'text_assessment'
const draftSaving = ref(false)

const saveDraft = async () => {
  if (!textForm.content.trim()) return
  draftSaving.value = true
  try {
    await userApi.saveDraft(TEXT_DRAFT_TYPE, {
      entry_type: textForm.entry_type,
      content: textForm.content,
      emotion_tags: textForm.emotion_tags,
      mood_score: textForm.mood_score
    })
    ElMessage.success(t('textAssess.saveDraftSuccess'))
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('textAssess.saveDraftFailed')).detail)
  } finally {
    draftSaving.value = false
  }
}

/** 把草稿 payload 安全地写回表单：字段类型不符时保留当前值，不盲目信任存量数据 */
const applyDraftPayload = (payload: Record<string, unknown>) => {
  if (typeof payload.entry_type === 'string' && ['diary', 'social', 'vent'].includes(payload.entry_type)) {
    textForm.entry_type = payload.entry_type
  }
  if (typeof payload.content === 'string') {
    textForm.content = payload.content.slice(0, 500)
  }
  if (Array.isArray(payload.emotion_tags)) {
    textForm.emotion_tags = payload.emotion_tags.filter((tag): tag is string => typeof tag === 'string')
  }
  if (typeof payload.mood_score === 'number' && payload.mood_score >= 1 && payload.mood_score <= 5) {
    textForm.mood_score = Math.round(payload.mood_score)
  }
}

const loadDraft = async () => {
  try {
    const draft = await userApi.getDraft(TEXT_DRAFT_TYPE)
    const payload = draft?.data_payload ?? {}
    if (typeof payload.content !== 'string' || !payload.content.trim()) return
    try {
      await ElMessageBox.confirm(t('textAssess.restoreFoundMsg'), t('textAssess.restoreFoundTitle'), {
        confirmButtonText: t('textAssess.restoreYes'),
        cancelButtonText: t('textAssess.restoreNo'),
        type: 'info'
      })
      applyDraftPayload(payload)
      ElMessage.success(t('textAssess.draftRestored'))
    } catch {
      // 用户选择放弃：用空内容覆盖后端草稿，避免下次进入重复询问
      textForm.content = ''
      userApi.saveDraft(TEXT_DRAFT_TYPE, { content: '' }).catch(() => {
        // 覆盖失败只影响下次是否重复询问，不打断当前流程
      })
    }
  } catch {
    // 草稿读取失败（网络/5xx）静默跳过：草稿恢复是非关键路径，不阻塞评估主流程
  }
}

onMounted(() => {
  loadTextPredictionHistory()
  loadDraft()
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

/* VIS-P3-01 修复：内联样式收敛为样式类 + 设计令牌 */
.form-max-width {
  max-width: 600px;
}

.full-width {
  width: 100%;
}

.btn-ml {
  margin-left: var(--spacing-sm);
}

.card-gap {
  margin-top: var(--spacing-md);
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
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
