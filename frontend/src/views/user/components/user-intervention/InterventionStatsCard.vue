<template>
  <el-card class="stats-card">
    <template #header>
      <span class="card-title">{{ t('userIntervention.stats.title') }}</span>
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
import SkeletonScreen from '@/components/common/SkeletonScreen.vue'

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
    // P1-15 / F-03：改用后端 SQL 层聚合端点。改前 page_size:200 拉全量计划到
    // 前端 filter，计划超 200 条时分子截断、分母不截断，统计结果是错的。
    const data = await userApi.getInterventionStats()
    stats.active = data.active
    stats.completed = data.completed
    stats.cancelled = data.cancelled
    stats.avgCompletion = data.avg_completion
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
