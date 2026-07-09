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

    <PageTable
      :loading="loading"
      :data="rows"
      :total="total"
      :page="page"
      :page-size="pageSize"
      @update:page="onPageChange"
      @update:page-size="onPageSizeChange"
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
            :type="getSilenceStatus(row).type"
            size="small"
          >
            {{ getSilenceStatus(row).label }}
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
              @action="openEdit(row)"
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
              @action="handleEnable(row)"
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
              @action="handleDelete(row)"
            />
          </div>
        </template>
      </el-table-column>
    </PageTable>

    <el-dialog
      v-model="formVisible"
      :title="isEditMode ? t('adminSilences.editDialogTitle') : t('adminSilences.createDialogTitle')"
      width="600px"
      destroy-on-close
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-width="100px"
      >
        <el-form-item
          :label="t('adminSilences.formName')"
          prop="name"
        >
          <el-input
            v-model="form.name"
            :placeholder="t('adminSilences.formNamePlaceholder')"
            maxlength="200"
            show-word-limit
          />
        </el-form-item>
        <el-form-item
          :label="t('adminSilences.formMatcher')"
          prop="matcherJson"
        >
          <el-input
            v-model="form.matcherJson"
            type="textarea"
            :rows="5"
            :placeholder="t('adminSilences.formMatcherPlaceholder')"
          />
          <div class="hint">
            {{ t('adminSilences.formMatcherHint') }}
          </div>
        </el-form-item>
        <el-form-item
          :label="t('adminSilences.formRange')"
          prop="range"
        >
          <el-date-picker
            v-model="form.range"
            type="datetimerange"
            value-format="YYYY-MM-DDTHH:mm:ss"
            :range-separator="t('adminSilences.rangeSeparator')"
            :start-placeholder="t('adminSilences.rangeStart')"
            :end-placeholder="t('adminSilences.rangeEnd')"
            style="width: 100%"
          />
          <div class="hint">
            {{ t('adminSilences.formRangeHint') }}
          </div>
        </el-form-item>
        <el-form-item
          :label="t('adminSilences.formComment')"
          prop="comment"
        >
          <el-input
            v-model="form.comment"
            type="textarea"
            :rows="2"
            :placeholder="t('adminSilences.formCommentPlaceholder')"
            maxlength="1000"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">
          {{ t('common.cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="formSaving"
          @click="submitForm"
        >
          {{ isEditMode ? t('common.save') : t('common.create') }}
        </el-button>
      </template>
    </el-dialog>
  </ListPageScaffold>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { alertsApi, type SilenceItem } from '@/api/alertsApi'
import PageTable from '@/components/common/PageTable.vue'
import FilterBar from '@/components/common/FilterBar.vue'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import ActionColumn from '@/components/common/ActionColumn.vue'
import { useListQueryState } from '@/composables/useListQueryState'
import { showHttpFeedback } from '@/utils/httpFeedback'
import { formatDate } from '@/utils/formatUtils'

const { t } = useI18n()

const queryState = useListQueryState('as')

const loading = ref(false)
const rows = ref<SilenceItem[]>([])
const total = ref(0)
const pageError = ref('')
const deleteLoadingId = ref<number | null>(null)
const editLoadingId = ref<number | null>(null)
const enableLoadingId = ref<number | null>(null)
const activeSilences = ref<SilenceItem[]>([])

const page = computed(() => queryState.page.value)
const pageSize = computed(() => queryState.pageSize.value)

const filters = reactive<{ isActive: boolean | '' }>({
  isActive: queryState.getString('is_active') === '' ? '' : queryState.getString('is_active') === 'true'
})

const formVisible = ref(false)
const formSaving = ref(false)
const formRef = ref<FormInstance>()
// ISS-073: 编辑模式状态
const isEditMode = ref(false)
const editingId = ref<number | null>(null)

interface SilenceForm {
  name: string
  matcherJson: string
  range: string[]
  comment: string
}

const form = reactive<SilenceForm>({
  name: '',
  matcherJson: '{\n  "alertname": ""\n}',
  range: [],
  comment: ''
})

const formRules: FormRules = {
  name: [
    { required: true, message: t('adminSilences.formNameRequired'), trigger: 'blur' },
    { max: 200, message: t('adminSilences.formNameMaxLength'), trigger: 'blur' }
  ],
  matcherJson: [
    { required: true, message: t('adminSilences.formMatcherRequired'), trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (!value) return callback(new Error(t('adminSilences.formMatcherRequired')))
        try {
          const parsed = JSON.parse(value)
          if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
            return callback(new Error(t('adminSilences.formMatcherNotObject')))
          }
          if (Object.keys(parsed).length === 0) {
            return callback(new Error(t('adminSilences.formMatcherEmpty')))
          }
          callback()
        } catch {
          callback(new Error(t('adminSilences.formMatcherJsonInvalid')))
        }
      },
      trigger: 'blur'
    }
  ],
  range: [
    {
      validator: (_rule, value: string[], callback) => {
        if (!value || value.length !== 2 || !value[0] || !value[1]) {
          return callback(new Error(t('adminSilences.formRangeRequired')))
        }
        callback()
      },
      trigger: 'change'
    }
  ]
}

const getSilenceStatus = (row: SilenceItem): { type: 'success' | 'info' | 'warning'; label: string } => {
  if (!row.is_active) return { type: 'info', label: t('adminSilences.statusInactive') }
  const now = Date.now()
  const start = row.starts_at ? new Date(row.starts_at).getTime() : 0
  const end = row.ends_at ? new Date(row.ends_at).getTime() : 0
  if (now < start) return { type: 'warning', label: t('adminSilences.statusPending') }
  if (now > end) return { type: 'info', label: t('adminSilences.statusExpired') }
  return { type: 'success', label: t('adminSilences.statusActive') }
}

const fetchData = async () => {
  loading.value = true
  pageError.value = ''
  try {
    const data = await alertsApi.listSilences({
      page: page.value,
      page_size: pageSize.value,
      is_active: filters.isActive === '' ? undefined : filters.isActive
    })
    rows.value = data.items
    total.value = data.total
    await fetchActiveSilences()
  } catch (error) {
    pageError.value = showHttpFeedback(error, t('adminSilences.loadFailed')).detail
  } finally {
    loading.value = false
  }
}

const fetchActiveSilences = async () => {
  try {
    const res = await alertsApi.listActiveSilences()
    activeSilences.value = res.items
  } catch {
    // 静默生效列表加载失败不阻塞主流程
    activeSilences.value = []
  }
}

const handleDelete = async (row: SilenceItem) => {
  deleteLoadingId.value = row.id
  try {
    await alertsApi.deleteSilence(row.id)
    ElMessage.success(t('adminSilences.deleted'))
    await fetchData()
  } catch (error) {
    showHttpFeedback(error, t('adminSilences.deleteFailed'))
  } finally {
    deleteLoadingId.value = null
  }
}

// ISS-073: 启用已停用的静默规则
const handleEnable = async (row: SilenceItem) => {
  enableLoadingId.value = row.id
  try {
    await alertsApi.enableSilence(row.id)
    ElMessage.success(t('adminSilences.enabled'))
    await fetchData()
  } catch (error) {
    showHttpFeedback(error, t('adminSilences.enableFailed'))
  } finally {
    enableLoadingId.value = null
  }
}

const openCreate = () => {
  isEditMode.value = false
  editingId.value = null
  form.name = ''
  form.matcherJson = '{\n  "alertname": ""\n}'
  form.range = []
  form.comment = ''
  formVisible.value = true
}

// ISS-073: 打开编辑对话框，预填充当前规则数据
const openEdit = (row: SilenceItem) => {
  isEditMode.value = true
  editingId.value = row.id
  form.name = row.name
  try {
    form.matcherJson = JSON.stringify(row.matcher || {}, null, 2)
  } catch {
    form.matcherJson = '{\n  "alertname": ""\n}'
  }
  const startsAt = row.starts_at ? row.starts_at.slice(0, 19) : ''
  const endsAt = row.ends_at ? row.ends_at.slice(0, 19) : ''
  form.range = startsAt && endsAt ? [startsAt, endsAt] : []
  form.comment = row.comment || ''
  formVisible.value = true
}

const submitForm = async () => {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  let matcher: Record<string, string>
  try {
    matcher = JSON.parse(form.matcherJson)
  } catch {
    ElMessage.error(t('adminSilences.formMatcherJsonInvalid'))
    return
  }

  const payload = {
    name: form.name,
    matcher,
    starts_at: form.range[0],
    ends_at: form.range[1],
    comment: form.comment || null
  }

  formSaving.value = true
  try {
    if (isEditMode.value && editingId.value !== null) {
      await alertsApi.updateSilence(editingId.value, payload)
      ElMessage.success(t('adminSilences.updated'))
    } else {
      await alertsApi.createSilence(payload)
      ElMessage.success(t('adminSilences.created'))
    }
    formVisible.value = false
    await fetchData()
  } catch (error) {
    showHttpFeedback(
      error,
      isEditMode.value ? t('adminSilences.updateFailed') : t('adminSilences.createFailed')
    )
  } finally {
    formSaving.value = false
  }
}

const onPageChange = async (value: number) => { await queryState.setQuery({ page: value }); fetchData() }
const onPageSizeChange = async (value: number) => { await queryState.setQuery({ page_size: value, page: 1 }); fetchData() }

const handleSearch = async () => {
  await queryState.setQuery({
    page: 1,
    is_active: filters.isActive === '' ? undefined : String(filters.isActive)
  })
  fetchData()
}

const handleReset = async () => {
  filters.isActive = ''
  await queryState.setQuery({ page: 1, is_active: undefined })
  fetchData()
}

onMounted(fetchData)
</script>

<style scoped>
.active-alert {
  margin-bottom: 12px;
}

.active-tag {
  margin-right: 6px;
  margin-bottom: 4px;
}

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

.hint {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
  line-height: 1.4;
  margin-top: 4px;
}
</style>
