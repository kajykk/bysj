<template>
  <el-card>
    <template #header>
      <span class="card-title">{{ t('userSettings.crisis.title') }}</span>
    </template>
    <p class="card-desc">
      {{ t('userSettings.crisis.desc') }}
    </p>

    <div class="crisis-list">
      <div class="crisis-item crisis-item--hotline">
        <div class="crisis-main">
          <div class="crisis-head">
            <span class="crisis-name">{{ t('userSettings.crisis.hotline') }}</span>
            <span class="crisis-number">{{ t('userSettings.crisis.hotlineNumber') }}</span>
          </div>
          <p class="crisis-desc">
            {{ t('userSettings.crisis.hotlineDesc') }}
          </p>
        </div>
        <a
          class="crisis-call"
          :href="`tel:${telHref(t('userSettings.crisis.hotlineNumber'))}`"
        >
          <el-button
            type="danger"
            size="small"
          >
            {{ t('userSettings.crisis.call') }}
          </el-button>
        </a>
      </div>

      <div class="crisis-item crisis-item--doctor">
        <div class="crisis-main">
          <div class="crisis-head">
            <span class="crisis-name">{{ t('userSettings.crisis.doctor') }}</span>
            <span class="crisis-number">{{ t('userSettings.crisis.doctorPhone') }}</span>
          </div>
          <p class="crisis-desc">
            {{ t('userSettings.crisis.doctorName') }} · {{ t('userSettings.crisis.doctorDesc') }}
          </p>
        </div>
        <a
          class="crisis-call"
          :href="`tel:${telHref(t('userSettings.crisis.doctorPhone'))}`"
        >
          <el-button
            type="primary"
            size="small"
          >
            {{ t('userSettings.crisis.call') }}
          </el-button>
        </a>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineOptions({ name: 'CrisisCard' })
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const telHref = (raw: string): string => raw.replace(/[^\d+]/g, '')
</script>

<style scoped>
.card-title {
  font-weight: var(--font-weight-semibold);
}

.card-desc {
  margin: 0 0 var(--spacing-md);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  line-height: 1.6;
}

.crisis-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.crisis-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  border-radius: var(--radius-md);
  background-color: var(--bg-page);
  border-left: 3px solid transparent;
}

.crisis-item--hotline {
  border-left-color: var(--danger-color);
}

.crisis-item--doctor {
  border-left-color: var(--primary-color);
}

.crisis-main {
  flex: 1;
  min-width: 0;
}

.crisis-head {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: var(--spacing-xs) var(--spacing-sm);
}

.crisis-name {
  font-weight: var(--font-weight-medium);
}

.crisis-number {
  font-variant-numeric: tabular-nums;
  font-size: var(--font-size-large);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  letter-spacing: 0.01em;
}

.crisis-desc {
  margin: var(--spacing-xs) 0 0;
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
  line-height: 1.5;
}

.crisis-call {
  flex-shrink: 0;
  text-decoration: none;
}

.crisis-call :deep(.el-button) {
  margin-left: 0;
}

@media (max-width: 480px) {
  .crisis-item {
    flex-direction: column;
    align-items: stretch;
  }

  .crisis-call {
    align-self: flex-start;
  }
}
</style>
