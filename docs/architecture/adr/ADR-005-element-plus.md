# ADR-005: 选择 Element Plus 而非 Ant Design Vue

## 状态 (Status)
Accepted

## 日期 (Date)
2026-07-03

## 上下文 (Context)
DWS 前端为三类角色 (学生用户 / 咨询师 / 管理员) 提供中后台密集型界面, 对 UI 组件库的需求集中在:

1. **企业级组件完备性**: 管理后台 (`frontend/src/views/admin/`) 需要表格 (含排序/筛选/分页)、复杂表单 (风险评估问卷、模板编辑)、对话框、上传 (`app/api/v1/uploads.py` 对接)、日期选择器、标签页等全套组件。
2. **暗黑模式**: 系统支持主题切换 (`frontend/src/composables/useTheme.ts`、`frontend/src/styles/theme.scss`), 组件库需原生暗黑模式以降低适配成本。
3. **中文优先国际化**: 系统面向国内高校, 主语言为中文 (`frontend/src/i18n/locales/zh-CN.ts`), 组件库默认语言与文档需中文友好。
4. **Vue 3 原生**: 与 ADR-004 选定的 Vue 3 Composition API 深度集成, 避免适配层带来的性能与维护负担。
5. **表单校验集成**: 风险评估、用户信息、告警静默 (`frontend/src/views/admin/AdminSilencesPage.vue`) 等表单需与组件库的校验机制深度集成。

## 决策 (Decision)
选择 **Element Plus 2.8 (`element-plus>=2.8.4`)** 作为 UI 组件库, 配套:

- **图标库**: `@element-plus/icons-vue (>=2.3.2)` (见 `frontend/package.json`)。
- **按需引入**: 通过 `unplugin-auto-import` 与 `unplugin-vue-components` 自动注册组件, 减少打包体积。
- **国际化**: 接入 vue-i18n, 默认 `zh-CN`, 支持切换至 `en-US` (`frontend/src/i18n/index.ts`)。
- **暗黑模式**: 复用 Element Plus 暗黑主题 CSS 变量, 与自研 `frontend/src/styles/theme.scss` 协同。
- **表单校验**: 使用 Element Plus 的 `el-form` + `rules` 机制, 配合 `frontend/src/utils/passwordValidation.ts` 等自定义校验器。

## 替代方案 (Alternatives Considered)
- **Ant Design Vue**: 组件完备但中文文档与社区生态不如 Element Plus, 且设计风格偏 "蚂蚁" 视觉, 与国内高校中后台审美存在差距。
- **Vuetify**: 基于 Material Design, 视觉风格不符合本项目的中后台密集表格场景; Vue 3 版本生态成熟度略逊。
- **Naive UI**: TypeScript 友好但组件数量较少, 部分高级组件 (如虚拟化表格、复杂上传) 缺失, 无法覆盖管理后台全部需求。
- **TDesign (腾讯)**: 质量不错但生态规模与社区活跃度不及 Element Plus, 长期维护风险较高。

## 后果 (Consequences)
- **正面**:
  - **中文生态最佳**: 文档、社区案例、Stack Overflow 问答以中文为主, 团队排障效率高。
  - **Vue 3 原生**: 基于 Composition API 重写, 与本项目 `<script setup>` 风格一致, 无适配层。
  - **暗黑模式**: 通过 CSS 变量原生支持, 与 `frontend/src/composables/useTheme.ts` 联动顺畅。
  - **国际化**: 内置 i18n, 与 vue-i18n 集成简单, 默认中文降低初次接入成本。
  - **组件覆盖广**: 表格、表单、上传、对话框、标签页等中后台刚需组件齐全, 满足管理后台与咨询师工作台需求。
- **负面**:
  - 部分组件定制性不足 (如 `el-table` 复杂合并单元格需手写渲染函数), 深度定制成本较高。
  - 打包体积较大, 需严格依赖 `unplugin-vue-components` 按需引入控制首屏体积 (见 `docs/FRONTEND_OPTIMIZATION_PLAN.md`)。
- **中性**:
  - 需建立组件二次封装规范 (`frontend/src/components/` 下的 `BaseChart.vue` 等模式), 避免直接散用 Element Plus 原生组件导致风格漂移。

## 关联 (Related)
- ADR-004: Vue 3 + Composition API 选型
- `frontend/package.json` (Element Plus / 图标库版本)
- `frontend/src/composables/useTheme.ts` (主题切换)
- `frontend/src/styles/theme.scss` (主题样式)
- `frontend/src/i18n/locales/zh-CN.ts` (中文国际化)
- `frontend/src/views/admin/` (管理后台组件使用示例)
- `frontend/src/utils/passwordValidation.ts` (表单校验器)
- `docs/FRONTEND_OPTIMIZATION_PLAN.md` (按需引入与打包优化)
- `docs/I18N_MIGRATION_PROGRESS.md` (国际化迁移进度)
