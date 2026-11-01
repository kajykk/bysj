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
  background: var(--surface-1);
  border: 1px solid var(--card-border);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-light);
  transition: box-shadow 0.3s var(--transition-ease-out),
    border-color 0.3s var(--transition-ease-out);
}

.bento-cell:hover {
  box-shadow: var(--shadow-card-hover);
  border-color: var(--border-light);
}

.bento-cell__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
}

.bento-cell__title {
  margin: 0;
  font-family: var(--font-family-display);
  font-size: var(--font-size-medium);
  font-weight: var(--font-weight-semibold);
  letter-spacing: -0.01em;
  color: var(--text-primary);
}

.quick-actions {
  /* BLANK-09 修复：窄列被拉伸至与系统状态卡同高时，
     按钮改为纵向全宽排列并均匀分布，填满卡片高度，消除底部空白 */
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  flex: 1;
  justify-content: space-evenly;
}

.quick-actions .el-button {
  width: 100%;
  margin-left: 0;
}
</style>
