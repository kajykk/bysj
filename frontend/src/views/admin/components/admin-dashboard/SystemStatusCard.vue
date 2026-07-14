<template>
  <section class="bento-cell bento-item">
    <header class="bento-cell__head bento-cell__head--split">
      <div class="bento-cell__title-group">
        <span
          class="bento-cell__live-dot"
          :class="systemHealthy ? '' : 'bento-cell__live-dot--alert'"
          :aria-hidden="true"
        />
        <h3 class="bento-cell__title">
          {{ t('adminDashboard.systemStatusTitle') }}
        </h3>
        <span class="bento-cell__status-text">
          {{ systemHealthy ? t('adminDashboard.systemStatusAllOk') : t('adminDashboard.systemStatusPartial') }}
        </span>
      </div>
      <el-button
        type="primary"
        link
        size="small"
        @click="$emit('view-config')"
      >
        {{ t('adminDashboard.viewConfig') }}
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
    <template v-else>
      <ul class="component-list">
        <li
          v-for="comp in componentStatus"
          :key="comp.key"
          class="component-item"
        >
          <div class="component-info">
            <span
              class="component-dot"
              :class="{ 'component-dot--healthy': comp.healthy, 'breathe-dot': comp.healthy }"
              :aria-hidden="true"
            />
            <span class="component-name">{{ t(COMPONENT_NAME_KEYS[comp.key]) }}</span>
          </div>
          <el-tag
            :type="comp.healthy ? 'success' : 'danger'"
            size="small"
            effect="light"
          >
            {{ comp.healthy ? t('adminDashboard.statusHealthy') : t('adminDashboard.statusUnhealthy') }}
          </el-tag>
        </li>
      </ul>
    </template>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { COMPONENT_NAME_KEYS, type ComponentStatusItem } from './sharedAdminDashboardUtils'

defineProps<{
  loading: boolean
  systemHealthy: boolean
  componentStatus: ComponentStatusItem[]
}>()

defineEmits<{
  (e: 'view-config'): void
}>()

const { t } = useI18n()
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

.bento-cell__head--split {
  margin-bottom: 1rem;
}

.bento-cell__title-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
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
  background: var(--success-color);
  box-shadow: 0 0 8px rgba(90, 158, 58, 0.6);
  flex-shrink: 0;
}

.bento-cell__live-dot--alert {
  background: var(--danger-color);
  box-shadow: 0 0 8px rgba(214, 90, 90, 0.6);
}

.bento-cell__status-text {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.card-loading {
  padding: var(--spacing-lg) 0;
}

/* 系统组件列表 */
.component-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.component-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--border-extra-light);
}

.component-item:last-child {
  border-bottom: none;
}

.component-info {
  display: flex;
  align-items: center;
  gap: 0.625rem;
}

.component-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--danger-color);
  flex-shrink: 0;
}

.component-dot--healthy {
  background: var(--success-color);
  box-shadow: 0 0 8px rgba(90, 158, 58, 0.5);
}

.component-name {
  font-size: var(--font-size-base);
  color: var(--text-regular);
}
</style>
