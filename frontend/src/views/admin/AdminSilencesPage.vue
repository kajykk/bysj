<template>
  <ListPageScaffold
    :title="t('adminSilences.title')"
    :loading="loading"
    :empty="!loading && rows.length === 0"
    :error-message="pageError"
    :empty-text="t('adminSilences.empty')"
    @retry="fetchData"
  >
    <template #header-extra>
      <el-button
        type="primary"
        size="small"
        @click="openCreate"
      >
        <el-icon><Plus /></el-icon> {{ t('adminSilences.createBtn') }}
      </el-button>
    </template>

    <template #filters>
      <FilterBar
        @search="handleSearch"
        @reset="handleReset"
      >
        <el-form-item :label="t('adminSilences.filterStatus')">
          <el-select
            v-model="filters.isActive"
            clearable
            :placeholder="t('adminSilences.filterAll')"
            style="width: 140px"
          >
            <el-option
              :label="t('adminSilences.statusActive')"
              :value="true"
            />
            <el-option
              :label="t('adminSilences.statusInactive')"
              :value="false"
            />
          </el-select>
        </el-form-item>
      </FilterBar>
    </template>

    <el-alert
      v-if="activeSilences.length > 0"
      :title="t('adminSilences.activeAlertTitle', { count: activeSilences.length })"
      type="warning"
      :closable="false"
      show-icon
      class="active-alert"
    >
      <template #default>
        <el-tag
          v-for="s in activeSilences"
          :key="s.id"
          size="small"
          type="warning"
          effect="plain"
          class="active-tag"
        >
          #{{ s.id }} {{ s.name }}
        </el-tag>
      </template>
    </el-alert>

    <SilencesTable
      :loading="loading"
      :data="rows"
      :total="total"
      :page="page"
      :page-size="pageSize"
      :edit-loading-id="editLoadingId"
      :enable-loading-id="enableLoadingId"
      :delete-loading-id="deleteLoadingId"
      @update:page="onPageChange"
      @update:page-size="onPageSizeChange"
      @edit="openEdit"
      @enable="handleEnable"
      @delete="handleDelete"
    />

    <SilenceFormDialog
      v-model:visible="formVisible"
      :is-edit-mode="isEditMode"
      :loading="formSaving"
      :editing-row="editingRow"
      @submit="submitForm"
    />
  </ListPageScaffold>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Plus } from '@element-plus/icons-vue'
import FilterBar from '@/components/common/FilterBar.vue'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import SilencesTable from './components/admin-silences/SilencesTable.vue'
import SilenceFormDialog from './components/admin-silences/SilenceFormDialog.vue'
import { useSilencesData } from './components/admin-silences/useSilencesData'

const { t } = useI18n()

const {
  loading, rows, total, pageError,
  deleteLoadingId, editLoadingId, enableLoadingId,
  activeSilences,
  page, pageSize, filters,
  formVisible, formSaving, isEditMode, editingRow,
  fetchData, handleDelete, handleEnable,
  openCreate, openEdit, submitForm,
  onPageChange, onPageSizeChange, handleSearch, handleReset
} = useSilencesData()
</script>

<style scoped>
.active-alert {
  margin-bottom: 12px;
}

.active-tag {
  margin-right: 6px;
  margin-bottom: 4px;
}
</style>
