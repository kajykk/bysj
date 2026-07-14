<template>
  <section class="bento-cell bento-item">
    <header class="bento-cell__head">
      <h3 class="bento-cell__title">
        {{ t('adminDashboard.quickActions') }}
      </h3>
    </header>
    <div class="quick-actions">
      <el-button
        type="primary"
        class="magnetic-press"
        @click="$emit('navigate', '/admin/templates')"
      >
        {{ t('adminDashboard.btnTemplates') }}
      </el-button>
      <el-button
        type="warning"
        class="magnetic-press"
        @click="$emit('navigate', '/admin/settings')"
      >
        {{ t('adminDashboard.btnSettings') }}
      </el-button>
      <el-button
        type="info"
        class="magnetic-press"
        @click="$emit('navigate', '/admin/operation-logs')"
      >
        {{ t('adminDashboard.btnOperationLogs') }}
      </el-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineEmits<{
  (e: 'navigate', path: string): void
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

.bento-cell__title {
  margin: 0;
  font-family: var(--font-family-display);
  font-size: 0.9375rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-primary);
}

.quick-actions {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}
</style>
