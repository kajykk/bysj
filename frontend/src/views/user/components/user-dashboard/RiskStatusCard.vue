<template>
  <section
    class="bento-cell bento-cell--hero bento-item shimmer-sweep risk-hero"
    :data-level="riskLevel"
    :class="{ 'risk-pulse-high': riskLevel === 3, 'risk-pulse-critical': riskLevel === 4 }"
  >
    <!-- UI 升级 v3.2: 右上角风险等级水印图标 - 大号半透明,辅助视觉识别 -->
    <span
      v-if="riskLevel >= 1 && !riskLoading && !riskError"
      class="risk-watermark"
      :data-level="riskLevel"
      aria-hidden="true"
    >{{ riskIcon }}</span>
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
      <SkeletonScreen
        :rows="3"
        variant="text"
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
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Top, Bottom } from '@element-plus/icons-vue'
import EmptyState from '@/components/common/EmptyState.vue'
import CountUp from '@/components/common/CountUp.vue'
import SkeletonScreen from '@/components/common/SkeletonScreen.vue'
import type { RiskReport } from '@/api/userRiskApi'

const props = defineProps<{
  riskReport: RiskReport
  riskLoading: boolean
  riskError: string
  riskColor: string
  severityLabel: string
  severityTagType: 'info' | 'success' | 'warning' | 'danger'
}>()

const emit = defineEmits<{ reload: [] }>()

const { t } = useI18n()

// UI 升级 v3.2: 风险等级数字 (0=none, 1=mild, 2=moderate, 3=high, 4=critical)
const riskLevel = computed(() => props.riskReport?.risk_level ?? 0)

// 风险等级图标 - 用于右上角水印,双重编码(色+形)
const RISK_ICONS: Record<number, string> = {
  0: '○',   // 无风险 - 空心圆,平静
  1: '◐',   // 轻度 - 半圆,关注
  2: '◑',   // 中度 - 半圆(反向),留意
  3: '●',   // 高度 - 实心圆,重视
  4: '◉',   // 危急 - 同心圆,立即行动
}
const riskIcon = computed(() => RISK_ICONS[riskLevel.value] || '')
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
  position: relative;
  overflow: hidden;
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

/* UI 升级 v3.2: 风险 Hero 卡 - 按 data-level 切换渐变背景 */
.risk-hero[data-level="0"] {
  background:
    linear-gradient(180deg, rgba(122, 130, 144, 0.03) 0%, transparent 60%),
    var(--bg-primary);
}
.risk-hero[data-level="1"] {
  background:
    linear-gradient(180deg, rgba(90, 158, 58, 0.04) 0%, transparent 60%),
    var(--bg-primary);
}
.risk-hero[data-level="2"] {
  background:
    linear-gradient(180deg, rgba(212, 146, 58, 0.05) 0%, transparent 60%),
    var(--bg-primary);
}
.risk-hero[data-level="3"] {
  background:
    linear-gradient(180deg, rgba(214, 90, 90, 0.06) 0%, transparent 60%),
    var(--bg-primary);
  border-color: rgba(214, 90, 90, 0.2);
}
.risk-hero[data-level="4"] {
  background:
    linear-gradient(180deg, rgba(168, 46, 40, 0.08) 0%, transparent 60%),
    var(--bg-primary);
  border-color: rgba(168, 46, 40, 0.25);
  box-shadow: var(--shadow-hero);
}

/* UI 升级 v3.2: 右上角水印图标 - 大号半透明,辅助视觉识别 */
.risk-watermark {
  position: absolute;
  top: 1rem;
  right: 1.25rem;
  font-size: 4.5rem;
  line-height: 1;
  font-weight: 700;
  pointer-events: none;
  z-index: 0;
  opacity: 0.08;
}

.risk-watermark[data-level="0"] { color: var(--risk-none); }
.risk-watermark[data-level="1"] { color: var(--risk-mild); opacity: 0.1; }
.risk-watermark[data-level="2"] { color: var(--risk-moderate); opacity: 0.1; }
.risk-watermark[data-level="3"] { color: var(--risk-high); opacity: 0.12; }
.risk-watermark[data-level="4"] { color: var(--risk-critical); opacity: 0.15; }

.bento-cell__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 1.125rem;
  position: relative;
  z-index: 1;
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
  position: relative;
  z-index: 1;
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
  position: relative;
  z-index: 1;
}

.risk-score-display :deep(.count-up-number) {
  font-family: var(--font-family-display);
}

.risk-meta {
  display: flex;
  align-items: center;
  margin-top: var(--spacing-md);
  position: relative;
  z-index: 1;
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
  position: relative;
  z-index: 1;
}

/* 高/危急等级 advice 边框色跟随风险色 */
.risk-hero[data-level="3"] .risk-advice {
  border-left-color: var(--risk-high);
}
.risk-hero[data-level="4"] .risk-advice {
  border-left-color: var(--risk-critical);
}

@media (max-width: 768px) {
  .risk-score-display {
    font-size: 2.75rem;
  }
  .risk-watermark {
    font-size: 3.5rem;
  }
}

/* 减少动效偏好:关闭呼吸光晕 */
@media (prefers-reduced-motion: reduce) {
  .risk-pulse-high,
  .risk-pulse-critical {
    animation: none !important;
  }
}
</style>

