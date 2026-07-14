<template>
  <div class="bento-stats">
    <!-- 主指标卡：注册用户（Hero stat） -->
    <section class="bento-stat bento-stat--hero bento-item shimmer-sweep">
      <div class="stat-label">
        {{ primaryStat.label }}
      </div>
      <div
        v-if="loading"
        class="stat-loading"
      >
        <el-skeleton
          :rows="1"
          animated
        />
      </div>
      <div
        v-else
        class="stat stat--hero tabular-nums"
      >
        {{ primaryStat.value }}
      </div>
      <div class="stat-trend">
        <el-tag
          :type="primaryStat.trendType"
          size="small"
          effect="plain"
        >
          <el-icon>
            <ArrowUp v-if="primaryStat.trend >= 0" />
            <ArrowDown v-else />
          </el-icon>
          {{ Math.abs(primaryStat.trend) }}%
        </el-tag>
        <span class="trend-label">{{ t('adminDashboard.trendDayOverDay') }}</span>
      </div>
      <span class="stat-sub">{{ primaryStat.sub }}</span>
    </section>

    <!-- 副指标 2x2 网格 -->
    <div class="bento-stat-grid">
      <section
        v-for="card in secondaryStats"
        :key="card.key"
        class="bento-stat bento-item shimmer-sweep"
      >
        <div class="stat-label">
          {{ card.label }}
        </div>
        <div
          v-if="loading"
          class="stat-loading"
        >
          <el-skeleton
            :rows="1"
            animated
          />
        </div>
        <div
          v-else
          class="stat tabular-nums"
          :class="`stat--${card.tone}`"
        >
          {{ card.value }}
        </div>
        <div class="stat-trend">
          <el-tag
            :type="card.trendType"
            size="small"
            effect="plain"
          >
            <el-icon>
              <ArrowUp v-if="card.trend >= 0" />
              <ArrowDown v-else />
            </el-icon>
            {{ Math.abs(card.trend) }}%
          </el-tag>
          <span class="trend-label">{{ t('adminDashboard.trend') }}</span>
        </div>
        <span class="stat-sub">{{ card.sub }}</span>
        <el-button
          v-if="card.action"
          :type="card.actionType"
          link
          class="stat-action"
          @click="card.action"
        >
          {{ card.actionText }}
        </el-button>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ArrowUp, ArrowDown } from '@element-plus/icons-vue'
import type { StatCard } from './sharedAdminDashboardUtils'

defineProps<{
  loading: boolean
  primaryStat: StatCard
  secondaryStats: StatCard[]
}>()

const { t } = useI18n()
</script>

<style scoped>
/* ===== Bento 统计区：主指标（1.3fr）+ 副指标网格（2fr 内 2x2） ===== */
.bento-stats {
  display: grid;
  grid-template-columns: 1.3fr 2fr;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.bento-stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-lg);
}

.bento-stat {
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

.bento-stat:hover {
  box-shadow: 0 12px 32px -12px rgba(46, 111, 168, 0.14);
  border-color: var(--border-light);
}

.bento-stat--hero {
  background:
    linear-gradient(180deg, rgba(46, 111, 168, 0.04) 0%, transparent 60%),
    var(--bg-primary);
  justify-content: space-between;
}

.stat-label {
  font-family: var(--font-family-mono);
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-bottom: 0.75rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.stat {
  font-family: var(--font-family-display);
  font-size: 2rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  margin: 0.25rem 0 0.5rem;
  line-height: 1;
  color: var(--text-primary);
}

.stat--hero {
  font-size: 3.25rem;
  color: var(--primary-color);
}

.stat--primary { color: var(--primary-color); }
.stat--warning { color: var(--warning-color); }
.stat--danger { color: var(--danger-color); }
.stat--success { color: var(--success-color); }

.stat-sub {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
  display: block;
  margin-top: var(--spacing-xs);
}

.stat-loading {
  min-height: 44px;
}

.stat-trend {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin: 0.25rem 0;
}

.trend-label {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.stat-action {
  margin-top: auto;
  align-self: flex-start;
  padding-top: 0.5rem;
}

/* ===== 响应式：移动端单列回退 ===== */
@media (max-width: 1024px) {
  .bento-stats {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .bento-stat-grid {
    grid-template-columns: 1fr;
  }

  .stat {
    font-size: 1.75rem;
  }

  .stat--hero {
    font-size: 2.5rem;
  }
}
</style>
