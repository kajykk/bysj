<template>
  <PageTable
    :loading="loading"
    :data="data"
    :total="total"
    :page="page"
    :page-size="pageSize"
    @update:page="(v: number) => emit('update:page', v)"
    @update:page-size="(v: number) => emit('update:pageSize', v)"
  >
    <el-table-column
      prop="id"
      :label="t('adminSilences.colId')"
      width="80"
    />
    <el-table-column
      prop="name"
      :label="t('adminSilences.colName')"
      min-width="160"
      show-overflow-tooltip
    />
    <el-table-column
      prop="matcher"
      :label="t('adminSilences.colMatcher')"
      min-width="220"
    >
      <template #default="{ row }">
        <div
          v-if="row.matcher && Object.keys(row.matcher).length"
          class="matcher-list"
        >
          <el-tag
            v-for="(val, key) in row.matcher"
            :key="key"
            size="small"
            type="info"
            effect="plain"
            class="matcher-tag"
          >
            {{ key }}={{ val }}
          </el-tag>
        </div>
        <span
          v-else
          class="empty-cell"
        >-</span>
      </template>
    </el-table-column>
    <el-table-column
      prop="starts_at"
      :label="t('adminSilences.colStartsAt')"
      width="180"
    >
      <template #default="{ row }">
        {{ formatDate(row.starts_at) }}
      </template>
    </el-table-column>
    <el-table-column
      prop="ends_at"
      :label="t('adminSilences.colEndsAt')"
      width="180"
    >
      <template #default="{ row }">
        {{ formatDate(row.ends_at) }}
      </template>
    </el-table-column>
    <el-table-column
      prop="is_active"
      :label="t('adminSilences.colStatus')"
      width="120"
    >
      <template #default="{ row }">
        <el-tag
          :type="getSilenceStatus(row, t).type"
          size="small"
        >
          {{ getSilenceStatus(row, t).label }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column
      prop="created_by"
      :label="t('adminSilences.colCreatedBy')"
      width="100"
    >
      <template #default="{ row }">
        {{ row.created_by != null ? row.created_by : '-' }}
      </template>
    </el-table-column>
    <el-table-column
      prop="comment"
      :label="t('adminSilences.colComment')"
      min-width="140"
      show-overflow-tooltip
    >
      <template #default="{ row }">
        {{ row.comment || '-' }}
      </template>
    </el-table-column>
    <el-table-column
      :label="t('adminSilences.colOperation')"
      width="220"
      fixed="right"
    >
      <template #default="{ row }">
        <div class="action-row">
          <ActionColumn
            :label="t('common.edit')"
            type="primary"
            link
            :loading="editLoadingId === row.id"
            @action="emit('edit', row)"
          />
          <ActionColumn
            v-if="!row.is_active"
            :label="t('adminSilences.actionEnable')"
            type="success"
            link
            :loading="enableLoadingId === row.id"
            :confirm-text="t('adminSilences.enableConfirmText')"
            :confirm-title="t('adminSilences.enableConfirmTitle')"
            show-audit
            @action="emit('enable', row)"
          />
          <ActionColumn
            :label="t('common.delete')"
            type="danger"
            link
            :loading="deleteLoadingId === row.id"
            :disabled="!row.is_active"
            :disabled-reason="!row.is_active ? t('adminSilences.deleteDisabledReason') : undefined"
            :confirm-text="t('adminSilences.deleteConfirmText')"
            :confirm-title="t('adminSilences.deleteConfirmTitle')"
            show-audit
            @action="emit('delete', row)"
          />
        </div>
      </template>
    </el-table-column>
  </PageTable>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import PageTable from '@/components/common/PageTable.vue'
import ActionColumn from '@/components/common/ActionColumn.vue'
import { formatDate } from '@/utils/formatUtils'
import type { SilenceItem } from '@/api/alertsApi'
import { getSilenceStatus } from './sharedSilencesUtils'

defineProps<{
  loading: boolean
  data: SilenceItem[]
  total: number
  page: number
  pageSize: number
  editLoadingId: number | null
  enableLoadingId: number | null
  deleteLoadingId: number | null
}>()

const emit = defineEmits<{
  (e: 'update:page', value: number): void
  (e: 'update:pageSize', value: number): void
  (e: 'edit', row: SilenceItem): void
  (e: 'enable', row: SilenceItem): void
  (e: 'delete', row: SilenceItem): void
}>()

const { t } = useI18n()
</script>

<style scoped>
.matcher-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.matcher-tag {
  margin-right: 0;
}

.action-row {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}

.empty-cell {
  color: var(--text-placeholder);
}
</style>
