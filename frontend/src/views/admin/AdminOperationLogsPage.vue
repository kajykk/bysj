<template>
  <div class="operation-logs-page">
    <OperationLogStatsCard />
    <ListPageScaffold
      :title="t('adminOperationLogs.title')"
      :loading="loading"
      :empty="!loading && rows.length === 0"
      :error-message="pageError"
      :empty-text="t('adminOperationLogs.empty')"
      @retry="fetchData"
    >
      <template #filters>
        <FilterBar
          @search="handleSearch"
          @reset="handleReset"
        >
          <el-form-item :label="t('adminOperationLogs.filterActionType')">
            <el-input
              v-model="filters.actionType"
              clearable
              :placeholder="t('adminOperationLogs.actionTypePlaceholder')"
              style="width: 220px"
            />
          </el-form-item>

          <el-form-item :label="t('adminOperationLogs.filterOperatorRole')">
            <el-select
              v-model="filters.operatorRole"
              clearable
              style="width: 180px"
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
            </el-select>
          </el-form-item>

          <el-form-item :label="t('adminOperationLogs.filterOperatorName')">
            <el-input
              v-model="filters.operatorName"
              clearable
              :placeholder="t('adminOperationLogs.operatorNamePlaceholder')"
              style="width: 160px"
            />
          </el-form-item>

          <el-form-item :label="t('adminOperationLogs.filterRange')">
            <el-date-picker
              v-model="filters.range"
              type="datetimerange"
              value-format="YYYY-MM-DD HH:mm:ss"
              :range-separator="t('adminOperationLogs.rangeSeparator')"
              :start-placeholder="t('adminOperationLogs.rangeStart')"
              :end-placeholder="t('adminOperationLogs.rangeEnd')"
            />
          </el-form-item>

          <el-form-item>
            <el-button
              type="success"
              plain
              :loading="exporting"
              @click="exportLogs"
            >
              <el-icon><Download /></el-icon> {{ t('adminOperationLogs.exportCsv') }}
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
          :label="t('adminOperationLogs.colId')"
          width="80"
        />
        <el-table-column
          prop="action_type"
          :label="t('adminOperationLogs.colActionType')"
          width="160"
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
          :label="t('adminOperationLogs.colOperatorRole')"
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
          :label="t('adminOperationLogs.colTargetType')"
          width="140"
        />
        <el-table-column
          prop="target_id"
          :label="t('adminOperationLogs.colTargetId')"
          width="120"
        />
        <el-table-column
          prop="created_at"
          :label="t('adminOperationLogs.colCreatedAt')"
          min-width="180"
        />
        <el-table-column
          :label="t('adminOperationLogs.colOperation')"
          width="160"
          fixed="right"
        >
          <template #default="{ row }">
            <ActionColumn
              :label="t('adminOperationLogs.actionViewDetail')"
              :disabled="!canAuditDetail"
              :disabled-reason="t('adminOperationLogs.detailNoPermission')"
              show-audit
              @action="openDetail(row)"
            />
          </template>
        </el-table-column>
      </PageTable>

      <el-dialog
        v-model="detailVisible"
        :title="t('adminOperationLogs.detailTitle')"
        width="620px"
        @closed="current = null"
      >
        <pre class="json-view">{{ JSON.stringify(current, null, 2) }}</pre>
        <template #footer>
          <el-button
            :disabled="!current"
            @click="copyDetail"
          >
            {{ t('adminOperationLogs.copyDetail') }}
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
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { adminApi, type OperationLogItem } from '@/api/adminApi'
import PageTable from '@/components/common/PageTable.vue'
import FilterBar from '@/components/common/FilterBar.vue'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import ActionColumn from '@/components/common/ActionColumn.vue'
import OperationLogStatsCard from './components/admin-operation-logs/OperationLogStatsCard.vue'
import type { ActionType } from '@/types/contracts'
import { hasPermission } from '@/config/permissions'
import { useAuthStore } from '@/stores/auth'
import { useListQueryState } from '@/composables/useListQueryState'
import { showHttpFeedback } from '@/utils/httpFeedback'
// ISS-052 修复：复用 exportToCSV 统一公式注入防护与单元格转义，消除手动拼接
import { exportToCSV } from '@/utils/exportUtils'

const { t } = useI18n()
const auth = useAuthStore()
const queryState = useListQueryState('aol')

const loading = ref(false)
const rows = ref<OperationLogItem[]>([])
const total = ref(0)
const pageError = ref('')

const page = computed(() => queryState.page.value)
const pageSize = computed(() => queryState.pageSize.value)

const filters = reactive<{ actionType?: ActionType; operatorRole: string; operatorName: string; range: string[] }>({
  actionType: (queryState.getString('action_type') as ActionType) || undefined,
  operatorRole: queryState.getString('operator_role'),
  operatorName: queryState.getString('operator_name') || '',
  range: [queryState.getString('start_time'), queryState.getString('end_time')].filter(Boolean) as string[]
})

const detailVisible = ref(false)
const current = ref<Record<string, unknown> | null>(null)
const canAuditDetail = hasPermission(auth.role, 'admin.operation_log.audit')
const exporting = ref(false)

const getActionTypeTag = (actionType: string) => {
  if (actionType.includes('warning')) return 'warning'
  if (actionType.includes('user')) return 'primary'
  if (actionType.includes('delete')) return 'danger'
  if (actionType.includes('create')) return 'success'
  if (actionType.includes('update')) return 'info'
  return 'info'
}

const getRoleTagType = (role: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' => {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'primary'> = { user: 'success', counselor: 'warning', admin: 'danger' }
  return map[role] || 'info'
}

const ROLE_LABEL_KEYS: Record<string, string> = {
  user: 'role.user',
  counselor: 'role.counselor',
  admin: 'role.admin'
}

const getRoleLabel = (role: string): string => {
  const key = ROLE_LABEL_KEYS[role]
  return key ? t(key) : role
}

// ISS-060 备注：safeJson 在 copyDetail 中使用（非模板），保留不删除
const safeJson = (value: Record<string, unknown> | null) => JSON.stringify(value ?? {}, null, 2)

const fetchData = async () => {
  loading.value = true
  pageError.value = ''
  try {
    const data = await adminApi.listAdminOperationLogs({
      page: page.value,
      page_size: pageSize.value,
      action_type: filters.actionType,
      operator_role: filters.operatorRole || undefined,
      start_time: filters.range?.[0],
      end_time: filters.range?.[1]
    })
    rows.value = data.items
    total.value = data.total
  } catch (error) {
    pageError.value = showHttpFeedback(error, t('adminOperationLogs.loadFailed')).detail
  } finally {
    loading.value = false
  }
}

const onPageChange = async (value: number) => { await queryState.setQuery({ page: value }); fetchData() }
const onPageSizeChange = async (value: number) => { await queryState.setQuery({ page_size: value, page: 1 }); fetchData() }
const handleSearch = async () => { await queryState.setQuery({ page: 1, action_type: filters.actionType, operator_role: filters.operatorRole, operator_name: filters.operatorName, start_time: filters.range?.[0], end_time: filters.range?.[1] }); fetchData() }
const handleReset = async () => { filters.actionType = undefined; filters.operatorRole = ''; filters.operatorName = ''; filters.range = []; await queryState.setQuery({ page: 1, action_type: undefined, operator_role: undefined, operator_name: undefined, start_time: undefined, end_time: undefined }); fetchData() }

const exportLogs = async () => {
  exporting.value = true
  try {
    // ISS-080: 调用后端导出接口获取全部筛选结果，而非仅导出当前页
    const data = await adminApi.exportAdminOperationLogs({
      action_type: filters.actionType,
      operator_role: filters.operatorRole || undefined,
      start_time: filters.range?.[0],
      end_time: filters.range?.[1]
    })
    const allRows = data.items
    // ISS-052 修复：复用 exportToCSV，内部统一调用 sanitizeCellForExcel 防止公式注入
    exportToCSV(
      allRows as unknown as Record<string, unknown>[],
      [
        { key: 'id', label: t('adminOperationLogs.csvHeaderId') },
        { key: 'action_type', label: t('adminOperationLogs.csvHeaderActionType') },
        { key: 'operator_role', label: t('adminOperationLogs.csvHeaderOperatorRole') },
        { key: 'target_type', label: t('adminOperationLogs.csvHeaderTargetType') },
        { key: 'target_id', label: t('adminOperationLogs.csvHeaderTargetId') },
        { key: 'created_at', label: t('adminOperationLogs.csvHeaderCreatedAt') }
      ],
      `operation_logs_${new Date().toISOString().slice(0, 10)}.csv`
    )
    ElMessage.success(t('adminOperationLogs.exportSuccess', { count: allRows.length }))
  } catch (error) {
    showHttpFeedback(error, t('adminOperationLogs.exportFailed'))
  } finally {
    exporting.value = false
  }
}

const openDetail = (row: Record<string, unknown>) => {
  // ISS-013 修复：权限不足改为行级 ElMessage.warning 提示，避免污染页面级 pageError 导致整页错误
  if (!canAuditDetail) {
    ElMessage.warning(t('adminOperationLogs.noAuditPermission'))
    return
  }
  current.value = row
  detailVisible.value = true
}

const copyDetail = async () => {
  if (!current.value) return
  try {
    await navigator.clipboard.writeText(safeJson(current.value))
    ElMessage.success(t('adminOperationLogs.copySuccess'))
  } catch {
    ElMessage.error(t('adminOperationLogs.copyFailed'))
  }
}

onMounted(fetchData)
</script>

<style scoped>
.operation-logs-page {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.json-view { margin: 0; white-space: pre-wrap; word-break: break-word; }
</style>
