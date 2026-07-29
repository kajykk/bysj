<template>
  <svg
    class="empty-illustration float-soft"
    viewBox="0 0 80 80"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    role="img"
    aria-hidden="true"
  >
    <title>暂无预警</title>
    <!-- 平静的铃铛 - 传递"一切安好"的感觉 -->
    <path
      d="M40 18 C 30 18, 24 26, 24 36 L 24 46 L 20 52 L 60 52 L 56 46 L 56 36 C 56 26, 50 18, 40 18 Z"
      fill="var(--success-light, #eef5e8)"
      stroke="currentColor"
    />
    <!-- 铃铛底部小球 -->
    <circle
      cx="40"
      cy="58"
      r="3"
      fill="var(--calm-accent, #7ab0a8)"
      opacity="0.5"
    />
    <!-- 铃铛顶部按钮 -->
    <line
      x1="40"
      y1="14"
      x2="40"
      y2="18"
      stroke="currentColor"
    />
    <circle
      cx="40"
      cy="13"
      r="2"
      fill="currentColor"
      opacity="0.6"
    />
    <!-- 旁边的Zzz - 表示安静 -->
    <text
      x="56"
      y="32"
      font-size="10"
      font-weight="600"
      fill="currentColor"
      opacity="0.3"
      stroke="none"
      font-family="var(--font-family, sans-serif)"
    >z</text>
    <text
      x="60"
      y="26"
      font-size="8"
      font-weight="600"
      fill="currentColor"
      opacity="0.2"
      stroke="none"
      font-family="var(--font-family, sans-serif)"
    >z</text>
    <!-- 内部的勾 - 表示已确认安全 -->
    <path
      d="M34 36 L 38 40 L 46 32"
      stroke="var(--success-color, #5a9e3a)"
      stroke-width="2"
      opacity="0.5"
    />
  </svg>
</template>

<script setup lang="ts">
// 预警空状态插画 - 平静的铃铛 + Zzz + 内部勾选,传递"一切安好"
</script>

<style scoped>
.empty-illustration {
  width: 80px;
  height: 80px;
  color: var(--calm-accent, #7ab0a8);
}

@media (prefers-reduced-motion: reduce) {
  .empty-illustration {
    animation: none !important;
  }
}
</style>
