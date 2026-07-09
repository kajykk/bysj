<template>
  <BentoCell
    :title="t('userWarnings.title')"
    class="warnings-card bento-item"
  >
    <template #actions>
      <el-tag
        type="warning"
        effect="light"
      >
        {{ unreadCountLabel }}
      </el-tag>
    </template>
    <FilterBar
      @search="fetchData"
      @reset="handleReset"
    >
      <el-form-item :label="t('userWarnings.filterStatusLabel')">
        <el-select
          v-model="filters.isRead"
          clearable
          style="width: 140px"
        >
          <el-option
            :label="t('userWarnings.filterUnread')"
            :value="false"
          />
          <el-option
            :label="t('userWarnings.filterRead')"
            :value="true"
          />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button
          type="primary"
          plain
          :loading="bulkLoading"
          :disabled="!hasUnreadRows"
          @click="handleMarkAllRead"
        >
          {{ t('userWarnings.btnMarkAllRead') }}
        </el-button>
      </el-form-item>
    </FilterBar>

    <StatefulContainer
      :loading="loading"
      :empty="!loading && rows.length === 0"
      :error-message="pageError"
      :empty-text="t('userWarnings.emptyText')"
      @retry="fetchData"
    >
      <!-- L-29 优化说明：大数据列表渲染优化
           该页面已通过 PageTable 实现服务端分页（仅渲染当前 page_size 条数据），
           DOM 节点数量受 page_size 限制，性能影响较小。
           若后续需在单页渲染超大量数据（如关闭分页或 page_size > 200），
           建议迁移至 el-table-v2（虚拟滚动版本）以避免全量 DOM 渲染。 -->
      <PageTable
        :loading="loading"
        :data="rows"
        :total="total"
        :page="page"
        :page-size="pageSize"
        :row-class-name="rowClassName"
        @update:page="(value: number) => { queryState.setQuery({ page: value }); fetchData() }"
        @update:page-size="(value: number) => { queryState.setQuery({ page_size: value, page: 1 }); fetchData() }"
      >
        <el-table-column
          prop="id"
          :label="t('userWarnings.colId')"
          width="80"
        />
        <el-table-column
          prop="title"
          :label="t('userWarnings.colTitle')"
          min-width="180"
        />
        <el-table-column
          :label="t('userWarnings.colContent')"
          min-width="220"
        >
          <template #default="{ row }">
            {{ row.content }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('userWarnings.colRiskLevel')"
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
          :label="t('userWarnings.colStatus')"
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
          :label="t('userWarnings.colReadStatus')"
          width="100"
        >
          <template #default="{ row }">
            <el-tag
              :type="row.is_read ? 'success' : 'warning'"
              size="small"
            >
              {{ row.is_read ? t('userWarnings.readLabel') : t('userWarnings.unreadLabel') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="created_at"
          :label="t('userWarnings.colTime')"
          min-width="180"
        >
          <template #default="{ row }">
            {{ formatWarningDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('userWarnings.colHandleRecord')"
          min-width="240"
        >
          <template #default="{ row }">
            <div class="row-meta">
              <span>{{ t('userWarnings.handlerLabel') }}{{ row.handled_by || '—' }}</span>
              <span>{{ t('userWarnings.handleTimeLabel') }}{{ formatWarningDateTime(row.handled_at) }}</span>
              <span>{{ t('userWarnings.handleNoteLabel') }}{{ row.handled_note || '—' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column
          :label="t('userWarnings.colInlineHint')"
          min-width="200"
        >
          <template #default="{ row }">
            <span
              v-if="rowErrors[row.id]"
              class="row-error"
            >{{ rowErrors[row.id] }}</span>
            <span
              v-else
              class="row-ok"
            >-</span>
          </template>
        </el-table-column>
        <el-table-column
          :label="t('userWarnings.colModalInfo')"
          min-width="180"
        >
          <template #default="{ row }">
            <div class="row-meta">
              <span>{{ t('userWarnings.physiologicalScoreLabel') }}{{ row.physiological_score ?? '—' }}</span>
              <span>{{ t('userWarnings.fusionDetailLabel') }}{{ row.fusion_detail ? t('userWarnings.fusionIncluded') : '—' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column
          :label="t('userWarnings.colOperation')"
          width="140"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button
              v-if="canTrackWarning()"
              link
              type="primary"
              :loading="isRowPending(row.id)"
              :disabled="row.is_read || isRowPending(row.id)"
              @click="handleMarkRead(row)"
            >
              {{ t('userWarnings.btnMarkRead') }}
            </el-button>
            <el-tag
              v-else
              type="info"
              size="small"
            >
              {{ t('userWarnings.noTrackPermission') }}
            </el-tag>
          </template>
        </el-table-column>
      </PageTable>
    </StatefulContainer>
  </BentoCell>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { userApi, type WarningItem } from '@/api/userApi'
import FilterBar from '@/components/common/FilterBar.vue'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import PageTable from '@/components/common/PageTable.vue'
import BentoCell from '@/components/common/BentoCell.vue'
import { mockWarnings } from '@/mocks/business'
import { withMockFallback } from '@/utils/mockFallback'
import { getErrorDetail } from '@/utils/errorDetail'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { hasPermission } from '@/config/permissions'
import { useAuthStore } from '@/stores/auth'
import { useListQueryState } from '@/composables/useListQueryState'
import { formatWarningDateTime, getWarningRiskLevelLabel, getWarningRiskLevelTagType, getWarningStatusLabel, getWarningStatusTagType } from '@/utils/warning'

const { t } = useI18n()
const auth = useAuthStore()
const queryState = useListQueryState('uw')

const loading = ref(false)
const rows = ref<WarningItem[]>([])
const total = ref(0)
const pageError = ref('')
const bulkLoading = ref(false)

const page = computed(() => queryState.page.value)
const pageSize = computed(() => queryState.pageSize.value)
// R-009 修复：将模板中的 rows.some() 提取为 computed，避免每次渲染都重新遍历数组
const hasUnreadRows = computed(() => rows.value.some((row) => !row.is_read))
const unreadCountLabel = computed(() => `${rows.value.filter((row) => !row.is_read).length} ${t('userWarnings.unreadLabel')}`)

const rowPendingIds = ref<Set<number>>(new Set())
const rowErrors = ref<Record<number, string>>({})
const rowHighlightIds = ref<Set<number>>(new Set())

const filters = reactive<{ isRead?: boolean }>({ isRead: undefined })

const canReadWarning = () => hasPermission(auth.role, 'user.warning.read')
// P2 修复：canTrackWarning 与 canReadWarning 检查相同权限，合并以消除重复代码
const canTrackWarning = canReadWarning

const isRowPending = (id: number) => rowPendingIds.value.has(id)

const setRowPending = (id: number, pending: boolean) => {
  const next = new Set(rowPendingIds.value)
  if (pending) next.add(id)
  else next.delete(id)
  rowPendingIds.value = next
}

const clearRowError = (id: number) => {
  const next = { ...rowErrors.value }
  delete next[id]
  rowErrors.value = next
}

const setRowError = (id: number, message: string) => {
  rowErrors.value = { ...rowErrors.value, [id]: message }
}

// P1-D-9 修复：保存 highlight timer ID 以便卸载时清理
const highlightTimers = new Set<ReturnType<typeof setTimeout>>()
const highlightRowFor2s = (id: number) => {
  const next = new Set(rowHighlightIds.value)
  next.add(id)
  rowHighlightIds.value = next
  const timer = setTimeout(() => {
    const after = new Set(rowHighlightIds.value)
    after.delete(id)
    rowHighlightIds.value = after
    highlightTimers.delete(timer)
  }, 2000)
  highlightTimers.add(timer)
}

const clearTransientRowState = () => {
  rowErrors.value = {}
  rowHighlightIds.value = new Set()
}

const rowClassName = ({ row }: { row: unknown; rowIndex: number }) => {
  const warning = row as WarningItem
  if (rowHighlightIds.value.has(warning.id)) return 'row-highlight-success'
  if (rowErrors.value[warning.id]) return 'row-highlight-error'
  return ''
}

const fetchData = async () => {
  if (!canReadWarning()) {
    rows.value = []
    total.value = 0
    pageError.value = t('userWarnings.noReadPermission')
    return
  }

  loading.value = true
  pageError.value = ''
  try {
    await queryState.setQuery({ page: page.value, page_size: pageSize.value })
    const data = await withMockFallback(
      () => userApi.getUserWarnings({ page: page.value, page_size: pageSize.value, is_read: filters.isRead }),
      () => mockWarnings(page.value, pageSize.value)
    )
    rows.value = data.items
    total.value = data.total
    clearTransientRowState()
  } catch (error) {
    pageError.value = normalizeHttpError(error, t('userWarnings.loadFailed')).detail
  } finally {
    loading.value = false
  }
}

const handleMarkRead = async (row: WarningItem) => {
  if (row.is_read || isRowPending(row.id)) return

  try {
    await ElMessageBox.confirm(t('userWarnings.markReadConfirm'), t('common.info'), { type: 'warning' })
  } catch {
    return
  }

  const previousIsRead = !!row.is_read
  clearRowError(row.id)
  row.is_read = true
  setRowPending(row.id, true)

  try {
    await userApi.markUserWarningRead(row.id)
    highlightRowFor2s(row.id)
    ElMessage.success(t('userWarnings.markReadSuccess'))
  } catch (error) {
    row.is_read = previousIsRead
    setRowError(row.id, getErrorDetail(error, t('userWarnings.markReadFailed')))
  } finally {
    setRowPending(row.id, false)
  }
}

const handleMarkAllRead = async () => {
  if (bulkLoading.value) return
  const unread = rows.value.filter((row) => !row.is_read)
  if (!unread.length) return
  bulkLoading.value = true
  try {
    await userApi.markAllWarningsRead()
    unread.forEach((row) => { row.is_read = true; highlightRowFor2s(row.id) })
    ElMessage.success(t('userWarnings.markAllReadSuccess'))
    await fetchData()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('userWarnings.bulkMarkFailed')).detail)
  } finally {
    bulkLoading.value = false
  }
}

const handleReset = async () => {
  filters.isRead = undefined
  clearTransientRowState()
  await queryState.setQuery({ page: 1 })
  fetchData()
}

onMounted(fetchData)

// P1-D-9 修复：组件卸载时清理所有 highlight timer
onBeforeUnmount(() => {
  highlightTimers.forEach((timer) => clearTimeout(timer))
  highlightTimers.clear()
})
</script>

<style scoped>
.row-error {
  color: var(--danger-color);
}

.row-ok {
  color: var(--text-secondary);
}

.row-meta {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

:deep(.row-highlight-success) {
  --el-table-tr-bg-color: var(--success-light);
}

:deep(.row-highlight-error) {
  --el-table-tr-bg-color: var(--danger-light);
}
</style>
