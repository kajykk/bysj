<template>
  <el-card class="stats-card">
    <template #header>
      <span class="card-title">{{ t('userIntervention.stats.title') }}</span>
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
      <div class="stat-tile stat-tile--active">
        <div class="stat-value">
          {{ stats.active }}
        </div>
        <div class="stat-label">
          {{ t('userIntervention.stats.active') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--completed">
        <div class="stat-value">
          {{ stats.completed }}
        </div>
        <div class="stat-label">
          {{ t('userIntervention.stats.completed') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--cancelled">
        <div class="stat-value">
          {{ stats.cancelled }}
        </div>
        <div class="stat-label">
          {{ t('userIntervention.stats.cancelled') }}
        </div>
      </div>
      <div class="stat-tile">
        <div class="stat-value">
          {{ stats.avgCompletion }}<span class="stat-unit">%</span>
        </div>
        <div class="stat-label">
          {{ t('userIntervention.stats.avgCompletion') }}
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineOptions({ name: 'InterventionStatsCard' })
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { userApi } from '@/api/userApi'

const { t } = useI18n()

const loading = ref(true)
const stats = reactive({
  active: 0,
  completed: 0,
  cancelled: 0,
  avgCompletion: 0
})

const loadStats = async () => {
  loading.value = true
  try {
    const data = await userApi.getInterventionHistory({ page: 1, page_size: 200 })
    const items = data.items || []
    stats.active = items.filter((i) => i.status === 'active').length
    stats.completed = items.filter((i) => i.status === 'completed').length
    stats.cancelled = items.filter((i) => i.status === 'cancelled').length
    const rates = items.map((i) => Number(i.completion_rate) || 0)
    stats.avgCompletion = rates.length
      ? Math.round(rates.reduce((sum, r) => sum + r, 0) / rates.length)
      : 0
  } catch {
    // 统计加载失败时使用空值，不阻断主页面
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
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
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

.stat-tile--active {
  border-left-color: var(--primary-color);
}

.stat-tile--completed {
  border-left-color: var(--success-color);
}

.stat-tile--cancelled {
  border-left-color: var(--info-color);
}

.stat-value {
  font-size: var(--font-size-stat);
  font-weight: var(--font-weight-bold);
  line-height: 1.1;
  color: var(--text-primary);
}

.stat-unit {
  font-size: var(--font-size-large);
  font-weight: var(--font-weight-semibold);
  margin-left: 2px;
}

.stat-label {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}
</style>
