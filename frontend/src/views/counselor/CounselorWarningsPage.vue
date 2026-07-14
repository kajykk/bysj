<template>
  <div class="counselor-warnings-page">
    <ListPageScaffold
      :title="t('counselorWarnings.title')"
      :loading="loading"
      :empty="!loading && rows.length === 0"
      :error-message="pageError"
      :empty-text="t('counselorWarnings.empty')"
      @retry="fetchData"
    >
      <template #header-extra>
        <div
          v-if="canBatchPermission"
          class="batch-actions"
        >
          <el-select
            v-model="batchPolicy"
            style="width: 160px"
            size="small"
          >
            <el-option
              :label="t('counselorWarnings.batchPolicyAtomic')"
              value="atomic"
            />
            <el-option
              :label="t('counselorWarnings.batchPolicyPartial')"
              value="partial"
            />
          </el-select>
          <el-button
            v-if="canHandlePermission"
            type="primary"
            size="small"
            :disabled="!canBatchOperate || batchOperating"
            :loading="batchOperating && batchAction === 'handle'"
            @click="handleBatch('handle')"
          >
            {{ t('counselorWarnings.batchHandleBtn') }}
          </el-button>
          <el-button
            v-if="canIgnorePermission"
            size="small"
            :disabled="!canBatchOperate || batchOperating"
            :loading="batchOperating && batchAction === 'ignore'"
            @click="handleBatch('ignore')"
          >
            {{ t('counselorWarnings.batchIgnoreBtn') }}
          </el-button>
        </div>
      </template>

      <template #filters>
        <FilterBar
          @search="fetchData"
          @reset="handleReset"
        >
          <el-form-item :label="t('counselorWarnings.filterOnlyUnhandled')">
            <el-switch v-model="filters.onlyUnhandled" />
          </el-form-item>
        </FilterBar>
      </template>

      <WarningsTable
        :loading="loading"
        :data="rows"
        :total="total"
        :page="page"
        :page-size="pageSize"
        :row-highlight-ids="rowHighlightIds"
        :row-errors="rowErrors"
        :row-action-pending="rowActionPending"
        :can-handle-permission="canHandlePermission"
        :can-ignore-permission="canIgnorePermission"
        :can-escalate-permission="canEscalatePermission"
        :batch-operating="batchOperating"
        @update:page="onPageChange"
        @update:page-size="onPageSizeChange"
        @selection-change="onSelectionChange"
        @open-detail="openDetail"
        @handle="(row: WarningItem) => handleWarning(row, 'handle')"
        @ignore="(row: WarningItem) => handleWarning(row, 'ignore')"
        @escalate="escalateWarning"
      />
    </ListPageScaffold>

    <WarningDetailDrawer
      v-model:visible="detailVisible"
      :detail-row="detailRow"
      :can-handle-permission="canHandlePermission"
      :can-ignore-permission="canIgnorePermission"
      :can-escalate-permission="canEscalatePermission"
      :batch-operating="batchOperating"
      :row-action-pending="rowActionPending"
      @handle="(row: WarningItem) => { handleWarning(row, 'handle'); detailVisible = false }"
      @ignore="(row: WarningItem) => { handleWarning(row, 'ignore'); detailVisible = false }"
      @escalate="(row: WarningItem) => { escalateWarning(row); detailVisible = false }"
    />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { WarningItem } from '@/api/userTypes'
import FilterBar from '@/components/common/FilterBar.vue'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import WarningsTable from './components/counselor-warnings/WarningsTable.vue'
import WarningDetailDrawer from './components/counselor-warnings/WarningDetailDrawer.vue'
import { useCounselorWarningsData } from './components/counselor-warnings/useCounselorWarningsData'

const { t } = useI18n()

const {
  loading, rows, total, pageError,
  page, pageSize, filters,
  rowActionPending, rowErrors, rowHighlightIds,
  batchPolicy, batchOperating, batchAction,
  detailVisible, detailRow,
  canBatchPermission, canHandlePermission, canIgnorePermission, canEscalatePermission, canBatchOperate,
  fetchData, handleWarning, escalateWarning, handleBatch,
  onPageChange, onPageSizeChange, handleReset,
  openDetail, onSelectionChange
} = useCounselorWarningsData()
</script>

<style scoped>
.counselor-warnings-page { width: 100%; }
.batch-actions { display: flex; gap: var(--spacing-sm); align-items: center; }
</style>
