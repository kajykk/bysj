<template>
  <div class="counselor-users-page">
    <UserOverviewStatsCard />
    <ListPageScaffold
      :title="t('counselorUsers.pageTitle')"
      :loading="loading"
      :empty="!loading && rows.length === 0"
      :error-message="pageError"
      :empty-text="t('counselorUsers.emptyText')"
      @retry="fetchData"
    >
      <template #filters>
        <FilterBar
          @search="fetchData"
          @reset="handleReset"
        >
          <el-form-item :label="t('counselorUsers.filterRiskLevel')">
            <el-select
              v-model="filters.riskLevel"
              :placeholder="t('counselorUsers.filterRiskLevelPlaceholder')"
              clearable
              style="width: 140px"
              @change="onRiskLevelChange"
            >
              <el-option
                :label="t('counselorUsers.riskOptionNone')"
                :value="0"
              />
              <el-option
                :label="t('counselorUsers.riskOptionLow')"
                :value="1"
              />
              <el-option
                :label="t('counselorUsers.riskOptionMedium')"
                :value="2"
              />
              <el-option
                :label="t('counselorUsers.riskOptionHigh')"
                :value="3"
              />
              <el-option
                :label="t('counselorUsers.riskOptionCritical')"
                :value="4"
              />
            </el-select>
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
          :label="t('counselorUsers.colId')"
          width="80"
        />
        <el-table-column
          :label="t('counselorUsers.colUser')"
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
          :label="t('counselorUsers.colEmail')"
          min-width="220"
        />
        <el-table-column
          :label="t('counselorUsers.colRiskLevel')"
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
          :label="t('counselorUsers.colStatus')"
          width="120"
        />
        <el-table-column
          :label="t('counselorUsers.colOperation')"
          width="140"
          fixed="right"
        >
          <template #default="{ row }">
            <ActionColumn
              :label="t('counselorUsers.btnViewDetail')"
              :disabled="!canViewConsultation"
              :disabled-reason="t('counselorUsers.noPermission')"
              show-audit
              @action="openDetail(row)"
            />
          </template>
        </el-table-column>
      </PageTable>
    </ListPageScaffold>

    <el-drawer
      v-model="detailVisible"
      :title="t('counselorUsers.drawerTitle')"
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
          <el-descriptions-item :label="t('counselorUsers.detailColId')">
            {{ detailRow.id }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('counselorUsers.detailColEmail')">
            {{ detailRow.email || '—' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('counselorUsers.detailColRiskLevel')">
            <el-tag
              :type="getRiskTagType(detailRow.risk_level)"
              size="small"
            >
              {{ getRiskLabel(detailRow.risk_level) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('counselorUsers.detailColStatus')">
            {{ detailRow.status }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { counselorApi, type UserManageItem } from '@/api/counselorApi'
import PageTable from '@/components/common/PageTable.vue'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import UserOverviewStatsCard from './components/counselor-users/UserOverviewStatsCard.vue'
import ActionColumn from '@/components/common/ActionColumn.vue'
import FilterBar from '@/components/common/FilterBar.vue'
import { mockUsers } from '@/mocks/business'
import { withMockFallback } from '@/utils/mockFallback'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { hasPermission } from '@/config/permissions'
import { useAuthStore } from '@/stores/auth'
import { useListQueryState } from '@/composables/useListQueryState'

const { t } = useI18n()

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

const canViewConsultation = hasPermission(auth.role, 'counselor.user.consultation.view')

const getInitials = (name: string) => {
  if (!name) return '?'
  return name.charAt(0).toUpperCase()
}

const getAvatarColor = (username: string) => {
  const colors = ['#2e6fa8', '#5a9e3a', '#d4923a', '#d65a5a', '#7a8290', '#9254de', '#ff85c0']
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

const RISK_LABEL_KEYS = ['riskLabelNone', 'riskLabelLow', 'riskLabelMedium', 'riskLabelHigh', 'riskLabelCritical']

const getRiskLabel = (level: number | undefined) => {
  const key = RISK_LABEL_KEYS[level ?? 0]
  return key ? t(`counselorUsers.${key}`) : t('counselorUsers.riskLabelUnknown')
}

const fetchData = async () => {
  loading.value = true
  pageError.value = ''
  try {
    const data = await withMockFallback(
      () => counselorApi.getCounselorUsers({ page: page.value, page_size: pageSize.value, risk_level: filters.riskLevel ?? undefined }),
      () => mockUsers(page.value, pageSize.value)
    )
    rows.value = data.items.map(normalizeUserRow)
    total.value = data.total
  } catch (error) {
    pageError.value = normalizeHttpError(error, t('counselorUsers.loadFailed')).detail
  } finally {
    loading.value = false
  }
}

const onRiskLevelChange = async () => {
  await queryState.setQuery({ page: 1 })
  fetchData()
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
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.user-cell {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.user-info {
  display: flex;
  flex-direction: column;
}

.user-name {
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

.user-username {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.detail-content {
  padding: var(--spacing-sm) 0;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-xl);
  padding-bottom: var(--spacing-lg);
  border-bottom: 1px solid var(--border-light);
}

.detail-header-info h3 {
  margin: 0 0 var(--spacing-xs);
  font-size: var(--font-size-large);
  color: var(--text-primary);
}

.detail-header-info p {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-base);
}

/* 响应式：移动端适配 */
@media (max-width: 768px) {
  :deep(.el-drawer) {
    width: 90% !important;
  }
}
</style>
