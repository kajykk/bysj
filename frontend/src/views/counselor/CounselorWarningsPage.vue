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

      <PageTable
        :loading="loading"
        :data="rows"
        :total="total"
        :page="page"
        :page-size="pageSize"
        :row-class-name="rowClassName"
        @selection-change="onSelectionChange"
        @update:page="onPageChange"
        @update:page-size="onPageSizeChange"
      >
        <el-table-column
          type="selection"
          width="52"
          :selectable="isRowSelectable"
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
              @click="openDetail(row)"
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
              @action="handleWarning(row, 'handle')"
            />
            <ActionColumn
              v-if="canIgnorePermission"
              :label="t('counselorWarnings.actionIgnore')"
              type="info"
              :loading="isRowActionPending(row.id, 'ignore')"
              :disabled="isActionDisabled(row, 'ignore')"
              :disabled-reason="getDisabledReason(row, 'ignore')"
              show-audit
              @action="handleWarning(row, 'ignore')"
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
              @action="escalateWarning(row)"
            />
          </template>
        </el-table-column>
      </PageTable>
    </ListPageScaffold>

    <el-drawer
      v-model="detailVisible"
      :title="t('counselorWarnings.detailTitle')"
      size="500px"
      destroy-on-close
    >
      <div
        v-if="detailRow"
        class="detail-content"
      >
        <el-descriptions
          :column="1"
          border
        >
          <el-descriptions-item :label="t('counselorWarnings.colId')">
            {{ detailRow.id }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('counselorWarnings.colTitle')">
            {{ detailRow.title }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('counselorWarnings.detailColContent')">
            {{ detailRow.content }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('counselorWarnings.colRiskLevel')">
            <el-tag
              :type="getWarningRiskLevelTagType(detailRow.risk_level)"
              size="small"
            >
              {{ getWarningRiskLevelLabel(detailRow.risk_level) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('counselorWarnings.colStatus')">
            <el-tag
              :type="getWarningStatusTagType(detailRow.status)"
              size="small"
            >
              {{ getWarningStatusLabel(detailRow.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('counselorWarnings.colReadStatus')">
            <el-tag
              :type="detailRow.is_read ? 'success' : 'warning'"
              size="small"
            >
              {{ detailRow.is_read ? t('warning.read') : t('warning.unread') }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('counselorWarnings.colHandledBy')">
            {{ detailRow.handled_by || '—' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('counselorWarnings.colHandledAt')">
            {{ formatWarningDateTime(detailRow.handled_at) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('counselorWarnings.colCreatedAt')">
            {{ formatWarningDateTime(detailRow.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('counselorWarnings.colHandledNote')">
            {{ detailRow.handled_note || '—' }}
          </el-descriptions-item>
        </el-descriptions>
        <div class="detail-actions">
          <ActionColumn
            v-if="canHandlePermission && !isHandled(detailRow)"
            :label="t('counselorWarnings.actionHandle')"
            type="primary"
            :disabled="isActionDisabled(detailRow, 'handle')"
            :disabled-reason="getDisabledReason(detailRow, 'handle')"
            show-audit
            @action="handleWarning(detailRow, 'handle'); detailVisible = false"
          />
          <ActionColumn
            v-if="canIgnorePermission && !isHandled(detailRow)"
            :label="t('counselorWarnings.actionIgnore')"
            type="info"
            :disabled="isActionDisabled(detailRow, 'ignore')"
            :disabled-reason="getDisabledReason(detailRow, 'ignore')"
            show-audit
            @action="handleWarning(detailRow, 'ignore'); detailVisible = false"
          />
          <!-- ISS-058: 详情抽屉升级按钮 -->
          <ActionColumn
            v-if="canEscalatePermission && !isHandled(detailRow)"
            :label="t('counselorWarnings.actionEscalate')"
            type="warning"
            :disabled="isActionDisabled(detailRow, 'escalate')"
            :disabled-reason="getDisabledReason(detailRow, 'escalate')"
            show-audit
            @action="escalateWarning(detailRow); detailVisible = false"
          />
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { counselorApi } from '@/api/counselorApi'
import type { WarningItem } from '@/api/userTypes'
import FilterBar from '@/components/common/FilterBar.vue'
import PageTable from '@/components/common/PageTable.vue'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import ActionColumn from '@/components/common/ActionColumn.vue'
import ErrorCell from '@/components/common/ErrorCell.vue'
import { mockWarnings } from '@/mocks/business'
import { withMockFallback } from '@/utils/mockFallback'
import { getErrorDetail } from '@/utils/errorDetail'
import { hasPermission } from '@/config/permissions'
import { useAuthStore } from '@/stores/auth'
import { useListQueryState } from '@/composables/useListQueryState'
import { showHttpFeedback } from '@/utils/httpFeedback'
import { formatWarningDateTime, getWarningRiskLevelLabel, getWarningRiskLevelTagType, getWarningStatusLabel, getWarningStatusTagType, isWarningHandled } from '@/utils/warning'

const { t } = useI18n()
const auth = useAuthStore()
const queryState = useListQueryState('cw')

const loading = ref(false)
const rows = ref<WarningItem[]>([])
const total = ref(0)
const pageError = ref('')

const page = computed(() => queryState.page.value)
const pageSize = computed(() => queryState.pageSize.value)

const rowActionPending = ref<Record<number, 'handle' | 'ignore' | 'escalate' | undefined>>({})
const rowErrors = ref<Record<number, string>>({})
const rowHighlightIds = ref<Set<number>>(new Set())
const selectedRows = ref<WarningItem[]>([])
const batchOperating = ref(false)
const batchAction = ref<'handle' | 'ignore' | null>(null)
const batchPolicy = ref<'atomic' | 'partial'>((queryState.getString('policy') as 'atomic' | 'partial') || 'atomic')
const detailVisible = ref(false)
const detailRow = ref<WarningItem | null>(null)

const openDetail = (row: WarningItem) => {
  detailRow.value = row
  detailVisible.value = true
}

const filters = reactive({ onlyUnhandled: queryState.getString('only_unhandled', '1') !== '0' })

// ISS-058: 行内动作类型扩展 escalate
type RowAction = 'handle' | 'ignore' | 'escalate'
const isRowActionPending = (id: number, action: RowAction) => rowActionPending.value[id] === action
const isAnyActionPending = (id: number) => !!rowActionPending.value[id]
const setRowActionPending = (id: number, action?: RowAction) => { rowActionPending.value = { ...rowActionPending.value, [id]: action } }
const isHandled = (row: WarningItem) => isWarningHandled(row)

const canBatchPermission = computed(() => hasPermission(auth.role, 'counselor.warning.batch'))
const canHandlePermission = computed(() => hasPermission(auth.role, 'counselor.warning.handle'))
const canIgnorePermission = computed(() => hasPermission(auth.role, 'counselor.warning.ignore'))
// ISS-058: 升级权限复用 handle 权限
const canEscalatePermission = computed(() => hasPermission(auth.role, 'counselor.warning.handle'))
const canBatchOperate = computed(() => canBatchPermission.value && selectedRows.value.length > 0)



const getDisabledReason = (row: WarningItem, action: RowAction) => {
  if (action === 'handle' && !canHandlePermission.value) return t('counselorWarnings.disabledNoHandlePermission')
  if (action === 'ignore' && !canIgnorePermission.value) return t('counselorWarnings.disabledNoIgnorePermission')
  // ISS-058: 升级权限校验
  if (action === 'escalate' && !canEscalatePermission.value) return t('counselorWarnings.disabledNoEscalatePermission')
  if (isHandled(row)) return t('counselorWarnings.disabledAlreadyHandled')
  if (isAnyActionPending(row.id)) return t('counselorWarnings.disabledProcessing')
  if (batchOperating.value) return t('counselorWarnings.disabledBatchProcessing')
  return ''
}

const isActionDisabled = (row: WarningItem, action: RowAction) => !!getDisabledReason(row, action)
const clearRowError = (id: number) => { const next = { ...rowErrors.value }; delete next[id]; rowErrors.value = next }
const clearTransientRowState = () => {
  rowErrors.value = {}
  rowHighlightIds.value = new Set()
}
const setRowError = (id: number, message: string) => { rowErrors.value = { ...rowErrors.value, [id]: message } }
// P1-D-9 修复：保存 highlight timer ID 以便卸载时清理
const highlightTimers = new Set<ReturnType<typeof setTimeout>>()
const highlightRowFor2s = (id: number) => {
  const next = new Set(rowHighlightIds.value); next.add(id); rowHighlightIds.value = next
  const timer = setTimeout(() => {
    const after = new Set(rowHighlightIds.value); after.delete(id); rowHighlightIds.value = after
    highlightTimers.delete(timer)
  }, 2000)
  highlightTimers.add(timer)
}

const rowClassName = ({ row }: { row: unknown; rowIndex: number }) => {
  const warning = row as WarningItem
  if (rowHighlightIds.value.has(warning.id)) return 'row-highlight-success'
  if (rowErrors.value[warning.id]) return 'row-highlight-error'
  return ''
}
const onSelectionChange = (tableRows: unknown[]) => { selectedRows.value = tableRows as WarningItem[] }
const isRowSelectable = (row: WarningItem) => !isHandled(row) && !isAnyActionPending(row.id)

const fetchData = async () => {
  loading.value = true
  pageError.value = ''
  clearTransientRowState()
  try {
    await queryState.setQuery({ page: page.value, page_size: pageSize.value, only_unhandled: filters.onlyUnhandled ? '1' : '0', policy: batchPolicy.value })
    const data = await withMockFallback(
      () => counselorApi.getCounselorWarnings({ page: page.value, page_size: pageSize.value, only_unhandled: filters.onlyUnhandled }),
      () => mockWarnings(page.value, pageSize.value)
    )
    rows.value = data.items
    total.value = data.total
    selectedRows.value = []
    clearTransientRowState()
  } catch (error) {
    pageError.value = showHttpFeedback(error, t('counselorWarnings.loadFailed')).detail
  } finally {
    loading.value = false
  }
}

const handleWarning = async (row: WarningItem, action: 'handle' | 'ignore') => {
  if (isActionDisabled(row, action)) return
  // ISS-059: 执行前弹出备注输入框
  let note: string | undefined
  try {
    const result = await ElMessageBox.prompt(t('counselorWarnings.promptNote'), action === 'handle' ? t('counselorWarnings.promptTitleHandle') : t('counselorWarnings.promptTitleIgnore'), {
      inputType: 'textarea',
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel')
    })
    note = result.value || undefined
  } catch {
    return
  }
  const previousStatus = row.status
  const previousIsRead = row.is_read
  const previousHandledAt = row.handled_at
  const previousHandledBy = row.handled_by
  const previousHandledNote = row.handled_note
  clearRowError(row.id)
  row.status = action === 'handle' ? 'handled' : 'ignored'
  row.is_read = true
  row.handled_note = note || null
  setRowActionPending(row.id, action)
  try {
    await counselorApi.handleCounselorWarning(row.id, action, note)
    highlightRowFor2s(row.id)
    ElMessage.success(action === 'handle' ? t('counselorWarnings.warnHandled') : t('counselorWarnings.warnIgnored'))
  } catch (error) {
    row.status = previousStatus
    row.is_read = previousIsRead
    row.handled_at = previousHandledAt
    row.handled_by = previousHandledBy
    row.handled_note = previousHandledNote
    setRowError(row.id, getErrorDetail(error, action === 'handle' ? t('counselorWarnings.errHandleFailed') : t('counselorWarnings.errIgnoreFailed')))
  } finally {
    setRowActionPending(row.id, undefined)
  }
}

// ISS-058: 升级预警
const escalateWarning = async (row: WarningItem) => {
  if (isActionDisabled(row, 'escalate')) return
  let reason: string
  try {
    const result = await ElMessageBox.prompt(t('counselorWarnings.promptEscalateReason'), t('counselorWarnings.promptTitleEscalate'), {
      inputType: 'textarea',
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel'),
      inputValidator: (value: string) => !!value.trim() || t('counselorWarnings.errEscalateReasonRequired')
    })
    reason = result.value.trim()
  } catch {
    return
  }
  const previousStatus = row.status
  const previousIsRead = row.is_read
  const previousHandledAt = row.handled_at
  const previousHandledBy = row.handled_by
  const previousHandledNote = row.handled_note
  clearRowError(row.id)
  row.status = 'escalated'
  row.is_read = true
  row.handled_note = reason
  setRowActionPending(row.id, 'escalate')
  try {
    await counselorApi.escalateCounselorWarning(row.id, { reason })
    highlightRowFor2s(row.id)
    ElMessage.success(t('counselorWarnings.warnEscalated'))
  } catch (error) {
    row.status = previousStatus
    row.is_read = previousIsRead
    row.handled_at = previousHandledAt
    row.handled_by = previousHandledBy
    row.handled_note = previousHandledNote
    setRowError(row.id, getErrorDetail(error, t('counselorWarnings.errEscalateFailed')))
  } finally {
    setRowActionPending(row.id, undefined)
  }
}

const handleBatch = async (action: 'handle' | 'ignore') => {
  if (!selectedRows.value.length || batchOperating.value) return
  const validTargets = selectedRows.value.filter((row) => !isHandled(row) && !isAnyActionPending(row.id))
  if (!validTargets.length) return ElMessage.warning(t('counselorWarnings.warnNoSelection'))
  try { await ElMessageBox.confirm(action === 'handle' ? t('counselorWarnings.batchConfirmHandle', { count: validTargets.length }) : t('counselorWarnings.batchConfirmIgnore', { count: validTargets.length }), t('counselorWarnings.batchConfirmTitle'), { type: 'warning' }) } catch { return }
  batchOperating.value = true
  batchAction.value = action
  const snapshot = validTargets.map((row) => ({ row, prevStatus: row.status, prevIsRead: row.is_read, prevHandledAt: row.handled_at, prevHandledBy: row.handled_by, prevHandledNote: row.handled_note }))
  snapshot.forEach(({ row }) => { clearRowError(row.id); row.status = action === 'handle' ? 'handled' : 'ignored'; row.is_read = true; row.handled_at = new Date().toISOString(); row.handled_by = undefined; row.handled_note = action === 'handle' ? t('counselorWarnings.batchHandleNote') : t('counselorWarnings.batchIgnoreNote'); setRowActionPending(row.id, action) })

  if (batchPolicy.value === 'atomic') {
    try {
      await Promise.all(snapshot.map(({ row }) => counselorApi.handleCounselorWarning(row.id, action)))
      snapshot.forEach(({ row }) => highlightRowFor2s(row.id))
      ElMessage.success(t('counselorWarnings.batchAtomicSuccess', { count: snapshot.length }))
    } catch (error) {
      const detail = getErrorDetail(error, action === 'handle' ? t('counselorWarnings.batchAtomicFailedHandle') : t('counselorWarnings.batchAtomicFailedIgnore'))
      snapshot.forEach(({ row, prevStatus, prevIsRead, prevHandledAt, prevHandledBy, prevHandledNote }) => { row.status = prevStatus; row.is_read = prevIsRead; row.handled_at = prevHandledAt; row.handled_by = prevHandledBy; row.handled_note = prevHandledNote; setRowError(row.id, detail) })
      ElMessage.warning(detail)
    }
  } else {
    let successCount = 0
    let failCount = 0
    const results = await Promise.allSettled(snapshot.map(({ row }) => counselorApi.handleCounselorWarning(row.id, action)))
    results.forEach((result, idx) => {
      if (result.status === 'fulfilled') {
        successCount++
        highlightRowFor2s(snapshot[idx].row.id)
      } else {
        failCount++
        const { row, prevStatus, prevIsRead, prevHandledAt, prevHandledBy, prevHandledNote } = snapshot[idx]
        row.status = prevStatus; row.is_read = prevIsRead; row.handled_at = prevHandledAt; row.handled_by = prevHandledBy; row.handled_note = prevHandledNote
        setRowError(row.id, getErrorDetail(result.reason, t('counselorWarnings.batchPartialFailure')))
      }
    })
    ElMessage.success(t('counselorWarnings.batchPartialSummary', { success: successCount, failPart: failCount > 0 ? t('counselorWarnings.batchPartialFailPart', { count: failCount }) : '' }))
  }

  snapshot.forEach(({ row }) => setRowActionPending(row.id, undefined))
  batchOperating.value = false
  batchAction.value = null
  selectedRows.value = []
}

const onPageChange = async (value: number) => { await queryState.setQuery({ page: value }); fetchData() }
const onPageSizeChange = async (value: number) => { await queryState.setQuery({ page_size: value, page: 1 }); fetchData() }
const handleReset = async () => { filters.onlyUnhandled = true; batchPolicy.value = 'atomic'; clearTransientRowState(); await queryState.setQuery({ page: 1, only_unhandled: '1', policy: 'atomic' }); fetchData() }

onMounted(fetchData)

// P1-D-9 修复：组件卸载时清理所有 highlight timer
onBeforeUnmount(() => {
  highlightTimers.forEach((timer) => clearTimeout(timer))
  highlightTimers.clear()
})
</script>

<style scoped>
.counselor-warnings-page { width: 100%; }
.batch-actions { display: flex; gap: var(--spacing-sm); align-items: center; }
:deep(.row-highlight-success) { --el-table-tr-bg-color: var(--success-light); }
:deep(.row-highlight-error) { --el-table-tr-bg-color: var(--danger-light); }

.detail-content {
  padding: var(--spacing-sm) 0;
}

.detail-actions {
  margin-top: var(--spacing-xl);
  display: flex;
  gap: var(--spacing-md);
}

/* 响应式：移动端适配 */
@media (max-width: 768px) {
  :deep(.el-drawer) {
    width: 90% !important;
  }
}
</style>
