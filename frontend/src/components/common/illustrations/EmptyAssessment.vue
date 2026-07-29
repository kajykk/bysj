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
    <title>暂无评估记录</title>
    <!-- 空白问卷 - 传递"等待开始记录"的感觉 -->
    <rect
      x="20"
      y="14"
      width="32"
      height="44"
      rx="3"
      fill="var(--calm-accent-light, #e8f4f2)"
      stroke="currentColor"
    />
    <line
      x1="26"
      y1="24"
      x2="46"
      y2="24"
      stroke="currentColor"
      opacity="0.5"
    />
    <line
      x1="26"
      y1="30"
      x2="42"
      y2="30"
      stroke="currentColor"
      opacity="0.5"
    />
    <line
      x1="26"
      y1="36"
      x2="44"
      y2="36"
      stroke="currentColor"
      opacity="0.5"
    />
    <circle
      cx="26"
      cy="44"
      r="1.5"
      fill="currentColor"
      opacity="0.4"
    />
    <line
      x1="31"
      y1="44"
      x2="42"
      y2="44"
      stroke="currentColor"
      opacity="0.4"
    />
    <circle
      cx="26"
      cy="50"
      r="1.5"
      fill="currentColor"
      opacity="0.4"
    />
    <line
      x1="31"
      y1="50"
      x2="38"
      y2="50"
      stroke="currentColor"
      opacity="0.4"
    />
    <!-- 旁边的小叶子 - 陪伴感 -->
    <path
      d="M58 50 C 56 46, 52 46, 52 52 C 52 56, 58 60, 62 58 C 64 54, 62 50, 58 50 Z"
      fill="var(--calm-accent, #7ab0a8)"
      opacity="0.3"
    />
    <path
      d="M56 54 L 60 56"
      stroke="currentColor"
      opacity="0.4"
    />
  </svg>
</template>

<script setup lang="ts">
// 评估空状态插画 - 一份空白问卷 + 旁边的小叶子
// 设计:使用 currentColor 自动适配主题,float-soft 动效传递"等待但不焦虑"
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
