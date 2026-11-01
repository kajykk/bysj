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
        <SkeletonScreen
          variant="text"
          :rows="1"
          :row-height="32"
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
            <AppIcon :name="primaryStat.trend >= 0 ? 'arrow-up' : 'arrow-down'" />
          </el-icon>
          {{ Math.abs(primaryStat.trend) }}%
        </el-tag>
        <span class="trend-label">{{ t('adminDashboard.trendDayOverDay') }}</span>
      </div>
      <span class="stat-sub">{{ primaryStat.sub }}</span>
    </section>

    <!-- 副指标：三卡同排，与 Hero 同高 -->
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
          <SkeletonScreen
            variant="text"
            :rows="1"
            :row-height="32"
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
              <AppIcon :name="card.trend >= 0 ? 'arrow-up' : 'arrow-down'" />
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
import AppIcon from '@/components/common/AppIcon.vue'
import SkeletonScreen from '@/components/common/SkeletonScreen.vue'
import type { StatCard } from './sharedAdminDashboardUtils'

defineProps<{
  loading: boolean
  primaryStat: StatCard
  secondaryStats: StatCard[]
}>()

const { t } = useI18n()
</script>

<style scoped>
/* ===== Bento 统计区（UI-B2 方案 B）：Hero 大卡 + 三副卡同排同高 ===== */
.bento-stats {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 2.6fr);
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.bento-stat-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--spacing-lg);
}

.bento-stat {
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

.bento-stat:hover {
  box-shadow: var(--shadow-card-hover);
  border-color: var(--border-light);
}

.bento-stat--hero {
  background: var(--gradient-surface), var(--surface-1);
  justify-content: space-between;
}

.stat-label {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-extra-small);
  font-weight: var(--font-weight-medium);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-sm);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.stat {
  font-family: var(--font-family-display);
  font-size: var(--font-size-stat);
  font-weight: var(--font-weight-bold);
  letter-spacing: -0.03em;
  margin: var(--spacing-xs) 0 var(--spacing-sm);
  line-height: 1;
  color: var(--text-primary);
}

.stat--hero {
  font-size: 3.25rem;
  color: var(--primary-color);
}

.stat--primary { color: var(--primary-color); }
.stat--neutral { color: var(--text-primary); }
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

/* ===== 响应式：Hero 先独占一行，再收副卡列数 ===== */
@media (max-width: 1280px) {
  .bento-stats {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1024px) {
  .bento-stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .bento-stat-grid {
    grid-template-columns: 1fr;
  }

  .stat {
    font-size: var(--font-size-heading);
  }

  .stat--hero {
    font-size: 2.5rem;
  }
}
</style>
