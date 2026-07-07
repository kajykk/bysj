<template>
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
            @action="handleAck(row)"
          />
        </template>
      </el-table-column>
    </PageTable>
  </ListPageScaffold>
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
import { useListQueryState } from '@/composables/useListQueryState'
import { showHttpFeedback } from '@/utils/httpFeedback'
import { formatDate } from '@/utils/formatUtils'

const { t } = useI18n()

type TabKey = 'history' | 'archive'

const queryState = useListQueryState('aa')

const loading = ref(false)
const rows = ref<(AlertHistoryItem | AlertArchiveItem)[]>([])
const total = ref(0)
const pageError = ref('')
const ackLoadingId = ref<number | null>(null)

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

const fetchData = async () => {
  loading.value = true
  pageError.value = ''
  try {
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
      rows.value = data.items
      total.value = data.total
    } else {
      const data = await alertsApi.listAlertArchive({ ...commonParams, rule: filters.rule || undefined })
      rows.value = data.items
      total.value = data.total
    }
  } catch (error) {
    pageError.value = showHttpFeedback(error, t('adminAlerts.loadFailed')).detail
  } finally {
    loading.value = false
  }
}

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

const onPageChange = async (value: number) => { await queryState.setQuery({ page: value }); fetchData() }
const onPageSizeChange = async (value: number) => { await queryState.setQuery({ page_size: value, page: 1 }); fetchData() }

const handleSearch = async () => {
  await queryState.setQuery({
    page: 1,
    severity: filters.severity || undefined,
    status: filters.status || undefined,
    rule: filters.rule || undefined,
    start_time: filters.range?.[0],
    end_time: filters.range?.[1]
  })
  fetchData()
}

const handleReset = async () => {
  filters.severity = ''
  filters.status = ''
  filters.rule = ''
  filters.range = []
  await queryState.setQuery({
    page: 1,
    severity: undefined,
    status: undefined,
    rule: undefined,
    start_time: undefined,
    end_time: undefined
  })
  fetchData()
}

const handleTabChange = async (value: string | number | boolean | undefined) => {
  activeTab.value = (value ?? 'history') as TabKey
  await queryState.setQuery({ page: 1, tab: activeTab.value })
  fetchData()
}

onMounted(fetchData)
</script>

<style scoped>
.mono-cell {
  font-family: 'Courier New', Courier, monospace;
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
