<template>
  <div class="template-page">
    <BentoCell
      :title="t('adminTemplates.cardTitle')"
      class="template-card bento-item"
    >
      <template #actions>
        <el-button
          type="primary"
          size="small"
          class="magnetic-press"
          @click="openCreate"
        >
          {{ t('adminTemplates.createBtn') }}
        </el-button>
      </template>

      <StatefulContainer
        :loading="loading"
        :empty="!loading && rows.length === 0"
        :error-message="pageError"
        :empty-text="t('adminTemplates.empty')"
        @retry="loadData"
      >
        <TemplatesTable
          :data="rows"
          @status-change="handleStatusChange"
          @preview="openPreview"
          @edit="openEdit"
          @delete="handleDelete"
        />
      </StatefulContainer>

      <div class="pager-wrap">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          @current-change="handlePageChange"
        />
      </div>
    </BentoCell>

    <TemplatePreviewDialog
      v-model:visible="previewVisible"
      :row="previewRow"
      @edit="handlePreviewEdit"
    />

    <TemplateFormDialog
      v-model:visible="formVisible"
      :is-edit-mode="isEditMode"
      :loading="formSaving"
      :editing-row="editingRow"
      @submit="submitForm"
    />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import BentoCell from '@/components/common/BentoCell.vue'
import TemplatesTable from './components/admin-templates/TemplatesTable.vue'
import TemplatePreviewDialog from './components/admin-templates/TemplatePreviewDialog.vue'
import TemplateFormDialog from './components/admin-templates/TemplateFormDialog.vue'
import { useTemplatesData } from './components/admin-templates/useTemplatesData'

const { t } = useI18n()

const {
  rows, total, page, pageSize, loading, pageError,
  formVisible, formSaving, isEditMode, editingRow,
  previewVisible, previewRow,
  loadData, handlePageChange,
  openCreate, openEdit, openPreview,
  handleStatusChange, handleDelete, submitForm,
} = useTemplatesData()

// 预览对话框中点击编辑：打开表单后关闭预览（保留原 openEdit(previewRow!); previewVisible = false 行为）
const handlePreviewEdit = () => {
  if (previewRow.value) {
    openEdit(previewRow.value)
  }
  previewVisible.value = false
}
</script>
