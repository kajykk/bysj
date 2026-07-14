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

    <StructuredResultPanel
      :structured-result="structuredResult"
      :model-tab-result="modelTabResult"
      @view-report="emit('view-report')"
    />

    <StructuredHistoryCard
      :prediction-history="predictionHistory"
      @clear="clearPredictionHistory"
      @export="exportPredictionHistoryCsv"
    />
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
import { normalizeHttpError } from '@/utils/errorPolicy'
import { useAnalytics } from '@/composables/useAnalytics'
import BasicInfoStep from './structured-steps/BasicInfoStep.vue'
import AcademicStep from './structured-steps/AcademicStep.vue'
import LifestyleStep from './structured-steps/LifestyleStep.vue'
import MentalHealthStep from './structured-steps/MentalHealthStep.vue'
import StructuredResultPanel from './structured-steps/StructuredResultPanel.vue'
import StructuredHistoryCard from './structured-steps/StructuredHistoryCard.vue'
import {
  DEFAULT_STRUCTURED_FORM,
  STEP_FIELDS,
  type StructuredForm,
} from './structured-steps/sharedStepUtils'
import { usePredictionHistory } from './structured-steps/usePredictionHistory'

interface Props {
  canUse: boolean
}

defineProps<Props>()
const emit = defineEmits<{
  submitted: [data: { featuresJson: string; structuredFormData: Record<string, unknown> }]
  'view-report': []
}>()

const { t } = useI18n()
// P1-5 埋点与隐私：评估流程追踪（不采集问卷内容）
const { track } = useAnalytics()
let isUnmounted = false

const {
  predictionHistory,
  loadPredictionHistory,
  clearPredictionHistory,
  exportPredictionHistoryCsv,
  addPredictionEntry,
} = usePredictionHistory()

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

const structuredSubmitting = ref(false)
const structuredResult = ref<StructuredCollectResult | null>(null)
const modelTabResult = ref<ModelPredictResponse | null>(null)
const structuredMode = ref<'single' | 'stepper'>('single')
const structuredStep = ref(0)
const structuredStepFormRef = ref<FormInstance>()

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

    addPredictionEntry(result)

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
</style>
