<template>
  <el-card class="stats-card">
    <template #header>
      <span class="card-title">{{ t('counselorWarnings.stats.title') }}</span>
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
          {{ t('counselorWarnings.stats.total') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--alert">
        <div class="stat-value">
          {{ stats.unhandled }}
        </div>
        <div class="stat-label">
          {{ t('counselorWarnings.stats.unhandled') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--done">
        <div class="stat-value">
          {{ stats.handled }}
        </div>
        <div class="stat-label">
          {{ t('counselorWarnings.stats.handled') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--high">
        <div class="stat-value">
          {{ stats.highRisk }}
        </div>
        <div class="stat-label">
          {{ t('counselorWarnings.stats.highRisk') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--medium">
        <div class="stat-value">
          {{ stats.mediumRisk }}
        </div>
        <div class="stat-label">
          {{ t('counselorWarnings.stats.mediumRisk') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--low">
        <div class="stat-value">
          {{ stats.lowRisk }}
        </div>
        <div class="stat-label">
          {{ t('counselorWarnings.stats.lowRisk') }}
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineOptions({ name: 'CounselorWarningStatsCard' })
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { counselorApi } from '@/api/counselorApi'
import { isHandled } from './sharedCounselorWarningsUtils'

const { t } = useI18n()

const loading = ref(true)
const stats = reactive({
  total: 0,
  unhandled: 0,
  handled: 0,
  highRisk: 0,
  mediumRisk: 0,
  lowRisk: 0
})

const loadStats = async () => {
  loading.value = true
  try {
    // 取全量（不过滤 only_unhandled）以统计整体概览；失败时用空值降级，不阻断主列表。
    const data = await counselorApi.getCounselorWarnings({ page: 1, page_size: 200 })
    const items = data.items || []
    stats.total = data.total ?? items.length
    stats.unhandled = items.filter((i) => !isHandled(i)).length
    stats.handled = items.filter((i) => isHandled(i)).length
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

.stat-tile--alert {
  border-left-color: var(--danger-color);
}

.stat-tile--done {
  border-left-color: var(--success-color);
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

.stat-tile--alert .stat-value,
.stat-tile--high .stat-value {
  color: var(--danger-color);
}

.stat-tile--done .stat-value,
.stat-tile--low .stat-value {
  color: var(--success-color);
}

.stat-tile--medium .stat-value {
  color: var(--warning-color);
}

.stat-label {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}
</style>
