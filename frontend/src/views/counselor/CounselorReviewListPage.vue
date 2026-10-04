<template>
  <div class="review-list-page">
    <ReviewStatsCard :stats="stats" />
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
            <!-- P2-TS 修复：el-table 的 slot row 推导为 DefaultRow，与 handler 的
                 ReviewItem 参数不兼容（本文件原有 2 处、全仓 16 文件共 47 处同类错误）。
                 此处显式断言，不留新的类型债。 -->
            <el-button
              type="primary"
              size="small"
              @click.stop="handleRowClick(row as ReviewItem)"
            >
              {{ t('counselorReviews.btnView') }}
            </el-button>
            <!-- ISS-060: 领取按钮，仅 pending 状态显示（咨询师） -->
            <el-button
              v-if="row.status === 'pending' && !isAdmin"
              type="primary"
              size="small"
              @click.stop="assignReview(row as ReviewItem)"
            >
              {{ t('counselorReviews.btnAssign') }}
            </el-button>
            <!-- AUDIT-2026-10-01：管理员把任务指定分配给某位咨询师 -->
            <el-button
              v-if="row.status === 'pending' && isAdmin"
              type="primary"
              size="small"
              @click.stop="openAssignDialog(row as ReviewItem)"
            >
              {{ t('counselorReviews.btnAssignTo') }}
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

    <!-- AUDIT-2026-10-01：管理员「指定分配」对话框 -->
    <el-dialog
      v-model="assignDialogVisible"
      :title="t('counselorReviews.assignToTitle')"
      width="440px"
    >
      <el-form label-width="96px">
        <el-form-item :label="t('counselorReviews.assignToSelectLabel')">
          <el-select
            v-model="selectedCounselorId"
            :placeholder="t('counselorReviews.assignToPlaceholder')"
            :loading="assignLoadingOptions"
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="item in counselorOptions"
              :key="item.id"
              :label="item.nickname || item.username"
              :value="item.id"
            />
          </el-select>
          <div
            v-if="!assignLoadingOptions && !counselorOptions.length"
            class="assign-empty-tip"
          >
            {{ t('counselorReviews.assignToEmpty') }}
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignDialogVisible = false">
          {{ t('common.cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="assignSubmitting"
          :disabled="!selectedCounselorId"
          @click="submitAssign"
        >
          {{ t('common.confirm') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { counselorApi, type CounselorBrief, type ReviewItem, type ReviewStats } from '@/api/counselorApi'
import { useAuthStore } from '@/stores/auth'
import ReviewStatsCard from './components/counselor-reviews/ReviewStatsCard.vue'
// P2-A 修复：复用 formatUtils 的 formatDate，避免本地重复定义
import { formatDate } from '@/utils/formatUtils'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

// AUDIT-2026-10-01：管理员与咨询师共用本页，但操作语义不同——
// 咨询师是「领取」（后端会校验学生绑定关系），管理员是「指定分配」给某位咨询师。
const isAdmin = computed(() => auth.role === 'admin' || auth.role === 'super_admin')

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

// AUDIT-2026-10-01：管理员「指定分配」到具体咨询师。
// 与咨询师的「领取」区分：管理员可选任意 active 咨询师，不受学生绑定关系限制（后端亦如此）。
const assignDialogVisible = ref(false)
const assignTarget = ref<ReviewItem | null>(null)
const counselorOptions = ref<CounselorBrief[]>([])
const selectedCounselorId = ref<number | null>(null)
const assignSubmitting = ref(false)
const assignLoadingOptions = ref(false)

const openAssignDialog = async (row: ReviewItem) => {
  assignTarget.value = row
  selectedCounselorId.value = null
  assignDialogVisible.value = true
  // 名单在会话内复用，避免每次打开都请求
  if (counselorOptions.value.length) return
  assignLoadingOptions.value = true
  try {
    const data = await counselorApi.getAssignableCounselors()
    counselorOptions.value = data.items
  } catch (error) {
    ElMessage.error(t('counselorReviews.assignToLoadFailed'))
  } finally {
    assignLoadingOptions.value = false
  }
}

const submitAssign = async () => {
  if (!assignTarget.value || !selectedCounselorId.value) return
  assignSubmitting.value = true
  try {
    await counselorApi.assignReview(assignTarget.value.id, { assignee_id: selectedCounselorId.value })
    ElMessage.success(t('counselorReviews.assignToSuccess'))
    assignDialogVisible.value = false
    await loadReviews()
    await loadStats()
  } catch (error) {
    ElMessage.error(t('counselorReviews.assignToFailed'))
  } finally {
    assignSubmitting.value = false
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
  /* BLANK-02 修复：外层 padding 交由 .layout-main 统一管控，避免双重内边距 */
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
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

.review-table {
  width: 100%;
  margin-top: var(--spacing-lg);
}

/* AUDIT-2026-10-01：指定分配对话框的空名单提示 */
.assign-empty-tip {
  margin-top: var(--spacing-xs);
  font-size: var(--font-size-small);
  color: var(--text-secondary);
}

:deep(.el-table__row) {
  cursor: pointer;
}

:deep(.el-table__row:hover) {
  background-color: var(--bg-hover);
}
</style>
