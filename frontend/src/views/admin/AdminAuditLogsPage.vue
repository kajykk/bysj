<template>
  <div class="audit-logs-page">
    <p class="page-subtitle">{{ t('adminAuditLogs.subtitle') }}</p>
    <ListPageScaffold
      :title="t('adminAuditLogs.title')"
      :loading="loading"
      :empty="!loading && rows.length === 0"
      :error-message="pageError"
      :empty-text="t('adminAuditLogs.empty')"
      @retry="fetchData"
    >
      <template #filters>
        <FilterBar
          @search="handleSearch"
          @reset="handleReset"
        >
          <el-form-item :label="t('adminAuditLogs.filterActionTypes')">
            <el-select
              v-model="filters.actionTypes"
              multiple
              filterable
              allow-create
              default-first-option
              clearable
              :placeholder="t('adminAuditLogs.actionTypesPlaceholder')"
              style="width: 260px"
            />
          </el-form-item>

          <el-form-item :label="t('adminAuditLogs.filterOperatorRole')">
            <el-select
              v-model="filters.operatorRole"
              clearable
              style="width: 160px"
            >
              <el-option
                :label="t('role.user')"
                value="user"
              />
              <el-option
                :label="t('role.counselor')"
                value="counselor"
              />
              <el-option
                :label="t('role.admin')"
                value="admin"
              />
              <el-option
                :label="t('role.superAdmin')"
                value="super_admin"
              />
            </el-select>
          </el-form-item>

          <el-form-item :label="t('adminAuditLogs.filterTargetType')">
            <el-input
              v-model="filters.targetType"
              clearable
              :placeholder="t('adminAuditLogs.targetTypePlaceholder')"
              style="width: 180px"
            />
          </el-form-item>

          <el-form-item :label="t('adminAuditLogs.filterRange')">
            <el-date-picker
              v-model="filters.range"
              type="datetimerange"
              value-format="YYYY-MM-DD HH:mm:ss"
              :range-separator="t('adminAuditLogs.rangeSeparator')"
              :start-placeholder="t('adminAuditLogs.rangeStart')"
              :end-placeholder="t('adminAuditLogs.rangeEnd')"
            />
          </el-form-item>
        </FilterBar>
      </template>

      <!-- 合规统计条：retention / 覆盖时间窗 / 按类型分布（仅展示 top 8，完整分布见明细） -->
      <div
        v-if="compliance"
        class="compliance-strip"
      >
        <div class="compliance-item">
          <div class="compliance-value">
            {{ compliance.retention_days }}
          </div>
          <div class="compliance-label">
            {{ t('adminAuditLogs.retentionDays') }}
          </div>
        </div>
        <div class="compliance-item">
          <div class="compliance-value compliance-time">
            {{ compliance.earliest_log ? compliance.earliest_log.slice(0, 10) : '—' }}
          </div>
          <div class="compliance-label">
            {{ t('adminAuditLogs.earliestLog') }}
          </div>
        </div>
        <div class="compliance-item">
          <div class="compliance-value compliance-time">
            {{ compliance.latest_log ? compliance.latest_log.slice(0, 10) : '—' }}
          </div>
          <div class="compliance-label">
            {{ t('adminAuditLogs.latestLog') }}
          </div>
        </div>
        <div class="compliance-item compliance-breakdown">
          <div class="breakdown-tags">
            <el-tag
              v-for="(count, actionType) in topBreakdown"
              :key="actionType"
              size="small"
              type="info"
              effect="plain"
              class="breakdown-tag"
            >
              {{ actionType }} · {{ count }}
            </el-tag>
            <span
              v-if="breakdownHiddenCount > 0"
              class="breakdown-more"
            >
              {{ t('adminAuditLogs.breakdownMore', { count: breakdownHiddenCount }) }}
            </span>
          </div>
          <div class="compliance-label">
            {{ t('adminAuditLogs.actionBreakdown') }}
          </div>
        </div>
      </div>

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
          :label="t('adminAuditLogs.colId')"
          width="80"
        />
        <el-table-column
          prop="action_type"
          :label="t('adminAuditLogs.colActionType')"
          width="180"
        >
          <template #default="{ row }">
            <el-tag
              :type="getActionTypeTag(row.action_type)"
              size="small"
            >
              {{ row.action_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="operator_role"
          :label="t('adminAuditLogs.colOperatorRole')"
          width="120"
        >
          <template #default="{ row }">
            <el-tag
              :type="getRoleTagType(row.operator_role)"
              size="small"
              effect="plain"
            >
              {{ getRoleLabel(row.operator_role) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="target_type"
          :label="t('adminAuditLogs.colTargetType')"
          width="150"
        />
        <el-table-column
          prop="target_id"
          :label="t('adminAuditLogs.colTargetId')"
          width="110"
        />
        <el-table-column
          prop="ip_address"
          :label="t('adminAuditLogs.colIpAddress')"
          width="140"
          show-overflow-tooltip
        />
        <el-table-column
          prop="created_at"
          :label="t('adminAuditLogs.colCreatedAt')"
          min-width="180"
        />
        <el-table-column
          :label="t('adminAuditLogs.colOperation')"
          width="140"
          fixed="right"
        >
          <template #default="{ row }">
            <ActionColumn
              :label="t('adminAuditLogs.actionViewDetail')"
              :disabled="!canAuditDetail"
              :disabled-reason="t('adminAuditLogs.detailNoPermission')"
              show-audit
              @action="openDetail(row)"
            />
          </template>
        </el-table-column>
      </PageTable>

      <el-dialog
        v-model="detailVisible"
        :title="t('adminAuditLogs.detailTitle')"
        width="620px"
        @closed="current = null"
      >
        <pre class="json-view">{{ JSON.stringify(current, null, 2) }}</pre>
        <template #footer>
          <el-button
            :disabled="!current"
            @click="copyDetail"
          >
            {{ t('adminAuditLogs.copyDetail') }}
          </el-button>
          <el-button
            type="primary"
            @click="detailVisible = false"
          >
            {{ t('common.close') }}
          </el-button>
        </template>
      </el-dialog>
    </ListPageScaffold>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'AdminAuditLogsPage' })
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { adminApi, type AuditCompliance, type OperationLogItem } from '@/api/adminApi'
import PageTable from '@/components/common/PageTable.vue'
import FilterBar from '@/components/common/FilterBar.vue'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import ActionColumn from '@/components/common/ActionColumn.vue'
import { hasPermission } from '@/config/permissions'
import { useAuthStore } from '@/stores/auth'
import { useListQueryState } from '@/composables/useListQueryState'
import { showHttpFeedback } from '@/utils/httpFeedback'

const { t } = useI18n()
const auth = useAuthStore()
const queryState = useListQueryState('aal')

const loading = ref(false)
const rows = ref<OperationLogItem[]>([])
const total = ref(0)
const pageError = ref('')
const compliance = ref<AuditCompliance | null>(null)

const page = computed(() => queryState.page.value)
const pageSize = computed(() => queryState.pageSize.value)

const filters = reactive<{ actionTypes: string[]; operatorRole: string; targetType: string; range: string[] }>({
  actionTypes: [],
  operatorRole: queryState.getString('operator_role'),
  targetType: queryState.getString('target_type') || '',
  range: [queryState.getString('start_time'), queryState.getString('end_time')].filter(Boolean) as string[]
})

const detailVisible = ref(false)
const current = ref<Record<string, unknown> | null>(null)
const canAuditDetail = hasPermission(auth.role, 'admin.operation_log.audit')

// 分布标签最多展示 8 个，避免 action_type 种类多时撑爆统计条
const MAX_BREAKDOWN_TAGS = 8
const topBreakdown = computed(() => {
  const entries = Object.entries(compliance.value?.action_breakdown ?? {})
  entries.sort((a, b) => b[1] - a[1])
  return Object.fromEntries(entries.slice(0, MAX_BREAKDOWN_TAGS))
})
const breakdownHiddenCount = computed(() =>
  Math.max(0, Object.keys(compliance.value?.action_breakdown ?? {}).length - MAX_BREAKDOWN_TAGS)
)

const getActionTypeTag = (actionType: string) => {
  if (actionType.includes('warning') || actionType.includes('crisis')) return 'warning'
  if (actionType.includes('delete') || actionType.includes('anonymi')) return 'danger'
  if (actionType.includes('create') || actionType.includes('restore')) return 'success'
  return 'info'
}

const getRoleTagType = (role: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' => {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'primary'> = { user: 'success', counselor: 'warning', admin: 'danger', super_admin: 'primary' }
  return map[role] || 'info'
}

const ROLE_LABEL_KEYS: Record<string, string> = {
  user: 'role.user',
  counselor: 'role.counselor',
  admin: 'role.admin',
  super_admin: 'role.superAdmin'
}

const getRoleLabel = (role: string): string => {
  const key = ROLE_LABEL_KEYS[role]
  return key ? t(key) : role
}

const fetchData = async () => {
  loading.value = true
  pageError.value = ''
  try {
    // AUDIT-2026-10-01（决策三 P2）：响应含 compliance 统计块，取完整结构而非仅分页
    const data = await adminApi.listAuditLogs({
      page: page.value,
      page_size: pageSize.value,
      action_types: filters.actionTypes.length > 0 ? filters.actionTypes : undefined,
      operator_role: filters.operatorRole || undefined,
      target_type: filters.targetType || undefined,
      start_time: filters.range?.[0],
      end_time: filters.range?.[1]
    })
    rows.value = data.items
    total.value = data.total
    compliance.value = data.compliance
  } catch (error) {
    pageError.value = showHttpFeedback(error, t('adminAuditLogs.loadFailed')).detail
  } finally {
    loading.value = false
  }
}

const onPageChange = async (value: number) => { await queryState.setQuery({ page: value }); fetchData() }
const onPageSizeChange = async (value: number) => { await queryState.setQuery({ page_size: value, page: 1 }); fetchData() }
const handleSearch = async () => {
  await queryState.setQuery({ page: 1, operator_role: filters.operatorRole, target_type: filters.targetType, start_time: filters.range?.[0], end_time: filters.range?.[1] })
  fetchData()
}
const handleReset = async () => {
  filters.actionTypes = []
  filters.operatorRole = ''
  filters.targetType = ''
  filters.range = []
  await queryState.setQuery({ page: 1, operator_role: undefined, target_type: undefined, start_time: undefined, end_time: undefined })
  fetchData()
}

const openDetail = (row: Record<string, unknown>) => {
  if (!canAuditDetail) {
    ElMessage.warning(t('adminAuditLogs.noAuditPermission'))
    return
  }
  current.value = row
  detailVisible.value = true
}

const copyDetail = async () => {
  if (!current.value) return
  try {
    await navigator.clipboard.writeText(JSON.stringify(current.value, null, 2))
    ElMessage.success(t('adminAuditLogs.copySuccess'))
  } catch {
    ElMessage.error(t('adminAuditLogs.copyFailed'))
  }
}

onMounted(fetchData)
</script>

<style scoped>
.audit-logs-page {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.page-subtitle {
  margin: 0;
  font-size: var(--font-size-small);
  color: var(--text-secondary);
  line-height: 1.6;
}

.compliance-strip {
  display: flex;
  align-items: stretch;
  gap: var(--spacing-md);
  flex-wrap: wrap;
}

.compliance-item {
  min-width: 140px;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-extra-light);
}

.compliance-value {
  font-size: 22px;
  font-weight: var(--font-weight-semibold);
  line-height: 1.4;
}

.compliance-time {
  font-size: 16px;
}

.compliance-label {
  font-size: var(--font-size-small);
  color: var(--text-secondary);
}

.compliance-breakdown {
  flex: 1;
  min-width: 260px;
}

.breakdown-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 4px;
}

.breakdown-more {
  font-size: var(--font-size-small);
  color: var(--text-secondary);
  align-self: center;
}

.json-view { margin: 0; white-space: pre-wrap; word-break: break-word; }
</style>
