<template>
  <div class="counselor-users-page">
    <ListPageScaffold
      title="用户管理"
      :loading="loading"
      :empty="!loading && rows.length === 0"
      :error-message="pageError"
      empty-text="暂无用户数据"
      @retry="fetchData"
    >
    <template #filters>
      <FilterBar
        @search="fetchData"
        @reset="handleReset"
      >
        <el-form-item label="风险等级">
          <el-select
            v-model="filters.riskLevel"
            placeholder="全部等级"
            clearable
            style="width: 140px"
          >
            <el-option
              label="无风险"
              :value="0"
            />
            <el-option
              label="低风险"
              :value="1"
            />
            <el-option
              label="中风险"
              :value="2"
            />
            <el-option
              label="高风险"
              :value="3"
            />
            <el-option
              label="严重"
              :value="4"
            />
          </el-select>
        </el-form-item>
      </FilterBar>
    </template>

    <PageTable
      :loading="loading"
      :data="filteredRows"
      :total="filteredTotal"
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
        label="用户"
        min-width="200"
      >
        <template #default="{ row }">
          <div class="user-cell">
            <el-avatar
              :size="32"
              :style="{ backgroundColor: getAvatarColor(row.username) }"
            >
              {{ getInitials(row.nickname || row.username) }}
            </el-avatar>
            <div class="user-info">
              <div class="user-name">
                {{ row.nickname || row.username }}
              </div>
              <div class="user-username">
                @{{ row.username }}
              </div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        prop="email"
        label="邮箱"
        min-width="220"
      />
      <el-table-column
        label="风险等级"
        width="120"
      >
        <template #default="{ row }">
          <el-tag
            :type="getRiskTagType(row.risk_level)"
            size="small"
          >
            {{ getRiskLabel(row.risk_level) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        prop="status"
        label="状态"
        width="120"
      />
      <el-table-column
        label="操作"
        width="140"
        fixed="right"
      >
        <template #default="{ row }">
          <ActionColumn
            label="查看详情"
            :disabled="!canViewConsultation"
            disabled-reason="无权限"
            show-audit
            @action="openDetail(row)"
          />
        </template>
      </el-table-column>
    </PageTable>
  </ListPageScaffold>

  <el-drawer
    v-model="detailVisible"
    title="用户详情"
    size="500px"
    destroy-on-close
  >
    <div
      v-if="detailRow"
      class="detail-content"
    >
      <div class="detail-header">
        <el-avatar
          :size="64"
          :style="{ backgroundColor: getAvatarColor(detailRow.username) }"
        >
          {{ getInitials(detailRow.nickname || detailRow.username) }}
        </el-avatar>
        <div class="detail-header-info">
          <h3>{{ detailRow.nickname || detailRow.username }}</h3>
          <p>@{{ detailRow.username }}</p>
        </div>
      </div>
      <el-descriptions
        :column="1"
        border
      >
        <el-descriptions-item label="ID">
          {{ detailRow.id }}
        </el-descriptions-item>
        <el-descriptions-item label="邮箱">
          {{ detailRow.email || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="风险等级">
          <el-tag
            :type="getRiskTagType(detailRow.risk_level)"
            size="small"
          >
            {{ getRiskLabel(detailRow.risk_level) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          {{ detailRow.status }}
        </el-descriptions-item>
      </el-descriptions>
    </div>
  </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { counselorApi, type UserManageItem } from '@/api/counselorApi'
import PageTable from '@/components/common/PageTable.vue'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import ActionColumn from '@/components/common/ActionColumn.vue'
import FilterBar from '@/components/common/FilterBar.vue'
import { mockUsers } from '@/mocks/business'
import { withMockFallback } from '@/utils/mockFallback'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { hasPermission } from '@/types/permission'
import { useAuthStore } from '@/stores/auth'
import { useListQueryState } from '@/composables/useListQueryState'

interface UserRow extends UserManageItem {
  risk_level: number
}

const normalizeRiskLevel = (value: UserManageItem['risk_level'] | UserManageItem['latest_risk_level']): number => {
  if (typeof value === 'number') return value
  const map: Record<string, number> = { none: 0, low: 1, medium: 2, high: 3, critical: 4 }
  return map[String(value ?? 'none')] ?? 0
}

const normalizeUserRow = (row: UserManageItem): UserRow => ({
  ...row,
  risk_level: normalizeRiskLevel(row.risk_level ?? row.latest_risk_level),
})

const auth = useAuthStore()
const queryState = useListQueryState('cu')

const loading = ref(false)
const rows = ref<UserRow[]>([])
const total = ref(0)
const pageError = ref('')
const detailVisible = ref(false)
const detailRow = ref<UserRow | null>(null)

const filters = reactive({ riskLevel: null as number | null })

const page = computed(() => queryState.page.value)
const pageSize = computed(() => queryState.pageSize.value)

const filteredRows = computed(() => {
  if (filters.riskLevel === null) return rows.value
  return rows.value.filter((row) => row.risk_level === filters.riskLevel)
})

const filteredTotal = computed(() => filteredRows.value.length)

const canViewConsultation = hasPermission(auth.role, 'counselor.user.consultation.view')

const getInitials = (name: string) => {
  if (!name) return '?'
  return name.charAt(0).toUpperCase()
}

const getAvatarColor = (username: string) => {
  const colors = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399', '#9254de', '#ff85c0']
  let hash = 0
  for (let i = 0; i < username.length; i++) {
    hash = username.charCodeAt(i) + ((hash << 5) - hash)
  }
  return colors[Math.abs(hash) % colors.length]
}

const getRiskTagType = (level: number | undefined): 'info' | 'success' | 'warning' | 'danger' | 'primary' => {
  const map: Record<number, 'info' | 'success' | 'warning' | 'danger' | 'primary'> = { 0: 'info', 1: 'success', 2: 'warning', 3: 'danger', 4: 'danger' }
  return map[level ?? 0] || 'info'
}

const getRiskLabel = (level: number | undefined) => {
  const map: Record<number, string> = { 0: '无风险', 1: '低风险', 2: '中风险', 3: '高风险', 4: '严重' }
  return map[level ?? 0] || '未知'
}

const fetchData = async () => {
  loading.value = true
  pageError.value = ''
  try {
    const data = await withMockFallback(
      () => counselorApi.getCounselorUsers({ page: page.value, page_size: pageSize.value }),
      () => mockUsers(page.value, pageSize.value)
    )
    rows.value = data.items.map(normalizeUserRow)
    total.value = data.total
  } catch (error) {
    pageError.value = normalizeHttpError(error, '用户列表加载失败').detail
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

const openDetail = (row: UserManageItem) => {
  detailRow.value = normalizeUserRow(row)
  detailVisible.value = true
}

const handleReset = () => {
  filters.riskLevel = null
  fetchData()
}

onMounted(fetchData)
</script>

<style scoped>
.counselor-users-page {
  width: 100%;
}

.user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-info {
  display: flex;
  flex-direction: column;
}

.user-name {
  font-weight: 500;
  color: #303133;
}

.user-username {
  font-size: 12px;
  color: #909399;
}

.detail-content {
  padding: 8px 0;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e4e7ed;
}

.detail-header-info h3 {
  margin: 0 0 4px;
  font-size: 18px;
  color: #303133;
}

.detail-header-info p {
  margin: 0;
  color: #909399;
  font-size: 14px;
}
</style>
