<template>
  <div class="review-detail-page">
    <el-page-header
      :title="t('counselorReviews.detailTitle')"
      @back="goBack"
    />

    <el-card
      v-if="review"
      style="margin-top: 16px"
    >
      <!-- 危机警告横幅 -->
      <el-alert
        v-if="review.crisis_override"
        :title="t('counselorReviews.crisisAlertTitle')"
        type="error"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      >
        <template #default>
          <strong>{{ t('counselorReviews.crisisAlertMessage') }}</strong>
        </template>
      </el-alert>

      <!-- 用户信息 -->
      <el-descriptions
        :title="t('counselorReviews.userInfoTitle')"
        :column="2"
        border
      >
        <el-descriptions-item :label="t('counselorReviews.detailColUserId')">
          {{ review.user_id }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('counselorReviews.detailColReviewId')">
          {{ review.id }}
        </el-descriptions-item>
      </el-descriptions>

      <!-- 模型预测结果 -->
      <el-descriptions
        :title="t('counselorReviews.modelPredictionTitle')"
        :column="2"
        border
        style="margin-top: 16px"
      >
        <el-descriptions-item :label="t('counselorReviews.detailColRiskScore')">
          <el-progress
            :percentage="review.risk_score"
            :color="getScoreColor(review.risk_score)"
            :stroke-width="16"
          />
        </el-descriptions-item>
        <el-descriptions-item :label="t('counselorReviews.detailColRiskLevel')">
          <el-tag
            :type="getRiskLevelType(review.risk_level)"
            size="large"
          >
            {{ getRiskLevelLabel(review.risk_level) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('counselorReviews.detailColPriority')">
          <el-tag
            :type="getPriorityType(review.priority)"
            effect="dark"
          >
            {{ getPriorityLabel(review.priority) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('counselorReviews.detailColStatus')">
          <el-tag :type="getStatusType(review.status)">
            {{ getStatusLabel(review.status) }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>

      <!-- 触发原因 -->
      <el-descriptions
        :title="t('counselorReviews.triggerReasonTitle')"
        :column="1"
        border
        style="margin-top: 16px"
      >
        <el-descriptions-item :label="t('counselorReviews.triggerReasonLabel')">
          <el-tag
            v-for="trigger in review.review_triggers"
            :key="trigger"
            type="warning"
            style="margin-right: 8px"
          >
            {{ trigger }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('counselorReviews.crisisOverrideLabel')">
          {{ review.crisis_override ? t('counselorReviews.yesLabel') : t('counselorReviews.noLabel') }}
        </el-descriptions-item>
      </el-descriptions>

      <!-- 处理操作 -->
      <div
        v-if="review.status === 'pending' || review.status === 'in_review'"
        class="actions"
        style="margin-top: 24px"
      >
        <el-divider>{{ t('counselorReviews.actionsDivider') }}</el-divider>

        <el-form
          :model="form"
          label-width="100px"
        >
          <el-form-item :label="t('counselorReviews.formNoteLabel')">
            <el-input
              v-model="form.note"
              type="textarea"
              :rows="4"
              :placeholder="t('counselorReviews.formNotePlaceholder')"
            />
          </el-form-item>

          <el-form-item>
            <el-button
              type="success"
              @click="handleResolve"
            >
              <el-icon><Check /></el-icon>
              {{ t('counselorReviews.btnMarkResolved') }}
            </el-button>
            <el-button
              type="danger"
              @click="handleEscalate"
            >
              <el-icon><Top /></el-icon>
              {{ t('counselorReviews.btnEscalate') }}
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- 处理结果 -->
      <div
        v-else
        class="resolution"
        style="margin-top: 24px"
      >
        <el-divider>{{ t('counselorReviews.resolutionDivider') }}</el-divider>
        <el-descriptions
          :column="1"
          border
        >
          <el-descriptions-item :label="t('counselorReviews.resolutionResolver')">
            {{ review.resolved_by }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('counselorReviews.resolutionNote')">
            {{ review.resolution_note }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('counselorReviews.resolutionTime')">
            {{ formatDate(review.resolved_at) }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>

    <el-skeleton
      v-else
      :rows="10"
      animated
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Check, Top } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { counselorApi, type ReviewItem } from '@/api/counselorApi'
// P2-A 修复：使用共享的 formatDate 替代本地重复实现
import { formatDate } from '@/utils/formatUtils'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const review = ref<ReviewItem | null>(null)
const form = ref({
  note: '',
})

const loadReview = async () => {
  const id = Number(route.params.id)
  try {
    review.value = await counselorApi.getReviewDetail(id)
  } catch (error) {
    ElMessage.error(t('counselorReviews.loadDetailFailed'))
  }
}

const goBack = () => {
  router.push('/counselor/reviews')
}

// P1-E 修复：移除 any 类型，使用 unknown 并进行类型守卫
const handleResolve = async () => {
  try {
    await ElMessageBox.confirm(t('counselorReviews.resolveConfirm'), t('counselorReviews.resolveConfirmTitle'), {
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel'),
      type: 'warning',
    })

    const id = Number(route.params.id)
    await counselorApi.resolveReview(id, { resolution_note: form.value.note || t('counselorReviews.defaultResolveNote') })

    ElMessage.success(t('counselorReviews.resolveSuccess'))
    loadReview()
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error(t('counselorReviews.resolveFailed'))
    }
  }
}

const handleEscalate = async () => {
  try {
    await ElMessageBox.confirm(t('counselorReviews.escalateConfirm'), t('counselorReviews.escalateConfirmTitle'), {
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel'),
      type: 'error',
    })

    const id = Number(route.params.id)
    await counselorApi.escalateReview(id, { reason: form.value.note || t('counselorReviews.defaultEscalateReason') })

    ElMessage.success(t('counselorReviews.escalateSuccess'))
    loadReview()
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error(t('counselorReviews.escalateFailed'))
    }
  }
}

const getScoreColor = (score: number) => {
  if (score >= 80) return '#d65a5a'
  if (score >= 60) return '#d4923a'
  if (score >= 40) return '#3b82c4'
  return '#5a9e3a'
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

// P2-A 修复：formatDate 已从 @/utils/formatUtils 导入，移除本地重复定义

onMounted(() => {
  loadReview()
})
</script>

<style scoped>
.review-detail-page {
  padding: var(--spacing-lg);
}

.actions {
  padding: var(--spacing-lg);
  background: var(--bg-page);
  border-radius: var(--radius-large);
}

.resolution {
  padding: var(--spacing-lg);
  background: var(--primary-light);
  border-radius: var(--radius-large);
}
</style>
