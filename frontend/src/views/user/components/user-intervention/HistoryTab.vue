<template>
  <ListPageScaffold
    :title="t('userIntervention.historyTitle')"
    :loading="loading"
    :empty="!loading && rows.length === 0"
    :error-message="errorMessage"
    :empty-text="t('userIntervention.emptyHistory')"
    @retry="emit('retry')"
  >
    <PageTable
      :loading="loading"
      :data="rows"
      :total="total"
      :page="page"
      :page-size="pageSize"
      @update:page="(v: number) => emit('update:page', v)"
      @update:page-size="(v: number) => emit('update:pageSize', v)"
    >
      <el-table-column
        prop="plan_id"
        :label="t('userIntervention.colId')"
        width="80"
      />
      <el-table-column
        prop="plan_name"
        :label="t('userIntervention.colPlanName')"
        min-width="180"
      />
      <el-table-column
        prop="status"
        :label="t('userIntervention.colStatus')"
        width="100"
      >
        <template #default="{ row }">
          <el-tag
            :type="historyStatusTag(row.status)"
            size="small"
          >
            {{ getHistoryStatusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        prop="start_date"
        :label="t('userIntervention.colStartDate')"
        width="120"
      />
      <el-table-column
        prop="end_date"
        :label="t('userIntervention.colEndDate')"
        width="120"
      >
        <template #default="{ row }">
          {{ row.end_date || '-' }}
        </template>
      </el-table-column>
      <el-table-column
        prop="completion_rate"
        :label="t('userIntervention.colCompletionRate')"
        width="120"
      >
        <template #default="{ row }">
          <el-progress
            :percentage="row.completion_rate"
            :stroke-width="8"
            :show-text="true"
          />
        </template>
      </el-table-column>
      <el-table-column
        prop="dominant_modality"
        :label="t('userIntervention.colDominantModality')"
        min-width="120"
      >
        <template #default="{ row }">
          {{ row.dominant_modality ? getModalityLabel(row.dominant_modality) : '-' }}
        </template>
      </el-table-column>
    </PageTable>
  </ListPageScaffold>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import PageTable from '@/components/common/PageTable.vue'
import type { InterventionHistoryItem } from '@/api/userTypes'
import { HISTORY_STATUS_LABEL_KEYS, MODALITY_LABEL_KEYS, historyStatusTag } from './sharedInterventionUtils'

defineProps<{
  loading: boolean
  rows: InterventionHistoryItem[]
  total: number
  page: number
  pageSize: number
  errorMessage: string
}>()

const emit = defineEmits<{
  (e: 'update:page', value: number): void
  (e: 'update:pageSize', value: number): void
  (e: 'retry'): void
}>()

const { t } = useI18n()

const getModalityLabel = (modality: string | null | undefined) => {
  if (!modality) return ''
  const key = MODALITY_LABEL_KEYS[modality]
  return key ? t(`userIntervention.${key}`) : modality
}

const getHistoryStatusLabel = (status: string) => {
  const key = HISTORY_STATUS_LABEL_KEYS[status]
  return key ? t(`userIntervention.${key}`) : status
}
</script>
