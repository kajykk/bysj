<template>
  <ListPageScaffold
    :title="t('userAssessments.pageTitle')"
    :loading="loading"
    :empty="!loading && rows.length === 0"
    :error-message="pageError"
    :empty-text="t('userAssessments.emptyText')"
    @retry="fetchData"
  >
    <template #filters>
      <FilterBar
        @search="handleSearch"
        @reset="handleReset"
      >
        <el-form-item :label="t('userAssessments.filterType')">
          <el-select
            v-model="filters.type"
            clearable
            style="width: 160px"
          >
            <el-option
              :label="t('userAssessments.typeStructured')"
              value="structured"
            />
            <el-option
              :label="t('userAssessments.typeText')"
              value="text"
            />
            <el-option
              :label="t('userAssessments.typePhysiological')"
              value="physiological"
            />
          </el-select>
        </el-form-item>

        <el-form-item :label="t('userAssessments.filterTimeRange')">
          <el-date-picker
            v-model="filters.range"
            type="daterange"
            value-format="YYYY-MM-DD"
            :range-separator="t('userAssessments.rangeSeparator')"
            :start-placeholder="t('userAssessments.startPlaceholder')"
            :end-placeholder="t('userAssessments.endPlaceholder')"
          />
        </el-form-item>

        <el-form-item>
          <el-button @click="handleExport">
            {{ t('userAssessments.btnExport') }}
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
        :label="t('userAssessments.colId')"
        width="80"
      />
      <el-table-column
        prop="assessment_type"
        :label="t('userAssessments.colType')"
        width="120"
      />
      <el-table-column
        prop="score"
        :label="t('userAssessments.colScore')"
        width="100"
      />
      <el-table-column
        prop="risk_level"
        :label="t('userAssessments.colRiskLevel')"
        width="120"
      />
      <el-table-column
        prop="summary"
        :label="t('userAssessments.colSummary')"
        min-width="220"
      />
      <el-table-column
        prop="created_at"
        :label="t('userAssessments.colTime')"
        min-width="180"
      />
      <el-table-column
        :label="t('userAssessments.colOperation')"
        width="180"
        fixed="right"
      >
        <template #default="{ row }">
          <ActionColumn
            :label="t('userAssessments.btnViewDetail')"
            :disabled="!canViewAssessment"
            :disabled-reason="t('userAssessments.noPermission')"
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
import { useI18n } from 'vue-i18n'
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
import { hasPermission } from '@/config/permissions'
import { useAuthStore } from '@/stores/auth'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { useListQueryState } from '@/composables/useListQueryState'

const { t } = useI18n()
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
    pageError.value = normalizeHttpError(error, t('userAssessments.loadFailed')).detail
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
    const url = URL.createObjectURL(blob)
    link.href = url
    link.download = `assessment_export_${Date.now()}.csv`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    ElMessage.success(t('userAssessments.exportSuccess'))
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('userAssessments.exportFailed')).detail)
  }
}

onMounted(fetchData)
</script>
