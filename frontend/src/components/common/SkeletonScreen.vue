<template>
  <div class="skeleton-screen">
    <!-- 自定义骨架布局：优先使用插槽 -->
    <slot>
      <!-- 文本行骨架（向后兼容） -->
      <template v-if="variant === 'text'">
        <div
          v-for="i in rows"
          :key="i"
          class="skeleton-row"
          :style="{ height: `${rowHeight}px` }"
        >
          <div
            class="skeleton-item skeleton-shimmer"
            :style="{ width: `${getRandomWidth(i)}%` }"
          />
        </div>
      </template>

      <!-- 统计卡片骨架 -->
      <div
        v-else-if="variant === 'stat-card'"
        class="skeleton-grid"
        :style="{ '--skeleton-cols': cols }"
      >
        <div
          v-for="i in cols"
          :key="i"
          class="skeleton-stat-card"
        >
          <div class="skeleton-item skeleton-shimmer skeleton-stat-label" />
          <div class="skeleton-item skeleton-shimmer skeleton-stat-value" />
          <div class="skeleton-item skeleton-shimmer skeleton-stat-trend" />
        </div>
      </div>

      <!-- 卡片网格骨架 -->
      <div
        v-else-if="variant === 'card'"
        class="skeleton-grid"
        :style="{ '--skeleton-cols': cols }"
      >
        <div
          v-for="i in cols"
          :key="i"
          class="skeleton-card"
        >
          <div class="skeleton-item skeleton-shimmer skeleton-card-media" />
          <div class="skeleton-card-body">
            <div class="skeleton-item skeleton-shimmer skeleton-card-title" />
            <div class="skeleton-item skeleton-shimmer skeleton-card-text" />
            <div class="skeleton-item skeleton-shimmer skeleton-card-text short" />
          </div>
        </div>
      </div>

      <!-- 图表区域骨架 -->
      <div
        v-else-if="variant === 'chart'"
        class="skeleton-chart"
      >
        <div class="skeleton-item skeleton-shimmer skeleton-chart-header" />
        <div class="skeleton-item skeleton-shimmer skeleton-chart-body" />
      </div>

      <!-- 头像骨架 -->
      <div
        v-else-if="variant === 'avatar'"
        class="skeleton-avatar-row"
      >
        <div class="skeleton-item skeleton-shimmer skeleton-avatar-circle" />
        <div class="skeleton-avatar-info">
          <div class="skeleton-item skeleton-shimmer skeleton-avatar-line" />
          <div class="skeleton-item skeleton-shimmer skeleton-avatar-line short" />
        </div>
      </div>

      <!-- 表格骨架 -->
      <div
        v-else-if="variant === 'table'"
        class="skeleton-table"
      >
        <div class="skeleton-table-header">
          <div
            v-for="c in cols"
            :key="c"
            class="skeleton-item skeleton-shimmer skeleton-table-cell"
          />
        </div>
        <div
          v-for="r in rows"
          :key="r"
          class="skeleton-table-row"
        >
          <div
            v-for="c in cols"
            :key="c"
            class="skeleton-item skeleton-shimmer skeleton-table-cell"
          />
        </div>
      </div>
    </slot>
  </div>
</template>

<script setup lang="ts">
interface Props {
  /** 骨架屏类型 */
  variant?: 'text' | 'stat-card' | 'card' | 'chart' | 'avatar' | 'table'
  /** 行数（text/table 类型使用） */
  rows?: number
  /** 列数（stat-card/card/table 类型使用） */
  cols?: number
  /** 行高（text 类型使用） */
  rowHeight?: number
  /** 是否激活动画 */
  animate?: boolean
}

withDefaults(defineProps<Props>(), {
  variant: 'text',
  rows: 5,
  cols: 4,
  rowHeight: 20,
  animate: true,
})

const getRandomWidth = (index: number) => {
  const widths = [40, 60, 80, 50, 90, 30, 70, 45, 85, 55]
  return widths[index % widths.length]
}
</script>

<style scoped>
.skeleton-screen {
  width: 100%;
}

/* ===== 通用闪烁动画（与全局 transitions.scss 保持一致） ===== */
.skeleton-shimmer {
  background: linear-gradient(
    90deg,
    var(--border-light) 25%,
    var(--bg-page) 50%,
    var(--border-light) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-loading 1.5s infinite;
  border-radius: var(--radius-xs);
}

@media (prefers-reduced-motion: reduce) {
  .skeleton-shimmer {
    animation: none;
  }
}

/* ===== text 变体（向后兼容） ===== */
.skeleton-row {
  display: flex;
  align-items: center;
  padding: var(--spacing-xs) 0;
}

.skeleton-item {
  height: 100%;
}

/* ===== stat-card 变体 ===== */
.skeleton-grid {
  display: grid;
  grid-template-columns: repeat(var(--skeleton-cols, 4), 1fr);
  gap: var(--spacing-md);
}

.skeleton-stat-card {
  background-color: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
}

.skeleton-stat-label {
  width: 40%;
  height: 12px;
  margin-bottom: var(--spacing-md);
}

.skeleton-stat-value {
  width: 60%;
  height: 32px;
  margin-bottom: var(--spacing-sm);
}

.skeleton-stat-trend {
  width: 50%;
  height: 12px;
}

/* ===== card 变体 ===== */
.skeleton-card {
  background-color: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.skeleton-card-media {
  width: 100%;
  height: 160px;
  border-radius: 0;
}

.skeleton-card-body {
  padding: var(--spacing-md);
}

.skeleton-card-title {
  width: 60%;
  height: 16px;
  margin-bottom: var(--spacing-sm);
}

.skeleton-card-text {
  width: 90%;
  height: 12px;
  margin-bottom: var(--spacing-xs);
}

.skeleton-card-text.short {
  width: 40%;
}

/* ===== chart 变体 ===== */
.skeleton-chart {
  background-color: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
}

.skeleton-chart-header {
  width: 30%;
  height: 18px;
  margin-bottom: var(--spacing-lg);
}

.skeleton-chart-body {
  width: 100%;
  height: 280px;
  border-radius: var(--radius-sm);
}

/* ===== avatar 变体 ===== */
.skeleton-avatar-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.skeleton-avatar-circle {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  flex-shrink: 0;
}

.skeleton-avatar-info {
  flex: 1;
}

.skeleton-avatar-line {
  width: 50%;
  height: 14px;
  margin-bottom: var(--spacing-xs);
}

.skeleton-avatar-line.short {
  width: 30%;
  height: 12px;
  margin-bottom: 0;
}

/* ===== table 变体 ===== */
.skeleton-table {
  background-color: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.skeleton-table-header {
  display: grid;
  grid-template-columns: repeat(var(--skeleton-cols, 4), 1fr);
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--border-light);
  background-color: var(--bg-page);
}

.skeleton-table-row {
  display: grid;
  grid-template-columns: repeat(var(--skeleton-cols, 4), 1fr);
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--border-lighter, var(--border-light));
}

.skeleton-table-row:last-child {
  border-bottom: none;
}

.skeleton-table-cell {
  height: 16px;
  border-radius: var(--radius-xs);
}
</style>
