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
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import type { ModelPredictResponse } from '@/api/modelApi'
import type { StructuredCollectResult } from '@/api/userRiskApi'
import {
  severityFromLevel,
  routeFamilyLabel,
  routeFamilyTagType,
  routeReasonLabel,
  confidenceTagType,
  confidenceLabel,
  formatArrayText,
} from '@/utils/riskFormatters'

interface Props {
  structuredResult: StructuredCollectResult | null
  modelTabResult: ModelPredictResponse | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'view-report': []
}>()

const { t } = useI18n()

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
