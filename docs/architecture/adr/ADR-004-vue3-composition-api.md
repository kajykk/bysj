# ADR-004: 选择 Vue 3 + Composition API 而非 Options API

## 状态 (Status)
Accepted

## 日期 (Date)
2026-07-03

## 上下文 (Context)
DWS 前端 (见 `frontend/package.json`, 名称 `depression-warning-system-frontend`) 需要支撑三类角色 (学生用户 / 咨询师 / 管理员) 的复杂交互场景:

1. **复杂状态管理**: 风险趋势 ECharts 图表 (`frontend/src/components/charts/RiskTrendChart.vue`)、WebSocket 实时告警推送 (`frontend/src/composables/useWebSocket.ts`)、风险评估表单与多步骤问卷, 涉大量响应式状态与副作用。
2. **逻辑复用需求**: ECharts 实例管理、断点响应、列表查询状态、主题切换等逻辑需在多个视图间复用 (`frontend/src/composables/useECharts.ts`、`useBreakpoint.ts`、`useListQueryState.ts`、`useTheme.ts`)。
3. **TypeScript 强约束**: 前端需与后端 OpenAPI 契约对齐 (`frontend/src/types/contracts.ts`、`frontend/src/api/`), 类型安全要求高, 类型推导需贯穿模板与脚本。
4. **组件复用性**: 管理后台、咨询师工作台、用户中心三大模块共享表单、表格、对话框、上传组件, 需要高复用性的组件设计。
5. **性能要求**: 首屏需支持 PWA 离线 (`vite-plugin-pwa`) 与按需加载 (`frontend/src/router/lazyLoad.ts`), Tree-shaking 友好度影响打包体积。

## 决策 (Decision)
选择 **Vue 3.5 (>=3.5.13) + Composition API + `<script setup>` 语法 + TypeScript**, 配套生态:

- **状态管理**: Pinia (`pinia>=2.1.7`, 见 `frontend/src/stores/auth.ts`、`layout.ts`、`loading.ts`)。
- **路由**: Vue Router 4 (`vue-router>=4.4.3`, 见 `frontend/src/router/`)。
- **构建工具**: Vite 6 (`vite>=6.2.6`), 配合 `unplugin-auto-import` 与 `unplugin-vue-components` 自动导入。
- **国际化**: vue-i18n 9 (`vue-i18n>=9.14.5`, 见 `frontend/src/i18n/locales/zh-CN.ts`、`en-US.ts`)。
- **类型检查**: `vue-tsc` (见 `package.json` 的 `typecheck` 脚本)。

具体落地方式:
- 所有新组件统一使用 `<script setup lang="ts">` 语法, 禁止 Options API。
- 可复用逻辑抽取为 `composables/useXxx.ts`, 通过组合返回响应式状态与方法。
- 组件按职责分层: `components/` (通用 UI)、`views/` (页面)、`composables/` (逻辑)、`stores/` (全局状态)。

## 替代方案 (Alternatives Considered)
- **Options API**: 逻辑复用依赖 mixin, 易产生命名冲突与来源不清晰; `this` 上下文在 TypeScript 中类型推导差; 大组件中 data/methods/computed 分散, 维护成本高。
- **React**: 生态成熟但团队学习成本高, 且 JSX 与现有 Vue 团队栈不匹配; 表单密集型中后台场景 Vue 双向绑定更高效。
- **Angular**: 框架过重, 依赖注入与 RxJS 学习曲线陡峭, 不适合本项目规模与团队配置。

## 后果 (Consequences)
- **正面**:
  - **逻辑复用**: composables 机制干净利落, ECharts/WebSocket/断点等逻辑跨视图复用无冲突 (见 `frontend/src/composables/`)。
  - **TypeScript 友好**: `<script setup lang="ts">` 配合 `vue-tsc` 提供完整的模板与脚本类型检查, 与后端契约类型对齐。
  - **Tree-shaking**: Composition API 基于 import, 比 Options API 全局注册更利于打包优化, 配合 Vite 按需加载首屏体积可控。
  - **响应式精度**: Vue 3.5 的响应式系统性能优于 2.x, 适合 ECharts 高频更新与 WebSocket 推送场景。
- **负面**:
  - 团队需学习 Composition API 范式 (reactive/ref/watch/computed 心智模型), 从 Options API 迁移存在适应期。
  - `ref` vs `reactive` 的取舍、`watch` 副作用清理等细节需团队建立规范, 否则易引入内存泄漏。
- **中性**:
  - 需配套 ESLint 规则 (`frontend/.eslintrc.cjs` 的 `eslint-plugin-vue`) 强制 Composition API 风格一致性。

## 关联 (Related)
- ADR-005: Element Plus UI 组件库选型
- `frontend/package.json` (Vue / Pinia / Vue Router / Vite 版本)
- `frontend/src/composables/` (composables 实现集合)
- `frontend/src/stores/` (Pinia 状态管理)
- `frontend/src/router/` (路由与懒加载)
- `frontend/src/types/contracts.ts` (前后端契约类型)
- `frontend/.eslintrc.cjs` (代码风格约束)
- `docs/FRONTEND_OPTIMIZATION_PLAN.md` (前端优化方案)
