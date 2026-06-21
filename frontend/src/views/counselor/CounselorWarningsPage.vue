<template>
  <div class="counselor-warnings-page">
    <ListPageScaffold
      title="预警处理"
      :loading="loading"
      :empty="!loading && rows.length === 0"
      :error-message="pageError"
      empty-text="暂无预警数据"
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
            label="全成功才提交"
            value="atomic"
          />
          <el-option
            label="允许部分成功"
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
          批量处理
        </el-button>
        <el-button
          v-if="canIgnorePermission"
          size="small"
          :disabled="!canBatchOperate || batchOperating"
          :loading="batchOperating && batchAction === 'ignore'"
          @click="handleBatch('ignore')"
        >
          批量忽略
        </el-button>
      </div>
    </template>

    <template #filters>
      <FilterBar
        @search="fetchData"
        @reset="handleReset"
      >
        <el-form-item label="仅未处理">
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
        label="ID"
        width="80"
      />
      <el-table-column
        prop="title"
        label="标题"
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
        label="内容摘要"
        min-width="220"
      >
        <template #default="{ row }">
          {{ row.content }}
        </template>
      </el-table-column>
      <el-table-column
        label="风险等级"
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
        label="状态"
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
        label="已读状态"
        width="100"
      >
        <template #default="{ row }">
          <el-tag
            :type="row.is_read ? 'success' : 'warning'"
            size="small"
          >
            {{ row.is_read ? '已读' : '未读' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        prop="handled_by"
        label="处理来源"
        width="120"
      >
        <template #default="{ row }">
          {{ row.handled_by || '—' }}
        </template>
      </el-table-column>
      <el-table-column
        prop="handled_at"
        label="处理时间"
        min-width="180"
      >
        <template #default="{ row }">
          {{ formatWarningDateTime(row.handled_at) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="created_at"
        label="创建时间"
        min-width="180"
      >
        <template #default="{ row }">
          {{ formatWarningDateTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column
        label="处理备注"
        min-width="180"
      >
        <template #default="{ row }">
          {{ row.handled_note || '—' }}
        </template>
      </el-table-column>
      <el-table-column
        label="行内提示"
        min-width="220"
      >
        <template #default="{ row }">
          <ErrorCell :message="rowErrors[row.id]" />
        </template>
      </el-table-column>
      <el-table-column
        label="操作"
        width="220"
        fixed="right"
      >
        <template #default="{ row }">
          <ActionColumn
            v-if="canHandlePermission"
            label="处理"
            type="primary"
            :loading="isRowActionPending(row.id, 'handle')"
            :disabled="isActionDisabled(row, 'handle')"
            :disabled-reason="getDisabledReason(row, 'handle')"
            confirm-text="确认处理该预警吗？"
            show-audit
            @action="handleWarning(row, 'handle')"
          />
          <ActionColumn
            v-if="canIgnorePermission"
            label="忽略"
            type="info"
            :loading="isRowActionPending(row.id, 'ignore')"
            :disabled="isActionDisabled(row, 'ignore')"
            :disabled-reason="getDisabledReason(row, 'ignore')"
            confirm-text="确认忽略该预警吗？"
            show-audit
            @action="handleWarning(row, 'ignore')"
          />
        </template>
      </el-table-column>
    </PageTable>
  </ListPageScaffold>

  <el-drawer
    v-model="detailVisible"
    title="预警详情"
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
        <el-descriptions-item label="ID">
          {{ detailRow.id }}
        </el-descriptions-item>
        <el-descriptions-item label="标题">
          {{ detailRow.title }}
        </el-descriptions-item>
        <el-descriptions-item label="内容">
          {{ detailRow.content }}
        </el-descriptions-item>
        <el-descriptions-item label="风险等级">
          <el-tag
            :type="getWarningRiskLevelTagType(detailRow.risk_level)"
            size="small"
          >
            {{ getWarningRiskLevelLabel(detailRow.risk_level) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag
            :type="getWarningStatusTagType(detailRow.status)"
            size="small"
          >
            {{ getWarningStatusLabel(detailRow.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="已读状态">
          <el-tag
            :type="detailRow.is_read ? 'success' : 'warning'"
            size="small"
          >
            {{ detailRow.is_read ? '已读' : '未读' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="处理来源">
          {{ detailRow.handled_by || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="处理时间">
          {{ formatWarningDateTime(detailRow.handled_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">
          {{ formatWarningDateTime(detailRow.created_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="处理备注">
          {{ detailRow.handled_note || '—' }}
        </el-descriptions-item>
      </el-descriptions>
      <div class="detail-actions">
        <ActionColumn
          v-if="canHandlePermission && !isHandled(detailRow)"
          label="处理"
          type="primary"
          :disabled="isActionDisabled(detailRow, 'handle')"
          :disabled-reason="getDisabledReason(detailRow, 'handle')"
          confirm-text="确认处理该预警吗？"
          show-audit
          @action="handleWarning(detailRow, 'handle'); detailVisible = false"
        />
        <ActionColumn
          v-if="canIgnorePermission && !isHandled(detailRow)"
          label="忽略"
          type="info"
          :disabled="isActionDisabled(detailRow, 'ignore')"
          :disabled-reason="getDisabledReason(detailRow, 'ignore')"
          confirm-text="确认忽略该预警吗？"
          show-audit
          @action="handleWarning(detailRow, 'ignore'); detailVisible = false"
        />
      </div>
    </div>
  </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref } from 'vue'
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
import { hasPermission } from '@/types/permission'
import { useAuthStore } from '@/stores/auth'
import { useListQueryState } from '@/composables/useListQueryState'
import { showHttpFeedback } from '@/utils/httpFeedback'
import { formatWarningDateTime, getWarningRiskLevelLabel, getWarningRiskLevelTagType, getWarningStatusLabel, getWarningStatusTagType, isWarningHandled } from '@/utils/warning'

const auth = useAuthStore()
const queryState = useListQueryState('cw')

const loading = ref(false)
const rows = ref<WarningItem[]>([])
const total = ref(0)
const pageError = ref('')

const page = computed(() => queryState.page.value)
const pageSize = computed(() => queryState.pageSize.value)

const rowActionPending = ref<Record<number, 'handle' | 'ignore' | undefined>>({})
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

const isRowActionPending = (id: number, action: 'handle' | 'ignore') => rowActionPending.value[id] === action
const isAnyActionPending = (id: number) => !!rowActionPending.value[id]
const setRowActionPending = (id: number, action?: 'handle' | 'ignore') => { rowActionPending.value = { ...rowActionPending.value, [id]: action } }
const isHandled = (row: WarningItem) => isWarningHandled(row)

const canBatchPermission = computed(() => hasPermission(auth.role, 'counselor.warning.batch'))
const canHandlePermission = computed(() => hasPermission(auth.role, 'counselor.warning.handle'))
const canIgnorePermission = computed(() => hasPermission(auth.role, 'counselor.warning.ignore'))
const canBatchOperate = computed(() => canBatchPermission.value && selectedRows.value.length > 0)



const getDisabledReason = (row: WarningItem, action: 'handle' | 'ignore') => {
  if (action === 'handle' && !canHandlePermission.value) return '无处理权限'
  if (action === 'ignore' && !canIgnorePermission.value) return '无忽略权限'
  if (isHandled(row)) return '该条已处理'
  if (isAnyActionPending(row.id)) return '处理中'
  if (batchOperating.value) return '批量处理中'
  return ''
}

const isActionDisabled = (row: WarningItem, action: 'handle' | 'ignore') => !!getDisabledReason(row, action)
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
    pageError.value = showHttpFeedback(error, '预警列表加载失败').detail
  } finally {
    loading.value = false
  }
}

const handleWarning = async (row: WarningItem, action: 'handle' | 'ignore') => {
  if (isActionDisabled(row, action)) return
  const previousStatus = row.status
  const previousIsRead = row.is_read
  const previousHandledAt = row.handled_at
  const previousHandledBy = row.handled_by
  const previousHandledNote = row.handled_note
  clearRowError(row.id)
  row.status = action === 'handle' ? 'handled' : 'ignored'
  row.is_read = true
  setRowActionPending(row.id, action)
  try {
    await counselorApi.handleCounselorWarning(row.id, action)
    highlightRowFor2s(row.id)
    ElMessage.success(action === 'handle' ? '预警已处理' : '已忽略该预警')
  } catch (error) {
    row.status = previousStatus
    row.is_read = previousIsRead
    row.handled_at = previousHandledAt
    row.handled_by = previousHandledBy
    row.handled_note = previousHandledNote
    setRowError(row.id, getErrorDetail(error, `${action === 'handle' ? '处理' : '忽略'}失败，请稍后重试`))
  } finally {
    setRowActionPending(row.id, undefined)
  }
}

const handleBatch = async (action: 'handle' | 'ignore') => {
  if (!selectedRows.value.length || batchOperating.value) return
  const validTargets = selectedRows.value.filter((row) => !isHandled(row) && !isAnyActionPending(row.id))
  if (!validTargets.length) return ElMessage.warning('选中项均不可操作')
  try { await ElMessageBox.confirm(`确认批量${action === 'handle' ? '处理' : '忽略'} ${validTargets.length} 条预警吗？`, '批量操作确认', { type: 'warning' }) } catch { return }
  batchOperating.value = true
  batchAction.value = action
  const snapshot = validTargets.map((row) => ({ row, prevStatus: row.status, prevIsRead: row.is_read, prevHandledAt: row.handled_at, prevHandledBy: row.handled_by, prevHandledNote: row.handled_note }))
  snapshot.forEach(({ row }) => { clearRowError(row.id); row.status = action === 'handle' ? 'handled' : 'ignored'; row.is_read = true; row.handled_at = new Date().toISOString(); row.handled_by = undefined; row.handled_note = action === 'handle' ? '批量处理' : '批量忽略'; setRowActionPending(row.id, action) })

  if (batchPolicy.value === 'atomic') {
    try {
      await Promise.all(snapshot.map(({ row }) => counselorApi.handleCounselorWarning(row.id, action)))
      snapshot.forEach(({ row }) => highlightRowFor2s(row.id))
      ElMessage.success(`批量操作完成：成功 ${snapshot.length} 条`)
    } catch (error) {
      const detail = getErrorDetail(error, `批量${action === 'handle' ? '处理' : '忽略'}失败，已回滚`)
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
        setRowError(row.id, getErrorDetail(result.reason, '操作失败'))
      }
    })
    ElMessage.success(`批量操作完成：成功 ${successCount} 条${failCount > 0 ? `，失败 ${failCount} 条` : ''}`)
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
.batch-actions { display: flex; gap: 8px; align-items: center; }
:deep(.row-highlight-success) { --el-table-tr-bg-color: #f0f9eb; }
:deep(.row-highlight-error) { --el-table-tr-bg-color: #fef0f0; }

.detail-content {
  padding: 8px 0;
}

.detail-actions {
  margin-top: 20px;
  display: flex;
  gap: 12px;
}
</style>
