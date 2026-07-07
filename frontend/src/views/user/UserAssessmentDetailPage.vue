<template>
  <el-card>
    <template #header>
      {{ t('userAssessmentDetail.cardTitle') }}
    </template>

    <StatefulContainer
      :loading="loading"
      :empty="!loading && !record"
      :error-message="pageError"
      :empty-text="t('userAssessmentDetail.emptyText')"
      @retry="fetchDetail"
    >
      <el-descriptions
        v-if="record"
        :column="1"
        border
      >
        <el-descriptions-item :label="t('userAssessmentDetail.labelRecordId')">
          {{ record.id }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('userAssessmentDetail.labelAssessmentType')">
          {{ assessmentTypeLabel(record.assessment_type) }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('userAssessmentDetail.labelScore')">
          {{ record.score ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('userAssessmentDetail.labelRiskLevel')">
          {{ record.risk_level ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('userAssessmentDetail.labelTime')">
          {{ record.created_at ? formatDateTime(record.created_at) : '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('userAssessmentDetail.labelSummary')">
          {{ record.summary ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('userAssessmentDetail.labelDetail')">
          {{ record.detail ?? '-' }}
        </el-descriptions-item>
      </el-descriptions>

      <div
        v-if="record"
        class="json-box"
      >
        <div class="json-box__title">
          {{ t('userAssessmentDetail.rawDataTitle') }}
        </div>
        <pre>{{ JSON.stringify(record, null, 2) }}</pre>
      </div>

      <div class="footer">
        <el-button @click="goBack">
          {{ t('userAssessmentDetail.btnBack') }}
        </el-button>
      </div>
    </StatefulContainer>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { userApi, type AssessmentRecordItem } from '@/api/userApi'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import { normalizeHttpError } from '@/utils/errorPolicy'
// P2-A 修复：复用 formatUtils 的 formatDate（别名 formatDateTime 保持模板兼容），避免本地重复定义
import { formatDate as formatDateTime } from '@/utils/formatUtils'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const loading = ref(false)
const pageError = ref('')
const record = ref<AssessmentRecordItem | null>(null)

const recordId = computed(() => Number(route.params.id))

const ASSESSMENT_TYPE_LABEL_KEYS: Record<string, string> = {
  structured: 'typeStructured',
  text: 'typeText',
  physiological: 'typePhysiological',
  record: 'typeRecord'
}
const assessmentTypeLabel = (value?: string) => {
  const key = ASSESSMENT_TYPE_LABEL_KEYS[value || '']
  return key ? t(`userAssessmentDetail.${key}`) : value || '-'
}

const fetchDetail = async () => {
  loading.value = true
  pageError.value = ''
  try {
    record.value = await userApi.getAssessmentDetail(recordId.value)
  } catch (error) {
    pageError.value = normalizeHttpError(error, t('userAssessmentDetail.loadFailed')).detail
  } finally {
    loading.value = false
  }
}

// ISS-056 修复：改用 router.back()，避免透传全部 query（可能包含 token 等敏感参数）
// 无历史记录时回退到评估列表页
const goBack = () => {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/user/assessments')
  }
}

onMounted(fetchDetail)
</script>

<style scoped>
.footer {
  margin-top: 12px;
}

.json-box {
  margin-top: 16px;
  padding: 12px;
  border: 1px solid var(--border-lighter);
  border-radius: var(--radius-large);
  background: var(--bg-page);
}

.json-box__title {
  margin-bottom: 8px;
  font-weight: 600;
  color: var(--text-primary);
}

pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
}
</style>
