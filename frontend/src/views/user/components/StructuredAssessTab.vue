<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="24">
        <el-card class="panel-card">
          <template #header>
            <div class="header-row">
              <span class="card-title">{{ t('structuredAssess.formTitle') }}</span>
              <div class="header-actions">
                <el-radio-group
                  v-model="structuredMode"
                  size="small"
                >
                  <el-radio-button value="single">
                    {{ t('structuredAssess.singleMode') }}
                  </el-radio-button>
                  <el-radio-button value="stepper">
                    {{ t('structuredAssess.stepperMode') }}
                  </el-radio-button>
                </el-radio-group>
                <el-tag
                  type="warning"
                  effect="light"
                >
                  {{ t('structuredAssess.newModelTag') }}
                </el-tag>
              </div>
            </div>
          </template>

          <!-- 单页模式 -->
          <el-form
            v-if="structuredMode === 'single'"
            ref="structuredFormRef"
            :model="structuredForm"
            :rules="structuredRules"
            label-width="120px"
            class="compact-form"
          >
            <BasicInfoStep :form="structuredForm" />
            <AcademicStep :form="structuredForm" />
            <LifestyleStep :form="structuredForm" />
            <MentalHealthStep :form="structuredForm" />
            <el-form-item>
              <el-button
                type="primary"
                :loading="structuredSubmitting"
                @click="submitStructured"
              >
                {{ t('structuredAssess.submit') }}
              </el-button>
              <el-button
                style="margin-left: 8px"
                @click="resetStructuredForm"
              >
                {{ t('structuredAssess.reset') }}
              </el-button>
            </el-form-item>
          </el-form>

          <!-- 分步向导模式 -->
          <el-form
            v-else
            ref="structuredStepFormRef"
            :model="structuredForm"
            :rules="structuredRules"
            label-width="120px"
            class="compact-form"
          >
            <el-steps
              :active="structuredStep"
              finish-status="success"
              simple
            >
              <el-step :title="t('structuredAssess.stepBasicInfo')" />
              <el-step :title="t('structuredAssess.stepAcademic')" />
              <el-step :title="t('structuredAssess.stepLifestyle')" />
              <el-step :title="t('structuredAssess.stepMentalHealth')" />
            </el-steps>

            <BasicInfoStep
              v-show="structuredStep === 0"
              :form="structuredForm"
              class="step-content"
            />

            <AcademicStep
              v-show="structuredStep === 1"
              :form="structuredForm"
              class="step-content"
            />

            <LifestyleStep
              v-show="structuredStep === 2"
              :form="structuredForm"
              class="step-content"
            />

            <MentalHealthStep
              v-show="structuredStep === 3"
              :form="structuredForm"
              class="step-content"
            />

            <div class="step-actions">
              <el-button
                v-if="structuredStep > 0"
                @click="structuredStep--"
              >
                {{ t('structuredAssess.prevStep') }}
              </el-button>
              <el-button
                v-if="structuredStep < 3"
                type="primary"
                @click="handleStepNext"
              >
                {{ t('structuredAssess.nextStep') }}
              </el-button>
              <el-button
                v-else
                type="primary"
                :loading="structuredSubmitting"
                @click="submitStructured"
              >
                {{ t('structuredAssess.submitAssess') }}
              </el-button>
              <el-button
                style="margin-left: 8px"
                @click="resetStructuredForm"
              >
                {{ t('structuredAssess.reset') }}
              </el-button>
            </div>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

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
        v-if="modelTabResult?.requires_human_review"
        style="margin-bottom: 12px"
      >
        <el-alert
          type="warning"
          :closable="false"
          show-icon
        >
          <template #title>
            {{ t('structuredAssess.crisisDetectedAlert') }}<span v-if="modelTabResult?.crisis_keywords_matched?.length">：{{ modelTabResult.crisis_keywords_matched.join('、') }}</span>
          </template>
        </el-alert>
      </div>

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
              :icon="(modelTabResult?.risk_level ?? 0) <= 1 ? 'success' : (modelTabResult?.risk_level ?? 0) <= 2 ? 'warning' : 'error'"
              :title="severityFromLevel(modelTabResult?.risk_level ?? 0)"
            >
              <template #sub-title>
                <p>{{ t('structuredAssess.riskScoreLabel') }}{{ modelTabResult?.risk_score != null ? modelTabResult.risk_score.toFixed(2) : '-' }}</p>
                <p>{{ t('structuredAssess.businessLevelLabel') }}{{ modelTabResult ? severityFromLevel(modelTabResult.risk_level ?? 0) : '-' }}</p>
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
              <el-descriptions-item :label="t('structuredAssess.fallbackLabel')">
                {{ modelTabResult.fallback_used ? t('structuredAssess.yesOption') : t('structuredAssess.noOption') }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('structuredAssess.fallbackReasonLabel')">
                {{ modelTabResult.fallback_reason || t('structuredAssess.notAvailable') }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('structuredAssess.humanReviewLabel')">
                {{ modelTabResult.requires_human_review ? t('structuredAssess.reviewRequired') : t('structuredAssess.reviewNotRequired') }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('structuredAssess.safetyFlagsLabel')">
                {{ formatArrayText(modelTabResult.safety_flags, '、') }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('structuredAssess.crisisKeywordsLabel')">
                {{ formatArrayText(modelTabResult.crisis_keywords_matched, '、') }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('structuredAssess.systemWarningLabel')">
                {{ modelTabResult.warning || t('structuredAssess.notAvailable') }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('structuredAssess.dataQualityLabel')">
                {{ modelTabResult.data_quality?.quality_level || 'unknown' }}
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
              :icon="(structuredResult?.risk_level ?? 0) <= 1 ? 'success' : (structuredResult?.risk_level ?? 0) <= 2 ? 'warning' : 'error'"
              :title="severityFromLevel(structuredResult?.risk_level ?? 0)"
            >
              <template #sub-title>
                <p>{{ t('structuredAssess.riskScoreLabel') }}{{ structuredResult ? structuredResult.risk_score : '-' }}</p>
                <p>{{ t('structuredAssess.severityLabel') }}{{ structuredResult ? structuredResult.severity : '-' }}</p>
                <p>{{ t('structuredAssess.warningTriggeredLabel') }}{{ structuredResult ? (structuredResult.warning_generated ? t('structuredAssess.yesOption') : t('structuredAssess.noOption')) : '-' }}</p>
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

    <el-card style="margin-top: 16px">
      <template #header>
        <div class="header-row">
          <span class="card-title">{{ t('structuredAssess.historyTitle') }}</span>
          <div style="display:flex; gap:8px;">
            <el-button
              size="small"
              :disabled="!predictionHistory.length"
              @click="exportPredictionHistoryCsv"
            >
              {{ t('structuredAssess.exportHistoryBtn') }}
            </el-button>
            <el-button
              size="small"
              type="danger"
              plain
              :disabled="!predictionHistory.length"
              @click="clearPredictionHistory"
            >
              {{ t('structuredAssess.clearHistoryBtn') }}
            </el-button>
          </div>
        </div>
      </template>
      <el-table
        :data="predictionHistory"
        size="small"
        stripe
      >
        <el-table-column
          prop="time"
          :label="t('structuredAssess.colTime')"
          min-width="170"
        />
        <el-table-column
          prop="risk_score"
          :label="t('structuredAssess.colRiskScore')"
          width="110"
        />
        <el-table-column
          prop="risk_level"
          :label="t('structuredAssess.colBusinessLevel')"
          width="90"
        >
          <template #default="{ row }">
            {{ severityFromLevel(row.risk_level) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="severity"
          :label="t('structuredAssess.colSeverity')"
          width="120"
        >
          <template #default="{ row }">
            {{ severityLabel(row.severity) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('structuredAssess.colReviewTriggered')"
          width="100"
        >
          <template #default="{ row }">
            {{ row.warning_generated ? t('structuredAssess.csvYes') : t('structuredAssess.csvNo') }}
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="!predictionHistory.length"
        :description="t('structuredAssess.emptyHistory')"
        :image-size="60"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { userApi } from '@/api/userApi'
import { modelApi, type ModelPredictResponse } from '@/api/modelApi'
import type { StructuredCollectResult } from '@/api/userRiskApi'
import { useAuthStore } from '@/stores/auth'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { useAnalytics } from '@/composables/useAnalytics'
import { sanitizeCellForExcel } from '@/utils/exportUtils'
import {
  severityLabel,
  severityFromLevel,
  routeFamilyLabel,
  routeFamilyTagType,
  routeReasonLabel,
  confidenceTagType,
  confidenceLabel,
  formatArrayText,
} from '@/utils/riskFormatters'
import BasicInfoStep from './structured-steps/BasicInfoStep.vue'
import AcademicStep from './structured-steps/AcademicStep.vue'
import LifestyleStep from './structured-steps/LifestyleStep.vue'
import MentalHealthStep from './structured-steps/MentalHealthStep.vue'
import {
  DEFAULT_STRUCTURED_FORM,
  STEP_FIELDS,
  type StructuredForm,
} from './structured-steps/sharedStepUtils'

interface Props {
  canUse: boolean
}

defineProps<Props>()
const emit = defineEmits<{
  submitted: [data: { featuresJson: string; structuredFormData: Record<string, unknown> }]
  'view-report': []
}>()

const { t } = useI18n()
const auth = useAuthStore()
// P1-5 埋点与隐私：评估流程追踪（不采集问卷内容）
const { track } = useAnalytics()
let isUnmounted = false

// ISS-058 修复：匿名用户（id=0 或未登录）使用会话级随机 ID，避免共享 localStorage 导致历史相互覆盖
const anonSessionId = (() => {
  const key = 'structured_anon_session_id'
  try {
    let id = sessionStorage.getItem(key)
    if (!id) {
      id = 'anon_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8)
      sessionStorage.setItem(key, id)
    }
    return id
  } catch {
    // sessionStorage 不可用时回退到内存随机 ID
    return 'anon_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8)
  }
})()
const historyKey = (base: string) => {
  const userId = auth.user?.id
  if (userId && userId > 0) return `${base}_u${userId}`
  return `${base}_${anonSessionId}`
}
const PREDICTION_HISTORY_KEY = historyKey('prediction_history_v1')

const structuredFormRef = ref<FormInstance>()
const structuredForm = reactive<StructuredForm>({ ...DEFAULT_STRUCTURED_FORM })

const structuredRules: FormRules = {
  identity_type: [{ required: true, message: t('structuredAssess.ruleIdentityType'), trigger: 'change' }],
  age: [{ required: true, type: 'number', min: 15, max: 60, message: t('structuredAssess.ruleAge'), trigger: 'change' }],
  gender: [{ required: true, type: 'number', message: t('structuredAssess.ruleGender'), trigger: 'change' }],
  study_year: [
    {
      validator: (_rule, value, callback) => {
        if (structuredForm.identity_type !== 'student') {
          callback()
          return
        }
        if (typeof value !== 'number' || Number.isNaN(value)) {
          callback(new Error(t('structuredAssess.ruleStudyYearRequired')))
          return
        }
        if (value < 1 || value > 6) {
          callback(new Error(t('structuredAssess.ruleStudyYearRange')))
          return
        }
        callback()
      },
      trigger: 'change'
    }
  ],
  cgpa: [{ required: true, type: 'number', min: 0, max: 10, message: t('structuredAssess.ruleCgpa'), trigger: 'change' }],
  stress_level: [{ required: true, type: 'number', min: 0, max: 5, message: t('structuredAssess.ruleStressLevel'), trigger: 'change' }],
  sleep_duration: [{ required: true, type: 'number', min: 0, max: 12, message: t('structuredAssess.ruleSleepDuration'), trigger: 'change' }],
  social_support: [{ required: true, type: 'number', min: 0, max: 5, message: t('structuredAssess.ruleSocialSupport'), trigger: 'change' }],
  financial_pressure: [{ required: true, type: 'number', min: 0, max: 5, message: t('structuredAssess.ruleFinancialPressure'), trigger: 'change' }],
  family_history: [{ required: true, type: 'number', message: t('structuredAssess.ruleFamilyHistory'), trigger: 'change' }],
  academic_pressure: [{ required: true, type: 'number', min: 0, max: 5, message: t('structuredAssess.ruleAcademicPressure'), trigger: 'change' }],
  exercise_frequency: [{ required: true, type: 'number', min: 0, max: 7, message: t('structuredAssess.ruleExerciseFrequency'), trigger: 'change' }],
  anxiety: [{ required: true, type: 'number', min: 0, max: 5, message: t('structuredAssess.ruleAnxiety'), trigger: 'change' }],
  panic_attack: [{ required: true, type: 'number', message: t('structuredAssess.rulePanicAttack'), trigger: 'change' }],
  treatment_seeking: [{ required: true, type: 'number', message: t('structuredAssess.ruleTreatmentSeeking'), trigger: 'change' }]
}

const predictionHistory = ref<Array<StructuredCollectResult & { time: string }>>([])
const structuredSubmitting = ref(false)
const structuredResult = ref<StructuredCollectResult | null>(null)
const modelTabResult = ref<ModelPredictResponse | null>(null)
const structuredMode = ref<'single' | 'stepper'>('single')
const structuredStep = ref(0)
const structuredStepFormRef = ref<FormInstance>()

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
    row.warning_generated ? t('structuredAssess.csvYes') : t('structuredAssess.csvNo')
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

const handleStepNext = async () => {
  if (!structuredStepFormRef.value) return
  const fields = STEP_FIELDS[structuredStep.value] || []
  try {
    await structuredStepFormRef.value.validateField(fields)
    if (structuredStep.value < 3) {
      structuredStep.value++
    } else {
      await submitStructured()
    }
  } catch {
    ElMessage.warning(t('structuredAssess.stepIncomplete'))
  }
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
    model_predict: modelTabResult.value,
    business_result: structuredResult.value,
  }
  await copyJson(payload)
}

const resetStructuredForm = () => {
  Object.assign(structuredForm, DEFAULT_STRUCTURED_FORM)
  structuredFormRef.value?.resetFields()
  // ISS-014 修复：重置分步向导当前步骤，避免重置后停留在中间步骤
  structuredStep.value = 0
  structuredStepFormRef.value?.resetFields()
}

const buildStructuredFeatures = (): Record<string, number | string> => {
  const dataPayload: Record<string, number | string> = {
    age: structuredForm.age,
    gender: structuredForm.gender,
    cgpa: structuredForm.cgpa,
    stress_level: structuredForm.stress_level,
    sleep_duration: structuredForm.sleep_duration,
    social_support: structuredForm.social_support,
    financial_pressure: structuredForm.financial_pressure,
    family_history: structuredForm.family_history,
    academic_pressure: structuredForm.academic_pressure,
    exercise_frequency: structuredForm.exercise_frequency,
    anxiety: structuredForm.anxiety,
    panic_attack: structuredForm.panic_attack,
    treatment_seeking: structuredForm.treatment_seeking,
    identity_type: structuredForm.identity_type,
    is_student: structuredForm.identity_type === 'student' ? 1 : 0
  }

  if (structuredForm.identity_type === 'student' && typeof structuredForm.study_year === 'number') {
    dataPayload.study_year = structuredForm.study_year
  }
  return dataPayload
}

const submitStructured = async () => {
  const formRef = structuredMode.value === 'stepper' ? structuredStepFormRef.value : structuredFormRef.value
  // ISS-015 修复：分离 catch，记录校验器异常，避免静默吞掉错误导致难以排查
  const valid = await formRef?.validate().catch((err) => {
    console.error('[StructuredAssess] validate error:', err)
    return false
  })
  if (!valid) {
    ElMessage.warning(t('structuredAssess.fixFieldsBeforeSubmit'))
    return
  }

  // P1-5 埋点与隐私：记录开始评估事件（不采集问卷内容）
  track('assessment_start', { assessment_type: 'structured' })

  structuredSubmitting.value = true
  try {
    const dataPayload = buildStructuredFeatures()

    try {
      modelTabResult.value = await modelApi.predictTabularModel(dataPayload)
    } catch (error) {
      modelTabResult.value = null
      console.warn('结构化模型预测接口调用失败，继续保存评估结果', error)
    }

    const result = await userApi.collectStructuredData({
      assessment_type: 'comprehensive',
      data_payload: dataPayload
    })
    structuredResult.value = result

    // P1-5 埋点与隐私：记录完成评估事件（仅采集风险等级，不采集评估内容）
    track('assessment_complete', {
      assessment_type: 'structured',
      risk_level: typeof result?.risk_level === 'number' ? result.risk_level : undefined,
    })

    predictionHistory.value.unshift({
      ...result,
      time: new Date().toLocaleString()
    })
    savePredictionHistory()

    if (modelTabResult.value) {
      ElMessage.success(t('structuredAssess.submitSuccessWithModel'))
    } else {
      ElMessage.success(t('structuredAssess.submitSuccessNoModel'))
    }

    if (!isUnmounted) {
      emit('submitted', {
        featuresJson: JSON.stringify(dataPayload),
        structuredFormData: { ...structuredForm }
      })
    }
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('structuredAssess.submitFailed')).detail)
  } finally {
    structuredSubmitting.value = false
  }
}

onMounted(() => {
  loadPredictionHistory()
})

onUnmounted(() => {
  isUnmounted = true
})
</script>

<style scoped>
.panel-card {
  border-radius: 16px;
}

.compact-form :deep(.el-form-item) {
  margin-bottom: 14px;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.card-title {
  font-weight: 600;
}

.step-content {
  margin-top: 20px;
  min-height: 200px;
}

.step-actions {
  margin-top: 20px;
  display: flex;
  justify-content: flex-start;
  gap: 8px;
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

.result-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.experimental-ref {
  font-size: var(--font-size-extra-small);
  color: #7a8290;
  line-height: 1.7;
  padding: 8px 10px;
  background: rgba(144, 147, 153, 0.06);
  border-radius: 8px;
  border: 1px dashed rgba(144, 147, 153, 0.3);
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
  background: rgba(64, 158, 255, 0.06);
  border-radius: 8px;
  border: 1px solid rgba(64, 158, 255, 0.15);
  flex-wrap: wrap;
}

.routing-reason {
  font-size: var(--font-size-extra-small);
  color: #5a6470;
  flex: 1;
  min-width: 0;
}
</style>
