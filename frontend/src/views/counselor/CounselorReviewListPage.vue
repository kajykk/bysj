<template>
  <div class="review-list-page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span class="card-title">{{ t('counselorReviews.listTitle') }}</span>
          <el-button
            type="primary"
            @click="loadReviews"
          >
            <el-icon><Refresh /></el-icon>
            {{ t('counselorReviews.btnRefresh') }}
          </el-button>
        </div>
      </template>

      <!-- 筛选栏 -->
      <el-form
        :inline="true"
        class="filter-form"
      >
        <el-form-item :label="t('counselorReviews.filterStatusLabel')">
          <el-select
            v-model="filterStatus"
            :placeholder="t('counselorReviews.filterStatusPlaceholder')"
            clearable
          >
            <el-option
              :label="t('counselorReviews.statusPending')"
              value="pending"
            />
            <el-option
              :label="t('counselorReviews.statusInReview')"
              value="in_review"
            />
            <el-option
              :label="t('counselorReviews.statusResolved')"
              value="resolved"
            />
            <el-option
              :label="t('counselorReviews.statusEscalated')"
              value="escalated"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('counselorReviews.filterPriorityLabel')">
          <el-select
            v-model="filterPriority"
            :placeholder="t('counselorReviews.filterPriorityPlaceholder')"
            clearable
          >
            <el-option
              :label="t('counselorReviews.priorityNormal')"
              value="normal_review"
            />
            <el-option
              :label="t('counselorReviews.priorityHighRisk')"
              value="high_risk_review"
            />
            <el-option
              :label="t('counselorReviews.priorityCrisis')"
              value="crisis_review"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            @click="loadReviews"
          >
            {{ t('counselorReviews.btnQuery') }}
          </el-button>
          <el-button @click="resetFilter">
            {{ t('counselorReviews.btnReset') }}
          </el-button>
        </el-form-item>
      </el-form>

      <!-- 统计卡片 -->
      <el-row
        :gutter="16"
        class="stats-row"
      >
        <el-col
          :xs="12"
          :sm="6"
        >
          <el-statistic
            :title="t('counselorReviews.statPending')"
            :value="stats.pending"
          />
        </el-col>
        <el-col
          :xs="12"
          :sm="6"
        >
          <el-statistic
            :title="t('counselorReviews.statInReview')"
            :value="stats.in_review"
          />
        </el-col>
        <el-col
          :xs="12"
          :sm="6"
        >
          <el-statistic
            :title="t('counselorReviews.statResolved')"
            :value="stats.resolved"
          />
        </el-col>
        <el-col
          :xs="12"
          :sm="6"
        >
          <el-statistic
            :title="t('counselorReviews.statCrisis')"
            :value="stats.crisis_count"
          >
            <template #suffix>
              <el-icon class="crisis-icon">
                <Warning />
              </el-icon>
            </template>
          </el-statistic>
        </el-col>
      </el-row>

      <!-- 任务列表 -->
      <el-table
        v-loading="loading"
        :data="reviews"
        class="review-table"
        @row-click="handleRowClick"
      >
        <el-table-column
          prop="id"
          :label="t('counselorReviews.colId')"
          width="60"
        />
        <el-table-column
          prop="user_id"
          :label="t('counselorReviews.colUserId')"
          width="80"
        />
        <el-table-column
          :label="t('counselorReviews.colRiskLevel')"
          width="100"
        >
          <template #default="{ row }">
            <el-tag :type="getRiskLevelType(row.risk_level)">
              {{ getRiskLevelLabel(row.risk_level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          :label="t('counselorReviews.colPriority')"
          width="100"
        >
          <template #default="{ row }">
            <el-tag
              :type="getPriorityType(row.priority)"
              effect="dark"
            >
              {{ getPriorityLabel(row.priority) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          :label="t('counselorReviews.colStatus')"
          width="100"
        >
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          :label="t('counselorReviews.colCrisisOverride')"
          width="100"
        >
          <template #default="{ row }">
            <el-tag
              v-if="row.crisis_override"
              type="danger"
              effect="dark"
            >
              {{ t('counselorReviews.yesLabel') }}
            </el-tag>
            <span v-else>{{ t('counselorReviews.noLabel') }}</span>
          </template>
        </el-table-column>
        <el-table-column
          :label="t('counselorReviews.colReviewTriggers')"
          min-width="200"
        >
          <template #default="{ row }">
            <el-tag
              v-for="trigger in row.review_triggers"
              :key="trigger"
              type="warning"
              size="small"
              style="margin-right: 4px; margin-bottom: 4px"
            >
              {{ trigger }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="created_at"
          :label="t('counselorReviews.colCreatedAt')"
          width="180"
        >
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('counselorReviews.colOperation')"
          width="180"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              @click.stop="handleRowClick(row)"
            >
              {{ t('counselorReviews.btnView') }}
            </el-button>
            <!-- ISS-060: 领取按钮，仅 pending 状态显示 -->
            <el-button
              v-if="row.status === 'pending'"
              type="primary"
              size="small"
              @click.stop="assignReview(row)"
            >
              {{ t('counselorReviews.btnAssign') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        style="margin-top: 16px; justify-content: flex-end"
        @change="loadReviews"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Refresh, Warning } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { counselorApi, type ReviewItem, type ReviewStats } from '@/api/counselorApi'
// P2-A 修复：复用 formatUtils 的 formatDate，避免本地重复定义
import { formatDate } from '@/utils/formatUtils'

const { t } = useI18n()
const router = useRouter()

const loading = ref(false)
const reviews = ref<ReviewItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filterStatus = ref('')
const filterPriority = ref('')

const stats = ref<ReviewStats>({
  total: 0,
  pending: 0,
  in_review: 0,
  resolved: 0,
  escalated: 0,
  crisis_count: 0,
  high_risk_count: 0,
})

const loadReviews = async () => {
  loading.value = true
  try {
    const query: { page: number; page_size: number; status?: string; priority?: string } = {
      page: page.value,
      page_size: pageSize.value,
    }
    if (filterStatus.value) query.status = filterStatus.value
    if (filterPriority.value) query.priority = filterPriority.value

    const data = await counselorApi.getReviews(query)
    reviews.value = data.items
    total.value = data.total
  } catch (error) {
    ElMessage.error(t('counselorReviews.loadListFailed'))
  } finally {
    loading.value = false
  }
}

const loadStats = async () => {
  try {
    stats.value = await counselorApi.getReviewStats()
  } catch (error) {
    console.error(t('counselorReviews.loadStatsFailed'), error)
  }
}

const resetFilter = () => {
  filterStatus.value = ''
  filterPriority.value = ''
  page.value = 1
  loadReviews()
}

// P1-E 修复：移除 any 类型，使用明确的 ReviewItem 类型
const handleRowClick = (row: ReviewItem) => {
  router.push(`/counselor/reviews/${row.id}`)
}

// ISS-060: 领取复核任务
const assignReview = async (row: ReviewItem) => {
  try {
    await ElMessageBox.confirm(t('counselorReviews.assignConfirm'), t('counselorReviews.assignConfirmTitle'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await counselorApi.assignReview(row.id)
    ElMessage.success(t('counselorReviews.assignSuccess'))
    await loadReviews()
    await loadStats()
  } catch (error) {
    ElMessage.error(t('counselorReviews.assignFailed'))
  }
}

type ElTagType = 'primary' | 'success' | 'warning' | 'danger' | 'info'

const getRiskLevelType = (level: number): ElTagType => {
  const types: ElTagType[] = ['success', 'success', 'warning', 'danger', 'danger']
  return types[level] || 'info'
}

const RISK_LEVEL_LABEL_KEYS = ['riskLevelNone', 'riskLevelLow', 'riskLevelMedium', 'riskLevelHigh', 'riskLevelCritical']

const getRiskLevelLabel = (level: number) => {
  const key = RISK_LEVEL_LABEL_KEYS[level]
  return key ? t(`counselorReviews.${key}`) : t('counselorReviews.riskLevelUnknown')
}

const getPriorityType = (priority: string): ElTagType => {
  const types: Record<string, ElTagType> = {
    normal_review: 'info',
    high_risk_review: 'warning',
    crisis_review: 'danger',
  }
  return types[priority] || 'info'
}

const PRIORITY_LABEL_KEYS: Record<string, string> = {
  normal_review: 'priorityNormal',
  high_risk_review: 'priorityHighRisk',
  crisis_review: 'priorityCrisis',
}

const getPriorityLabel = (priority: string) => {
  const key = PRIORITY_LABEL_KEYS[priority]
  return key ? t(`counselorReviews.${key}`) : t('counselorReviews.priorityUnknown')
}

const getStatusType = (status: string): ElTagType => {
  const types: Record<string, ElTagType> = {
    pending: 'warning',
    in_review: 'primary',
    resolved: 'success',
    escalated: 'danger',
  }
  return types[status] || 'info'
}

const STATUS_LABEL_KEYS: Record<string, string> = {
  pending: 'statusPending',
  in_review: 'statusInReview',
  resolved: 'statusResolved',
  escalated: 'statusEscalated',
}

const getStatusLabel = (status: string) => {
  const key = STATUS_LABEL_KEYS[status]
  return key ? t(`counselorReviews.${key}`) : t('counselorReviews.statusUnknown')
}

onMounted(() => {
  loadReviews()
  loadStats()
})
</script>

<style scoped>
.review-list-page {
  padding: 16px;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: var(--font-size-large);
  font-weight: var(--font-weight-semibold);
}

.filter-form {
  margin-bottom: var(--spacing-lg);
}

.stats-row {
  margin-bottom: var(--spacing-lg);
}

.review-table {
  width: 100%;
  margin-top: var(--spacing-lg);
}

.crisis-icon {
  color: var(--danger-color);
}

:deep(.el-table__row) {
  cursor: pointer;
}

:deep(.el-table__row:hover) {
  background-color: var(--bg-hover);
}
</style>
