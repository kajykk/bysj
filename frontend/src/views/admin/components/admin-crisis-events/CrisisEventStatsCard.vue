<template>
  <el-card class="stats-card">
    <template #header>
      <span class="card-title">{{ t('adminCrisisEvents.stats.title') }}</span>
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
          {{ t('adminCrisisEvents.stats.total') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--detected">
        <div class="stat-value">
          {{ stats.detected }}
        </div>
        <div class="stat-label">
          {{ t('adminCrisisEvents.status.detected') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--reviewed">
        <div class="stat-value">
          {{ stats.reviewed }}
        </div>
        <div class="stat-label">
          {{ t('adminCrisisEvents.status.reviewed') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--escalated">
        <div class="stat-value">
          {{ stats.escalated }}
        </div>
        <div class="stat-label">
          {{ t('adminCrisisEvents.status.escalated') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--resolved">
        <div class="stat-value">
          {{ stats.resolved }}
        </div>
        <div class="stat-label">
          {{ t('adminCrisisEvents.status.resolved') }}
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineOptions({ name: 'CrisisEventStatsCard' })
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { adminApi } from '@/api/adminApi'

const { t } = useI18n()

const loading = ref(true)
const stats = reactive({
  total: 0,
  detected: 0,
  reviewed: 0,
  escalated: 0,
  resolved: 0
})

const loadStats = async () => {
  loading.value = true
  try {
    // 一次性全量聚合（不过滤日期/状态），呈现全局状态分布概览
    const data = await adminApi.getCrisisEvents({ page: 1, page_size: 200 })
    const items = data.items || []
    stats.total = data.total ?? items.length
    stats.detected = items.filter((i) => i.status === 'detected').length
    stats.reviewed = items.filter((i) => i.status === 'reviewed').length
    stats.escalated = items.filter((i) => i.status === 'escalated').length
    stats.resolved = items.filter((i) => i.status === 'resolved').length
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

.stat-tile--detected {
  border-left-color: var(--warning-color);
}

.stat-tile--reviewed {
  border-left-color: var(--primary-color);
}

.stat-tile--escalated {
  border-left-color: var(--danger-color);
}

.stat-tile--resolved {
  border-left-color: var(--success-color);
}

.stat-value {
  font-size: var(--font-size-stat);
  font-weight: var(--font-weight-bold);
  line-height: 1.1;
  color: var(--text-primary);
}

.stat-tile--detected .stat-value {
  color: var(--warning-color);
}

.stat-tile--reviewed .stat-value {
  color: var(--primary-color);
}

.stat-tile--escalated .stat-value {
  color: var(--danger-color);
}

.stat-tile--resolved .stat-value {
  color: var(--success-color);
}

.stat-label {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}
</style>
