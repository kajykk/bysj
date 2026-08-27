<template>
  <div>
    <el-card>
      <el-form
        :model="model"
        label-width="120px"
        class="fusion-form"
      >
        <el-form-item :label="t('userRisk.fusionTextLabel')">
          <el-input
            :model-value="model.text"
            type="textarea"
            :rows="5"
            :placeholder="t('userRisk.fusionTextPlaceholder')"
            @update:model-value="(v: string) => emit('update:model', { text: v })"
          />
        </el-form-item>
        <el-form-item :label="t('userRisk.fusionFeaturesLabel')">
          <el-input
            :model-value="model.featuresJson"
            type="textarea"
            :rows="6"
            :placeholder="t('userRisk.fusionFeaturesPlaceholder')"
            @update:model-value="(v: string) => emit('update:model', { featuresJson: v })"
          />
        </el-form-item>
        <el-form-item :label="t('userRisk.fusionPhysiologicalLabel')">
          <el-input
            :model-value="model.physiologicalJson"
            type="textarea"
            :rows="6"
            :placeholder="t('userRisk.fusionPhysiologicalPlaceholder')"
            @update:model-value="(v: string) => emit('update:model', { physiologicalJson: v })"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            :loading="submitting"
            @click="() => emit('submit', false)"
          >
            {{ t('userRisk.btnFusion') }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card
      v-if="result"
      class="card-gap"
    >
      <template #header>
        <div class="header-row">
          <span class="card-title">{{ t('userRisk.fusionResultTitle') }}</span>
          <div class="header-actions">
            <el-tag
              v-if="result.crisis_override"
              type="danger"
              effect="dark"
            >
              {{ t('userRisk.fusionCrisisOverride') }}
            </el-tag>
            <el-tag
              v-if="result.review_required"
              type="warning"
              effect="dark"
            >
              {{ t('userRisk.fusionReviewRequired') }}
            </el-tag>
          </div>
        </div>
      </template>
      <el-result
        :icon="result.risk_level <= 1 ? 'success' : result.risk_level <= 2 ? 'warning' : 'error'"
        :title="result.severity"
      >
        <template #sub-title>
          <p>{{ t('userRisk.fusionScoreLabel') }}{{ result.risk_score.toFixed(2) }}</p>
          <p>{{ t('userRisk.fusionSeverityLabel') }}{{ severityFromLevel(result.risk_level) }}</p>
          <p>{{ t('userRisk.fusionModelVersionLabel') }}{{ result.model_version || t('userRisk.notAvailable') }}</p>
          <p>{{ t('userRisk.fusionModelNameLabel') }}{{ formatArrayText(result.model_used, ' / ') }}</p>
        </template>
      </el-result>
      <el-descriptions
        :column="2"
        border
        class="desc-gap"
      >
        <el-descriptions-item :label="t('userRisk.labelReviewStatus')">
          {{ result.review_required ? t('userRisk.reviewRequired') : t('userRisk.reviewNotRequired') }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('userRisk.labelCrisisOverride')">
          {{ result.crisis_override ? t('userRisk.yesOption') : t('userRisk.noOption') }}
        </el-descriptions-item>
        <el-descriptions-item
          :label="t('userRisk.labelReviewReason')"
          :span="2"
        >
          <el-tag
            v-for="reason in result.review_triggers"
            :key="reason"
            type="warning"
            size="small"
            class="tag-inline"
          >
            {{ featureLabel(reason) }}
          </el-tag>
          <span v-if="!result.review_triggers?.length">{{ t('userRisk.notAvailable') }}</span>
        </el-descriptions-item>
        <el-descriptions-item :label="t('userRisk.labelInterventionLevel')">
          {{ result.intervention_level || t('userRisk.notAvailable') }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('userRisk.labelGateWeights')">
          {{ formatArrayText(result.fusion_detail?.gate_weights) }}
        </el-descriptions-item>
        <el-descriptions-item
          :label="t('userRisk.labelModalityScores')"
          :span="2"
        >
          {{ result.fusion_detail?.modality_scores ? JSON.stringify(result.fusion_detail.modality_scores) : t('userRisk.notAvailable') }}
        </el-descriptions-item>
        <el-descriptions-item
          :label="t('userRisk.labelWeightsInfo')"
          :span="2"
        >
          {{ result.fusion_detail?.weights ? JSON.stringify(result.fusion_detail.weights) : t('userRisk.notAvailable') }}
        </el-descriptions-item>
        <el-descriptions-item
          :label="t('userRisk.labelModelName')"
          :span="2"
        >
          {{ formatArrayText(result.model_used, ' / ') }}
        </el-descriptions-item>
        <el-descriptions-item
          :label="t('userRisk.labelModelVersion')"
          :span="2"
        >
          {{ result.model_version || t('userRisk.notAvailable') }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { FusionPredictResult } from '@/api/modelApi'
import { formatArrayText, featureLabel, severityFromLevel } from '@/utils/riskFormatters'

interface Props {
  model: {
    text: string
    featuresJson: string
    physiologicalJson: string
  }
  submitting: boolean
  result: FusionPredictResult | null
}

defineProps<Props>()

const emit = defineEmits<{
  submit: [auto: boolean]
  'update:model': [patch: Partial<{ text: string; featuresJson: string; physiologicalJson: string }>]
}>()

const { t } = useI18n()
</script>

<style scoped>
/* VIS-P3-01 修复：内联样式收敛为样式类 + 设计令牌 */
.fusion-form {
  max-width: 760px;
}

.card-gap {
  margin-top: var(--spacing-md);
}

.card-title {
  font-weight: 600;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.desc-gap {
  margin-top: var(--spacing-md);
}

.tag-inline {
  margin-right: var(--spacing-xs);
  margin-bottom: var(--spacing-xs);
}
</style>
