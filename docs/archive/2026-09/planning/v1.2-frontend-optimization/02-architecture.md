# 系统架构设计 - v1.2 前端体验优化

## 1. 技术栈

### 1.1 前端
- **框架**: Vue 3.4+ (Composition API + `<script setup>`)
- **构建工具**: Vite 5.4+
- **UI 库**: Element Plus 2.8+
- **状态管理**: Pinia 2.1+
- **路由**: Vue Router 4.4+
- **图表**: ECharts 5.5+
- **HTTP 客户端**: Axios 1.7+
- **样式预处理器**: Sass 1.77+

### 1.2 质量保障
- **单元测试**: Vitest 4.1 + @vue/test-utils 2.4
- **E2E 测试**: Playwright 1.59
- **类型检查**: vue-tsc 2.1 + TypeScript 5.6
- **代码规范**: ESLint + Prettier（沿用现有配置）

---

## 2. 目录结构规范

```
frontend/
├── src/
│   ├── api/              # API 调用层（按模块组织）
│   ├── components/       # 公共组件
│   │   ├── common/       # 通用组件（StatefulContainer, PageTable 等）
│   │   ├── charts/       # 图表封装组件
│   │   └── feedback/     # 反馈组件（Skeleton, EmptyState 等）
│   ├── composables/      # 组合式函数
│   │   ├── useChart.ts   # ECharts 实例管理
│   │   ├── useLoading.ts # 加载状态管理
│   │   └── useAnimation.ts # 动画工具
│   ├── layouts/          # 布局组件
│   ├── router/           # 路由配置
│   ├── stores/           # Pinia 状态管理
│   ├── styles/           # 全局样式
│   │   ├── variables.scss  # SCSS 变量（颜色、间距）
│   │   ├── mixins.scss     # SCSS Mixins
│   │   └── transitions.scss # 过渡动画
│   ├── utils/            # 工具函数
│   │   ├── format.ts     # 格式化工具
│   │   ├── validate.ts   # 验证工具
│   │   └── export.ts     # 导出工具（CSV/PDF）
│   ├── views/            # 页面视图
│   │   ├── user/         # 用户端页面
│   │   ├── counselor/    # 咨询师端页面
│   │   ├── admin/        # 管理后台页面
│   │   ├── login/        # 登录相关页面
│   │   └── common/       # 公共页面（403, 404）
│   ├── App.vue
│   └── main.ts
├── tests/
│   ├── unit/             # 单元测试
│   └── e2e/              # E2E 测试
├── docs/
│   └── planning/         # 规划文档
└── package.json
```

---

## 3. 组件设计策略

### 3.1 原子化组件分层
- **基础层 (Base)**: 直接基于 Element Plus 的二次封装（如 ElButton 扩展）
- **复合层 (Composite)**: 业务通用组件（StatefulContainer, PageTable）
- **页面层 (Page)**: 特定页面组件，不复用

### 3.2 状态管理边界
- **Pinia Store**: 全局状态（用户信息、权限、通知）
- **组件状态**: 局部状态（表单数据、加载状态）
- **URL 状态**: 列表筛选、分页参数同步到 URL Query

---

## 4. 关键优化方案

### 4.1 性能优化
- **路由懒加载**: 已实施，继续沿用
- **组件异步加载**: 大组件（图表、编辑器）使用 `defineAsyncComponent`
- **ECharts 按需引入**: 仅注册需要的图表类型
- **图片优化**: 使用 WebP 格式，懒加载

### 4.2 动画策略
- **页面过渡**: 使用 Vue `<Transition>` 组件，统一 `fade-slide` 效果
- **数字动画**: 使用 `requestAnimationFrame` 实现 count-up
- **图表动画**: ECharts 内置动画，统一配置 duration 和 easing

### 4.3 主题与样式
- **CSS 变量**: 定义 `--primary-color`, `--success-color` 等变量
- **SCSS 变量**: 定义 `$spacing-base: 8px`，所有间距为 8 的倍数
- **暗黑模式基础**: 预留 CSS 变量结构，v1.2 不实现但可扩展

---

## 5. API 接口规范（沿用现有）

v1.2 迭代不涉及后端 API 变更，沿用 v1.1 已定义的接口规范：
- `userApi` - 用户端 API
- `counselorApi` - 咨询师端 API
- `adminApi` - 管理后台 API
- `modelApi` - 模型相关 API

---

## 6. 关键流程设计

### 6.1 页面加载优化流程
1. 路由守卫检查权限 -> 2. 异步加载页面组件 -> 3. 显示 Skeleton 屏 -> 4. 并行请求数据 -> 5. 渲染内容 -> 6. 隐藏 Skeleton

### 6.2 表单提交优化流程
1. 前端校验 -> 2. 防重复提交（按钮 Loading）-> 3. API 请求 -> 4. 成功 Toast + 自动刷新数据 -> 5. 失败 Toast + 保留表单数据

### 6.3 图表渲染优化流程
1. 获取容器 DOM -> 2. 初始化 ECharts（带 resize 监听）-> 3. 设置选项（带动画）-> 4. 组件卸载时销毁实例
