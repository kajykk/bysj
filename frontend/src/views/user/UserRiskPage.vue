<template>
  <div class="risk-page">
    <div class="risk-page__summary">
      <p class="risk-page__eyebrow">
        {{ t('userRisk.pageEyebrow') }}
      </p>
      <h2>{{ t('userRisk.pageTitle') }}</h2>
      <p>{{ t('userRisk.pageLede') }}</p>
      <div class="risk-page__actions">
        <el-button
          type="primary"
          @click="activeTab = 'structured'"
        >
          {{ t('userRisk.quickStartStructured') }}
        </el-button>
        <el-button
          @click="activeTab = 'report'"
        >
          {{ t('userRisk.quickViewReport') }}
        </el-button>
      </div>
    </div>
    <el-tabs
      v-model="activeTab"
      type="border-card"
    >
      <el-tab-pane
        :label="t('userRisk.tabReport')"
        name="report"
        lazy
      >
        <RiskReportTab
          :report="report"
          :loading="reportLoading"
          :error="reportError"
          :can-export="canExportRisk"
          :trend-data="reportTrendData"
          @retry="loadReport"
          @export="handleExport"
        />
      </el-tab-pane>

      <el-tab-pane
        v-if="canUsePrediction"
        :label="t('userRisk.tabStructured')"
        name="structured"
        lazy
      >
        <StructuredAssessTab
          :can-use="canUsePrediction"
          @submitted="handleStructuredSubmitted"
          @view-report="activeTab = 'report'"
        />
      </el-tab-pane>

      <el-tab-pane
        v-if="canUsePrediction"
        :label="t('userRisk.tabText')"
        name="text"
        lazy
      >
        <TextAssessTab
          :can-use="canUsePrediction"
          @submitted="handleTextSubmitted"
        />
      </el-tab-pane>

      <el-tab-pane
        v-if="canUsePrediction"
        :label="t('userRisk.tabFusion')"
        name="fusion"
        lazy
      >
        <el-card>
          <el-form
            :model="fusionForm"
            label-width="120px"
            style="max-width: 760px"
          >
            <el-form-item :label="t('userRisk.fusionTextLabel')">
              <el-input
                v-model="fusionForm.text"
                type="textarea"
                :rows="5"
                :placeholder="t('userRisk.fusionTextPlaceholder')"
              />
            </el-form-item>
            <el-form-item :label="t('userRisk.fusionFeaturesLabel')">
              <el-input
                v-model="fusionForm.featuresJson"
                type="textarea"
                :rows="6"
                :placeholder="t('userRisk.fusionFeaturesPlaceholder')"
              />
            </el-form-item>
            <el-form-item :label="t('userRisk.fusionPhysiologicalLabel')">
              <el-input
                v-model="fusionForm.physiologicalJson"
                type="textarea"
                :rows="6"
                :placeholder="t('userRisk.fusionPhysiologicalPlaceholder')"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="fusionSubmitting"
                @click="() => submitFusion()"
              >
                {{ t('userRisk.btnFusion') }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card
          v-if="fusionResult"
          style="margin-top: 16px"
        >
          <template #header>
            <div class="header-row">
              <span class="card-title">{{ t('userRisk.fusionResultTitle') }}</span>
              <div style="display: flex; gap: 8px;">
                <el-tag
                  v-if="fusionResult.crisis_override"
                  type="danger"
                  effect="dark"
                >
                  {{ t('userRisk.fusionCrisisOverride') }}
                </el-tag>
                <el-tag
                  v-if="fusionResult.review_required"
                  type="warning"
                  effect="dark"
                >
                  {{ t('userRisk.fusionReviewRequired') }}
                </el-tag>
              </div>
            </div>
          </template>
          <el-result
            :icon="fusionResult.risk_level <= 1 ? 'success' : fusionResult.risk_level <= 2 ? 'warning' : 'error'"
            :title="fusionResult.severity"
          >
            <template #sub-title>
              <p>{{ t('userRisk.fusionScoreLabel') }}{{ fusionResult.risk_score.toFixed(2) }}</p>
              <p>{{ t('userRisk.fusionSeverityLabel') }}{{ severityFromLevel(fusionResult.risk_level) }}</p>
              <p>{{ t('userRisk.fusionModelVersionLabel') }}{{ fusionResult.model_version || t('userRisk.notAvailable') }}</p>
              <p>{{ t('userRisk.fusionModelNameLabel') }}{{ formatArrayText(fusionResult.model_used, ' / ') }}</p>
            </template>
          </el-result>
          <el-descriptions
            :column="2"
            border
            style="margin-top: 12px"
          >
            <el-descriptions-item :label="t('userRisk.labelReviewStatus')">
              {{ fusionResult.review_required ? t('userRisk.reviewRequired') : t('userRisk.reviewNotRequired') }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('userRisk.labelCrisisOverride')">
              {{ fusionResult.crisis_override ? t('userRisk.yesOption') : t('userRisk.noOption') }}
            </el-descriptions-item>
            <el-descriptions-item
              :label="t('userRisk.labelReviewReason')"
              :span="2"
            >
              <el-tag
                v-for="reason in fusionResult.review_triggers"
                :key="reason"
                type="warning"
                size="small"
                style="margin-right: 4px; margin-bottom: 4px"
              >
                {{ reason }}
              </el-tag>
              <span v-if="!fusionResult.review_triggers?.length">{{ t('userRisk.notAvailable') }}</span>
            </el-descriptions-item>
            <el-descriptions-item :label="t('userRisk.labelInterventionLevel')">
              {{ fusionResult.intervention_level || t('userRisk.notAvailable') }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('userRisk.labelGateWeights')">
              {{ formatArrayText(fusionResult.fusion_detail?.gate_weights) }}
            </el-descriptions-item>
            <el-descriptions-item
              :label="t('userRisk.labelModalityScores')"
              :span="2"
            >
              {{ fusionResult.fusion_detail?.modality_scores ? JSON.stringify(fusionResult.fusion_detail.modality_scores) : t('userRisk.notAvailable') }}
            </el-descriptions-item>
            <el-descriptions-item
              :label="t('userRisk.labelWeightsInfo')"
              :span="2"
            >
              {{ fusionResult.fusion_detail?.weights ? JSON.stringify(fusionResult.fusion_detail.weights) : t('userRisk.notAvailable') }}
            </el-descriptions-item>
            <el-descriptions-item
              :label="t('userRisk.labelModelName')"
              :span="2"
            >
              {{ formatArrayText(fusionResult.model_used, ' / ') }}
            </el-descriptions-item>
            <el-descriptions-item
              :label="t('userRisk.labelModelVersion')"
              :span="2"
            >
              {{ fusionResult.model_version || t('userRisk.notAvailable') }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-tab-pane>

      <el-tab-pane
        v-if="canUsePrediction"
        :label="t('userRisk.tabExperiment')"
        name="experiment"
        lazy
      >
        <ExperimentTab />
      </el-tab-pane>

      <el-tab-pane
        v-if="canUsePrediction"
        :label="t('userRisk.tabPhysiological')"
        name="physiological"
        lazy
      >
        <PhysioTab
          :can-use="canUsePrediction"
          @submitted="handlePhysioSubmitted"
        />
      </el-tab-pane>
    </el-tabs>
  </div>

  <!-- 危机预警弹窗 -->
  <el-dialog
    v-model="crisisDialogVisible"
    :title="t('crisis.dialogTitle')"
    width="500px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
    align-center
    destroy-on-close
  >
    <div class="crisis-alert-content">
      <el-result
        icon="error"
        :title="t('crisis.detectedTitle')"
        :sub-title="t('crisis.detectedSubtitle')"
      />
      <el-alert
        type="error"
        :closable="false"
        show-icon
      >
        <template #title>
          <strong>{{ t('crisis.seekHelp') }}</strong>
        </template>
      </el-alert>
      <div class="crisis-hotlines">
        <div class="hotline-item">
          <el-icon><PhoneFilled /></el-icon>
          <div class="hotline-info">
            <div class="hotline-name">
              {{ t('crisis.hotlines.national24h') }}
            </div>
            <div class="hotline-number">
              400-161-9995
            </div>
          </div>
        </div>
        <div class="hotline-item">
          <el-icon><PhoneFilled /></el-icon>
          <div class="hotline-info">
            <div class="hotline-name">
              {{ t('crisis.hotlines.beijingCrisis') }}
            </div>
            <div class="hotline-number">
              010-82951332
            </div>
          </div>
        </div>
        <div class="hotline-item">
          <el-icon><PhoneFilled /></el-icon>
          <div class="hotline-info">
            <div class="hotline-name">
              {{ t('crisis.hotlines.lifeLine') }}
            </div>
            <div class="hotline-number">
              400-821-1215
            </div>
          </div>
        </div>
      </div>
      <el-alert
        type="warning"
        :closable="false"
        style="margin-top: 12px"
      >
        <template #title>
          {{ t('crisis.contactNearby') }}
        </template>
      </el-alert>
    </div>
    <template #footer>
      <el-button
        type="primary"
        size="large"
        @click="crisisDialogVisible = false"
      >
        {{ t('crisis.acknowledge') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { PhoneFilled } from '@element-plus/icons-vue'
import { modelApi, type FusionPredictResult, type RiskTrend } from '@/api/modelApi'
import type { RiskReport } from '@/api/userRiskApi'
import { userApi } from '@/api/userApi'
import { reportsApi } from '@/api/reportsApi'
import { useAuthStore } from '@/stores/auth'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { hasPermission } from '@/config/permissions'
import { severityFromLevel, formatArrayText } from '@/utils/riskFormatters'
import RiskReportTab from './components/RiskReportTab.vue'
import StructuredAssessTab from './components/StructuredAssessTab.vue'
import TextAssessTab from './components/TextAssessTab.vue'
import ExperimentTab from './components/ExperimentTab.vue'
import PhysioTab from './components/PhysioTab.vue'

const auth = useAuthStore()
const { t } = useI18n()
// 卸载守卫，防止异步操作在组件卸载后更新状态导致泄漏与告警
let isUnmounted = false
const activeTab = ref('report')
const crisisDialogVisible = ref(false)
const canUsePrediction = computed(() => hasPermission(auth.role, 'user.predict.use'))
const canExportRisk = computed(() => hasPermission(auth.role, 'user.export.risk'))
const showCrisisDialog = () => {
  crisisDialogVisible.value = true
}

// ===== 报告概览状态 =====
const report = ref<RiskReport | null>(null)
const reportLoading = ref(true)
const reportError = ref('')
const reportTrendData = ref<RiskTrend>({ days: 30, direction: 'stable', points: [] })

const loadReport = async () => {
  reportLoading.value = true
  reportError.value = ''
  try {
    report.value = await userApi.getRiskReport()
  } catch (error) {
    reportError.value = normalizeHttpError(error, t('userRisk.reportLoadFailed')).detail
  } finally {
    if (!isUnmounted) {
      reportLoading.value = false
    }
  }
  if (isUnmounted) return
  try {
    const trendResult = await userApi.getRiskTrend(30)
    if (isUnmounted) return
    reportTrendData.value = trendResult
  } catch (error) {
    console.warn('风险趋势接口调用失败，使用空趋势图占位', error)
  }
}

const handleExport = async (format: 'json' | 'csv' | 'pdf') => {
  try {
    const blob =
      format === 'pdf'
        ? await reportsApi.exportUserRiskPdf(90)
        : format === 'csv'
          ? await reportsApi.exportUserRiskCsv(90)
          : new Blob([JSON.stringify(await reportsApi.exportUserRiskJson(90), null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = format === 'pdf' ? `risk_report_${Date.now()}.pdf` : `risk_export_${Date.now()}.${format}`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    ElMessage.success(t('userRisk.exportSuccess', { format: format.toUpperCase() }))
  } catch {
    ElMessage.error(t('userRisk.exportFailed', { format: format.toUpperCase() }))
  }
}

// ===== 融合预测状态 =====
const fusionForm = reactive({
  text: '',
  featuresJson: '{"age":20,"stress_level":3,"sleep_duration":6}',
  physiologicalJson: '{"sleep_hours":6.5,"heart_rate":78,"steps":4200}'
})
const fusionSubmitting = ref(false)
const fusionResult = ref<FusionPredictResult | null>(null)
const autoFusionReady = reactive({
  structured: false,
  text: false,
  physiological: false,
})

// 各模态最近一次提交数据，供自动融合同步使用
const latestStructuredData = ref<{ featuresJson: string; structuredFormData: Record<string, unknown> } | null>(null)
const latestTextContent = ref('')
const latestPhysioData = ref<{ physiologicalJson: string; physioFormData: Record<string, unknown> } | null>(null)

const syncFusionInputsFromLatest = () => {
  // 自动融合会同步最近一次结构化、文本和生理输入到融合表单
  if (latestTextContent.value) {
    fusionForm.text = latestTextContent.value
  }
  if (latestStructuredData.value) {
    fusionForm.featuresJson = latestStructuredData.value.featuresJson
  }
  if (latestPhysioData.value) {
    fusionForm.physiologicalJson = latestPhysioData.value.physiologicalJson
  }
}

const maybeAutoSubmitFusion = async () => {
  if (!autoFusionReady.structured || !autoFusionReady.text || !autoFusionReady.physiological) return
  if (fusionSubmitting.value) return
  syncFusionInputsFromLatest()
  await submitFusion(true)
}

const submitFusion = async (auto = false) => {
  // 融合预测允许三种模态任意组合；自动融合会先同步最近一次结构化、文本和生理输入。
  if (auto) {
    syncFusionInputsFromLatest()
  }

  fusionSubmitting.value = true
  try {
    const features = JSON.parse(fusionForm.featuresJson || '{}')
    const physiological = JSON.parse(fusionForm.physiologicalJson || '{}')
    fusionResult.value = await modelApi.predictFusionModel({ features, text: fusionForm.text, physiological })
    // 检测到危机覆盖时自动弹出预警弹窗
    if (fusionResult.value?.crisis_override) {
      showCrisisDialog()
    }
    await loadReport()
    ElMessage.success(auto ? t('userRisk.fusionAutoSuccess') : t('userRisk.fusionSuccess'))
    if (auto) activeTab.value = 'fusion'
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, auto ? t('userRisk.fusionAutoFailed') : t('userRisk.fusionFailed')).detail)
  } finally {
    fusionSubmitting.value = false
  }
}

// ===== 各模态提交事件处理：存储最新数据 → 标记就绪 → 刷新报告 → 尝试自动融合 =====
const handleStructuredSubmitted = async (data: { featuresJson: string; structuredFormData: Record<string, unknown> }) => {
  latestStructuredData.value = data
  autoFusionReady.structured = true
  await loadReport()
  await maybeAutoSubmitFusion()
}

const handleTextSubmitted = async (data: { text: string }) => {
  latestTextContent.value = data.text
  autoFusionReady.text = true
  await loadReport()
  await maybeAutoSubmitFusion()
}

const handlePhysioSubmitted = async (data: { physiologicalJson: string; physioFormData: Record<string, unknown> }) => {
  latestPhysioData.value = data
  autoFusionReady.physiological = true
  await loadReport()
  await maybeAutoSubmitFusion()
}

onMounted(() => {
  loadReport()
})

onUnmounted(() => {
  // 标记组件已卸载，通知进行中的异步操作停止后续状态更新与副作用
  isUnmounted = true
})
</script>

<style scoped>
.risk-page {
  padding: 0;
}

.risk-page__summary {
  margin-bottom: 1rem;
  padding: 1rem 1.25rem;
  border: 1px solid var(--border-extra-light);
  border-radius: 1rem;
  background: var(--bg-primary);
}

.risk-page__eyebrow {
  margin: 0 0 0.35rem;
  color: var(--text-secondary);
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.risk-page__summary h2 {
  margin: 0;
  color: var(--text-primary);
}

.risk-page__summary p:last-child {
  margin: 0.4rem 0 0;
  color: var(--text-secondary);
  line-height: 1.6;
}

.risk-page__actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 0.85rem;
  flex-wrap: wrap;
}

.card-title {
  font-weight: 600;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.crisis-alert-content {
  text-align: center;
}

.crisis-hotlines {
  margin: 16px 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.hotline-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 8px;
  background: #fef0f0;
}

.hotline-info {
  text-align: left;
}

.hotline-name {
  font-size: 13px;
  color: #606266;
}

.hotline-number {
  font-size: 18px;
  font-weight: 600;
  color: #f56c6c;
  margin-top: 4px;
}
</style>
