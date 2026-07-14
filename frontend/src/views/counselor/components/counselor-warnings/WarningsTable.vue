<template>
  <PageTable
    :loading="loading"
    :data="data"
    :total="total"
    :page="page"
    :page-size="pageSize"
    :row-class-name="rowClassName"
    @selection-change="(rows: unknown[]) => emit('selection-change', rows as WarningItem[])"
    @update:page="(v: number) => emit('update:page', v)"
    @update:page-size="(v: number) => emit('update:page-size', v)"
  >
    <el-table-column
      type="selection"
      width="52"
      :selectable="selectable"
    />
    <el-table-column
      prop="id"
      :label="t('counselorWarnings.colId')"
      width="80"
    />
    <el-table-column
      prop="title"
      :label="t('counselorWarnings.colTitle')"
      min-width="180"
    >
      <template #default="{ row }">
        <el-link
          type="primary"
          @click="emit('open-detail', row)"
        >
          {{ row.title }}
        </el-link>
      </template>
    </el-table-column>
    <el-table-column
      :label="t('counselorWarnings.colContentSummary')"
      min-width="220"
    >
      <template #default="{ row }">
        {{ row.content }}
      </template>
    </el-table-column>
    <el-table-column
      :label="t('counselorWarnings.colRiskLevel')"
      width="120"
    >
      <template #default="{ row }">
        <el-tag
          :type="getWarningRiskLevelTagType(row.risk_level)"
          size="small"
        >
          {{ getWarningRiskLevelLabel(row.risk_level) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column
      :label="t('counselorWarnings.colStatus')"
      width="120"
    >
      <template #default="{ row }">
        <el-tag
          :type="getWarningStatusTagType(row.status)"
          size="small"
        >
          {{ getWarningStatusLabel(row.status) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column
      :label="t('counselorWarnings.colReadStatus')"
      width="100"
    >
      <template #default="{ row }">
        <el-tag
          :type="row.is_read ? 'success' : 'warning'"
          size="small"
        >
          {{ row.is_read ? t('warning.read') : t('warning.unread') }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column
      prop="handled_by"
      :label="t('counselorWarnings.colHandledBy')"
      width="120"
    >
      <template #default="{ row }">
        {{ row.handled_by || '—' }}
      </template>
    </el-table-column>
    <el-table-column
      prop="handled_at"
      :label="t('counselorWarnings.colHandledAt')"
      min-width="180"
    >
      <template #default="{ row }">
        {{ formatWarningDateTime(row.handled_at) }}
      </template>
    </el-table-column>
    <el-table-column
      prop="created_at"
      :label="t('counselorWarnings.colCreatedAt')"
      min-width="180"
    >
      <template #default="{ row }">
        {{ formatWarningDateTime(row.created_at) }}
      </template>
    </el-table-column>
    <el-table-column
      :label="t('counselorWarnings.colHandledNote')"
      min-width="180"
    >
      <template #default="{ row }">
        {{ row.handled_note || '—' }}
      </template>
    </el-table-column>
    <el-table-column
      :label="t('counselorWarnings.colInlineHint')"
      min-width="220"
    >
      <template #default="{ row }">
        <ErrorCell :message="rowErrors[row.id]" />
      </template>
    </el-table-column>
    <el-table-column
      :label="t('counselorWarnings.colOperation')"
      width="280"
      fixed="right"
    >
      <template #default="{ row }">
        <ActionColumn
          v-if="canHandlePermission"
          :label="t('counselorWarnings.actionHandle')"
          type="primary"
          :loading="isRowActionPending(row.id, 'handle')"
          :disabled="isActionDisabled(row, 'handle')"
          :disabled-reason="getDisabledReason(row, 'handle')"
          show-audit
          @action="emit('handle', row)"
        />
        <ActionColumn
          v-if="canIgnorePermission"
          :label="t('counselorWarnings.actionIgnore')"
          type="info"
          :loading="isRowActionPending(row.id, 'ignore')"
          :disabled="isActionDisabled(row, 'ignore')"
          :disabled-reason="getDisabledReason(row, 'ignore')"
          show-audit
          @action="emit('ignore', row)"
        />
        <!-- ISS-058: 升级按钮 -->
        <ActionColumn
          v-if="canEscalatePermission"
          :label="t('counselorWarnings.actionEscalate')"
          type="warning"
          :loading="isRowActionPending(row.id, 'escalate')"
          :disabled="isActionDisabled(row, 'escalate')"
          :disabled-reason="getDisabledReason(row, 'escalate')"
          show-audit
          @action="emit('escalate', row)"
        />
      </template>
    </el-table-column>
  </PageTable>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import PageTable from '@/components/common/PageTable.vue'
import ActionColumn from '@/components/common/ActionColumn.vue'
import ErrorCell from '@/components/common/ErrorCell.vue'
import type { WarningItem } from '@/api/userTypes'
import { formatWarningDateTime, getWarningRiskLevelLabel, getWarningRiskLevelTagType, getWarningStatusLabel, getWarningStatusTagType } from '@/utils/warning'
import {
  isRowActionDisabled,
  getRowDisabledReason,
  isRowSelectable as isRowSelectableUtil,
  type RowAction,
  type RowActionContext
} from './sharedCounselorWarningsUtils'

const props = defineProps<{
  loading: boolean
  data: WarningItem[]
  total: number
  page: number
  pageSize: number
  rowHighlightIds: Set<number>
  rowErrors: Record<number, string>
  rowActionPending: Record<number, RowAction | undefined>
  canHandlePermission: boolean
  canIgnorePermission: boolean
  canEscalatePermission: boolean
  batchOperating: boolean
}>()

const emit = defineEmits<{
  (e: 'update:page', value: number): void
  (e: 'update:page-size', value: number): void
  (e: 'selection-change', rows: WarningItem[]): void
  (e: 'open-detail', row: WarningItem): void
  (e: 'handle', row: WarningItem): void
  (e: 'ignore', row: WarningItem): void
  (e: 'escalate', row: WarningItem): void
}>()

const { t } = useI18n()

const isRowActionPending = (id: number, action: RowAction) => props.rowActionPending[id] === action
const isAnyActionPending = (id: number) => !!props.rowActionPending[id]

const buildActionContext = (): RowActionContext => ({
  canHandle: props.canHandlePermission,
  canIgnore: props.canIgnorePermission,
  canEscalate: props.canEscalatePermission,
  batchOperating: props.batchOperating,
  isActionPending: isAnyActionPending
})

const getDisabledReason = (row: WarningItem, action: RowAction) =>
  getRowDisabledReason(row, action, buildActionContext(), t)
const isActionDisabled = (row: WarningItem, action: RowAction) =>
  isRowActionDisabled(row, action, buildActionContext(), t)

const selectable = (row: WarningItem) => isRowSelectableUtil(row, isAnyActionPending)

const rowClassName = ({ row }: { row: unknown; rowIndex: number }) => {
  const warning = row as WarningItem
  if (props.rowHighlightIds.has(warning.id)) return 'row-highlight-success'
  if (props.rowErrors[warning.id]) return 'row-highlight-error'
  return ''
}
</script>

<style scoped>
:deep(.row-highlight-success) { --el-table-tr-bg-color: var(--success-light); }
:deep(.row-highlight-error) { --el-table-tr-bg-color: var(--danger-light); }
</style>
