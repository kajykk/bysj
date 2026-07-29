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
    <title>暂无报告</title>
    <!-- 空文件夹 - 传递"还没有归档记录"的感觉 -->
    <path
      d="M16 24 L 16 58 C 16 59.1, 16.9 60, 18 60 L 62 60 C 63.1 60, 64 59.1, 64 58 L 64 28 C 64 26.9, 63.1 26, 62 26 L 38 26 L 34 22 L 18 22 C 16.9 22, 16 22.9, 16 24 Z"
      fill="var(--primary-light, #e8f1f8)"
      stroke="currentColor"
    />
    <!-- 文件夹内部空白 -->
    <path
      d="M20 32 L 60 32 L 60 56 L 20 56 Z"
      fill="var(--bg-primary, #ffffff)"
      stroke="currentColor"
      opacity="0.3"
    />
    <!-- 里面的纸张轮廓 - 表示等待被填充 -->
    <rect
      x="28"
      y="38"
      width="24"
      height="16"
      rx="1"
      fill="none"
      stroke="currentColor"
      stroke-dasharray="3 2"
      opacity="0.4"
    />
    <line
      x1="32"
      y1="44"
      x2="48"
      y2="44"
      stroke="currentColor"
      opacity="0.2"
    />
    <line
      x1="32"
      y1="48"
      x2="44"
      y2="48"
      stroke="currentColor"
      opacity="0.2"
    />
    <!-- 旁边的星星 - 表示等待生成 -->
    <path
      d="M64 38 L 65 41 L 68 41 L 65.5 43 L 66.5 46 L 64 44 L 61.5 46 L 62.5 43 L 60 41 L 63 41 Z"
      fill="var(--warm-accent, #e8b96a)"
      opacity="0.4"
    />
  </svg>
</template>

<script setup lang="ts">
// 报告空状态插画 - 空文件夹 + 虚线纸张 + 旁边的小星星,传递"等待生成"
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
