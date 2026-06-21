<template>
  <ListPageScaffold
    title="危机事件管理"
    :loading="loading"
    :empty="!loading && rows.length === 0"
    :error-message="pageError"
    empty-text="暂无危机事件"
    @retry="fetchData"
  >
    <template #filters>
      <FilterBar
        @search="handleSearch"
        @reset="handleReset"
      >
        <el-form-item label="状态">
          <el-select
            v-model="filters.status"
            clearable
            style="width: 140px"
          >
            <el-option label="已检测" value="detected" />
            <el-option label="已复核" value="reviewed" />
            <el-option label="已升级" value="escalated" />
            <el-option label="已解决" value="resolved" />
          </el-select>
        </el-form-item>

        <el-form-item label="日期范围">
          <el-date-picker
            v-model="filters.dateRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
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
            <el-icon><Download /></el-icon> 导出 CSV
          </el-button>
        </el-form-item>
      </FilterBar>
    </template>

    <PageTable
      :loading="loading"
      :data="rows"
      :total="total"
      :page="page"
      :page-size="pageSize"
      @update:page="onPageChange"
      @update:page-size="onPageSizeChange"
    >
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="user_id" label="用户ID" width="100">
        <template #default="{ row }">
          {{ maskUserId(row.user_id) }}
        </template>
      </el-table-column>
      <el-table-column prop="trigger_source" label="触发来源" width="100">
        <template #default="{ row }">
          <el-tag :type="getTriggerSourceTag(row.trigger_source)" size="small">
            {{ getTriggerSourceLabel(row.trigger_source) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="crisis_score" label="危机分数" width="100">
        <template #default="{ row }">
          <span :style="{ color: getScoreColor(row.crisis_score), fontWeight: 'bold' }">
            {{ row.crisis_score != null ? row.crisis_score.toFixed(1) : '-' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="getStatusTag(row.status)" size="small">
            {{ getStatusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="crisis_keywords" label="关键词" min-width="150">
        <template #default="{ row }">
          <template v-if="row.crisis_keywords && row.crisis_keywords.length">
            <el-tag
              v-for="kw in row.crisis_keywords"
              :key="kw"
              size="small"
              type="warning"
              effect="plain"
              style="margin-right: 4px; margin-bottom: 2px;"
            >
              {{ kw }}
            </el-tag>
          </template>
          <span v-else style="color: #999">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="review_task_id" label="复核任务" width="90">
        <template #default="{ row }">
          <template v-if="row.review_task_id">
            <el-tag type="primary" size="small">#{{ row.review_task_id }}</el-tag>
          </template>
          <span v-else style="color: #999">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" min-width="170">
        <template #default="{ row }">
          {{ formatDate(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column prop="handled_by" label="处理人ID" width="100">
        <template #default="{ row }">
          {{ row.handled_by ? maskUserId(row.handled_by) : '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="handled_action" label="处理动作" min-width="120">
        <template #default="{ row }">
          {{ row.handled_action || '-' }}
        </template>
      </el-table-column>
    </PageTable>
  </ListPageScaffold>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { adminApi } from '@/api/adminApi'
import request from '@/api/request'
import PageTable from '@/components/common/PageTable.vue'
import FilterBar from '@/components/common/FilterBar.vue'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import { useListQueryState } from '@/composables/useListQueryState'
import { showHttpFeedback } from '@/utils/httpFeedback'
// P2-A 修复：复用 formatUtils 的 formatDate，避免本地重复定义
import { formatDate } from '@/utils/formatUtils'

interface CrisisEventItem {
  id: number
  user_id: number
  report_id: number | null
  trigger_source: string
  crisis_keywords: string[]
  crisis_score: number | null
  input_summary: string | null
  review_task_id: number | null
  status: string
  handled_by: number | null
  handled_action: string | null
  created_at: string
  handled_at: string | null
}

const queryState = useListQueryState('ce')

const loading = ref(false)
const rows = ref<CrisisEventItem[]>([])
const total = ref(0)
const pageError = ref('')
const exporting = ref(false)

const page = computed(() => queryState.page.value)
const pageSize = computed(() => queryState.pageSize.value)

const today = new Date()
const thirtyDaysAgo = new Date(today.getTime() - 30 * 24 * 3600 * 1000)
const defaultStart = thirtyDaysAgo.toISOString().slice(0, 10)
const defaultEnd = today.toISOString().slice(0, 10)

const filters = reactive({
  status: '',
  dateRange: [defaultStart, defaultEnd] as string[]
})

const maskUserId = (userId: number | string): string => {
  const s = String(userId)
  if (s.length <= 2) return s + '****'
  return s.slice(0, 2) + '****'
}

const getTriggerSourceTag = (source: string): 'success' | 'warning' | 'info' => {
  const map: Record<string, 'success' | 'warning' | 'info'> = {
    text: 'warning',
    fusion: 'info',
    manual: 'success'
  }
  return map[source] || 'info'
}

const getTriggerSourceLabel = (source: string): string => {
  const map: Record<string, string> = {
    text: '文本检测',
    fusion: '融合预测',
    manual: '人工标记'
  }
  return map[source] || source
}

const getStatusTag = (status: string): 'danger' | 'warning' | 'info' | 'success' => {
  const map: Record<string, 'danger' | 'warning' | 'info' | 'success'> = {
    detected: 'danger',
    reviewed: 'warning',
    escalated: 'danger',
    resolved: 'success'
  }
  return map[status] || 'info'
}

const getStatusLabel = (status: string): string => {
  const map: Record<string, string> = {
    detected: '已检测',
    reviewed: '已复核',
    escalated: '已升级',
    resolved: '已解决'
  }
  return map[status] || status
}

const getScoreColor = (score: number | null): string => {
  if (score == null) return '#999'
  if (score >= 80) return '#f56c6c'
  if (score >= 50) return '#e6a23c'
  return '#67c23a'
}

const fetchData = async () => {
  loading.value = true
  pageError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: page.value,
      page_size: pageSize.value
    }
    if (filters.status) params.status = filters.status
    if (filters.dateRange && filters.dateRange.length === 2) {
      params.start_date = filters.dateRange[0]
      params.end_date = filters.dateRange[1]
    }
    const response = await request.get('/reviews/crisis-events', { params })
    const data = response.data
    rows.value = data.data?.items || []
    total.value = data.data?.total || 0
  } catch (error) {
    pageError.value = showHttpFeedback(error, '危机事件加载失败').detail
  } finally {
    loading.value = false
  }
}

const onPageChange = async (value: number) => {
  await queryState.setQuery({ page: value })
  fetchData()
}

const onPageSizeChange = async (value: number) => {
  await queryState.setQuery({ page_size: value, page: 1 })
  fetchData()
}

const handleSearch = async () => {
  await queryState.setQuery({ page: 1 })
  fetchData()
}

const handleReset = async () => {
  filters.status = ''
  filters.dateRange = [defaultStart, defaultEnd]
  await queryState.setQuery({ page: 1 })
  fetchData()
}

const handleExport = async () => {
  if (!filters.dateRange || filters.dateRange.length < 2) {
    ElMessage.warning('请选择导出日期范围')
    return
  }
  exporting.value = true
  try {
    const response = await request.get('/admin/crisis-events/export', {
      params: {
        start_date: filters.dateRange[0],
        end_date: filters.dateRange[1]
      },
      responseType: 'blob'
    })
    const blob = new Blob([response.data], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `crisis_events_${filters.dateRange[0].replace(/-/g, '')}_${filters.dateRange[1].replace(/-/g, '')}.csv`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (error: unknown) {
    const err = error as { response?: { status?: number } }
    if (err?.response?.status === 403) {
      ElMessage.error('无权限导出危机事件')
    } else {
      ElMessage.error(showHttpFeedback(error, '导出失败').detail)
    }
  } finally {
    exporting.value = false
  }
}

onMounted(fetchData)
</script>
