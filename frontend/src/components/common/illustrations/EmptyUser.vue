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
    <title>暂无用户</title>
    <!-- 一个空座位 - 传递"等待加入"的感觉,而非"没有人" -->
    <!-- 椅子靠背 -->
    <path
      d="M24 30 L 24 52 C 24 53.1, 24.9 54, 26 54 L 54 54 C 55.1 54, 56 53.1, 56 52 L 56 30"
      fill="var(--calm-accent-light, #e8f4f2)"
      stroke="currentColor"
    />
    <!-- 椅子座面 -->
    <path
      d="M20 54 L 60 54 L 60 58 C 60 59.1, 59.1 60, 58 60 L 22 60 C 20.9 60, 20 59.1, 20 58 Z"
      fill="var(--primary-light, #e8f1f8)"
      stroke="currentColor"
    />
    <!-- 椅子腿 -->
    <line
      x1="24"
      y1="60"
      x2="24"
      y2="66"
      stroke="currentColor"
    />
    <line
      x1="56"
      y1="60"
      x2="56"
      y2="66"
      stroke="currentColor"
    />
    <!-- 上方的虚线人形轮廓 - 表示"等待某人坐下" -->
    <circle
      cx="40"
      cy="22"
      r="6"
      fill="none"
      stroke="currentColor"
      stroke-dasharray="3 2"
      opacity="0.4"
    />
    <path
      d="M30 36 C 30 30, 34 28, 40 28 C 46 28, 50 30, 50 36"
      fill="none"
      stroke="currentColor"
      stroke-dasharray="3 2"
      opacity="0.4"
    />
    <!-- 旁边的小植物 - 增加温度感 -->
    <path
      d="M64 60 L 64 56"
      stroke="currentColor"
      opacity="0.5"
    />
    <path
      d="M64 56 C 60 54, 58 50, 62 48 C 64 50, 64 54, 64 56 Z"
      fill="var(--calm-accent, #7ab0a8)"
      opacity="0.3"
    />
    <path
      d="M64 56 C 68 54, 70 50, 66 48 C 64 50, 64 54, 64 56 Z"
      fill="var(--calm-accent, #7ab0a8)"
      opacity="0.3"
    />
  </svg>
</template>

<script setup lang="ts">
// 用户空状态插画 - 空座位 + 虚线人形 + 旁边的小植物,传递"等待加入"而非"没有人"
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
