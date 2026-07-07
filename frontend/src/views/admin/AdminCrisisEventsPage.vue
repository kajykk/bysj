<template>
  <ListPageScaffold
    :title="t('adminCrisisEvents.title')"
    :loading="loading"
    :empty="!loading && rows.length === 0"
    :error-message="pageError"
    :empty-text="t('adminCrisisEvents.empty')"
    @retry="fetchData"
  >
    <template #filters>
      <FilterBar
        @search="handleSearch"
        @reset="handleReset"
      >
        <el-form-item :label="t('adminCrisisEvents.filterStatus')">
          <el-select
            v-model="filters.status"
            clearable
            style="width: 140px"
          >
            <el-option
              :label="t('adminCrisisEvents.status.detected')"
              value="detected"
            />
            <el-option
              :label="t('adminCrisisEvents.status.reviewed')"
              value="reviewed"
            />
            <el-option
              :label="t('adminCrisisEvents.status.escalated')"
              value="escalated"
            />
            <el-option
              :label="t('adminCrisisEvents.status.resolved')"
              value="resolved"
            />
          </el-select>
        </el-form-item>

        <el-form-item :label="t('adminCrisisEvents.filterDateRange')">
          <el-date-picker
            v-model="filters.dateRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            :range-separator="t('adminCrisisEvents.rangeSeparator')"
            :start-placeholder="t('adminCrisisEvents.rangeStart')"
            :end-placeholder="t('adminCrisisEvents.rangeEnd')"
            :default-time="[new Date(0, 0, 0, 0, 0, 0), new Date(0, 0, 0, 23, 59, 59)]"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="success"
            plain
            :loading="exporting"
            :disabled="!filters.dateRange || filters.dateRange.length < 2"
            @click="handleExport"
          >
            <el-icon><Download /></el-icon> {{ t('adminCrisisEvents.exportBtn') }}
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
        :label="t('adminCrisisEvents.colId')"
        width="70"
      />
      <el-table-column
        prop="user_id"
        :label="t('adminCrisisEvents.colUserId')"
        width="100"
      >
        <template #default="{ row }">
          {{ maskUserId(row.user_id) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="trigger_source"
        :label="t('adminCrisisEvents.colTriggerSource')"
        width="100"
      >
        <template #default="{ row }">
          <el-tag
            :type="getTriggerSourceTag(row.trigger_source)"
            size="small"
          >
            {{ getTriggerSourceLabel(row.trigger_source) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        prop="crisis_score"
        :label="t('adminCrisisEvents.colCrisisScore')"
        width="120"
      >
        <template #default="{ row }">
          <span :style="{ color: getScoreColor(row.crisis_score), fontWeight: 'bold' }">
            {{ row.crisis_score != null ? row.crisis_score.toFixed(1) : '-' }}
          </span>
          <!-- ISS-040 修复：颜色旁附加文字标签，避免颜色作为唯一状态表达（A11Y） -->
          <el-tag
            v-if="row.crisis_score != null"
            :color="getScoreColor(row.crisis_score)"
            effect="dark"
            size="small"
            class="score-label"
            :aria-label="t('adminCrisisEvents.colCrisisScore') + ': ' + getScoreLabel(row.crisis_score)"
          >
            {{ getScoreLabel(row.crisis_score) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        prop="status"
        :label="t('adminCrisisEvents.colStatus')"
        width="100"
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
        prop="crisis_keywords"
        :label="t('adminCrisisEvents.colKeywords')"
        min-width="150"
      >
        <template #default="{ row }">
          <template v-if="row.crisis_keywords && row.crisis_keywords.length">
            <el-tag
              v-for="kw in row.crisis_keywords"
              :key="kw"
              size="small"
              type="warning"
              effect="plain"
              class="keyword-tag"
            >
              {{ kw }}
            </el-tag>
          </template>
          <span
            v-else
            class="empty-cell"
          >-</span>
        </template>
      </el-table-column>
      <el-table-column
        prop="review_task_id"
        :label="t('adminCrisisEvents.colReviewTask')"
        width="90"
      >
        <template #default="{ row }">
          <template v-if="row.review_task_id">
            <el-tag
              type="primary"
              size="small"
            >
              #{{ row.review_task_id }}
            </el-tag>
          </template>
          <span
            v-else
            class="empty-cell"
          >-</span>
        </template>
      </el-table-column>
      <el-table-column
        prop="created_at"
        :label="t('adminCrisisEvents.colCreatedAt')"
        min-width="170"
      >
        <template #default="{ row }">
          {{ formatDate(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="handled_by"
        :label="t('adminCrisisEvents.colHandledBy')"
        width="100"
      >
        <template #default="{ row }">
          {{ row.handled_by ? maskUserId(row.handled_by) : '-' }}
        </template>
      </el-table-column>
      <el-table-column
        prop="handled_action"
        :label="t('adminCrisisEvents.colHandledAction')"
        min-width="120"
      >
        <template #default="{ row }">
          {{ row.handled_action || '-' }}
        </template>
      </el-table-column>
      <el-table-column
        :label="t('adminCrisisEvents.colOperation')"
        width="200"
        fixed="right"
      >
        <template #default="{ row }">
          <el-button
            v-if="canHandle(row.status)"
            link
            type="primary"
            size="small"
            @click="openHandleDialog(row)"
          >
            {{ t('adminCrisisEvents.actionHandle') }}
          </el-button>
          <el-button
            v-if="canEscalate(row.status)"
            link
            type="warning"
            size="small"
            @click="openEscalateDialog(row)"
          >
            {{ t('adminCrisisEvents.actionEscalate') }}
          </el-button>
          <el-button
            v-if="canClose(row.status)"
            link
            type="success"
            size="small"
            @click="openCloseDialog(row)"
          >
            {{ t('adminCrisisEvents.actionClose') }}
          </el-button>
          <span
            v-if="row.status === 'resolved'"
            class="empty-cell"
          >{{ t('adminCrisisEvents.statusClosed') }}</span>
        </template>
      </el-table-column>
    </PageTable>

    <!-- ISS-072 修复：处理对话框 -->
    <el-dialog
      v-model="handleDialogVisible"
      :title="t('adminCrisisEvents.handleDialogTitle')"
      width="500px"
      destroy-on-close
    >
      <el-form label-width="100px">
        <el-form-item :label="t('adminCrisisEvents.handleEventId')">
          <span>{{ currentEvent?.id }}</span>
        </el-form-item>
        <el-form-item :label="t('adminCrisisEvents.handleAction')">
          <el-select
            v-model="handleForm.action"
            :placeholder="t('adminCrisisEvents.handleActionPlaceholder')"
            style="width: 100%"
          >
            <el-option
              :label="t('adminCrisisEvents.handleActionOptions.notifyCounselor')"
              value="notify_counselor"
            />
            <el-option
              :label="t('adminCrisisEvents.handleActionOptions.emergencyContact')"
              value="emergency_contact"
            />
            <el-option
              :label="t('adminCrisisEvents.handleActionOptions.resolved')"
              value="resolved"
            />
            <el-option
              :label="t('adminCrisisEvents.handleActionOptions.escalate')"
              value="escalate"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('adminCrisisEvents.handleNote')">
          <el-input
            v-model="handleForm.note"
            type="textarea"
            :rows="3"
            :placeholder="t('adminCrisisEvents.handleNotePlaceholder')"
            maxlength="2000"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleDialogVisible = false">
          {{ t('common.cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="actionLoading"
          @click="submitHandle"
        >
          {{ t('adminCrisisEvents.handleConfirmBtn') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- ISS-072 修复：升级对话框 -->
    <el-dialog
      v-model="escalateDialogVisible"
      :title="t('adminCrisisEvents.escalateDialogTitle')"
      width="500px"
      destroy-on-close
    >
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        class="dialog-alert"
      >
        {{ t('adminCrisisEvents.escalateAlert') }}
      </el-alert>
      <el-form label-width="100px">
        <el-form-item :label="t('adminCrisisEvents.handleEventId')">
          <span>{{ currentEvent?.id }}</span>
        </el-form-item>
        <el-form-item :label="t('adminCrisisEvents.escalateReason')">
          <el-input
            v-model="escalateForm.reason"
            type="textarea"
            :rows="3"
            :placeholder="t('adminCrisisEvents.escalateReasonPlaceholder')"
            maxlength="2000"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="escalateDialogVisible = false">
          {{ t('common.cancel') }}
        </el-button>
        <el-button
          type="warning"
          :loading="actionLoading"
          :disabled="!escalateForm.reason.trim()"
          @click="submitEscalate"
        >
          {{ t('adminCrisisEvents.escalateConfirmBtn') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- ISS-072 修复：关闭对话框 -->
    <el-dialog
      v-model="closeDialogVisible"
      :title="t('adminCrisisEvents.closeDialogTitle')"
      width="500px"
      destroy-on-close
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="dialog-alert"
      >
        {{ t('adminCrisisEvents.closeAlert') }}
      </el-alert>
      <el-form label-width="100px">
        <el-form-item :label="t('adminCrisisEvents.handleEventId')">
          <span>{{ currentEvent?.id }}</span>
        </el-form-item>
        <el-form-item :label="t('adminCrisisEvents.closeNote')">
          <el-input
            v-model="closeForm.note"
            type="textarea"
            :rows="3"
            :placeholder="t('adminCrisisEvents.closeNotePlaceholder')"
            maxlength="2000"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="closeDialogVisible = false">
          {{ t('common.cancel') }}
        </el-button>
        <el-button
          type="success"
          :loading="actionLoading"
          @click="submitClose"
        >
          {{ t('adminCrisisEvents.closeConfirmBtn') }}
        </el-button>
      </template>
    </el-dialog>
  </ListPageScaffold>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { adminApi, type CrisisEventItem } from '@/api/adminApi'
import PageTable from '@/components/common/PageTable.vue'
import FilterBar from '@/components/common/FilterBar.vue'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import { useListQueryState } from '@/composables/useListQueryState'
import { showHttpFeedback } from '@/utils/httpFeedback'
// P2-A 修复：复用 formatUtils 的 formatDate，避免本地重复定义
import { formatDate } from '@/utils/formatUtils'
// ISS-012 修复：复用 riskFormatters 中的 getRiskScoreColor，统一阈值，避免硬编码颜色
import { getRiskScoreColor } from '@/utils/riskFormatters'

const { t } = useI18n()

const queryState = useListQueryState('ce')

const loading = ref(false)
const rows = ref<CrisisEventItem[]>([])
const total = ref(0)
const pageError = ref('')
const exporting = ref(false)

const page = computed(() => queryState.page.value)
const pageSize = computed(() => queryState.pageSize.value)

// ISS-055 修复：默认日期范围改为 getter 函数，每次查询/重置时重新计算，避免跨午夜后默认值过期
const getDefaultDateRange = (): string[] => {
  const now = new Date()
  const start = new Date(now.getTime() - 30 * 24 * 3600 * 1000)
  return [start.toISOString().slice(0, 10), now.toISOString().slice(0, 10)]
}

const filters = reactive({
  status: '',
  dateRange: getDefaultDateRange() as string[]
})

const maskUserId = (userId: number | string): string => {
  const s = String(userId)
  if (s.length <= 2) return s + '****'
  return s.slice(0, 2) + '****'
}

const getTriggerSourceTag = (source: string): 'success' | 'warning' | 'info' => {
  const map: Record<string, 'success' | 'warning' | 'info'> = {
    text: 'warning',
    fusion: 'info',
    manual: 'success'
  }
  return map[source] || 'info'
}

const getTriggerSourceLabel = (source: string): string => {
  const map: Record<string, string> = {
    text: t('adminCrisisEvents.triggerSource.text'),
    fusion: t('adminCrisisEvents.triggerSource.fusion'),
    manual: t('adminCrisisEvents.triggerSource.manual')
  }
  return map[source] || source
}

const getStatusTag = (status: string): 'danger' | 'warning' | 'info' | 'success' => {
  const map: Record<string, 'danger' | 'warning' | 'info' | 'success'> = {
    detected: 'danger',
    reviewed: 'warning',
    escalated: 'danger',
    resolved: 'success'
  }
  return map[status] || 'info'
}

const getStatusLabel = (status: string): string => {
  const map: Record<string, string> = {
    detected: t('adminCrisisEvents.status.detected'),
    reviewed: t('adminCrisisEvents.status.reviewed'),
    escalated: t('adminCrisisEvents.status.escalated'),
    resolved: t('adminCrisisEvents.status.resolved')
  }
  return map[status] || status
}

// ISS-012 修复：复用 riskFormatters.getRiskScoreColor，统一风险分数阈值与配色
// 本地仅保留对 null 的适配（getRiskScoreColor 入参为 number）
const getScoreColor = (score: number | null): string => {
  if (score == null) return '#999'
  return getRiskScoreColor(score)
}

// ISS-040 修复：根据危机分数返回风险等级文字标签
// 阈值与 getRiskScoreColor 保持一致，确保颜色与文字语义对齐
const getScoreLabel = (score: number | null): string => {
  if (score == null) return '-'
  if (score <= 20) return t('adminCrisisEvents.riskLevel.low')
  if (score <= 40) return t('adminCrisisEvents.riskLevel.mild')
  if (score <= 60) return t('adminCrisisEvents.riskLevel.moderate')
  return t('adminCrisisEvents.riskLevel.high')
}

const fetchData = async () => {
  loading.value = true
  pageError.value = ''
  try {
    const query: { page: number; page_size: number; status?: string; start_date?: string; end_date?: string } = {
      page: page.value,
      page_size: pageSize.value
    }
    if (filters.status) query.status = filters.status
    if (filters.dateRange && filters.dateRange.length === 2) {
      query.start_date = filters.dateRange[0]
      query.end_date = filters.dateRange[1]
    }
    const data = await adminApi.getCrisisEvents(query)
    rows.value = data.items
    total.value = data.total
  } catch (error) {
    pageError.value = showHttpFeedback(error, t('adminCrisisEvents.loadFailed')).detail
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

const handleSearch = async () => {
  await queryState.setQuery({ page: 1 })
  fetchData()
}

const handleReset = async () => {
  filters.status = ''
  filters.dateRange = getDefaultDateRange()
  await queryState.setQuery({ page: 1 })
  fetchData()
}

const handleExport = async () => {
  if (!filters.dateRange || filters.dateRange.length < 2) {
    ElMessage.warning(t('adminCrisisEvents.exportRangeRequired'))
    return
  }
  exporting.value = true
  try {
    // ISS-051 备注：CSV 由后端 /admin/crisis-events/export 生成并以 Blob 返回，
    // 公式注入防护与单元格转义由后端统一处理；文件名仅由日期构成，无注入风险
    const blobData = await adminApi.exportCrisisEvents(filters.dateRange[0], filters.dateRange[1])
    const blob = new Blob([blobData], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `crisis_events_${filters.dateRange[0].replace(/-/g, '')}_${filters.dateRange[1].replace(/-/g, '')}.csv`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    ElMessage.success(t('adminCrisisEvents.exportSuccess'))
  } catch (error: unknown) {
    const err = error as { response?: { status?: number } }
    if (err?.response?.status === 403) {
      ElMessage.error(t('adminCrisisEvents.exportNoPermission'))
    } else {
      ElMessage.error(showHttpFeedback(error, t('adminCrisisEvents.exportFailed')).detail)
    }
  } finally {
    exporting.value = false
  }
}

// ISS-072 修复：状态流转操作列 + 对话框逻辑
// 状态机：detected → reviewed → escalated → resolved
const canHandle = (status: string): boolean => ['detected', 'reviewed', 'escalated'].includes(status)
const canEscalate = (status: string): boolean => ['detected', 'reviewed'].includes(status)
const canClose = (status: string): boolean => ['detected', 'reviewed', 'escalated'].includes(status)

const handleDialogVisible = ref(false)
const escalateDialogVisible = ref(false)
const closeDialogVisible = ref(false)
const actionLoading = ref(false)
const currentEvent = ref<CrisisEventItem | null>(null)

const handleForm = reactive<{ action: string; note: string }>({
  action: 'notify_counselor',
  note: ''
})
const escalateForm = reactive<{ reason: string }>({ reason: '' })
const closeForm = reactive<{ note: string }>({ note: '' })

const openHandleDialog = (row: CrisisEventItem) => {
  currentEvent.value = row
  handleForm.action = 'notify_counselor'
  handleForm.note = ''
  handleDialogVisible.value = true
}

const openEscalateDialog = (row: CrisisEventItem) => {
  currentEvent.value = row
  escalateForm.reason = ''
  escalateDialogVisible.value = true
}

const openCloseDialog = (row: CrisisEventItem) => {
  currentEvent.value = row
  closeForm.note = ''
  closeDialogVisible.value = true
}

const submitHandle = async () => {
  if (!currentEvent.value) return
  if (!handleForm.action) {
    ElMessage.warning(t('adminCrisisEvents.handleActionRequired'))
    return
  }
  actionLoading.value = true
  try {
    await adminApi.handleCrisisEvent(currentEvent.value.id, {
      action: handleForm.action,
      note: handleForm.note || null
    })
    ElMessage.success(t('adminCrisisEvents.handled'))
    handleDialogVisible.value = false
    await fetchData()
  } catch (error) {
    showHttpFeedback(error, t('adminCrisisEvents.handleFailed'))
  } finally {
    actionLoading.value = false
  }
}

const submitEscalate = async () => {
  if (!currentEvent.value) return
  if (!escalateForm.reason.trim()) {
    ElMessage.warning(t('adminCrisisEvents.escalateReasonRequired'))
    return
  }
  actionLoading.value = true
  try {
    await adminApi.escalateCrisisEvent(currentEvent.value.id, {
      reason: escalateForm.reason
    })
    ElMessage.success(t('adminCrisisEvents.escalated'))
    escalateDialogVisible.value = false
    await fetchData()
  } catch (error) {
    showHttpFeedback(error, t('adminCrisisEvents.escalateFailed'))
  } finally {
    actionLoading.value = false
  }
}

const submitClose = async () => {
  if (!currentEvent.value) return
  actionLoading.value = true
  try {
    await adminApi.closeCrisisEvent(currentEvent.value.id, {
      note: closeForm.note || null
    })
    ElMessage.success(t('adminCrisisEvents.closed'))
    closeDialogVisible.value = false
    await fetchData()
  } catch (error) {
    showHttpFeedback(error, t('adminCrisisEvents.closeFailed'))
  } finally {
    actionLoading.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.keyword-tag {
  margin-right: var(--spacing-xs);
  margin-bottom: 2px;
}

/* ISS-040 修复：危机分数风险等级标签样式 */
.score-label {
  margin-left: var(--spacing-xs);
  color: #ffffff;
  border: none;
  font-weight: 600;
}

.empty-cell {
  color: var(--text-placeholder);
}

.dialog-alert {
  margin-bottom: var(--spacing-md);
}
</style>
