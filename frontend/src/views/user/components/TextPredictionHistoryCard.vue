<template>
  <el-card class="card-gap">
    <template #header>
      <div class="header-row">
        <span class="card-title">{{ t('textAssess.historyTitle') }}</span>
        <div class="header-actions">
          <el-button
            size="small"
            :disabled="!history.length"
            @click="emit('export')"
          >
            {{ t('textAssess.exportHistoryBtn') }}
          </el-button>
          <el-button
            size="small"
            type="danger"
            plain
            :disabled="!history.length"
            @click="emit('clear')"
          >
            {{ t('textAssess.clearHistoryBtn') }}
          </el-button>
        </div>
      </div>
    </template>
    <el-table
      :data="history"
      size="small"
      stripe
    >
      <el-table-column
        prop="time"
        :label="t('textAssess.colTime')"
        min-width="170"
      />
      <el-table-column
        prop="content_preview"
        :label="t('textAssess.colContentPreview')"
        min-width="220"
      />
      <el-table-column
        :label="t('textAssess.colPredictResult')"
        width="180"
      >
        <template #default="{ row }">
          <div class="history-result">
            <span>{{ row.prediction === 1 ? t('textAssess.predictionHighRisk') : t('textAssess.predictionLowRisk') }}</span>
            <el-tag
              v-if="row.crisis_detected"
              type="danger"
              size="small"
            >
              {{ t('textAssess.crisisHistoryTag') }}
            </el-tag>
            <el-tag
              size="small"
              effect="plain"
              :type="row.label_source === 'fused' ? 'primary' : 'info'"
            >
              {{ row.label_source === 'fused' ? t('textAssess.labelSourceFused') : t('textAssess.labelSourceMl') }}
            </el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        :label="t('textAssess.colPredictProbability')"
        width="120"
      >
        <template #default="{ row }">
          <!--
            SEC-FIX-2026-10-05: probability 为后端 Optional 字段，
            无防御时 (null * 100).toFixed(2) 静默显示 "NaN%"。
          -->
          {{ row.probability != null ? (row.probability * 100).toFixed(2) + '%' : '-' }}
        </template>
      </el-table-column>
      <el-table-column
        prop="model_used"
        :label="t('textAssess.colModelName')"
        min-width="170"
      />
    </el-table>
    <el-empty
      v-if="!history.length"
      :description="t('textAssess.emptyHistory')"
      :image-size="60"
    />
  </el-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { TextPredictionHistoryItem } from './composables/useTextPredictionHistory'

defineProps<{
  history: TextPredictionHistoryItem[]
}>()

const emit = defineEmits<{
  clear: []
  export: []
}>()

const { t } = useI18n()
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

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.history-result {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  flex-wrap: wrap;
}

.card-gap {
  margin-top: var(--spacing-md);
}
</style>
