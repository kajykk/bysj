<template>
  <el-card class="stats-card">
    <template #header>
      <span class="card-title">{{ t('userAssessments.stats.title') }}</span>
    </template>
    <div
      v-if="loading"
      class="skeleton-padding"
    >
      <el-skeleton
        :rows="2"
        animated
      />
    </div>
    <div
      v-else
      class="stat-grid"
    >
      <div class="stat-tile">
        <div class="stat-value">
          {{ stats.total }}
        </div>
        <div class="stat-label">
          {{ t('userAssessments.stats.total') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--type">
        <div class="stat-value">
          {{ stats.structured }}
        </div>
        <div class="stat-label">
          {{ t('userAssessments.stats.structured') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--type">
        <div class="stat-value">
          {{ stats.text }}
        </div>
        <div class="stat-label">
          {{ t('userAssessments.stats.text') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--type">
        <div class="stat-value">
          {{ stats.physiological }}
        </div>
        <div class="stat-label">
          {{ t('userAssessments.stats.physiological') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--high">
        <div class="stat-value">
          {{ stats.highRisk }}
        </div>
        <div class="stat-label">
          {{ t('userAssessments.stats.highRisk') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--medium">
        <div class="stat-value">
          {{ stats.mediumRisk }}
        </div>
        <div class="stat-label">
          {{ t('userAssessments.stats.mediumRisk') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--low">
        <div class="stat-value">
          {{ stats.lowRisk }}
        </div>
        <div class="stat-label">
          {{ t('userAssessments.stats.lowRisk') }}
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineOptions({ name: 'AssessmentsStatsCard' })
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { userApi, type AssessmentRecordItem } from '@/api/userApi'
import { hasPermission } from '@/config/permissions'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const auth = useAuthStore()

const loading = ref(true)
const stats = reactive({
  total: 0,
  structured: 0,
  text: 0,
  physiological: 0,
  highRisk: 0,
  mediumRisk: 0,
  lowRisk: 0
})

const canReadAssessment = () => hasPermission(auth.role, 'user.assessment.read')

const loadStats = async () => {
  if (!canReadAssessment()) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const data = await userApi.getUserAssessmentHistory({ page: 1, page_size: 200 })
    const items = (data.items || []) as AssessmentRecordItem[]
    stats.total = data.total ?? items.length
    stats.structured = items.filter((i) => i.assessment_type === 'structured').length
    stats.text = items.filter((i) => i.assessment_type === 'text').length
    stats.physiological = items.filter((i) => i.assessment_type === 'physiological').length
    stats.highRisk = items.filter((i) => i.risk_level === 3).length
    stats.mediumRisk = items.filter((i) => i.risk_level === 2).length
    stats.lowRisk = items.filter((i) => i.risk_level === 1).length
  } catch {
    // 统计加载失败时使用空值，不阻断主列表
  } finally {
    loading.value = false
  }
}

onMounted(loadStats)
</script>

<style scoped>
.card-title {
  font-weight: var(--font-weight-semibold);
}

.skeleton-padding {
  padding: var(--spacing-md) 0;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--spacing-md);
}

.stat-tile {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  padding: var(--spacing-md);
  border-radius: var(--radius-md);
  background-color: var(--bg-page);
  border-left: 3px solid var(--border-light);
}

.stat-tile--type {
  border-left-color: var(--info-color);
}

.stat-tile--high {
  border-left-color: var(--danger-color);
}

.stat-tile--medium {
  border-left-color: var(--warning-color);
}

.stat-tile--low {
  border-left-color: var(--success-color);
}

.stat-value {
  font-size: var(--font-size-stat);
  font-weight: var(--font-weight-bold);
  line-height: 1.1;
  color: var(--text-primary);
}

.stat-tile--high .stat-value {
  color: var(--danger-color);
}

.stat-tile--medium .stat-value {
  color: var(--warning-color);
}

.stat-tile--low .stat-value {
  color: var(--success-color);
}

.stat-label {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}
</style>
