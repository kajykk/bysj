<template>
  <el-card>
    <template #header>
      我的预警
    </template>

    <FilterBar
      @search="fetchData"
      @reset="handleReset"
    >
      <el-form-item label="状态">
        <el-select
          v-model="filters.isRead"
          clearable
          style="width: 140px"
        >
          <el-option
            label="未读"
            :value="false"
          />
          <el-option
            label="已读"
            :value="true"
          />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button
          type="primary"
          plain
          :loading="bulkLoading"
          :disabled="!rows.some((row) => !row.is_read)"
          @click="handleMarkAllRead"
        >
          全部标记已读
        </el-button>
      </el-form-item>
    </FilterBar>

    <StatefulContainer
      :loading="loading"
      :empty="!loading && rows.length === 0"
      :error-message="pageError"
      empty-text="暂无预警数据"
      @retry="fetchData"
    >
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
          label="ID"
          width="80"
        />
        <el-table-column
          prop="title"
          label="标题"
          min-width="180"
        />
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
          label="处理状态"
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
          prop="created_at"
          label="时间"
          min-width="180"
        >
          <template #default="{ row }">
            {{ formatWarningDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column
          label="处理记录"
          min-width="240"
        >
          <template #default="{ row }">
            <div class="row-meta">
              <span>处理人：{{ row.handled_by || '—' }}</span>
              <span>处理时间：{{ formatWarningDateTime(row.handled_at) }}</span>
              <span>备注：{{ row.handled_note || '—' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column
          label="行内提示"
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
          label="模态信息"
          min-width="180"
        >
          <template #default="{ row }">
            <div class="row-meta">
              <span>生理分数：{{ row.physiological_score ?? '—' }}</span>
              <span>融合详情：{{ row.fusion_detail ? '已包含' : '—' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
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
              标记已读
            </el-button>
            <el-tag
              v-else
              type="info"
              size="small"
            >
              无追踪权限
            </el-tag>
          </template>
        </el-table-column>
      </PageTable>
    </StatefulContainer>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { userApi, type WarningItem } from '@/api/userApi'
import FilterBar from '@/components/common/FilterBar.vue'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import PageTable from '@/components/common/PageTable.vue'
import { mockWarnings } from '@/mocks/business'
import { withMockFallback } from '@/utils/mockFallback'
import { getErrorDetail } from '@/utils/errorDetail'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { hasPermission } from '@/types/permission'
import { useAuthStore } from '@/stores/auth'
import { useListQueryState } from '@/composables/useListQueryState'
import { formatWarningDateTime, getWarningRiskLevelLabel, getWarningRiskLevelTagType, getWarningStatusLabel, getWarningStatusTagType } from '@/utils/warning'

const auth = useAuthStore()
const queryState = useListQueryState('uw')

const loading = ref(false)
const rows = ref<WarningItem[]>([])
const total = ref(0)
const pageError = ref('')
const bulkLoading = ref(false)

const page = computed(() => queryState.page.value)
const pageSize = computed(() => queryState.pageSize.value)

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
    pageError.value = '无权限查看预警列表'
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
    pageError.value = normalizeHttpError(error, '预警列表加载失败').detail
  } finally {
    loading.value = false
  }
}

const handleMarkRead = async (row: WarningItem) => {
  if (row.is_read || isRowPending(row.id)) return

  try {
    await ElMessageBox.confirm('确认将该预警标记为已读吗？', '提示', { type: 'warning' })
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
    ElMessage.success('已标记为已读')
  } catch (error) {
    row.is_read = previousIsRead
    setRowError(row.id, getErrorDetail(error, '标记已读失败，请稍后重试'))
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
    ElMessage.success('已全部标记为已读')
    await fetchData()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '批量标记失败').detail)
  } finally {
    bulkLoading.value = false
  }
}

const handleReset = () => {
  filters.isRead = undefined
  clearTransientRowState()
  queryState.setQuery({ page: 1 })
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
  color: #f56c6c;
}

.row-ok {
  color: #909399;
}

.row-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

:deep(.row-highlight-success) {
  --el-table-tr-bg-color: #f0f9eb;
}

:deep(.row-highlight-error) {
  --el-table-tr-bg-color: #fef0f0;
}
</style>
