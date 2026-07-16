<template>
  <el-card class="stats-card">
    <template #header>
      <span class="card-title">{{ t('adminSilences.stats.title') }}</span>
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
          {{ t('adminSilences.stats.total') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--active">
        <div class="stat-value">
          {{ stats.active }}
        </div>
        <div class="stat-label">
          {{ t('adminSilences.statusActive') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--inactive">
        <div class="stat-value">
          {{ stats.inactive }}
        </div>
        <div class="stat-label">
          {{ t('adminSilences.statusInactive') }}
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineOptions({ name: 'SilenceStatsCard' })
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { alertsApi } from '@/api/alertsApi'

const { t } = useI18n()

const loading = ref(true)
const stats = reactive({
  total: 0,
  active: 0,
  inactive: 0
})

const loadStats = async () => {
  loading.value = true
  try {
    // 一次性全量聚合（不过滤），呈现生效/停用分布概览
    const data = await alertsApi.listSilences({ page: 1, page_size: 200 })
    const items = data.items || []
    stats.total = data.total ?? items.length
    stats.active = items.filter((i) => i.is_active).length
    stats.inactive = items.filter((i) => !i.is_active).length
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

.stat-tile--active {
  border-left-color: var(--success-color);
}

.stat-tile--inactive {
  border-left-color: var(--info-color);
}

.stat-value {
  font-size: var(--font-size-stat);
  font-weight: var(--font-weight-bold);
  line-height: 1.1;
  color: var(--text-primary);
}

.stat-tile--active .stat-value {
  color: var(--success-color);
}

.stat-tile--inactive .stat-value {
  color: var(--info-color);
}

.stat-label {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}
</style>
