<template>
  <el-form
    :inline="true"
    class="filter-bar"
  >
    <slot />
    <el-form-item>
      <el-button
        type="primary"
        @click="$emit('search')"
      >
        {{ t('common.query') }}
      </el-button>
      <el-button @click="$emit('reset')">
        {{ t('common.reset') }}
      </el-button>
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

// ISS-030 修复：硬编码"查询/重置"改用 i18n
// ISS-084 TODO：小屏下筛选项过多时可考虑换行布局或折叠抽屉式筛选面板，提升移动端可用性
// ISS-093 TODO：可补充常用快捷筛选 chips（如"近7天/高风险"），减少重复表单输入
defineEmits<{
  search: []
  reset: []
}>()

const { t } = useI18n()
</script>

<style scoped>
.filter-bar {
  margin-bottom: var(--spacing-md);
}
</style>
