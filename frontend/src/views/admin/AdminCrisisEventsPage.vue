<template>
  <div class="crisis-events-page">
    <CrisisEventStatsCard />
    <ListPageScaffold
      :title="t('adminCrisisEvents.title')"
      :loading="loading"
      :empty="!loading && rows.length === 0"
      :error-message="pageError"
      :empty-text="t('adminCrisisEvents.empty')"
      @retry="fetchData"
    >
      <template #filters>
        <FilterBar
          @search="handleSearch"
          @reset="handleReset"
        >
          <el-form-item :label="t('adminCrisisEvents.filterStatus')">
            <el-select
              v-model="filters.status"
              clearable
              style="width: 140px"
            >
              <el-option
                :label="t('adminCrisisEvents.status.detected')"
                value="detected"
              />
              <el-option
                :label="t('adminCrisisEvents.status.reviewed')"
                value="reviewed"
              />
              <el-option
                :label="t('adminCrisisEvents.status.escalated')"
                value="escalated"
              />
              <el-option
                :label="t('adminCrisisEvents.status.resolved')"
                value="resolved"
              />
            </el-select>
          </el-form-item>

          <el-form-item :label="t('adminCrisisEvents.filterDateRange')">
            <el-date-picker
              v-model="filters.dateRange"
              type="daterange"
              value-format="YYYY-MM-DD"
              :range-separator="t('adminCrisisEvents.rangeSeparator')"
              :start-placeholder="t('adminCrisisEvents.rangeStart')"
              :end-placeholder="t('adminCrisisEvents.rangeEnd')"
              :default-time="[new Date(0, 0, 0, 0, 0, 0), new Date(0, 0, 0, 23, 59, 59)]"
            />
          </el-form-item>

          <el-form-item>
            <el-button
              type="success"
              plain
              :loading="exporting"
              :disabled="!filters.dateRange || filters.dateRange.length < 2"
              @click="handleExport"
            >
              <el-icon><Download /></el-icon> {{ t('adminCrisisEvents.exportBtn') }}
            </el-button>
          </el-form-item>
        </FilterBar>
      </template>

      <CrisisEventsTable
        :loading="loading"
        :data="rows"
        :total="total"
        :page="page"
        :page-size="pageSize"
        @update:page="onPageChange"
        @update:page-size="onPageSizeChange"
        @handle="openHandleDialog"
        @escalate="openEscalateDialog"
        @close="openCloseDialog"
      />

      <!-- ISS-072 修复：处理对话框 -->
      <HandleEventDialog
        v-model:visible="handleDialogVisible"
        :event="currentEvent"
        :loading="actionLoading"
        @submit="submitHandle"
      />

      <!-- ISS-072 修复：升级对话框 -->
      <EscalateEventDialog
        v-model:visible="escalateDialogVisible"
        :event="currentEvent"
        :loading="actionLoading"
        @submit="submitEscalate"
      />

      <!-- ISS-072 修复：关闭对话框 -->
      <CloseEventDialog
        v-model:visible="closeDialogVisible"
        :event="currentEvent"
        :loading="actionLoading"
        @submit="submitClose"
      />
    </ListPageScaffold>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Download } from '@element-plus/icons-vue'
import FilterBar from '@/components/common/FilterBar.vue'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import CrisisEventsTable from './components/admin-crisis-events/CrisisEventsTable.vue'
import CrisisEventStatsCard from './components/admin-crisis-events/CrisisEventStatsCard.vue'
import HandleEventDialog from './components/admin-crisis-events/HandleEventDialog.vue'
import EscalateEventDialog from './components/admin-crisis-events/EscalateEventDialog.vue'
import CloseEventDialog from './components/admin-crisis-events/CloseEventDialog.vue'
import { useCrisisEventsData } from './components/admin-crisis-events/useCrisisEventsData'

const { t } = useI18n()

const {
  loading, rows, total, pageError, exporting,
  page, pageSize, filters,
  fetchData, onPageChange, onPageSizeChange, handleSearch, handleReset, handleExport,
  handleDialogVisible, escalateDialogVisible, closeDialogVisible,
  actionLoading, currentEvent,
  openHandleDialog, openEscalateDialog, openCloseDialog,
  submitHandle, submitEscalate, submitClose
} = useCrisisEventsData()
</script>

<style scoped>
.crisis-events-page {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}
</style>
