<template>
  <section class="bento-cell bento-item">
    <header class="bento-cell__head">
      <h3 class="bento-cell__title">
        {{ t('userDashboard.activity.title') }}
      </h3>
      <el-button
        type="primary"
        link
        class="cell-view-all"
        @click="router.push('/user/reports')"
      >
        {{ t('userDashboard.activity.viewAll') }}
      </el-button>
    </header>

    <div
      v-if="loading"
      class="card-loading"
    >
      <el-skeleton
        :rows="4"
        animated
      />
    </div>

    <ul
      v-else-if="activities.length > 0"
      class="activity-list"
    >
      <li
        v-for="item in activities"
        :key="item.id"
        class="activity-item"
      >
        <span
          class="activity-dot"
          :style="{ background: item.color, boxShadow: `0 0 0 4px ${item.color}21` }"
          aria-hidden="true"
        />
        <div class="activity-body">
          <p class="activity-title">
            {{ item.title }}
          </p>
          <span class="activity-time tabular-nums">{{ formatRelativeTime(item.time) }}</span>
        </div>
      </li>
    </ul>

    <EmptyState
      v-else
      :title="t('userDashboard.activity.empty')"
      :description="t('userDashboard.activity.emptyDesc')"
      :image-size="48"
    />
  </section>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import EmptyState from '@/components/common/EmptyState.vue'
import { formatRelativeTime } from '@/utils/formatUtils'
import type { ActivityItem } from './useUserDashboardData'

defineProps<{
  activities: ActivityItem[]
  loading: boolean
}>()

const { t } = useI18n()
const router = useRouter()
</script>

<style scoped>
.bento-cell {
  background: var(--bg-primary);
  border: 1px solid var(--border-extra-light);
  border-radius: 1.25rem;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  box-shadow: 0 1px 2px rgba(15, 22, 32, 0.04);
  transition: box-shadow 0.3s var(--transition-ease-out),
    border-color 0.3s var(--transition-ease-out);
}

.bento-cell:hover {
  box-shadow: 0 12px 32px -12px rgba(46, 111, 168, 0.14);
  border-color: var(--border-light);
}

.bento-cell__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 1.125rem;
}

.bento-cell__title {
  margin: 0;
  font-family: var(--font-family-display);
  font-size: 0.9375rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-primary);
}

.cell-view-all {
  font-size: var(--font-size-extra-small);
  padding: 0;
}

.card-loading {
  padding: var(--spacing-lg) 0;
}

/* ===== 时间线 ===== */
.activity-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.activity-item {
  position: relative;
  display: flex;
  gap: var(--spacing-sm);
  padding: 0.625rem 0;
  padding-left: 1.5rem;
}

.activity-item:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 4px;
  top: 1.35rem;
  bottom: -0.75rem;
  width: 2px;
  background: var(--border-light);
}

.activity-dot {
  position: absolute;
  left: 0;
  top: 0.85rem;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.activity-body {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  min-width: 0;
}

.activity-title {
  margin: 0;
  font-size: var(--font-size-small);
  line-height: 1.4;
  color: var(--text-primary);
}

.activity-time {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
  font-family: var(--font-family-mono);
}
</style>
