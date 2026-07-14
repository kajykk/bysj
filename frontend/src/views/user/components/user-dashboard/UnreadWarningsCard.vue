<template>
  <section class="bento-cell bento-item">
    <header class="bento-cell__head">
      <div class="bento-cell__title-group">
        <span
          v-if="unreadWarnings.length > 0"
          class="bento-cell__live-dot bento-cell__live-dot--alert breathe-dot"
          aria-hidden="true"
        />
        <h3 class="bento-cell__title">
          {{ t('userDashboard.unreadWarningsTitle') }}
        </h3>
      </div>
      <span
        v-if="unreadWarnings.length > 0"
        class="warning-count tabular-nums"
      >{{ unreadWarnings.length }}</span>
    </header>
    <div
      v-if="loading"
      class="card-loading"
    >
      <el-skeleton
        :rows="3"
        animated
      />
    </div>
    <EmptyState
      v-else-if="error"
      :title="t('userDashboard.loadFailed')"
      :description="error"
      :image-size="60"
    >
      <template #action>
        <el-button
          type="primary"
          plain
          @click="emit('reload')"
        >
          {{ t('userDashboard.btnReload') }}
        </el-button>
      </template>
    </EmptyState>
    <template v-else-if="unreadWarnings.length > 0">
      <ul class="warning-list">
        <li
          v-for="w in unreadWarnings.slice(0, 5)"
          :key="w.id"
          class="warning-item"
        >
          <el-tag
            :type="w.risk_level >= 3 ? 'danger' : w.risk_level === 2 ? 'warning' : 'info'"
            size="small"
            effect="light"
          >
            {{ w.risk_level >= 3 ? t('userDashboard.warningHigh') : w.risk_level === 2 ? t('userDashboard.warningMedium') : t('userDashboard.warningLow') }}
          </el-tag>
          <span class="warning-title">{{ w.title }}</span>
          <span class="warning-time tabular-nums">{{ formatDate(w.created_at, 'MM/DD HH:mm') }}</span>
        </li>
      </ul>
      <el-button
        type="primary"
        link
        class="cell-action"
        @click="router.push('/user/warnings')"
      >
        {{ t('userDashboard.btnViewAll') }}
      </el-button>
    </template>
    <EmptyState
      v-else
      :title="t('userDashboard.emptyNoUnread')"
      :description="t('userDashboard.emptyNoUnreadDesc')"
      :image-size="60"
    />
  </section>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import EmptyState from '@/components/common/EmptyState.vue'
import { formatDate } from '@/utils/formatUtils'
import type { WarningItem } from '@/api/userTypes'

defineProps<{
  unreadWarnings: WarningItem[]
  loading: boolean
  error: string
}>()

const emit = defineEmits<{ reload: [] }>()

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

.bento-cell__title-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.bento-cell__title {
  margin: 0;
  font-family: var(--font-family-display);
  font-size: 0.9375rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-primary);
}

.bento-cell__live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--primary-color);
  box-shadow: 0 0 8px rgba(46, 111, 168, 0.6);
  flex-shrink: 0;
}

.bento-cell__live-dot--alert {
  background: var(--danger-color);
  box-shadow: 0 0 8px rgba(214, 90, 90, 0.6);
}

.warning-count {
  font-family: var(--font-family-mono);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--danger-color);
  background: var(--danger-light);
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
  min-width: 1.5rem;
  text-align: center;
}

.card-loading {
  padding: var(--spacing-lg) 0;
}

/* 未读预警列表 */
.warning-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.warning-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: 0.625rem 0;
  border-bottom: 1px solid var(--border-extra-light);
  transition: background var(--transition-fast) var(--transition-timing);
}

.warning-item:last-child {
  border-bottom: none;
}

.warning-item:hover {
  background: var(--bg-hover);
}

.warning-title {
  flex: 1;
  font-size: var(--font-size-small);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary);
}

.warning-time {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
  font-family: var(--font-family-mono);
}

.cell-action {
  margin-top: auto;
  align-self: flex-start;
  padding-top: 0.75rem;
}
</style>
