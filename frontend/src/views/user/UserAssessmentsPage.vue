<template>
  <ListPageScaffold
    title="评估记录"
    :loading="loading"
    :empty="!loading && rows.length === 0"
    :error-message="pageError"
    empty-text="暂无评估记录"
    @retry="fetchData"
  >
    <template #filters>
      <FilterBar
        @search="handleSearch"
        @reset="handleReset"
      >
        <el-form-item label="类型">
          <el-select
            v-model="filters.type"
            clearable
            style="width: 160px"
          >
            <el-option
              label="结构化"
              value="structured"
            />
            <el-option
              label="文本"
              value="text"
            />
            <el-option
              label="生理"
              value="physiological"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="时间区间">
          <el-date-picker
            v-model="filters.range"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
          />
        </el-form-item>

        <el-form-item>
          <el-button @click="handleExport">
            导出
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
      <el-table-column
        prop="id"
        label="ID"
        width="80"
      />
      <el-table-column
        prop="assessment_type"
        label="类型"
        width="120"
      />
      <el-table-column
        prop="score"
        label="得分"
        width="100"
      />
      <el-table-column
        prop="risk_level"
        label="风险等级"
        width="120"
      />
      <el-table-column
        prop="summary"
        label="摘要"
        min-width="220"
      />
      <el-table-column
        prop="created_at"
        label="时间"
        min-width="180"
      />
      <el-table-column
        label="操作"
        width="180"
        fixed="right"
      >
        <template #default="{ row }">
          <ActionColumn
            label="查看详情"
            :disabled="!canViewAssessment"
            disabled-reason="无权限"
            show-audit
            @action="openDetail(row)"
          />
        </template>
      </el-table-column>
    </PageTable>
  </ListPageScaffold>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { userApi, type AssessmentRecordItem } from '@/api/userApi'
import { userFileApi } from '@/api/userFileApi'
import { type DataHistoryItem } from '@/api/userTypes'
import { type UnifiedPageResult } from '@/types/contracts'
import FilterBar from '@/components/common/FilterBar.vue'
import PageTable from '@/components/common/PageTable.vue'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import ActionColumn from '@/components/common/ActionColumn.vue'
import { mockAssessments } from '@/mocks/business'
import { withMockFallback } from '@/utils/mockFallback'
import { hasPermission } from '@/types/permission'
import { useAuthStore } from '@/stores/auth'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { useListQueryState } from '@/composables/useListQueryState'

const auth = useAuthStore()
const router = useRouter()
const queryState = useListQueryState('ua')

const loading = ref(false)
const rows = ref<AssessmentRecordItem[]>([])
const total = ref(0)
const pageError = ref('')

const page = computed(() => queryState.page.value)
const pageSize = computed(() => queryState.pageSize.value)

const filters = reactive<{ type?: 'structured' | 'text' | 'physiological'; range: string[] }>({
  type: (queryState.getString('type') as 'structured' | 'text' | 'physiological') || undefined,
  range: [queryState.getString('start_date'), queryState.getString('end_date')].filter(Boolean)
})

const canViewAssessment = hasPermission(auth.role, 'user.assessment.read')

const syncQuery = async () => {
  // 列表筛选、分页和 URL 查询参数保持同步，方便刷新页面后恢复当前浏览上下文。
  await queryState.setQuery({
    page: page.value,
    page_size: pageSize.value,
    type: filters.type,
    start_date: filters.range?.[0],
    end_date: filters.range?.[1]
  })
}

const fetchData = async () => {
  // 无权限时直接清空本地列表，避免界面短暂闪现上一位用户或上一次会话的数据。
  if (!canViewAssessment) {
    rows.value = []
    total.value = 0
    return
  }

  loading.value = true
  pageError.value = ''
  try {
    await syncQuery()
    const data = await withMockFallback<UnifiedPageResult<DataHistoryItem>>(
      () =>
        userApi.getUserAssessmentHistory({
          page: page.value,
          page_size: pageSize.value,
          type: filters.type,
          start_date: filters.range?.[0],
          end_date: filters.range?.[1]
        }),
      async () => {
        const mock = await mockAssessments(page.value, pageSize.value)
        return {
          items: mock.items as unknown as DataHistoryItem[],
          total: mock.total,
          page: mock.page,
          page_size: mock.page_size,
        }
      }
    )
    rows.value = data.items
    total.value = data.total
  } catch (error) {
    pageError.value = normalizeHttpError(error, '评估记录加载失败').detail
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

const openDetail = (row: AssessmentRecordItem) => {
  router.push({ path: `/user/assessments/${row.id}`, query: router.currentRoute.value.query })
}

const handleReset = async () => {
  filters.type = undefined
  filters.range = []
  await queryState.setQuery({ page: 1, type: undefined, start_date: undefined, end_date: undefined })
  fetchData()
}

const handleSearch = async () => {
  await queryState.setQuery({ page: 1 })
  fetchData()
}

const handleExport = async () => {
  try {
    const res = await userFileApi.exportRiskData('csv', 3650)
    const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `assessment_export_${Date.now()}.csv`
    link.click()
    URL.revokeObjectURL(link.href)
    ElMessage.success('导出成功')
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '导出失败').detail)
  }
}

onMounted(fetchData)
</script>
