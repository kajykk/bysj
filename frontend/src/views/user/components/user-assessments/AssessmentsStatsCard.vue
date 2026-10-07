<template>
  <el-card class="stats-card">
    <template #header>
      <span class="card-title">{{ t('userAssessments.stats.title') }}</span>
    </template>
    <div
      v-if="loading"
      class="skeleton-padding"
    >
      <SkeletonScreen
        :rows="2"
        variant="text"
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
import { userApi, type DataHistoryItem } from '@/api/userApi'
import SkeletonScreen from '@/components/common/SkeletonScreen.vue'
import { hasPermission } from '@/config/permissions'
import { useAuthStore } from '@/stores/auth'
import { summarizeAssessmentHistory } from '../../utils/assessmentHistory'

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
    // FIX-2026-10-08：`GET /user/data/history` 的 `type` 是**单值**且后端默认
    // 为 structured（backend/app/api/v1/user_data.py:138-140），一次请求拿不到
    // 全部类型。统计卡要按类型分布计数，必须按三种类型各取一次再合并；
    // 改前只发一次不带 type 的请求，于是 text / physiological 两类恒为 0。
    const types = ['structured', 'text', 'physiological'] as const
    const pages = await Promise.all(
      types.map((type) => userApi.getUserAssessmentHistory({ page: 1, page_size: 200, type }))
    )
    const items: DataHistoryItem[] = pages.flatMap((page) => page.items || [])
    const summary = summarizeAssessmentHistory(items)
    stats.total = summary.total
    stats.structured = summary.structured
    stats.text = summary.text
    stats.physiological = summary.physiological
    stats.highRisk = summary.highRisk
    stats.mediumRisk = summary.mediumRisk
    stats.lowRisk = summary.lowRisk
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
