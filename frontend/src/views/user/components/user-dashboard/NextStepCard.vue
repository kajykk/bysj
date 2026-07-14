<template>
  <section class="next-step-card">
    <p class="next-step-card__label">
      {{ nextAction.label }}
    </p>
    <p class="next-step-card__title">
      {{ nextAction.title }}
    </p>
    <p class="next-step-card__desc">
      {{ nextAction.description }}
    </p>
    <div class="next-step-card__actions">
      <el-button
        type="primary"
        @click="nextAction.action()"
      >
        {{ nextAction.primaryText }}
      </el-button>
      <el-button
        link
        type="primary"
        @click="router.push(nextAction.secondaryPath)"
      >
        {{ nextAction.secondaryText }}
      </el-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import type { NextAction } from './sharedDashboardUtils'

defineProps<{
  nextAction: NextAction
}>()

const router = useRouter()
</script>

<style scoped>
.next-step-card {
  margin-top: var(--spacing-md);
  padding: 1rem 1.1rem;
  border: 1px solid var(--border-extra-light);
  border-radius: 1rem;
  background: var(--bg-primary);
  box-shadow: 0 1px 2px rgba(15, 22, 32, 0.04);
}

.next-step-card__label {
  margin: 0 0 0.35rem;
  font-size: var(--font-size-extra-small);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-secondary);
}

.next-step-card__title {
  margin: 0;
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.next-step-card__desc {
  margin: 0.35rem 0 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  line-height: 1.6;
}

.next-step-card__actions {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
  margin-top: 0.75rem;
}
</style>
