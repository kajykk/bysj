<template>
  <el-card class="stats-card">
    <template #header>
      <span class="card-title">{{ t('adminOperationLogs.stats.title') }}</span>
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
          {{ t('adminOperationLogs.stats.total') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--user">
        <div class="stat-value">
          {{ stats.user }}
        </div>
        <div class="stat-label">
          {{ t('role.user') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--counselor">
        <div class="stat-value">
          {{ stats.counselor }}
        </div>
        <div class="stat-label">
          {{ t('role.counselor') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--admin">
        <div class="stat-value">
          {{ stats.admin }}
        </div>
        <div class="stat-label">
          {{ t('role.admin') }}
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineOptions({ name: 'OperationLogStatsCard' })
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { adminApi } from '@/api/adminApi'

const { t } = useI18n()

const loading = ref(true)
const stats = reactive({
  total: 0,
  user: 0,
  counselor: 0,
  admin: 0
})

const loadStats = async () => {
  loading.value = true
  try {
    // 一次性全量聚合（不过滤），呈现操作人角色分布概览
    const data = await adminApi.listAdminOperationLogs({ page: 1, page_size: 200 })
    const items = data.items || []
    stats.total = data.total ?? items.length
    stats.user = items.filter((i) => i.operator_role === 'user').length
    stats.counselor = items.filter((i) => i.operator_role === 'counselor').length
    stats.admin = items.filter((i) => i.operator_role === 'admin').length
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

.stat-tile--user {
  border-left-color: var(--success-color);
}

.stat-tile--counselor {
  border-left-color: var(--warning-color);
}

.stat-tile--admin {
  border-left-color: var(--danger-color);
}

.stat-value {
  font-size: var(--font-size-stat);
  font-weight: var(--font-weight-bold);
  line-height: 1.1;
  color: var(--text-primary);
}

.stat-tile--user .stat-value {
  color: var(--success-color);
}

.stat-tile--counselor .stat-value {
  color: var(--warning-color);
}

.stat-tile--admin .stat-value {
  color: var(--danger-color);
}

.stat-label {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}
</style>
