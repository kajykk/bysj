<template>
  <a
    href="#main-content"
    class="skip-link"
  >{{ t('common.skipToMain') }}</a>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

// 无障碍跳转链接，键盘用户可快速跳过导航菜单到主内容区
const { t } = useI18n()
</script>

<style scoped>
/* ISS-028/039 修复：改用 CSS 变量，自动支持深色模式 */
.skip-link {
  position: absolute;
  top: -40px;
  left: 0;
  z-index: 10000;
  padding: var(--spacing-sm) var(--spacing-lg);
  background: var(--primary-color);
  color: var(--text-inverse, #ffffff);
  text-decoration: none;
  border-radius: 0 0 var(--radius-base) 0;
  transition: top var(--transition-fast) ease;
}

.skip-link:focus {
  top: 0;
}
</style>
