<template>
  <div>
    <el-card>
      <el-form
        :model="physioForm"
        label-width="120px"
        style="max-width: 600px"
      >
        <el-form-item :label="t('physioAssess.sourceLabel')">
          <el-select
            v-model="physioForm.source"
            style="width: 100%"
          >
            <el-option
              :label="t('physioAssess.sourceManual')"
              value="manual"
            />
            <el-option
              :label="t('physioAssess.sourceWearable')"
              value="wearable"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('physioAssess.sleepHoursLabel')">
          <el-input-number
            v-model="physioForm.sleep_hours"
            :min="0"
            :max="24"
            :step="0.5"
          />
          <span class="field-hint">{{ t('physioAssess.sleepHoursHint') }}</span>
        </el-form-item>
        <el-form-item :label="t('physioAssess.sleepQualityLabel')">
          <el-rate
            v-model="physioForm.sleep_quality"
            :max="5"
            show-score
          />
          <span class="field-hint">{{ t('physioAssess.sleepQualityHint') }}</span>
        </el-form-item>
        <el-form-item :label="t('physioAssess.exerciseMinutesLabel')">
          <el-input-number
            v-model="physioForm.exercise_minutes"
            :min="0"
            :max="480"
            :step="5"
          />
          <span class="field-hint">{{ t('physioAssess.exerciseMinutesHint') }}</span>
        </el-form-item>
        <el-form-item :label="t('physioAssess.heartRateLabel')">
          <el-input-number
            v-model="physioForm.heart_rate"
            :min="30"
            :max="220"
          />
          <span class="field-hint">{{ t('physioAssess.heartRateHint') }}</span>
        </el-form-item>
        <el-form-item :label="t('physioAssess.systolicBpLabel')">
          <el-input-number
            v-model="physioForm.systolic_bp"
            :min="60"
            :max="250"
          />
          <span class="field-hint">{{ t('physioAssess.systolicBpHint') }}</span>
        </el-form-item>
        <el-form-item :label="t('physioAssess.diastolicBpLabel')">
          <el-input-number
            v-model="physioForm.diastolic_bp"
            :min="40"
            :max="150"
          />
          <span class="field-hint">{{ t('physioAssess.diastolicBpHint') }}</span>
        </el-form-item>
        <el-form-item :label="t('physioAssess.stepsLabel')">
          <el-input-number
            v-model="physioForm.steps"
            :min="0"
            :max="100000"
            :step="100"
          />
          <span class="field-hint">{{ t('physioAssess.stepsHint') }}</span>
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            :loading="physioSubmitting"
            :disabled="!canUse"
            @click="submitPhysio"
          >
            {{ t('physioAssess.submitBtn') }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card style="margin-top: 16px">
      <template #header>
        <div class="header-row">
          <span class="card-title">{{ t('physioAssess.historyTitle') }}</span>
          <div style="display:flex; gap:8px;">
            <el-button
              size="small"
              :disabled="!physioHistory.length"
              @click="exportPhysioHistoryCsv"
            >
              {{ t('physioAssess.exportHistoryBtn') }}
            </el-button>
            <el-button
              size="small"
              type="danger"
              plain
              :disabled="!physioHistory.length"
              @click="clearPhysioHistory"
            >
              {{ t('physioAssess.clearHistoryBtn') }}
            </el-button>
          </div>
        </div>
      </template>
      <el-table
        :data="physioHistoryWithTrend"
        size="small"
        stripe
      >
        <el-table-column
          prop="time"
          :label="t('physioAssess.colTime')"
          min-width="170"
        />
        <el-table-column
          :label="t('physioAssess.colSleepHours')"
          width="110"
        >
          <template #default="{ row }">
            <span>{{ row.sleep_hours }}</span>
            <TrendArrow
              :value="row.sleep_hours"
              :prev="row.prev_sleep_hours"
            />
          </template>
        </el-table-column>
        <el-table-column
          prop="sleep_quality"
          :label="t('physioAssess.colSleepQuality')"
          width="90"
        />
        <el-table-column
          :label="t('physioAssess.colExerciseMinutes')"
          width="120"
        >
          <template #default="{ row }">
            <span>{{ row.exercise_minutes }}</span>
            <TrendArrow
              :value="row.exercise_minutes"
              :prev="row.prev_exercise_minutes"
            />
          </template>
        </el-table-column>
        <el-table-column
          :label="t('physioAssess.colHeartRate')"
          width="110"
        >
          <template #default="{ row }">
            <span>{{ row.heart_rate }}</span>
            <TrendArrow
              :value="row.heart_rate"
              :prev="row.prev_heart_rate"
            />
          </template>
        </el-table-column>
        <el-table-column
          prop="systolic_bp"
          :label="t('physioAssess.colSystolicBp')"
          width="90"
        />
        <el-table-column
          prop="diastolic_bp"
          :label="t('physioAssess.colDiastolicBp')"
          width="90"
        />
        <el-table-column
          :label="t('physioAssess.colSteps')"
          min-width="120"
        >
          <template #default="{ row }">
            <span>{{ row.steps }}</span>
            <TrendArrow
              :value="row.steps"
              :prev="row.prev_steps"
            />
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="!physioHistory.length"
        :description="t('physioAssess.emptyHistory')"
        :image-size="60"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { userApi } from '@/api/userApi'
import { useAuthStore } from '@/stores/auth'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { sanitizeCellForExcel } from '@/utils/exportUtils'
import TrendArrow from '@/components/common/TrendArrow.vue'

interface Props {
  canUse: boolean
}

defineProps<Props>()
const emit = defineEmits<{
  submitted: [data: { physiologicalJson: string; physioFormData: Record<string, unknown> }]
}>()

const auth = useAuthStore()
const { t } = useI18n()
let isUnmounted = false

const historyKey = (base: string) => `${base}_u${auth.user?.id ?? 0}`
const PHYSIO_HISTORY_KEY = historyKey('physio_history_v1')

interface PhysioHistoryItem {
  time: string
  sleep_hours: number
  sleep_quality: number
  exercise_minutes: number
  heart_rate: number
  systolic_bp: number
  diastolic_bp: number
  steps: number
}

const physioForm = reactive({
  source: 'manual', sleep_hours: 7, sleep_quality: 3,
  exercise_minutes: 30, heart_rate: 72, systolic_bp: 120,
  diastolic_bp: 80, steps: 5000
})
const physioSubmitting = ref(false)
const physioHistory = ref<PhysioHistoryItem[]>([])

// 计算每条记录相对前一条的趋势，供 TrendArrow 组件展示升降方向。
const physioHistoryWithTrend = computed(() => {
  return physioHistory.value.map((item, index) => {
    const prev = physioHistory.value[index + 1]
    return {
      ...item,
      prev_sleep_hours: prev?.sleep_hours ?? null,
      prev_exercise_minutes: prev?.exercise_minutes ?? null,
      prev_heart_rate: prev?.heart_rate ?? null,
      prev_steps: prev?.steps ?? null
    }
  })
})

const loadPhysioHistory = () => {
  try {
    const raw = localStorage.getItem(PHYSIO_HISTORY_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      physioHistory.value = parsed
    }
  } catch {
    physioHistory.value = []
  }
}

const savePhysioHistory = () => {
  localStorage.setItem(PHYSIO_HISTORY_KEY, JSON.stringify(physioHistory.value.slice(0, 20)))
}

const clearPhysioHistory = () => {
  physioHistory.value = []
  localStorage.removeItem(PHYSIO_HISTORY_KEY)
  ElMessage.success(t('physioAssess.historyCleared'))
}

const exportPhysioHistoryCsv = () => {
  if (!physioHistory.value.length) {
    ElMessage.warning(t('physioAssess.noHistoryToExport'))
    return
  }

  const headers = [t('physioAssess.csvHeaderTime'), t('physioAssess.csvHeaderSleepHours'), t('physioAssess.csvHeaderSleepQuality'), t('physioAssess.csvHeaderExerciseMinutes'), t('physioAssess.csvHeaderHeartRate'), t('physioAssess.csvHeaderSystolicBp'), t('physioAssess.csvHeaderDiastolicBp'), t('physioAssess.csvHeaderSteps')]
  const rows = physioHistory.value.map((row) => [
    row.time,
    row.sleep_hours,
    row.sleep_quality,
    row.exercise_minutes,
    row.heart_rate,
    row.systolic_bp,
    row.diastolic_bp,
    row.steps
  ])

  const csv = [headers, ...rows]
    // 对每个单元格调用 sanitizeCellForExcel 防止 CSV 公式注入
    .map((line) => line.map((cell) => `"${sanitizeCellForExcel(String(cell)).replace(/"/g, '""')}"`).join(','))
    .join('\n')

  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `physio_history_${Date.now()}.csv`
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  ElMessage.success(t('physioAssess.historyCsvExported'))
}

const submitPhysio = async () => {
  // 生理数据既会落到服务端，也会即时写入本地历史，方便用户快速查看趋势。
  physioSubmitting.value = true
  try {
    await userApi.recordPhysiological({ ...physioForm })

    physioHistory.value.unshift({
      time: new Date().toLocaleString(),
      sleep_hours: physioForm.sleep_hours,
      sleep_quality: physioForm.sleep_quality,
      exercise_minutes: physioForm.exercise_minutes,
      heart_rate: physioForm.heart_rate,
      systolic_bp: physioForm.systolic_bp,
      diastolic_bp: physioForm.diastolic_bp,
      steps: physioForm.steps
    })
    savePhysioHistory()

    ElMessage.success(t('physioAssess.recordSuccess'))

    if (!isUnmounted) {
      // 融合预测所需的生理特征字段（不含 source），与原 syncFusionInputsFromLatest 保持一致。
      const physiologicalJson = JSON.stringify({
        sleep_hours: physioForm.sleep_hours,
        sleep_quality: physioForm.sleep_quality,
        exercise_minutes: physioForm.exercise_minutes,
        heart_rate: physioForm.heart_rate,
        systolic_bp: physioForm.systolic_bp,
        diastolic_bp: physioForm.diastolic_bp,
        steps: physioForm.steps,
      })
      emit('submitted', { physiologicalJson, physioFormData: { ...physioForm } })
    }
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('physioAssess.recordFailed')).detail)
  } finally {
    physioSubmitting.value = false
  }
}

onMounted(() => {
  loadPhysioHistory()
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

.field-hint {
  margin-left: 12px;
  color: #909399;
  font-size: 12px;
}
</style>
