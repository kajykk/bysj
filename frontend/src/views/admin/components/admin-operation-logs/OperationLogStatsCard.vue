<template>
  <el-card class="stats-card">
    <template #header>
      <span class="card-title">{{ t('adminOperationLogs.stats.title') }}</span>
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
      <div class="stat-tile stat-tile--super-admin">
        <div class="stat-value">
          {{ stats.superAdmin }}
        </div>
        <div class="stat-label">
          {{ t('role.superAdmin') }}
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
import SkeletonScreen from '@/components/common/SkeletonScreen.vue'

const { t } = useI18n()

const loading = ref(true)
const stats = reactive({
  total: 0,
  user: 0,
  counselor: 0,
  admin: 0,
  superAdmin: 0
})

const loadStats = async () => {
  loading.value = true
  try {
    // P1-15 / F-03：改用后端 SQL 层聚合端点。改前 page_size:200 拉全量操作
    // 日志到前端 filter，日志超 200 条时分子截断、分母不截断，分布是错的；
    // 且 detail 含 IP/request_id，传输 200 条完整记录的泄露面也随放大。
    const data = await adminApi.getOperationLogStats()
    stats.total = data.total
    stats.user = data.user
    stats.counselor = data.counselor
    stats.admin = data.admin
    stats.superAdmin = data.super_admin
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

.stat-tile--super-admin {
  border-left-color: var(--primary-color);
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

.stat-tile--super-admin .stat-value {
  color: var(--primary-color);
}

.stat-label {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}
</style>
