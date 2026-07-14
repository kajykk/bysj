<template>
  <section class="bento-cell bento-cell--hero bento-item shimmer-sweep">
    <header class="bento-cell__head">
      <div class="bento-cell__title-group">
        <span
          class="bento-cell__live-dot breathe-dot"
          aria-hidden="true"
        />
        <h3 class="bento-cell__title">
          {{ t('userDashboard.riskStatusTitle') }}
        </h3>
      </div>
      <el-tooltip
        :content="t('userDashboard.severityTooltip')"
        placement="top"
      >
        <el-tag
          :type="severityTagType"
          size="small"
          effect="light"
          round
        >
          {{ severityLabel }}
        </el-tag>
      </el-tooltip>
    </header>

    <div
      v-if="riskLoading"
      class="card-loading"
    >
      <el-skeleton
        :rows="3"
        animated
      />
    </div>
    <EmptyState
      v-else-if="riskError"
      :title="t('userDashboard.loadFailed')"
      :description="riskError"
      :image-size="40"
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
    <template v-else>
      <div class="risk-score-display">
        <CountUp
          :end="riskReport.risk_score"
          :duration="1500"
          :suffix="t('userDashboard.scoreUnit')"
        />
      </div>
      <el-progress
        :percentage="riskReport.risk_score"
        :color="riskColor"
        :stroke-width="14"
        :text-inside="true"
        :format="(p: number) => p + t('userDashboard.scoreUnit')"
      />
      <div class="risk-meta">
        <span class="trend-label">
          {{ t('userDashboard.trendLabel') }}
          <el-icon
            v-if="riskReport.trend === 'up'"
            color="#d65a5a"
            :aria-label="t('userDashboard.trendUp')"
          ><Top /></el-icon>
          <el-icon
            v-else-if="riskReport.trend === 'down'"
            color="#5a9e3a"
            :aria-label="t('userDashboard.trendDown')"
          ><Bottom /></el-icon>
          <span v-else>{{ t('userDashboard.trendStable') }}</span>
        </span>
      </div>
      <p class="risk-advice">
        <!-- ISS-092 TODO：风险说明目前仅显示 advice 第一条文案，后续可补充可展开的"风险因子与保护因素"详细说明 -->
        {{ riskReport.advice?.[0] || t('userDashboard.riskAdviceFallback') }}
      </p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Top, Bottom } from '@element-plus/icons-vue'
import EmptyState from '@/components/common/EmptyState.vue'
import CountUp from '@/components/common/CountUp.vue'
import type { RiskReport } from '@/api/userRiskApi'

defineProps<{
  riskReport: RiskReport
  riskLoading: boolean
  riskError: string
  riskColor: string
  severityLabel: string
  severityTagType: 'info' | 'success' | 'warning' | 'danger'
}>()

const emit = defineEmits<{ reload: [] }>()

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

.bento-cell--hero {
  background:
    linear-gradient(180deg, rgba(46, 111, 168, 0.025) 0%, transparent 60%),
    var(--bg-primary);
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

.card-loading {
  padding: var(--spacing-lg) 0;
}

/* 风险分数主视觉（Hero 卡内） */
.risk-score-display {
  font-family: var(--font-family-display);
  font-size: 3.5rem;
  font-weight: 700;
  letter-spacing: -0.04em;
  color: var(--text-primary);
  margin: 0.5rem 0 1rem;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.risk-score-display :deep(.count-up-number) {
  font-family: var(--font-family-display);
}

.risk-meta {
  display: flex;
  align-items: center;
  margin-top: var(--spacing-md);
}

.trend-label {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.risk-advice {
  font-size: var(--font-size-extra-small);
  color: var(--text-regular);
  margin-top: var(--spacing-md);
  line-height: 1.6;
  padding: 0.625rem 0.875rem;
  background: var(--bg-hover);
  border-radius: 0.625rem;
  border-left: 2px solid var(--primary-color);
}

@media (max-width: 768px) {
  .risk-score-display {
    font-size: 2.75rem;
  }
}
</style>
