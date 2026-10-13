<template>
  <div class="assessments-page">
    <AssessmentsStatsCard />

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
            <el-button
              :loading="exporting"
              @click="handleExport"
            >
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
          prop="type"
          :label="t('userAssessments.colType')"
          width="120"
        >
          <template #default="{ row }">
            {{ typeLabel(row.type) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="score"
          :label="t('userAssessments.colScore')"
          width="100"
        />
        <el-table-column
          prop="riskLevel"
          :label="t('userAssessments.colRiskLevel')"
          width="120"
        />
        <el-table-column
          prop="summary"
          :label="t('userAssessments.colSummary')"
          min-width="220"
        />
        <el-table-column
          prop="createdAt"
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
              @action="openDetail(asRow<AssessmentHistoryRow>(row))"
            />
          </template>
        </el-table-column>
      </PageTable>
    </ListPageScaffold>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { userApi } from '@/api/userApi'
import { type DataHistoryItem } from '@/api/userTypes'
import { type UnifiedPageResult } from '@/types/contracts'
import {
  type AssessmentHistoryRow,
  toAssessmentHistoryRows,
} from './utils/assessmentHistory'
import { writeAssessmentDetailCache, encodeStatePayload } from './utils/assessmentDetailCache'
import FilterBar from '@/components/common/FilterBar.vue'
import PageTable from '@/components/common/PageTable.vue'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import ActionColumn from '@/components/common/ActionColumn.vue'
import AssessmentsStatsCard from './components/user-assessments/AssessmentsStatsCard.vue'
import { mockAssessments } from '@/mocks/business'
import { withMockFallback } from '@/utils/mockFallback'
import { hasPermission } from '@/config/permissions'
import { useAuthStore } from '@/stores/auth'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { exportToCSV } from '@/utils/exportUtils'
import { useListQueryState } from '@/composables/useListQueryState'
import { asRow } from '@/utils/tableRow'

const { t } = useI18n()
const auth = useAuthStore()
const router = useRouter()
const queryState = useListQueryState('ua')

/**
 * 后端 `GET /user/data/history` 的返回项是 `{ id, type, created_at, data }`
 * （见 backend/app/services/user_data_service.py:371-464），**不含**顶层的
 * `assessment_type` / `score` / `risk_level` / `summary`。表格列因此必须走
 * `toAssessmentHistoryRows` 映射，直接用后端原字段会让三列恒为空白。
 */
const loading = ref(false)
const rows = ref<AssessmentHistoryRow[]>([])
/**
 * 原始列表项，详情页要用它做本地渲染（FIX-2026-10-08）。
 * 表格行 `AssessmentHistoryRow` 是为展示裁剪过的，不含 `data` 载荷。
 */
const rawItems = ref<DataHistoryItem[]>([])
const total = ref(0)
const pageError = ref('')

const TYPE_LABEL_KEYS: Record<string, string> = {
  structured: 'typeStructured',
  text: 'typeText',
  physiological: 'typePhysiological',
}
const typeLabel = (value?: string) => {
  const key = TYPE_LABEL_KEYS[value || '']
  return key ? t(`userAssessments.${key}`) : value || '-'
}

const page = computed(() => queryState.page.value)
const pageSize = computed(() => queryState.pageSize.value)
const exporting = ref(false)

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
    rows.value = toAssessmentHistoryRows(data.items)
    rawItems.value = data.items
    total.value = data.total
    // 详情页改为本地渲染（ID 空间错配修复）：把本页原始项留一份快照，
    // 供详情页在新标签页/收藏后打开时兜底取用。
    writeAssessmentDetailCache(data.items)
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

/**
 * FIX-2026-10-08：把原始项随路由带进详情页。
 *
 * 详情端点 `/user/risk/assessments/{id}` 查的是 `risk_assessments`，与列表行的
 * id 来源（structured_assessments / text_entries / physiological_records）
 * 是两个独立 ID 空间 —— 拿列表 id 去查必然 404，撞上同号更是显示别人的记录。
 * 列表响应里已带齐详情所需全部字段，直接带过去本地渲染。
 */
const openDetail = (row: AssessmentHistoryRow) => {
  const item = rawItems.value.find((raw) => Number(raw?.id) === Number(row.id)) ?? null
  router.push({
    path: `/user/assessments/${row.id}`,
    query: router.currentRoute.value.query,
    state: { assessmentItem: encodeStatePayload(item) },
  })
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
  // SEC-FIX (M3): 原实现调用 /user/risk/export 导出风险趋势数据,
  // 与本页展示的评估历史不一致。改为导出当前筛选条件下的全部评估历史记录。
  exporting.value = true
  try {
    const allItems: DataHistoryItem[] = []
    const exportPageSize = 100
    let currentPage = 1
    let fetchedTotal = 0
    do {
      const data = await withMockFallback<UnifiedPageResult<DataHistoryItem>>(
        () =>
          userApi.getUserAssessmentHistory({
            page: currentPage,
            page_size: exportPageSize,
            type: filters.type,
            start_date: filters.range?.[0],
            end_date: filters.range?.[1]
          }),
        async () => {
          const mock = await mockAssessments(currentPage, exportPageSize)
          return {
            items: mock.items as unknown as DataHistoryItem[],
            total: mock.total,
            page: mock.page,
            page_size: mock.page_size
          }
        }
      )
      allItems.push(...data.items)
      fetchedTotal = data.total
      currentPage += 1
    } while (allItems.length < fetchedTotal && currentPage <= 50)

    // SEC-FIX (P2): 超过 50 页 × 100 条上限时明确告知截断, 不再静默缺数据
    if (allItems.length < fetchedTotal) {
      ElMessage.warning(
        t('userAssessments.exportTruncated', {
          exported: allItems.length,
          total: fetchedTotal
        })
      )
    }

    // 导出列与表格列对齐（同一套映射），避免「表里看到的」和「导出的」两套口径。
    const exportRows = allItems.map((item) => ({
      ...toAssessmentHistoryRows([item])[0],
      detail: JSON.stringify(item?.data ?? {})
    }))

    exportToCSV(
      exportRows as unknown as Record<string, unknown>[],
      [
        { key: 'id', label: t('userAssessments.colId') },
        { key: 'type', label: t('userAssessments.colType') },
        { key: 'score', label: t('userAssessments.colScore') },
        { key: 'riskLevel', label: t('userAssessments.colRiskLevel') },
        { key: 'summary', label: t('userAssessments.colSummary') },
        { key: 'createdAt', label: t('userAssessments.colTime') },
        {
          key: 'detail',
          label: t('userAssessments.colDetail'),
          formatter: (value: unknown) => (value == null ? '' : String(value))
        }
      ],
      `assessment_history_${new Date().toISOString().slice(0, 10)}.csv`
    )
    ElMessage.success(t('userAssessments.exportSuccess'))
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('userAssessments.exportFailed')).detail)
  } finally {
    exporting.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.assessments-page {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}
</style>
