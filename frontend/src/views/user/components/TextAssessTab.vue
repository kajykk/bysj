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
            maxlength="5000"
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
            <div class="header-tags">
              <el-tag
                type="success"
                effect="light"
              >
                {{ t('textAssess.newTextModelTag') }}
              </el-tag>
              <el-tag
                v-if="textPredictResult.crisis_detected"
                type="danger"
              >
                {{ t('textAssess.crisisRuleHitTag') }}
              </el-tag>
              <el-tag
                v-if="textPredictResult.requires_human_review"
                type="warning"
              >
                {{ t('textAssess.humanReviewTag') }}
              </el-tag>
            </div>
          </div>
        </template>
        <el-alert
          v-if="textPredictResult.requires_human_review"
          class="review-alert"
          :type="textPredictResult.crisis_detected ? 'error' : 'warning'"
          :closable="false"
          show-icon
          :title="t('textAssess.reviewRequiredTitle')"
        >
          <p class="review-message">
            {{ reviewAlertMessage }}
          </p>
        </el-alert>
        <PopulationScopeNotice :scope="textPredictResult.population_scope" />
        <!-- 第三人称/转述命中只记录、不升级本人风险：中性信息提示，避免红色告警 -->
        <el-alert
          v-if="thirdPersonMatches.length"
          class="third-person-alert"
          type="info"
          :closable="false"
          show-icon
          :title="t('textAssess.thirdPersonNotice')"
        />
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
                :icon="resultIcon"
                :title="resultHeadline"
              >
                <template #sub-title>
                  <!--
                    SEC-FIX-2026-10-05: sentiment_score 原直接 .toFixed(2)。
                    后端 schemas/model_predict.py:39 该字段是 Optional
                    （模型回退路径可能不返回），为 null 时渲染期抛 TypeError
                    导致整棵子树白屏、用户刚提交的结果卡消失。
                    类型已在 api/userRiskApi.ts 一并修正为 number | null。
                  -->
                  <!--
                    P1-13 修复：probability 与 sentiment_score 同源同类型
                    （backend schemas/model_predict.py Optional[float]），
                    上面的注释早就指出"此处是遗漏"，但漏的正是这一行——
                    `null * 100` 直接抛 TypeError。改为与 sentiment_score
                    一致的 != null 防御，null 时显示 '-'。
                  -->
                  <p>{{ t('textAssess.mlPredictionLine') }}{{ textPredictResult.prediction === 1 ? t('textAssess.predictionHighRisk') : t('textAssess.predictionLowRisk') }}</p>
                  <p>{{ t('textAssess.probabilityLabel') }}{{ textPredictResult.probability != null ? (textPredictResult.probability * 100).toFixed(2) + '%' : '-' }}</p>
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
                  {{ predictionDisplay }}
                </el-descriptions-item>
                <el-descriptions-item :label="t('textAssess.predictionProbabilityLabel')">
                  {{ textPredictResult.probability != null ? (textPredictResult.probability * 100).toFixed(2) + '%' : t('textAssess.sentimentLabel') }}
                </el-descriptions-item>
                <el-descriptions-item :label="t('textAssess.riskLevelLabel')">
                  <el-tag :type="decisionTagType">
                    {{ decisionStateText }}
                  </el-tag>
                  <div
                    v-if="reviewReasonList.length"
                    class="review-reason-list"
                  >
                    <span class="review-reason-label">{{ t('textAssess.reviewReasonsLabel') }}</span>
                    <span
                      v-for="reason in reviewReasonList"
                      :key="reason"
                      class="review-reason-item"
                    >{{ reviewReasonLabel(reason) }}</span>
                  </div>
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
        <div
          v-if="scoreComponents"
          class="score-components"
        >
          <div class="section-header">
            <span class="mini-title">{{ t('textAssess.scoreComponentsTitle') }}</span>
            <span class="section-hint">{{ t('textAssess.scoreKindHint') }}</span>
          </div>
          <div class="component-grid">
            <div class="component-item">
              <span class="component-label">{{ t('textAssess.fusedScoreLabel') }}</span>
              <span class="component-value">{{ formatScore(textPredictResult.sentiment_score) }}</span>
            </div>
            <div class="component-item">
              <span class="component-label">{{ t('textAssess.mlProbabilityLabel') }}</span>
              <span class="component-value">{{ formatPercent(scoreComponents.ml_probability) }}</span>
            </div>
            <div class="component-item">
              <span class="component-label">{{ t('textAssess.heuristicScoreLabel') }}</span>
              <span class="component-value">{{ formatScore(scoreComponents.heuristic_score) }}</span>
            </div>
            <div class="component-item">
              <span class="component-label">{{ t('textAssess.weightsLabel') }}</span>
              <span class="component-value">
                {{ t('textAssess.mlWeightShort') }} {{ formatPercent(scoreComponents.model_weight) }} /
                {{ t('textAssess.heuristicWeightShort') }} {{ formatPercent(scoreComponents.heuristic_weight) }}
              </span>
            </div>
            <div class="component-item">
              <span class="component-label">{{ t('textAssess.crisisRuleScoreLabel') }}</span>
              <span class="component-value">{{ formatScore(scoreComponents.crisis_score, 1) }}</span>
            </div>
            <div class="component-item">
              <span class="component-label">{{ t('textAssess.decisionSourceLabel') }}</span>
              <span class="component-value">
                {{ scoreComponents.decision_source === 'crisis_rule' ? t('textAssess.decisionSourceCrisis') : t('textAssess.decisionSourceFusion') }}
              </span>
            </div>
            <div
              v-if="chunkInfo"
              class="component-item"
            >
              <span class="component-label">{{ t('textAssess.chunkingLabel') }}</span>
              <span class="component-value">
                {{ t('textAssess.chunkingValue', { count: chunkInfo.chunk_count, size: chunkInfo.chunk_size, aggregation: chunkInfo.aggregation }) }}
              </span>
            </div>
          </div>
        </div>
        <div
          v-if="hasEvidence"
          class="evidence-block"
        >
          <div class="evidence-row">
            <span class="evidence-label">{{ t('textAssess.riskFactorsLabel') }}</span>
            <div class="evidence-tags">
              <el-tag
                v-for="factor in riskFactorList"
                :key="factor"
                type="danger"
                size="small"
              >
                {{ factor }}
              </el-tag>
              <span
                v-if="!riskFactorList.length"
                class="evidence-none"
              >{{ t('textAssess.noneLabel') }}</span>
            </div>
          </div>
          <div class="evidence-row">
            <span class="evidence-label">{{ t('textAssess.protectiveFactorsLabel') }}</span>
            <div class="evidence-tags">
              <el-tag
                v-for="factor in protectiveFactorList"
                :key="factor"
                type="success"
                size="small"
              >
                {{ factor }}
              </el-tag>
              <span
                v-if="!protectiveFactorList.length"
                class="evidence-none"
              >{{ t('textAssess.noneLabel') }}</span>
            </div>
          </div>
          <div class="evidence-row">
            <span class="evidence-label">{{ t('textAssess.ruleHitLabel') }}</span>
            <div class="evidence-tags">
              <el-tag
                v-for="keyword in crisisKeywords"
                :key="keyword"
                type="danger"
                effect="dark"
                size="small"
              >
                {{ keyword }}
              </el-tag>
              <span
                v-if="!crisisKeywords.length"
                class="evidence-none"
              >{{ t('textAssess.noneLabel') }}</span>
            </div>
          </div>
          <div
            v-if="suppressedKeywords.length"
            class="evidence-row evidence-muted"
          >
            <span class="evidence-label">{{ t('textAssess.suppressedRuleLabel') }}</span>
            <div class="evidence-tags">
              <el-tag
                v-for="keyword in suppressedKeywords"
                :key="keyword"
                type="info"
                size="small"
              >
                {{ keyword }}
              </el-tag>
            </div>
          </div>
        </div>
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
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { userApi } from '@/api/userApi'
import { modelApi, type TextPredictModelResult } from '@/api/modelApi'
import type { TextAnalyzeResult } from '@/api/userRiskApi'
import { useAuthStore } from '@/stores/auth'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { historyKeyWithUser } from '@/utils/sensitiveStorage'
import { formatDate } from '@/utils/formatUtils'
import { reviewReasonLabel, severityFromLevel } from '@/utils/riskFormatters'
import {
  useTextPredictionHistory,
  type TextPredictionHistoryItem,
} from './composables/useTextPredictionHistory'
import PopulationScopeNotice from './PopulationScopeNotice.vue'
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

// 融合分是风险分，不是置信度：分量单独展示，避免让用户把 0.8 理解为「80% 确诊」。
const scoreComponents = computed(() => textPredictResult.value?.score_components ?? null)
const chunkInfo = computed(() => textPredictResult.value?.chunk_info ?? null)
const crisisKeywords = computed(() => textPredictResult.value?.crisis_keywords ?? [])
const suppressedKeywords = computed(() => textPredictResult.value?.suppressed_crisis_keywords ?? [])
const riskFactorList = computed(() => textPredictResult.value?.risk_factors ?? [])
const protectiveFactorList = computed(() => textPredictResult.value?.protective_factors ?? [])
const reviewReasonList = computed(() => textPredictResult.value?.review_reasons ?? [])
const thirdPersonMatches = computed(() => textPredictResult.value?.third_person_matches ?? [])
// 三态门控优先：文本 risk_level 在 normal/suspect 时为 null（后端语义是「未判定」），
// 直接按等级渲染会把「待复核」伪装成「无风险」。这里统一用 text_decision_state 判定。
const decisionStateText = computed(() => {
  const result = textPredictResult.value
  if (!result) return ''
  if (
    result.crisis_detected ||
    result.text_decision_state === 'high_risk' ||
    (result.risk_level != null && result.risk_level >= 3)
  ) {
    return t('textAssess.decisionHighRisk')
  }
  if (result.text_decision_state === 'suspect') return t('textAssess.decisionSuspect')
  if (result.requires_human_review) return t('textAssess.decisionPending')
  if (result.text_decision_state === 'normal') return t('textAssess.decisionNormal')
  if (result.risk_level == null) return t('textAssess.decisionPending')
  return severityFromLevel(result.risk_level)
})
// 原始 0/1 标签只是模型输出；疑似/待复核时追加说明，避免与「待复核」判定状态冲突
const predictionDisplay = computed(() => {
  const result = textPredictResult.value
  if (!result) return ''
  const raw = result.prediction === 1
    ? t('textAssess.predictionHighRisk')
    : t('textAssess.predictionLowRisk')
  const awaitingFinalDecision =
    result.text_decision_state === 'suspect' ||
    (result.requires_human_review && result.text_decision_state !== 'high_risk')
  return awaitingFinalDecision ? `${raw}（${t('textAssess.rawModelLabelNote')}）` : raw
})
const decisionTagType = computed((): 'success' | 'warning' | 'danger' | 'info' => {
  const result = textPredictResult.value
  if (!result) return 'info'
  if (
    result.crisis_detected ||
    result.text_decision_state === 'high_risk' ||
    (result.risk_level != null && result.risk_level >= 3)
  ) {
    return 'danger'
  }
  if (result.text_decision_state === 'suspect' || result.requires_human_review || result.risk_level == null) {
    return 'warning'
  }
  if (result.text_decision_state === 'normal') return 'success'
  return result.risk_level !== undefined && result.risk_level <= 1 ? 'success' : 'warning'
})
const hasEvidence = computed(() => Boolean(
  crisisKeywords.value.length ||
  suppressedKeywords.value.length ||
  riskFactorList.value.length ||
  protectiveFactorList.value.length
))
const reviewAlertMessage = computed(() =>
  textPredictResult.value?.crisis_detected
    ? t('textAssess.reviewCrisisMessage')
    : t('textAssess.reviewHighScoreMessage')
)
// 结果卡标题不能只反映 ML 的 0/1：危机规则命中时 ML 仍可能给低分，
// 绿色「低风险」会与上方红色复核警示直接矛盾。
const resultIcon = computed(() => {
  const result = textPredictResult.value
  if (!result) return 'success'
  if (
    result.crisis_detected ||
    result.text_decision_state === 'high_risk' ||
    result.text_decision_state === 'suspect' ||
    result.requires_human_review ||
    result.prediction === 1
  ) {
    return 'warning'
  }
  return 'success'
})
const resultHeadline = computed(() => {
  const result = textPredictResult.value
  if (!result) return ''
  if (result.crisis_detected) return t('textAssess.crisisResultTitle')
  if (result.text_decision_state === 'high_risk') return t('textAssess.predictHighRisk')
  if (result.text_decision_state === 'suspect') return t('textAssess.reviewResultTitle')
  if (result.requires_human_review) return t('textAssess.reviewResultTitle')
  if (result.text_decision_state === 'normal') return t('textAssess.predictLowRisk')
  return result.prediction === 1 ? t('textAssess.predictHighRisk') : t('textAssess.predictLowRisk')
})
const formatPercent = (value: number | null | undefined): string =>
  value != null && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : '-'
const formatScore = (value: number | null | undefined, digits = 2): string =>
  value != null && Number.isFinite(value) ? value.toFixed(digits) : '-'
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
      // 此 prediction 由融合后的 sentiment_label 反推，不是模型原始判定
      label_source: 'fused',
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
      source: 'model',
      // prediction 直接来自 /model/predict/text，未融合（与日记流的 'fused' 区分）
      label_source: 'ml'
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
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.header-tags {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  flex-wrap: wrap;
}

.review-alert {
  margin-bottom: var(--spacing-md);
}

.review-message {
  margin: 0;
  font-size: var(--font-size-small);
  line-height: 1.6;
}

.third-person-alert {
  margin-bottom: var(--spacing-md);
}

.review-reason-list {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.review-reason-label {
  color: var(--text-regular);
}

.review-reason-item {
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  border: 1px solid var(--card-border);
}

.score-components {
  margin-top: var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--surface-2);
  border: 1px solid var(--card-border);
  border-radius: var(--radius-md);
}

.section-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-sm);
  flex-wrap: wrap;
}

.section-hint {
  font-size: var(--font-size-extra-small);
  color: var(--text-placeholder);
}

.component-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--spacing-sm);
}

.component-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.component-label {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.component-value {
  font-size: var(--font-size-small);
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.evidence-block {
  margin-top: var(--spacing-sm);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.evidence-row {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-sm);
}

.evidence-muted {
  opacity: 0.72;
}

.evidence-label {
  flex: 0 0 72px;
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
  line-height: 22px;
}

.evidence-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
  align-items: center;
}

.evidence-none {
  font-size: var(--font-size-extra-small);
  color: var(--text-placeholder);
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
  border-radius: var(--radius-lg);
}

.result-grid {
  margin-bottom: 10px;
}

.mini-result-card {
  min-height: 260px;
  border-radius: var(--radius-lg);
}

.mini-title {
  font-weight: 600;
  color: var(--text-primary);
}
</style>
