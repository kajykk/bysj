<template>
  <el-table
    :data="data"
    border
    stripe
  >
    <el-table-column
      prop="id"
      :label="t('adminTemplates.colId')"
      width="80"
    />
    <el-table-column
      prop="template_name"
      :label="t('adminTemplates.colTemplateName')"
      min-width="160"
    />
    <el-table-column
      prop="applicable_levels"
      :label="t('adminTemplates.colApplicableLevels')"
      width="160"
    >
      <template #default="{ row }">
        <el-tag
          v-for="lv in row.applicable_levels"
          :key="lv"
          size="small"
          class="level-tag"
        >
          {{ t('adminTemplates.levelTag', { level: lv }) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column
      prop="estimated_weeks"
      :label="t('adminTemplates.colEstimatedWeeks')"
      width="100"
    >
      <template #default="{ row }">
        {{ row.estimated_weeks ?? '-' }}
      </template>
    </el-table-column>
    <el-table-column
      prop="task_list"
      :label="t('adminTemplates.colTaskCount')"
      width="80"
    >
      <template #default="{ row }">
        {{ row.task_list?.length || 0 }}
      </template>
    </el-table-column>
    <el-table-column
      prop="status"
      :label="t('adminTemplates.colStatus')"
      width="100"
    >
      <template #default="{ row }">
        <el-switch
          v-model="row.status"
          active-value="active"
          inactive-value="inactive"
          :loading="row.statusLoading"
          @change="(val: string | number | boolean) => emit('statusChange', row, val as 'active' | 'inactive')"
        />
      </template>
    </el-table-column>
    <el-table-column
      :label="t('adminTemplates.colOperation')"
      width="220"
      fixed="right"
    >
      <template #default="{ row }">
        <el-button
          link
          type="primary"
          size="small"
          @click="emit('preview', row)"
        >
          {{ t('adminTemplates.btnPreview') }}
        </el-button>
        <el-button
          link
          type="primary"
          size="small"
          @click="emit('edit', row)"
        >
          {{ t('adminTemplates.btnEdit') }}
        </el-button>
        <!-- ISS-075: 删除模板按钮 -->
        <el-button
          link
          type="danger"
          size="small"
          @click="emit('delete', row)"
        >
          {{ t('adminTemplates.btnDelete') }}
        </el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { TemplateItem } from '@/api/adminApi'
import type { TemplateStatus } from './sharedTemplatesUtils'

defineProps<{
  data: TemplateItem[]
}>()

const emit = defineEmits<{
  (e: 'statusChange', row: TemplateItem & { statusLoading?: boolean }, val: TemplateStatus): void
  (e: 'preview', row: TemplateItem): void
  (e: 'edit', row: TemplateItem): void
  (e: 'delete', row: TemplateItem): void
}>()

const { t } = useI18n()
</script>

<style scoped>
.level-tag {
  margin-right: var(--spacing-xs);
}
</style>
