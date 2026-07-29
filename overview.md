# DWS 前端界面优化方案 - 总览

## 任务摘要

为 DWS（心理健康风险评估系统）三端（学生 / 咨询师 / 管理员）公共前端框架制定"美观 + 易用并重"的整体升级方案，并执行 Phase 1-4 + Phase 6 的代码落地。

## 关键决策

1. **不推翻现有令牌系统**：项目现有 `variables.scss` 已是 A 级（WCAG AA 达标、Lighthouse 98/100），方案采用"追加扩展"而非"重写"。
2. **三端差异化**：通过 `body[data-role]` 注入角色强调色（学生端静谧青 / 咨询师端品牌蓝 / 管理员端中性灰），保持品牌主色不变。
3. **心理健康产品调性**：遵循"安全感 · 可控感 · 不评判 · 温度感 · 专业感"五原则，避免医疗冷感。
4. **分 6 阶段落地**：从低风险令牌扩展开始，逐步到高风险信息架构重组。

## 已执行的代码改动

### Phase 1: 令牌扩展 ✅

| 文件 | 改动 |
|---|---|
| `frontend/src/styles/variables.scss` | 追加情感化色彩、角色强调色、卡片语义阴影、风险视觉系统、动效令牌；`body[data-role]` 角色色切换 |
| `frontend/src/styles/transitions.scss` | 追加 risk-pulse / celebrate / safe-in / check-draw 动效；扩展 prefers-reduced-motion 兼容 |
| `frontend/src/styles/theme.scss` | 深色模式适配情感化色彩、语义阴影、风险渐变 |

### Phase 2: 导航/Header 升级 ✅

| 文件 | 改动 |
|---|---|
| `frontend/src/App.vue` | 注入 `body[data-role]` 激活角色强调色系统 |
| `frontend/src/layouts/components/main-layout/SidebarMenu.vue` | Logo 图形 Mark（双叶护心）、菜单激活态角色色条、未读数徽章（含折叠态小圆点）、折叠态分组分隔线 |
| `frontend/src/layouts/components/main-layout/useLayoutMenu.ts` | MenuItem 类型扩展支持 `badge` / `badgeVariant` |
| `frontend/src/layouts/components/main-layout/LayoutHeader.vue` | 三段式重构、文字头像（角色色差异化）、用户下拉菜单、预警数量徽章 |
| `frontend/src/layouts/MainLayout.vue` | 接入新 props/事件、主题循环切换、跳转个人设置 |
| `frontend/src/i18n/locales/zh-CN.ts` / `en-US.ts` | 补充 9 个 i18n key（appSubtitle / newWarningCount / userMenu* 等） |

### Phase 3: 风险视觉强化 ✅

| 文件 | 改动 |
|---|---|
| `frontend/src/views/user/components/user-dashboard/RiskStatusCard.vue` | 按 `risk_level` 切换 5 档渐变背景；高/危急等级启用呼吸光晕；右上角水印图标（○◐◑●◉ 五形双重编码）；advice 边框色跟随风险色 |

### Phase 4: 空状态情感化 ✅

| 文件 | 改动 |
|---|---|
| `frontend/src/components/common/illustrations/EmptyAssessment.vue` | 新建 - 空白问卷 + 小叶子 |
| `frontend/src/components/common/illustrations/EmptyWarning.vue` | 新建 - 平静铃铛 + Zzz + 内部勾选 |
| `frontend/src/components/common/illustrations/EmptyReport.vue` | 新建 - 空文件夹 + 虚线纸张 + 小星星 |
| `frontend/src/components/common/illustrations/EmptyUser.vue` | 新建 - 空座位 + 虚线人形 + 小植物 |
| `frontend/src/components/common/EmptyState.vue` | 升级支持 `variant` prop 自动选插画，向后兼容默认 Document 图标 |
| `LatestAssessmentCard.vue` / `UnreadWarningsCard.vue` / `RecentActivityCard.vue` | 关键空状态调用点添加 variant |

### Phase 6: 组件库语义化 ✅

| 文件 | 改动 |
|---|---|
| `frontend/src/styles/utilities.scss` | 追加 `.card-hero` / `.card-safety` / `.card-data` / `.card-emphasis` 四种语义卡类 |

### Phase 2 补充: 登录页品牌统一 ✅

| 文件 | 改动 |
|---|---|
| `frontend/src/components/common/AuthBrandPanel.vue` | Logo 从圆点升级为双叶护心 SVG（与侧边栏统一）；版本号 v3.1→v3.2；添加 useI18n 支持 |

> LoginPage 和 ResetPasswordPage 共用 AuthBrandPanel，均自动继承升级。

## 验证结果

| 检查项 | 结果 |
|---|---|
| vue-tsc 类型检查（含 AuthBrandPanel 改动后复测） | ✅ 通过（0 errors） |
| ESLint | ✅ 通过（0 errors，8 warnings 已 --fix 修复） |
| Vite 生产构建 | ✅ 成功（26.91s） |
| Lighthouse CI | ⚠️ 环境无 Chrome 无法自动运行，需手动复测 |

### 手动跑 Lighthouse 的命令

```bash
cd frontend
# 方式1: 对 dev server 跑（需要先启动 npm run dev）
npm run lighthouse

# 方式2: 对构建产物跑（更准确）
npm run build && npx vite preview --port 5173 &
npx lighthouse http://localhost:5173 --output=html --output-path=./lighthouse-report.html
```

## 未执行（需用户确认）

- **Phase 5: 信息架构重组** — 涉及三端菜单分组改为"任务驱动"，需同步更新新手引导流程与全量回归测试，风险最高。建议在前面 Phase 验证无误后单独执行。

## 交付物

| 文件 | 说明 |
|---|---|
| `outputs/ui-optimization-plan/ui-optimization-plan.md` | 完整方案文档（10 章） |
| `outputs/ui-optimization-plan/ui-upgrade-preview.html` | 可视化对比 Mockup |
| `overview.md` | 本文档（含已执行改动清单） |

## 后续建议

1. **启动开发服务器预览**：`cd frontend && npm run dev`，登录三个角色账号验证视觉差异
2. **Phase 5 单独确认**：信息架构重组需配套用户测试，建议先收集 Phase 1-4 的使用反馈
3. **Lighthouse 复测**：部署后跑一次 Lighthouse CI 确认 Performance/A11y 未退化
