<template>
  <div class="alerts-page">
    <AlertStatsCard />
    <ListPageScaffold
      :title="activeTab === 'history' ? t('adminAlerts.titleHistory') : t('adminAlerts.titleArchive')"
      :loading="loading"
      :empty="!loading && rows.length === 0"
      :error-message="pageError"
      :empty-text="activeTab === 'history' ? t('adminAlerts.emptyHistory') : t('adminAlerts.emptyArchive')"
      @retry="fetchData"
    >
      <template #header-extra>
        <el-radio-group
          v-model="activeTab"
          size="small"
          @change="handleTabChange"
        >
          <el-radio-button value="history">
            {{ t('adminAlerts.tabHistory') }}
          </el-radio-button>
          <el-radio-button value="archive">
            {{ t('adminAlerts.tabArchive') }}
          </el-radio-button>
        </el-radio-group>
      </template>

      <template #filters>
        <FilterBar
          @search="handleSearch"
          @reset="handleReset"
        >
          <el-form-item :label="t('adminAlerts.filterSeverity')">
            <el-select
              v-model="filters.severity"
              clearable
              :placeholder="t('adminAlerts.filterAll')"
              style="width: 140px"
            >
              <el-option
                :label="t('adminAlerts.severityP0')"
                value="P0"
              />
              <el-option
                :label="t('adminAlerts.severityP1')"
                value="P1"
              />
              <el-option
                :label="t('adminAlerts.severityP2')"
                value="P2"
              />
            </el-select>
          </el-form-item>

          <el-form-item :label="t('adminAlerts.filterStatus')">
            <el-select
              v-model="filters.status"
              clearable
              :placeholder="t('adminAlerts.filterAll')"
              style="width: 140px"
            >
              <el-option
                :label="t('adminAlerts.statusFiring')"
                value="firing"
              />
              <el-option
                :label="t('adminAlerts.statusResolved')"
                value="resolved"
              />
            </el-select>
          </el-form-item>

          <el-form-item
            v-if="activeTab === 'archive'"
            :label="t('adminAlerts.filterRule')"
          >
            <el-input
              v-model="filters.rule"
              clearable
              :placeholder="t('adminAlerts.filterRulePlaceholder')"
              style="width: 200px"
            />
          </el-form-item>

          <el-form-item :label="t('adminAlerts.filterRange')">
            <el-date-picker
              v-model="filters.range"
              type="datetimerange"
              value-format="YYYY-MM-DDTHH:mm:ss"
              :range-separator="t('adminAlerts.rangeSeparator')"
              :start-placeholder="t('adminAlerts.rangeStart')"
              :end-placeholder="t('adminAlerts.rangeEnd')"
            />
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
          :label="t('adminAlerts.colId')"
          width="80"
        />
        <el-table-column
          v-if="activeTab === 'archive'"
          prop="original_id"
          :label="t('adminAlerts.colOriginalId')"
          width="90"
        />
        <el-table-column
          prop="rule"
          :label="t('adminAlerts.colRule')"
          min-width="180"
          show-overflow-tooltip
        />
        <el-table-column
          prop="severity"
          :label="t('adminAlerts.colSeverity')"
          width="120"
        >
          <template #default="{ row }">
            <el-tag
              :type="getSeverityTag(row.severity)"
              size="small"
              effect="dark"
            >
              {{ getSeverityLabel(row.severity) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="status"
          :label="t('adminAlerts.colStatus')"
          width="110"
        >
          <template #default="{ row }">
            <el-tag
              :type="getStatusTag(row.status)"
              size="small"
            >
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="message"
          :label="t('adminAlerts.colMessage')"
          min-width="220"
          show-overflow-tooltip
        />
        <el-table-column
          prop="fingerprint"
          :label="t('adminAlerts.colFingerprint')"
          width="160"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <span class="mono-cell">{{ row.fingerprint || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="created_at"
          :label="t('adminAlerts.colCreatedAt')"
          width="180"
        >
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column
          v-if="activeTab === 'archive'"
          prop="archived_at"
          :label="t('adminAlerts.colArchivedAt')"
          width="180"
        >
          <template #default="{ row }">
            {{ formatDate(row.archived_at) }}
          </template>
        </el-table-column>
        <el-table-column
          v-if="activeTab === 'history'"
          :label="t('adminAlerts.colOperation')"
          width="120"
          fixed="right"
        >
          <template #default="{ row }">
            <ActionColumn
              :label="t('adminAlerts.actionAck')"
              type="warning"
              :loading="ackLoadingId === row.id"
              :disabled="row.status !== 'firing'"
              :disabled-reason="row.status !== 'firing' ? t('adminAlerts.ackDisabledReason') : undefined"
              :confirm-text="t('adminAlerts.ackConfirmText')"
              :confirm-title="t('adminAlerts.ackConfirmTitle')"
              show-audit
              @action="handleAck(asRow<AlertHistoryItem>(row))"
            />
          </template>
        </el-table-column>
      </PageTable>
    </ListPageScaffold>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { alertsApi, type AlertHistoryItem, type AlertArchiveItem, type AlertSeverity, type AlertStatus } from '@/api/alertsApi'
import PageTable from '@/components/common/PageTable.vue'
import FilterBar from '@/components/common/FilterBar.vue'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import ActionColumn from '@/components/common/ActionColumn.vue'
import AlertStatsCard from './components/admin-alerts/AlertStatsCard.vue'
import { useListQuery, type ListResult } from '@/composables/useListQuery'
import { useListQueryState } from '@/composables/useListQueryState'
import { showHttpFeedback } from '@/utils/httpFeedback'
import { formatDate } from '@/utils/formatUtils'
import { asRow } from '@/utils/tableRow'

const { t } = useI18n()

type TabKey = 'history' | 'archive'

const queryState = useListQueryState('aa')

const ackLoadingId = ref<number | null>(null)
type AlertRow = AlertHistoryItem | AlertArchiveItem

const activeTab = ref<TabKey>((queryState.getString('tab') as TabKey) || 'history')

const page = computed(() => queryState.page.value)
const pageSize = computed(() => queryState.pageSize.value)

const filters = reactive<{
  severity: AlertSeverity | ''
  status: AlertStatus | ''
  rule: string
  range: string[]
}>({
  severity: (queryState.getString('severity') as AlertSeverity) || '',
  status: (queryState.getString('status') as AlertStatus) || '',
  rule: queryState.getString('rule'),
  range: [queryState.getString('start_time'), queryState.getString('end_time')].filter(Boolean) as string[]
})

const getSeverityTag = (severity: string): 'danger' | 'warning' | 'info' => {
  const map: Record<string, 'danger' | 'warning' | 'info'> = { P0: 'danger', P1: 'warning', P2: 'info' }
  return map[severity] || 'info'
}

const SEVERITY_LABEL_KEYS: Record<string, string> = {
  P0: 'adminAlerts.severityLabelP0',
  P1: 'adminAlerts.severityLabelP1',
  P2: 'adminAlerts.severityLabelP2'
}

const getSeverityLabel = (severity: string): string => {
  const key = SEVERITY_LABEL_KEYS[severity]
  return key ? t(key) : severity
}

const getStatusTag = (status: string): 'danger' | 'success' | 'info' => {
  const map: Record<string, 'danger' | 'success' | 'info'> = { firing: 'danger', resolved: 'success' }
  return map[status] || 'info'
}

const STATUS_LABEL_KEYS: Record<string, string> = {
  firing: 'adminAlerts.statusFiring',
  resolved: 'adminAlerts.statusResolved'
}

const getStatusLabel = (status: string): string => {
  const key = STATUS_LABEL_KEYS[status]
  return key ? t(key) : status
}

// P2-36 第六批：列表三态 + 竞态守卫改由 useListQuery 统一提供。
// - fetcher 闭包按 tab 选数据源（history / archive 是两个不同端点，参数也不同）；
// - setPage 把「筛选/切 tab 后回到第 1 页」写回 URL query，与 useListQueryState 联动；
// - immediate:false —— 首次加载仍由本页的 onMounted 触发，与原行为一致。
const {
  rows, total, loading, error: pageError, run, search,
} = useListQuery<AlertRow>({
  fetcher: async (): Promise<ListResult<AlertRow>> => {
    const commonParams = {
      page: page.value,
      page_size: pageSize.value,
      severity: filters.severity || undefined,
      status: filters.status || undefined,
      start_time: filters.range?.[0],
      end_time: filters.range?.[1]
    }
    if (activeTab.value === 'history') {
      const data = await alertsApi.listAlertHistory(commonParams)
      return { items: data.items, total: data.total }
    }
    const data = await alertsApi.listAlertArchive({ ...commonParams, rule: filters.rule || undefined })
    return { items: data.items, total: data.total }
  },
  setPage: (value) => queryState.setQuery({ page: value }),
  immediate: false,
  onError: (error) => showHttpFeedback(error, t('adminAlerts.loadFailed')).detail,
})

/** 模板 @retry 与操作后刷新都沿用此名（对外名零改动）。 */
const fetchData = run

const handleAck = async (row: AlertHistoryItem) => {
  ackLoadingId.value = row.id
  try {
    await alertsApi.ackAlert(row.id)
    ElMessage.success(t('adminAlerts.ackSuccess'))
    await fetchData()
  } catch (error) {
    showHttpFeedback(error, t('adminAlerts.ackFailed'))
  } finally {
    ackLoadingId.value = null
  }
}

// SEC-FIX (M2 同型)：翻页先 await setQuery 再取数——原实现不 await 导致读取到旧 page
const onPageChange = async (value: number) => {
  await queryState.setQuery({ page: value })
  await fetchData()
}
const onPageSizeChange = async (value: number) => {
  await queryState.setQuery({ page_size: value, page: 1 })
  await fetchData()
}

// 筛选/切 tab 都走 search()：先作废在途请求，再回到第 1 页，避免旧页响应晚到覆盖。
const handleSearch = async () => {
  await queryState.setQuery({
    severity: filters.severity || undefined,
    status: filters.status || undefined,
    rule: filters.rule || undefined,
    start_time: filters.range?.[0],
    end_time: filters.range?.[1]
  })
  await search()
}

const handleReset = async () => {
  filters.severity = ''
  filters.status = ''
  filters.rule = ''
  filters.range = []
  await queryState.setQuery({
    severity: undefined,
    status: undefined,
    rule: undefined,
    start_time: undefined,
    end_time: undefined
  })
  await search()
}

const handleTabChange = async (value: string | number | boolean | undefined) => {
  activeTab.value = (value ?? 'history') as TabKey
  await queryState.setQuery({ tab: activeTab.value })
  await search()
}

onMounted(fetchData)
</script>

<style scoped>
.alerts-page {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.mono-cell {
  font-family: 'Courier New', Courier, monospace;
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}
</style>
