<template>
  <el-breadcrumb
    :separator-icon="ArrowRight"
    class="breadcrumb-nav"
  >
    <el-breadcrumb-item
      v-for="(item, index) in breadcrumbs"
      :key="index"
      :to="item.path"
    >
      {{ item.title }}
    </el-breadcrumb-item>
  </el-breadcrumb>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowRight } from '@element-plus/icons-vue'

const route = useRoute()

interface BreadcrumbItem {
  path: string
  title: string
}

const breadcrumbs = computed<BreadcrumbItem[]>(() => {
  const items: BreadcrumbItem[] = []
  const matched = route.matched.filter(item => item.meta?.title)

  for (const record of matched) {
    if (record.meta.title) {
      items.push({
        path: record.path,
        title: record.meta.title as string,
      })
    }
  }

  return items
})
</script>

<style scoped>
.breadcrumb-nav {
  line-height: 60px;
}
</style>
