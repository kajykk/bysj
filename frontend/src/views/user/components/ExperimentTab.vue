<template>
  <div>
    <el-card>
      <template #header>
        <div class="header-row">
          <span class="card-title">{{ t('experimentAssess.panelTitle') }}</span>
          <el-tag type="success">
            {{ t('experimentAssess.huggingFaceTrainerTag') }}
          </el-tag>
        </div>
      </template>
      <el-row :gutter="16">
        <el-col :span="14">
          <el-form
            :model="experimentForm"
            label-width="120px"
            style="max-width: 720px"
          >
            <el-form-item :label="t('experimentAssess.datasetNameLabel')">
              <el-input
                v-model="experimentForm.dataset_name"
                placeholder="bert_training_template"
              />
            </el-form-item>
            <el-form-item :label="t('experimentAssess.sourceTypeLabel')">
              <el-select
                v-model="experimentForm.source_type"
                style="width: 100%"
              >
                <el-option
                  :label="t('experimentAssess.sourceLocal')"
                  value="local"
                />
                <el-option
                  :label="t('experimentAssess.sourceDatabase')"
                  value="database"
                />
              </el-select>
            </el-form-item>
            <el-form-item :label="t('experimentAssess.trainRatioLabel')">
              <el-slider
                v-model="experimentForm.train_ratio"
                :min="0.5"
                :max="0.9"
                :step="0.05"
                show-input
              />
            </el-form-item>
            <el-form-item :label="t('experimentAssess.valRatioLabel')">
              <el-slider
                v-model="experimentForm.val_ratio"
                :min="0.05"
                :max="0.3"
                :step="0.05"
                show-input
              />
            </el-form-item>
            <el-form-item :label="t('experimentAssess.testRatioLabel')">
              <el-slider
                v-model="experimentForm.test_ratio"
                :min="0.05"
                :max="0.3"
                :step="0.05"
                show-input
              />
            </el-form-item>
            <el-form-item>
              <el-space wrap>
                <el-button
                  :loading="experimentLoading && experimentAction === 'import'"
                  @click="importDataset"
                >
                  {{ t('experimentAssess.importBtn') }}
                </el-button>
                <el-button
                  type="primary"
                  :loading="experimentLoading && experimentAction === 'train'"
                  @click="trainBert"
                >
                  {{ t('experimentAssess.trainBtn') }}
                </el-button>
                <el-button
                  type="success"
                  :loading="experimentLoading && experimentAction === 'evaluate'"
                  @click="evaluateBert"
                >
                  {{ t('experimentAssess.evaluateBtn') }}
                </el-button>
                <el-button
                  type="warning"
                  :loading="experimentLoading && experimentAction === 'compare'"
                  @click="compareModels"
                >
                  {{ t('experimentAssess.compareBtn') }}
                </el-button>
              </el-space>
            </el-form-item>
            <el-form-item v-if="experimentLoading && experimentProgress > 0">
              <div class="experiment-progress">
                <span class="progress-label">{{ t('experimentAssess.progressLabel', { action: experimentActionLabel }) }}</span>
                <el-progress
                  :percentage="experimentProgress"
                  :status="experimentProgress >= 100 ? 'success' : undefined"
                />
              </div>
            </el-form-item>
          </el-form>
        </el-col>
        <el-col :span="10">
          <el-card
            shadow="never"
            class="template-card"
          >
            <template #header>
              <span class="card-title">{{ t('experimentAssess.templateTitle') }}</span>
            </template>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              :title="t('experimentAssess.templateAlertTitle')"
            />
            <el-divider />
            <div class="template-path">
              {{ t('experimentAssess.templatePathLabel') }}backend/models/datasets/bert_training_template.csv
            </div>
            <ul class="template-list">
              <li><code>text</code>：{{ t('experimentAssess.templateTextCol') }}</li>
              <li><code>label</code>：{{ t('experimentAssess.templateLabelCol') }}</li>
              <li><code>age</code> / <code>stress_level</code> / <code>sleep_duration</code>：{{ t('experimentAssess.templateAuxFeaturesCol') }}</li>
              <li><code>social_support</code>：{{ t('experimentAssess.templateSocialSupportCol') }}</li>
            </ul>
          </el-card>
        </el-col>
      </el-row>
    </el-card>

    <el-row
      :gutter="16"
      style="margin-top: 16px"
    >
      <el-col :span="12">
        <LossChart
          :data="lossChartData"
          :loading="experimentLoading"
        />
      </el-col>
      <el-col :span="12">
        <AccuracyChart
          :data="accuracyChartData"
          :loading="experimentLoading"
        />
      </el-col>
    </el-row>

    <el-row
      :gutter="16"
      style="margin-top: 16px"
    >
      <el-col :span="14">
        <CompareChart
          :data="compareChartData"
          :loading="experimentLoading"
        />
      </el-col>
      <el-col :span="10">
        <ConfusionChart
          :data="confusionChartData"
          :loading="experimentLoading"
        />
      </el-col>
    </el-row>

    <EvalResultCard
      v-if="experimentRawResult"
      :summary="experimentSummary"
      :confusion-matrix="confusionMatrix"
      :train-log-rows="trainLogRows"
      :eval-log-rows="evalLogRows"
    />

    <MisclassifiedTable
      :sample-rows="sampleRows"
      :dataset-name="experimentForm.dataset_name"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { modelApi, type CompareResult, type EvaluateResult, type TrainResult } from '@/api/modelApi'
import { normalizeHttpError } from '@/utils/errorPolicy'
import LossChart from './experiment-charts/LossChart.vue'
import AccuracyChart from './experiment-charts/AccuracyChart.vue'
import CompareChart from './experiment-charts/CompareChart.vue'
import ConfusionChart from './experiment-charts/ConfusionChart.vue'
import EvalResultCard from './experiment-charts/EvalResultCard.vue'
import MisclassifiedTable from './experiment-charts/MisclassifiedTable.vue'
import type { CompareItem } from './experiment-charts/sharedChartUtils'

const { t } = useI18n()

const experimentForm = reactive({
  dataset_name: 'depression_multimodal_v1',
  source_type: 'local',
  train_ratio: 0.7,
  val_ratio: 0.15,
  test_ratio: 0.15
})
const experimentLoading = ref(false)
const experimentAction = ref<'import' | 'train' | 'evaluate' | 'compare'>('train')
const experimentProgress = ref(0)
const experimentRawResult = ref<string>('')
const experimentSummary = ref<Record<string, unknown> | null>(null)
const confusionMatrix = ref<{ tn: number; fp: number; fn: number; tp: number } | null>(null)
const sampleRows = ref<Array<{ index: number; true_label: number; pred_label: number; score: number }>>([])
const trainLogRows = ref<Record<string, unknown>[]>([])
const evalLogRows = ref<Record<string, unknown>[]>([])

const lossChartData = ref<number[]>([])
const accuracyChartData = ref<number[]>([])
const compareChartData = ref<CompareItem[]>([])
const confusionChartData = ref<number[][]>([])

const experimentActionLabel = computed(() => {
  const map: Record<string, string> = {
    import: t('experimentAssess.actionImport'),
    train: t('experimentAssess.actionTrain'),
    evaluate: t('experimentAssess.actionEvaluate'),
    compare: t('experimentAssess.actionCompare')
  }
  return map[experimentAction.value] || t('experimentAssess.actionDefault')
})

type TrainExperimentResult = TrainResult
type EvaluateExperimentResult = EvaluateResult
type CompareExperimentResult = CompareResult

const applyTrainResult = (res: TrainExperimentResult) => {
  const trainLoss = Array.isArray(res.train_loss) ? res.train_loss.map((n: number) => Number(n)) : []
  const valLoss = Array.isArray(res.val_loss) ? res.val_loss.map((n: number) => Number(n)) : []
  const valAccuracy = Array.isArray(res.val_accuracy) ? res.val_accuracy.map((n: number) => Number(n)) : []
  if (trainLoss.length) lossChartData.value = trainLoss
  else if (valLoss.length) lossChartData.value = valLoss
  if (valAccuracy.length) accuracyChartData.value = valAccuracy
  if (res.trainer_log_history) trainLogRows.value = res.trainer_log_history
  if (res.eval_history) evalLogRows.value = res.eval_history
  experimentSummary.value = {
    train_loss: Array.isArray(res.train_loss) ? res.train_loss.join(' / ') : (res.train_loss ?? '-'),
    val_loss: Array.isArray(res.val_loss) ? res.val_loss.join(' / ') : (res.val_loss ?? '-'),
    val_accuracy: Array.isArray(res.val_accuracy) ? res.val_accuracy.join(' / ') : (res.val_accuracy ?? '-'),
    status: res.status
  }
  experimentRawResult.value = JSON.stringify(res, null, 2)
}

const applyEvaluateResult = (res: EvaluateExperimentResult) => {
  const cm = res.confusion_matrix
  confusionMatrix.value = {
    tn: cm.tn,
    fp: cm.fp,
    fn: cm.fn,
    tp: cm.tp,
  }
  confusionChartData.value = [[cm.tn, cm.fp], [cm.fn, cm.tp]]
  sampleRows.value = res.prediction_samples
  experimentSummary.value = {
    train_loss: experimentSummary.value?.train_loss ?? '-',
    val_loss: experimentSummary.value?.val_loss ?? '-',
    val_accuracy: res.metrics.accuracy,
    status: 'evaluated'
  }
  if (res.eval_history) evalLogRows.value = res.eval_history
  experimentRawResult.value = JSON.stringify(res, null, 2)
}

const applyCompareResult = (res: CompareExperimentResult) => {
  compareChartData.value = res.results
  experimentRawResult.value = JSON.stringify(res, null, 2)
}

const importDataset = async () => {
  experimentLoading.value = true
  experimentAction.value = 'import'
  experimentProgress.value = 0
  try {
    const res = await modelApi.importDataset(experimentForm)
    experimentProgress.value = 100
    experimentSummary.value = {
      train_loss: '-',
      val_loss: '-',
      val_accuracy: '-',
      status: res.message
    }
    experimentRawResult.value = JSON.stringify(res, null, 2)
    ElMessage.success(t('experimentAssess.importSuccess'))
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('experimentAssess.importFailed')).detail)
  } finally {
    experimentLoading.value = false
    experimentProgress.value = 0
  }
}

const trainBert = async () => {
  experimentLoading.value = true
  experimentAction.value = 'train'
  experimentProgress.value = 10
  try {
    const res = await modelApi.trainModel({ dataset_name: experimentForm.dataset_name, model_name: 'text_bert_classifier', epochs: 3, batch_size: 16, learning_rate: 2e-5 })
    experimentProgress.value = 100
    applyTrainResult(res)
    ElMessage.success(t('experimentAssess.trainSuccess'))
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('experimentAssess.trainFailed')).detail)
  } finally {
    experimentLoading.value = false
    experimentProgress.value = 0
  }
}

const evaluateBert = async () => {
  experimentLoading.value = true
  experimentAction.value = 'evaluate'
  experimentProgress.value = 20
  try {
    const res = await modelApi.evaluateModel({ dataset_name: experimentForm.dataset_name, model_name: 'text_bert_classifier', split: 'validation' })
    experimentProgress.value = 100
    applyEvaluateResult(res)
    experimentSummary.value = {
      train_loss: experimentSummary.value?.train_loss ?? '-',
      val_loss: experimentSummary.value?.val_loss ?? '-',
      val_accuracy: res.metrics?.accuracy ?? '-',
      status: 'evaluated'
    }
    ElMessage.success(t('experimentAssess.evaluateSuccess'))
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('experimentAssess.evaluateFailed')).detail)
  } finally {
    experimentLoading.value = false
    experimentProgress.value = 0
  }
}

const compareModels = async () => {
  experimentLoading.value = true
  experimentAction.value = 'compare'
  experimentProgress.value = 30
  try {
    const res = await modelApi.compareModels({ dataset_name: experimentForm.dataset_name, model_names: ['text_bert_classifier', 'text_depression_model', 'fusion_dnn_best'] })
    experimentProgress.value = 100
    applyCompareResult(res)
    ElMessage.success(t('experimentAssess.compareSuccess'))
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('experimentAssess.compareFailed')).detail)
  } finally {
    experimentLoading.value = false
    experimentProgress.value = 0
  }
}
</script>

<style scoped>
.template-card {
  min-height: 100%;
}

.template-path {
  font-size: var(--font-size-small);
  color: #5a6470;
  margin-bottom: 12px;
}

.template-list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.8;
}

.card-title {
  font-weight: 600;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.experiment-progress {
  width: 100%;
}

.progress-label {
  font-size: var(--font-size-small);
  color: #5a6470;
  margin-bottom: 8px;
  display: block;
}
</style>
