<template>
  <section
    class="bento-cell"
    :class="[
      { 'bento-cell--hero': hero, 'bento-cell--shimmer': shimmer },
      `bento-cell--live-${liveDot}`,
    ]"
  >
    <header
      v-if="title || $slots.actions || $slots.header"
      class="bento-cell__head"
      :class="{ 'bento-cell__head--split': $slots.actions }"
    >
      <!-- 自定义 header 插槽优先 -->
      <slot name="header">
        <div class="bento-cell__title-group">
          <span
            v-if="liveDot && liveDot !== 'none'"
            class="bento-cell__live-dot breathe-dot"
            :class="{ 'bento-cell__live-dot--alert': liveDot === 'alert' }"
            :aria-hidden="true"
          />
          <h3
            v-if="title"
            class="bento-cell__title"
          >
            {{ title }}
          </h3>
          <slot name="title-suffix" />
        </div>
      </slot>
      <div
        v-if="$slots.actions"
        class="bento-cell__actions"
      >
        <slot name="actions" />
      </div>
    </header>

    <div class="bento-cell__body">
      <slot />
    </div>

    <footer
      v-if="$slots.footer"
      class="bento-cell__footer"
    >
      <slot name="footer" />
    </footer>
  </section>
</template>

<script setup lang="ts">
/**
 * Bento 单元公共组件
 * 规则 9-A：白底 + 1px 边框 + 扩散阴影，替代通用 el-card 过度使用
 * 规则 4：hover 光泽扫光、入场阶梯动画由全局 .bento-item / .shimmer-sweep 提供
 */
// ISS-094 TODO：可补充可选 clickable 属性，整卡可点击跳转详情，配合 :hover 阴影/边框反馈
// ISS-106 TODO：后续可扩展 variant 属性（default/outlined/soft），统一替代散落各页面的自定义卡片样式
withDefaults(
  defineProps<{
    /** 卡片标题（与 #header 插槽互斥，插槽优先） */
    title?: string
    /** Hero 变体：更大、带主色微染背景，用于主视觉数据卡 */
    hero?: boolean
    /** 启用 hover 光泽扫光 */
    shimmer?: boolean
    /** 活动状态指示点：none 无 / primary 主色 / alert 警示色 */
    liveDot?: 'none' | 'primary' | 'alert'
  }>(),
  {
    title: '',
    hero: false,
    shimmer: false,
    liveDot: 'none',
  }
)
</script>

<style scoped>
/* ===== Bento 单元：替代通用 el-card（规则 9-A） ===== */
/* ISS-032 修复：圆角/阴影/间距统一使用设计系统令牌，与 el-card 视觉一致 */
/* ISS-101 修复：硬编码间距改用设计令牌，确保全局间距一致性 */
.bento-cell {
  background: var(--bg-primary);
  border: 1px solid var(--border-extra-light);
  border-radius: var(--radius-xl);
  padding: var(--spacing-lg);
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-light);
  transition: box-shadow var(--transition-duration) var(--transition-ease-out),
    border-color var(--transition-duration) var(--transition-ease-out);
}

.bento-cell:hover {
  box-shadow: var(--shadow-card-hover);
  border-color: var(--border-light);
}

/* Hero 变体：主色微染背景 */
.bento-cell--hero {
  background:
    linear-gradient(180deg, rgba(59, 130, 196, 0.04) 0%, transparent 60%),
    var(--bg-primary);
}

/* 光泽扫光由全局 .shimmer-sweep 提供 ::before；这里仅启用溢出隐藏 */
.bento-cell--shimmer {
  overflow: hidden;
}

/* ===== 头部 ===== */
.bento-cell__head {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
}

.bento-cell__head--split {
  justify-content: space-between;
}

.bento-cell__title-group {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  min-width: 0;
}

.bento-cell__title {
  margin: 0;
  font-family: var(--font-family-display);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  letter-spacing: var(--letter-spacing-tight);
  color: var(--text-primary);
}

.bento-cell__actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  flex-shrink: 0;
}

/* 活动状态点 */
.bento-cell__live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--primary-color);
  box-shadow: 0 0 8px rgba(59, 130, 196, 0.6);
  flex-shrink: 0;
}

.bento-cell--live-alert .bento-cell__live-dot,
.bento-cell__live-dot--alert {
  background: var(--danger-color);
  box-shadow: 0 0 8px rgba(214, 90, 90, 0.6);
}

/* ===== 主体 ===== */
.bento-cell__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

/* ===== 页脚 ===== */
.bento-cell__footer {
  margin-top: auto;
  padding-top: var(--spacing-sm);
}
</style>
