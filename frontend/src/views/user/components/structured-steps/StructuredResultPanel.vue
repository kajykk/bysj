<template>
  <el-card
    v-if="structuredResult || modelTabResult"
    style="margin-top: 16px"
    class="result-panel"
  >
    <template #header>
      <div class="header-row">
        <span class="card-title">{{ t('structuredAssess.resultTitle') }}</span>
        <el-tag
          type="success"
          effect="light"
        >
          {{ t('structuredAssess.dualResultTag') }}
        </el-tag>
      </div>
    </template>

    <div
      v-if="showCrisisHint"
      style="margin-bottom: 12px"
    >
      <el-alert
        type="warning"
        :closable="false"
        show-icon
      >
        <template #title>
          <span v-if="modelTabResult?.requires_human_review">
            {{ t('structuredAssess.crisisDetectedAlert') }}<span v-if="modelTabResult?.crisis_keywords_matched?.length">：{{ modelTabResult.crisis_keywords_matched.join('、') }}</span>
          </span>
          <span v-else>{{ t('structuredAssess.highRiskHint') }}</span>
        </template>
      </el-alert>
    </div>

    <!-- 兜底评分口径：与校准口径区分，使用中性信息提示 -->
    <el-alert
      v-if="isFallbackThresholdSource"
      class="input-adjust-alert"
      type="info"
      :closable="false"
      show-icon
      :title="t('structuredAssess.fallbackThresholdNotice')"
    />
    <!-- 输入域修正提示：钳制/中性化是保护性处理，用信息态轻提示，不用报错红字 -->
    <el-alert
      v-if="hasInputAdjustments"
      class="input-adjust-alert"
      type="info"
      :closable="false"
      show-icon
      :title="t('structuredAssess.inputAdjustNoticeTitle')"
    >
      <p
        v-if="clampedFieldNames.length"
        class="adjust-line"
      >
        {{ t('structuredAssess.inputClampedNotice', { fields: clampedFieldNames.join('、') }) }}
      </p>
      <p
        v-if="defaultedFieldNames.length"
        class="adjust-line"
      >
        {{ t('structuredAssess.inputDefaultedNotice', { fields: defaultedFieldNames.join('、') }) }}
      </p>
    </el-alert>

    <PopulationScopeNotice :scope="modelTabResult?.population_scope" />
    <div
      v-if="modelTabResult?.routing_info"
      class="routing-info-bar"
    >
      <el-tag
        :type="routeFamilyTagType(modelTabResult.routing_info.selected_model_family)"
        size="small"
        effect="dark"
      >
        {{ routeFamilyLabel(modelTabResult.routing_info.selected_model_family) }}
      </el-tag>
      <span class="routing-reason">{{ routeReasonLabel(modelTabResult.routing_info.routing_reason) }}</span>
      <el-tag
        v-if="modelTabResult.routing_info.prediction_confidence_band"
        :type="confidenceTagType(modelTabResult.routing_info.prediction_confidence_band)"
        size="small"
        effect="plain"
      >
        {{ confidenceLabel(modelTabResult.routing_info.prediction_confidence_band) }}
      </el-tag>
    </div>

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
            <span class="mini-title">{{ t('structuredAssess.modelOverviewTitle') }}</span>
          </template>
          <el-result
            :icon="resultIcon(modelTabResult?.risk_level)"
            :title="modelTabResult ? riskLevelLabel(modelTabResult.risk_level) : '-'"
          >
            <template #sub-title>
              <p>{{ t('structuredAssess.riskScoreLabel') }}{{ modelTabResult?.risk_score != null ? modelTabResult.risk_score.toFixed(2) : '-' }}</p>
              <p class="score-band-note">
                {{ scoreBandNote(modelTabResult?.risk_level) }}
              </p>
              <p>{{ t('structuredAssess.modelNameLabel') }}{{ modelTabResult?.model_used || '-' }}</p>
            </template>
          </el-result>
          <el-descriptions
            v-if="modelTabResult"
            :column="1"
            border
            size="small"
            style="margin-top: 12px"
          >
            <el-descriptions-item :label="t('structuredAssess.modelVersionLabel')">
              {{ modelTabResult.model_version || t('structuredAssess.notAvailable') }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('structuredAssess.modelFamilyLabel')">
              {{ routeFamilyLabel(modelTabResult.model_family) }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('structuredAssess.modelConfidenceLabel')">
              {{ modelTabResult.confidence != null ? (modelTabResult.confidence * 100).toFixed(1) + '%' : t('structuredAssess.notAvailable') }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('structuredAssess.fallbackLabel')">
              {{ modelTabResult.fallback_used ? t('structuredAssess.yesOption') : t('structuredAssess.noOption') }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('structuredAssess.fallbackReasonLabel')">
              {{ fallbackReasonLabel(modelTabResult.fallback_reason) || t('structuredAssess.notAvailable') }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('structuredAssess.humanReviewLabel')">
              {{ modelTabResult.requires_human_review ? t('structuredAssess.reviewRequired') : t('structuredAssess.reviewNotRequired') }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('structuredAssess.safetyFlagsLabel')">
              {{ formatArrayText(modelTabResult.safety_flags?.map(safetyFlagLabel), '、') }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('structuredAssess.crisisKeywordsLabel')">
              {{ formatArrayText(modelTabResult.crisis_keywords_matched, '、') }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('structuredAssess.systemWarningLabel')">
              {{ modelTabResult.warning || t('structuredAssess.notAvailable') }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('structuredAssess.dataQualityLabel')">
              {{ qualityLevelLabel(modelTabResult.data_quality?.quality_level) }}
              <span v-if="modelTabResult.data_quality?.missing_fields?.length">{{ t('structuredAssess.missingFieldsPrefix') }}{{ formatArrayText(modelTabResult.data_quality.missing_fields, '、') }}</span>
            </el-descriptions-item>
          </el-descriptions>
          <div
            v-if="modelTabResult?.routing_info"
            class="experimental-ref"
          >
            <el-divider style="margin: 8px 0" />
            <el-tag
              type="info"
              size="small"
              effect="plain"
            >
              {{ t('structuredAssess.routingInfoTag') }}
            </el-tag>
            <p style="margin-top: 6px">
              {{ t('structuredAssess.selectedModelIdLabel') }}{{ modelTabResult.routing_info.selected_model_id || '-' }}<br>
              {{ t('structuredAssess.selectedModelFamilyLabel') }}{{ routeFamilyLabel(modelTabResult.routing_info.selected_model_family) }}<br>
              {{ t('structuredAssess.routingReasonLabel') }}{{ routeReasonLabel(modelTabResult.routing_info.routing_reason) }}<br>
              {{ t('structuredAssess.featureCoverageLabel') }}{{ modelTabResult.routing_info.feature_coverage_ratio != null ? (modelTabResult.routing_info.feature_coverage_ratio * 100).toFixed(1) + '%' : '-' }}<br>
              {{ t('structuredAssess.confidenceBandLabel') }}{{ confidenceLabel(modelTabResult.routing_info.prediction_confidence_band) }}
            </p>
          </div>
          <div
            v-if="modelTabResult"
            class="experimental-ref"
          >
            <el-divider style="margin: 8px 0" />
            <el-tag
              type="info"
              size="small"
              effect="plain"
            >
              {{ t('structuredAssess.experimentalTitle') }}
            </el-tag>
            <p
              v-if="hasAnyExperimentalField"
              style="margin-top: 6px"
            >
              <template v-if="modelTabResult.experimental_external_score != null">
                {{ t('structuredAssess.experimentalScoreLabel') }}{{ formatScore(modelTabResult.experimental_external_score) }}<br>
                {{ t('structuredAssess.experimentalDeltaLabel') }}{{ formatDelta(modelTabResult.experimental_external_delta) }}<br>
              </template>
              <template v-if="modelTabResult.experimental_external_model">
                {{ t('structuredAssess.experimentalModelLabel') }}{{ modelTabResult.experimental_external_model }}<br>
              </template>
              <template v-if="modelTabResult.adjusted_score != null">
                {{ t('structuredAssess.adjustedScoreLabel') }}{{ formatScore(modelTabResult.adjusted_score) }}<br>
                {{ t('structuredAssess.adjustedDeltaLabel') }}{{ formatDelta(modelTabResult.adjusted_delta) }}<br>
              </template>
              <template v-if="modelTabResult.adapter_version">
                {{ t('structuredAssess.adapterVersionLabel') }}{{ modelTabResult.adapter_version }}<br>
              </template>
            </p>
            <el-alert
              v-else
              type="info"
              :closable="false"
              show-icon
              :title="t('structuredAssess.experimentalUnavailable')"
            />
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card
          shadow="never"
          class="mini-result-card"
        >
          <template #header>
            <span class="mini-title">{{ t('structuredAssess.businessOverviewTitle') }}</span>
          </template>
          <el-result
            :icon="resultIcon(structuredResult?.risk_level)"
            :title="structuredResult ? riskLevelLabel(structuredResult.risk_level) : '-'"
          >
            <template #sub-title>
              <p>{{ t('structuredAssess.riskScoreLabel') }}{{ structuredResult ? formatScore(structuredResult.risk_score) : '-' }}</p>
              <p class="score-band-note">
                {{ scoreBandNote(structuredResult?.risk_level) }}
              </p>
              <p>{{ t('structuredAssess.severityLabel') }}{{ structuredResult ? structuredResult.severity : '-' }}</p>
              <p>{{ t('structuredAssess.warningTriggeredLabel') }}{{ structuredResult ? formatWarningGenerated(structuredResult.warning_generated, 'option') : '-' }}</p>
            </template>
          </el-result>
        </el-card>
      </el-col>
    </el-row>
    <div class="result-actions">
      <el-button
        type="primary"
        @click="emit('view-report')"
      >
        {{ t('structuredAssess.viewReportBtn') }}
      </el-button>
      <el-button
        :disabled="!structuredResult && !modelTabResult"
        @click="copyLatestStructuredResult"
      >
        {{ t('structuredAssess.copyResultBtn') }}
      </el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import type { ModelPredictResponse } from '@/api/modelApi'
import type { StructuredCollectResult } from '@/api/userRiskApi'
import {
  riskLevelLabel,
  routeFamilyLabel,
  routeFamilyTagType,
  routeReasonLabel,
  confidenceTagType,
  confidenceLabel,
  structuredScoreBand,
  STRUCTURED_RISK_THRESHOLDS,
  formatThresholdValues,
  type StructuredThresholds,
  formatArrayText,
} from '@/utils/riskFormatters'
import PopulationScopeNotice from '../PopulationScopeNotice.vue'
import { formatWarningGenerated } from './sharedStepUtils'

interface Props {
  structuredResult: StructuredCollectResult | null
  modelTabResult: ModelPredictResponse | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'view-report': []
}>()

const { t } = useI18n()

// 等级为主、分数为辅：等级标题 + 分数区间说明，消除「90 分 + 中等风险」的直观矛盾。
function resultIcon(level: number | null | undefined): 'success' | 'warning' | 'error' {
  if (level == null || !Number.isFinite(level)) return 'warning'
  if (level <= 1) return 'success'
  if (level === 2) return 'warning'
  return 'error'
}

// 阈值单源优先使用服务端下发值；缺失时回退本地常量，并在文案上显式标注，
// 不允许把两套口径静默混用。
const servedThresholds = computed<{ values: StructuredThresholds; fromServer: boolean }>(() => {
  const raw = props.modelTabResult?.thresholds
  if (
    raw &&
    [raw.mild, raw.moderate, raw.high, raw.critical].every(
      (value) => typeof value === 'number' && Number.isFinite(value)
    )
  ) {
    return { values: raw, fromServer: true }
  }
  return { values: STRUCTURED_RISK_THRESHOLDS, fromServer: false }
})

const isFallbackThresholdSource = computed(
  () => props.modelTabResult?.threshold_source === 'fallback'
)

function scoreBandNote(level: number | null | undefined): string {
  if (level == null || !Number.isFinite(level)) {
    return t('structuredAssess.levelPendingNote')
  }
  const { values, fromServer } = servedThresholds.value
  let note = t('structuredAssess.scoreBandNote', {
    band: structuredScoreBand(level, values),
    thresholds: formatThresholdValues(values),
  })
  if (!fromServer) {
    note += t('structuredAssess.localThresholdSuffix')
  }
  return note
}

// 结构化字段名 → 表单标签 key，用于把输入修正留痕翻译成用户能看懂的字段名
const FIELD_LABEL_KEYS: Record<string, string> = {
  stress_level: 'fieldStressLevel',
  anxiety: 'fieldAnxiety',
  academic_pressure: 'fieldAcademicPressure',
  financial_pressure: 'fieldFinancialPressure',
  social_support: 'fieldSocialSupport',
  sleep_duration: 'fieldSleepDuration',
  exercise_frequency: 'fieldExerciseFrequency',
  cgpa: 'fieldCgpa',
  family_history: 'fieldFamilyHistory',
  panic_attack: 'fieldPanicAttack',
  treatment_seeking: 'fieldTreatmentSeeking',
}

function adjustFieldLabel(field: string): string {
  const key = FIELD_LABEL_KEYS[field]
  return key ? t(`structuredAssess.${key}`) : field
}

const clampedFieldNames = computed(() =>
  (props.modelTabResult?.input_adjustments?.clamped_fields ?? []).map((item) =>
    adjustFieldLabel(item.field)
  )
)

const defaultedFieldNames = computed(() =>
  (
    props.modelTabResult?.defaulted_missing_fields ??
    props.modelTabResult?.input_adjustments?.defaulted_missing_fields ??
    []
  ).map((item) => adjustFieldLabel(item.field))
)

const hasInputAdjustments = computed(
  () => clampedFieldNames.value.length > 0 || defaultedFieldNames.value.length > 0
)

// 回退原因标签：后端下发枚举 code 或动态前缀字符串（forced_by_config: / model_load_failed:），
// 动态前缀仅显示通用文案，未知 code 回退原文（排障信息保留可读性）
function fallbackReasonLabel(reason: string | null | undefined): string {
  if (!reason) return ''
  if (reason.startsWith('forced_by_config')) return t('structuredAssess.fallbackForcedConfig')
  if (reason.startsWith('model_load_failed')) return t('structuredAssess.fallbackModelLoadFailed')
  const map: Record<string, string> = {
    model_not_found: t('structuredAssess.fallbackModelNotFound'),
    dependency_not_installed: t('structuredAssess.fallbackDependencyMissing'),
    prediction_error: t('structuredAssess.fallbackPredictionError'),
    ml_breaker_or_inference_error: t('structuredAssess.fallbackBreakerError'),
    insufficient_information: t('structuredAssess.fallbackInsufficientInformation'),
  }
  return map[reason] ?? reason
}

function qualityLevelLabel(level: string | null | undefined): string {
  if (!level) return t('structuredAssess.notAvailable')
  const map: Record<string, string> = {
    complete: t('structuredAssess.qualityComplete'),
    partial: t('structuredAssess.qualityPartial'),
    poor: t('structuredAssess.qualityPoor'),
  }
  return map[level] ?? level
}

function safetyFlagLabel(flag: string): string {
  return flag === 'crisis_keyword_detected' ? t('structuredAssess.safetyCrisisKeyword') : flag
}

const showCrisisHint = computed(
  () => !!(props.modelTabResult?.requires_human_review || (props.modelTabResult?.risk_level ?? 0) >= 3)
)

// 实验对照可用性：任一实验字段非空即展示数值，否则展示降级文案
const hasAnyExperimentalField = computed(() => {
  const r = props.modelTabResult
  if (!r) return false
  return (
    r.experimental_external_score != null ||
    r.experimental_external_model != null ||
    r.adjusted_score != null ||
    r.adapter_version != null
  )
})

function formatScore(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return t('structuredAssess.notAvailable')
  return value.toFixed(2)
}

function formatDelta(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return t('structuredAssess.notAvailable')
  return (value >= 0 ? '+' : '') + value.toFixed(2)
}

const copyJson = async (value: unknown) => {
  try {
    await navigator.clipboard.writeText(JSON.stringify(value, null, 2))
    ElMessage.success(t('structuredAssess.copiedToClipboard'))
  } catch {
    ElMessage.error(t('structuredAssess.copyFailed'))
  }
}

const copyLatestStructuredResult = async () => {
  const payload = {
    model_predict: props.modelTabResult,
    business_result: props.structuredResult,
  }
  await copyJson(payload)
}
</script>

<style scoped>
.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-weight: 600;
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

.result-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.experimental-ref {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
  line-height: 1.7;
  padding: 8px 10px;
  background: var(--surface-2);
  border-radius: var(--radius-md);
  border: 1px dashed var(--border-color);
}

.experimental-ref p {
  margin: 0;
}

.routing-info-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: var(--primary-light);
  border-radius: var(--radius-md);
  border: 1px solid var(--card-border);
  flex-wrap: wrap;
}

.routing-reason {
  font-size: var(--font-size-extra-small);
  color: var(--text-regular);
  flex: 1;
  min-width: 0;
}

.score-band-note {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.input-adjust-alert {
  margin-bottom: 12px;
}

.adjust-line {
  margin: 2px 0 0;
  font-size: var(--font-size-small);
  line-height: 1.6;
}
</style>
