<template>
  <ListPageScaffold
    title="操作日志"
    :loading="loading"
    :empty="!loading && rows.length === 0"
    :error-message="pageError"
    empty-text="暂无日志数据"
    @retry="fetchData"
  >
    <template #filters>
      <FilterBar
        @search="handleSearch"
        @reset="handleReset"
      >
        <el-form-item label="动作类型">
          <el-input
            v-model="filters.actionType"
            clearable
            placeholder="可输入动作类型，如 warning_handle"
            style="width: 220px"
          />
        </el-form-item>

        <el-form-item label="操作者角色">
          <el-select
            v-model="filters.operatorRole"
            clearable
            style="width: 180px"
          >
            <el-option
              label="用户"
              value="user"
            />
            <el-option
              label="咨询师"
              value="counselor"
            />
            <el-option
              label="管理员"
              value="admin"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="操作者">
          <el-input
            v-model="filters.operatorName"
            clearable
            placeholder="输入用户名"
            style="width: 160px"
          />
        </el-form-item>

        <el-form-item label="时间区间">
          <el-date-picker
            v-model="filters.range"
            type="datetimerange"
            value-format="YYYY-MM-DD HH:mm:ss"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="success"
            plain
            :loading="exporting"
            @click="exportLogs"
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
      <el-table-column
        prop="id"
        label="ID"
        width="80"
      />
      <el-table-column
        prop="action_type"
        label="操作类型"
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
        label="操作者角色"
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
        label="目标类型"
        width="140"
      />
      <el-table-column
        prop="target_id"
        label="目标ID"
        width="120"
      />
      <el-table-column
        prop="created_at"
        label="时间"
        min-width="180"
      />
      <el-table-column
        label="操作"
        width="160"
        fixed="right"
      >
        <template #default="{ row }">
          <ActionColumn
            label="查看详情"
            :disabled="!canAuditDetail"
            disabled-reason="无审计权限"
            show-audit
            @action="openDetail(row)"
          />
        </template>
      </el-table-column>
    </PageTable>

    <el-dialog
      v-model="detailVisible"
      title="日志详情"
      width="620px"
      @closed="current = null"
    >
      <pre class="json-view">{{ JSON.stringify(current, null, 2) }}</pre>
      <template #footer>
        <el-button
          :disabled="!current"
          @click="copyDetail"
        >
          复制详情
        </el-button>
        <el-button
          type="primary"
          @click="detailVisible = false"
        >
          关闭
        </el-button>
      </template>
    </el-dialog>
  </ListPageScaffold>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { adminApi, type OperationLogItem } from '@/api/adminApi'
import PageTable from '@/components/common/PageTable.vue'
import FilterBar from '@/components/common/FilterBar.vue'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import ActionColumn from '@/components/common/ActionColumn.vue'
import type { ActionType } from '@/types/contracts'
import { hasPermission } from '@/types/permission'
import { useAuthStore } from '@/stores/auth'
import { useListQueryState } from '@/composables/useListQueryState'
import { showHttpFeedback } from '@/utils/httpFeedback'
import { sanitizeCellForExcel } from '@/utils/exportUtils'

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

const getRoleLabel = (role: string) => {
  const map: Record<string, string> = { user: '用户', counselor: '咨询师', admin: '管理员' }
  return map[role] || role
}

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
    pageError.value = showHttpFeedback(error, '日志加载失败').detail
  } finally {
    loading.value = false
  }
}

const onPageChange = async (value: number) => { await queryState.setQuery({ page: value }); fetchData() }
const onPageSizeChange = async (value: number) => { await queryState.setQuery({ page_size: value, page: 1 }); fetchData() }
const handleSearch = async () => { await queryState.setQuery({ page: 1, action_type: filters.actionType, operator_role: filters.operatorRole, operator_name: filters.operatorName, start_time: filters.range?.[0], end_time: filters.range?.[1] }); fetchData() }
const handleReset = async () => { filters.actionType = undefined; filters.operatorRole = ''; filters.operatorName = ''; filters.range = []; await queryState.setQuery({ page: 1, action_type: undefined, operator_role: undefined, operator_name: undefined, start_time: undefined, end_time: undefined }); fetchData() }

const exportLogs = () => {
  exporting.value = true
  try {
    const headers = ['ID', '操作类型', '操作者角色', '目标类型', '目标ID', '时间']
    // P1-FE-006 修复：对每个单元格调用 sanitizeCellForExcel 防止 CSV 公式注入
    const csvContent = [
      headers.map((h) => `"${sanitizeCellForExcel(String(h)).replace(/"/g, '""')}"`).join(','),
      ...rows.value.map((row) => [
        row.id,
        row.action_type,
        row.operator_role,
        row.target_type,
        row.target_id,
        row.created_at
      ].map((v) => `"${sanitizeCellForExcel(String(v)).replace(/"/g, '""')}"`).join(','))
    ].join('\n')

    const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `operation_logs_${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    URL.revokeObjectURL(link.href)
    ElMessage.success('日志导出成功')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

const openDetail = (row: Record<string, unknown>) => {
  if (!canAuditDetail) {
    pageError.value = '无权限查看审计详情'
    return
  }
  current.value = row
  detailVisible.value = true
}

const copyDetail = async () => {
  if (!current.value) return
  try {
    await navigator.clipboard.writeText(safeJson(current.value))
    ElMessage.success('已复制日志详情')
  } catch {
    ElMessage.error('复制失败，请手动选择内容复制')
  }
}

onMounted(fetchData)
</script>

<style scoped>
.json-view { margin: 0; white-space: pre-wrap; word-break: break-word; }
</style>
