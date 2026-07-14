<template>
  <el-card>
    <template #header>
      <span class="card-title">{{ t('adminSettings.feedbacks.cardTitle') }}</span>
    </template>
    <StatefulContainer
      :loading="feedbackLoading"
      :empty="!feedbackLoading && feedbacks.length === 0"
      :error-message="feedbackError"
      :empty-text="t('adminSettings.feedbacks.empty')"
      @retry="loadFeedbacks"
    >
      <el-table
        :data="feedbacks"
        border
        stripe
      >
        <el-table-column
          prop="id"
          :label="t('adminSettings.feedbacks.colId')"
          width="80"
        />
        <el-table-column
          prop="counselor_id"
          :label="t('adminSettings.feedbacks.colCounselorId')"
          width="100"
        />
        <el-table-column
          prop="user_id"
          :label="t('adminSettings.feedbacks.colUserId')"
          width="100"
        />
        <el-table-column
          prop="assessment_id"
          :label="t('adminSettings.feedbacks.colAssessmentId')"
          width="100"
        />
        <el-table-column
          prop="agreed"
          :label="t('adminSettings.feedbacks.colAgreed')"
          width="100"
        >
          <template #default="{ row }">
            <el-tag
              :type="row.agreed ? 'success' : 'danger'"
              size="small"
            >
              {{ row.agreed ? t('adminSettings.feedbacks.agreed') : t('adminSettings.feedbacks.disagreed') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="reason"
          :label="t('adminSettings.feedbacks.colReason')"
          min-width="200"
        />
        <el-table-column
          prop="created_at"
          :label="t('adminSettings.feedbacks.colTime')"
          width="180"
        />
      </el-table>
    </StatefulContainer>
    <div class="pager-wrap">
      <el-pagination
        background
        layout="total, prev, pager, next"
        :total="feedbackTotal"
        :page-size="feedbackPageSize"
        :current-page="feedbackPage"
        @current-change="(v: number) => { feedbackPage = v; loadFeedbacks() }"
        @size-change="(v: number) => { feedbackPageSize = v; feedbackPage = 1; loadFeedbacks() }"
      />
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineOptions({ name: 'FeedbacksTab' })
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import { adminApi, type ModelFeedbackItem } from '@/api/adminApi'
import { normalizeHttpError } from '@/utils/errorPolicy'

const { t } = useI18n()

const feedbacks = ref<ModelFeedbackItem[]>([])
const feedbackTotal = ref(0)
const feedbackPage = ref(1)
const feedbackPageSize = ref(10)
const feedbackLoading = ref(false)
const feedbackError = ref('')

const loadFeedbacks = async () => {
  feedbackLoading.value = true
  feedbackError.value = ''
  try {
    const data = await adminApi.listAdminFeedbacks({ page: feedbackPage.value, page_size: feedbackPageSize.value })
    feedbacks.value = data.items
    feedbackTotal.value = data.total
  } catch (error) {
    feedbackError.value = normalizeHttpError(error, t('adminSettings.feedbacks.loadFailed')).detail
  } finally {
    feedbackLoading.value = false
  }
}

onMounted(() => {
  loadFeedbacks()
})
</script>

<style scoped>
.card-title {
  font-weight: var(--font-weight-semibold);
}

.pager-wrap {
  margin-top: var(--spacing-md);
  display: flex;
  justify-content: flex-end;
}
</style>
