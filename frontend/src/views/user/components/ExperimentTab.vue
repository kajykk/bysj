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
        <!-- BLANK-07 修复：补充响应式断点，窄屏下堆叠为整行，避免列被压缩成窄条 -->
        <el-col
          :xs="24"
          :sm="24"
          :md="14"
        >
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
                  :disabled="experimentLoading"
                  @click="importDataset"
                >
                  {{ t('experimentAssess.importBtn') }}
                </el-button>
                <!-- F-32 / RES-P2-039-01: BERT 入口永久禁用（无 @click）—— 不可达处理函数已移除，
                     保留禁用态与 title 解释，避免用户看到「点了必报错的坏按钮」。 -->
                <el-button
                  type="primary"
                  :disabled="bertDisabled"
                  :title="bertDisabled ? t('experimentAssess.bertDisabled') : undefined"
                >
                  {{ t('experimentAssess.trainBtn') }}
                </el-button>
                <el-button
                  type="success"
                  :disabled="bertDisabled"
                  :title="bertDisabled ? t('experimentAssess.bertDisabled') : undefined"
                >
                  {{ t('experimentAssess.evaluateBtn') }}
                </el-button>
                <el-button
                  type="warning"
                  :loading="experimentLoading && experimentAction === 'compare'"
                  :disabled="experimentLoading"
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
        <el-col
          :xs="24"
          :sm="24"
          :md="10"
        >
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
      <el-col
        :xs="24"
        :sm="24"
        :md="12"
      >
        <LossChart
          :data="lossChartData"
          :loading="experimentLoading"
        />
      </el-col>
      <el-col
        :xs="24"
        :sm="24"
        :md="12"
      >
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
      <el-col
        :xs="24"
        :sm="24"
        :md="14"
      >
        <CompareChart
          :data="compareChartData"
          :loading="experimentLoading"
        />
      </el-col>
      <el-col
        :xs="24"
        :sm="24"
        :md="10"
      >
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
import { modelApi, type CompareResult } from '@/api/modelApi'
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
const experimentAction = ref<'import' | 'compare'>('import')
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
    compare: t('experimentAssess.actionCompare')
  }
  return map[experimentAction.value] || t('experimentAssess.actionDefault')
})

type CompareExperimentResult = CompareResult

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

// AUDIT-2026-10-04 (P0-1 衍生) / RES-P2-039-01（保留决议，见 docs/RETENTION_REGISTRY.md）：
// BERT 权重已归档到 models/_archive/、注册条目已从 MODEL_PATHS 移除 —— 训练/评估 BERT
// 必然失败（加载时以「未注册」拒绝）。入口显式禁用，而不是让用户点了才收到报错。
// 恢复能力需同时恢复权重与注册条目（或走句向量路线）。
//
// F-32 拆分裁定（第十一轮）：原先 `trainBert` / `evaluateBert` 两个处理函数在
// `if (bertDisabled) return` 之后有约 40 行**永不可达**的函数体，已移除。
// 保留常量 + 禁用态 + 解释文案（UX），不保留不可达代码 —— 二者不是一回事。
const bertDisabled = true

const compareModels = async () => {
  experimentLoading.value = true
  experimentAction.value = 'compare'
  experimentProgress.value = 30
  try {
    // AUDIT-2026-10-04: 对比列表不再包含 text_bert_classifier（已归档，命中必失败）
    const res = await modelApi.compareModels({ dataset_name: experimentForm.dataset_name, model_names: ['text_depression_model', 'fusion_dnn_best'] })
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
