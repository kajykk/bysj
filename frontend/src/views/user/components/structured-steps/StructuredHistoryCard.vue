<template>
  <el-card style="margin-top: 16px">
    <template #header>
      <div class="header-row">
        <span class="card-title">{{ t('structuredAssess.historyTitle') }}</span>
        <div style="display:flex; gap:8px;">
          <el-button
            size="small"
            :disabled="!predictionHistory.length"
            @click="emit('export')"
          >
            {{ t('structuredAssess.exportHistoryBtn') }}
          </el-button>
          <el-button
            size="small"
            type="danger"
            plain
            :disabled="!predictionHistory.length"
            @click="emit('clear')"
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
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { severityFromLevel, severityLabel } from '@/utils/riskFormatters'
import type { PredictionHistoryEntry } from './usePredictionHistory'

interface Props {
  predictionHistory: PredictionHistoryEntry[]
}

defineProps<Props>()
const emit = defineEmits<{
  clear: []
  export: []
}>()

const { t } = useI18n()
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
</style>
