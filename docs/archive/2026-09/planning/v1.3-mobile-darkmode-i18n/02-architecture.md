# v1.3 架构设计文档 - 移动端适配、深色模式与国际化

> **迭代版本**: v1.3-mobile-darkmode-i18n
> **创建时间**: 2026-04-27

---

## 1. 架构概述

### 1.1 设计目标
- 模块化的主题系统
- 可扩展的国际化方案
- 响应式组件设计

### 1.2 技术栈
- Vue 3 + Composition API
- Vue I18n 9.x
- CSS Variables + SCSS
- Viewport 适配方案

---

## 2. 主题系统架构

### 2.1 CSS 变量设计
```scss
// 浅色主题（默认）
:root {
  --bg-primary: #ffffff;
  --bg-secondary: #f5f7fa;
  --text-primary: #303133;
  --text-secondary: #606266;
  --border-color: #dcdfe6;
  --primary-color: #409eff;
}

// 深色主题 - 使用 html.dark 类名（Element Plus 标准）
html.dark {
  --bg-primary: #141414;
  --bg-secondary: #1d1d1d;
  --text-primary: #e0e0e0;
  --text-secondary: #a0a0a0;
  --border-color: #434343;
  --primary-color: #5b8ff9;
}
```

> **调研结果**: Element Plus v2.2.0+ 支持通过 `html.dark` 类名切换暗黑模式，使用 CSS 变量 `--el-bg-color` 等。

### 2.2 主题管理器
```typescript
// src/composables/useTheme.ts
export function useTheme() {
  const theme = ref<'light' | 'dark' | 'auto'>('auto')
  
  const applyTheme = () => {
    const isDark = theme.value === 'dark' || 
      (theme.value === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches)
    // Element Plus 标准：使用 html.dark 类名
    document.documentElement.classList.toggle('dark', isDark)
  }
  
  watch(theme, applyTheme)
  
  return { theme, applyTheme }
}
```

---

## 3. 国际化架构

### 3.1 目录结构
```
src/
  i18n/
    index.ts          # i18n 配置
    locales/
      zh-CN.ts        # 中文语言包
      en-US.ts        # 英文语言包
      modules/
        common.ts     # 公共文本
        user.ts       # 用户模块
        admin.ts      # 管理模块
```

### 3.2 语言包结构
```typescript
// src/i18n/locales/zh-CN.ts
export default {
  common: {
    confirm: '确认',
    cancel: '取消',
    loading: '加载中...'
  },
  user: {
    dashboard: {
      title: '用户仪表盘',
      riskScore: '风险评分'
    }
  }
}
```

### 3.3 动态加载
```typescript
// src/i18n/index.ts
import { createI18n } from 'vue-i18n'

const i18n = createI18n({
  locale: localStorage.getItem('locale') || 'zh-CN',
  fallbackLocale: 'zh-CN',
  messages: {}
})

// 按需加载语言包 - 使用 Vite 动态导入
export async function loadLocaleMessages(locale: string) {
  // 避免重复加载
  if (i18n.global.availableLocales.includes(locale)) return
  
  const messages = await import(`./locales/${locale}.ts`)
  i18n.global.setLocaleMessage(locale, messages.default)
  i18n.global.locale.value = locale
  localStorage.setItem('locale', locale)
}
```

> **调研结果**: Vue I18n v9.3+ 支持将语言包编译为 AST，提升运行时性能。建议配合 `@intlify/bundle-tools` 使用。

---

## 4. 响应式架构

### 4.1 断点设计
```scss
// src/styles/breakpoints.scss
$breakpoints: (
  'xs': 320px,   // 手机竖屏
  'sm': 576px,   // 手机横屏
  'md': 768px,   // 平板
  'lg': 992px,   // 小型桌面
  'xl': 1200px,  // 标准桌面
  'xxl': 1400px  // 大型桌面
);

@mixin respond-to($breakpoint) {
  @media (min-width: map-get($breakpoints, $breakpoint)) {
    @content;
  }
}
```

### 4.2 移动端组件适配
```vue
<!-- 响应式布局示例 -->
<template>
  <div class="responsive-layout">
    <!-- 桌面端：侧边栏 -->
    <aside v-if="!isMobile" class="sidebar">
      <SideMenu />
    </aside>
    
    <!-- 移动端：底部导航 -->
    <BottomNav v-if="isMobile" />
    
    <!-- 主内容区 -->
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { useBreakpoint } from '@/composables/useBreakpoint'
const { isMobile } = useBreakpoint()
</script>
```

### 4.3 触摸事件优化
```typescript
// src/composables/useTouch.ts
import { onMounted, onUnmounted } from 'vue'

export function useTouch(element: HTMLElement, options: {
  onTap?: () => void
  onSwipeLeft?: () => void
  onSwipeRight?: () => void
  onPullDown?: () => void
}) {
  let startX = 0
  let startY = 0
  let startTime = 0
  
  const handleTouchStart = (e: TouchEvent) => {
    startX = e.touches[0].clientX
    startY = e.touches[0].clientY
    startTime = Date.now()
  }
  
  const handleTouchEnd = (e: TouchEvent) => {
    const endX = e.changedTouches[0].clientX
    const endY = e.changedTouches[0].clientY
    const deltaX = endX - startX
    const deltaY = endY - startY
    const deltaTime = Date.now() - startTime
    
    // Tap detection
    if (Math.abs(deltaX) < 10 && Math.abs(deltaY) < 10 && deltaTime < 300) {
      options.onTap?.()
    }
    
    // Swipe detection
    if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 50) {
      if (deltaX > 0) options.onSwipeRight?.()
      else options.onSwipeLeft?.()
    }
    
    // Pull down detection
    if (deltaY > 80 && Math.abs(deltaX) < 50) {
      options.onPullDown?.()
    }
  }
  
  onMounted(() => {
    element.addEventListener('touchstart', handleTouchStart, { passive: true })
    element.addEventListener('touchend', handleTouchEnd, { passive: true })
  })
  
  onUnmounted(() => {
    element.removeEventListener('touchstart', handleTouchStart)
    element.removeEventListener('touchend', handleTouchEnd)
  })
}
```

> **修复**: Round 1 Critical Issue - 移动端触摸事件与 Element Plus 冲突

---

## 5. 组件设计

### 5.1 主题感知组件
```vue
<!-- ThemeAwareButton.vue -->
<template>
  <button class="theme-aware-btn" :class="{ 'is-dark': isDark }">
    <slot />
  </button>
</template>

<script setup>
import { useTheme } from '@/composables/useTheme'
const { isDark } = useTheme()
</script>

<style scoped>
.theme-aware-btn {
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}
</style>
```

### 5.2 国际化文本组件
```vue
<!-- I18nText.vue -->
<template>
  <span>{{ t(key, params) }}</span>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
const { t } = useI18n()

defineProps<{
  key: string
  params?: Record<string, string | number>
}>()
</script>
```

---

## 6. ECharts 深色模式适配

### 6.1 ECharts 主题配置
```typescript
// src/composables/useEChartsTheme.ts
import { useTheme } from './useTheme'
import { watch } from 'vue'

export function useEChartsTheme() {
  const { isDark } = useTheme()
  
  const getChartTheme = () => {
    return isDark.value ? 'dark' : 'light'
  }
  
  const getChartOption = (baseOption: any) => {
    if (!isDark.value) return baseOption
    
    return {
      ...baseOption,
      backgroundColor: 'transparent',
      textStyle: { color: '#e0e0e0' },
      title: { textStyle: { color: '#e0e0e0' } },
      legend: { textStyle: { color: '#a0a0a0' } },
      xAxis: {
        ...baseOption.xAxis,
        axisLine: { lineStyle: { color: '#434343' } },
        axisLabel: { color: '#a0a0a0' },
        splitLine: { lineStyle: { color: '#2c2c2c' } }
      },
      yAxis: {
        ...baseOption.yAxis,
        axisLine: { lineStyle: { color: '#434343' } },
        axisLabel: { color: '#a0a0a0' },
        splitLine: { lineStyle: { color: '#2c2c2c' } }
      }
    }
  }
  
  return { getChartTheme, getChartOption }
}
```

> **修复**: Round 1 Critical Issue - ECharts 深色模式适配缺失

---

## 7. 性能优化

### 7.1 主题切换优化
- 使用 CSS 变量避免重绘
- 预加载主题样式
- 过渡动画平滑切换

### 6.2 语言包优化
- 按需加载语言包
- 懒加载非当前语言
- 缓存已加载语言

### 6.3 移动端优化
- 图片懒加载
- 虚拟滚动
- 骨架屏优化

---

## 7. 测试策略

### 7.1 主题测试
- 单元测试：主题切换逻辑
- 视觉测试：截图对比
- E2E 测试：用户切换流程

### 7.2 国际化测试
- 单元测试：翻译函数
- 集成测试：语言切换
- E2E 测试：完整流程

### 7.3 响应式测试
- 单元测试：断点逻辑
- 视觉测试：多设备截图
- E2E 测试：触摸交互

---

## 8. 部署计划

### 8.1 阶段划分
1. **Phase 1**: 主题系统搭建
2. **Phase 2**: 国际化集成
3. **Phase 3**: 移动端适配
4. **Phase 4**: 测试与优化

### 8.2 回滚策略
- 功能开关控制
- 渐进式发布
- 监控告警

---

> **状态**: 已锁定 (Locked)
> **锁定时间**: 2026-04-27
> **版本**: v1.3.0
