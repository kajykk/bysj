# 前端视觉改造计划（UI-B0 ~ UI-B7）

> 立项日期：2026-11-01
> 目标平台：Vue 3.5 + Vite 6.4 + Element Plus 2.14 + SCSS token + ECharts 6.1（**不换 UI 库**）
> 决策（用户已拍板）：① 先管理端打样再全端铺开 ② 允许新增图标/动效/图表三类依赖 ③ 暗色优先 ④ 分批小提交，每批出对照截图

---

## 0. 问题定义（基于 2026-11-01 实测截图与代码勘察）

管理端仪表盘"丑"的根因不是 Element Plus，而是三件事：

| 现象 | 根因 | 证据 |
|---|---|---|
| 卡片糊成一片，看不出层级 | 暗色主题未覆盖 `--bg-page`/`--bg-hover`/`--border-extra-light`/`--text-regular`/`--text-placeholder`/`--gradient-surface`；`--el-bg-color` 与 `--bg-primary` 指向近同色，el-card 与页面底色几乎一致 | `frontend/src/styles/theme.scss:86-197`；`frontend/src/styles/variables.scss:44,46,54,59,61,156` |
| 左上"注册用户"卡巨大且空 | `.bento-stats { grid-template-columns: 1.3fr 2fr }`，Hero 卡在 2×2 副指标组旁被拉到整列高，内部只有 1 个数字 | `frontend/src/views/admin/components/admin-dashboard/StatCardsSection.vue:114-119`、模板 `:4-39` |
| 四张统计卡蓝/橙/绿/红乱飞 | 颜色按卡片位置而非语义分配；环比"↑"一律绿色，预警类指标上升是坏消息也显示绿色 | `frontend/src/views/admin/components/admin-dashboard/useAdminDashboardData.ts:44-80` |
| 侧边栏分组标题层级弱 | 分组标题渲染为 disabled 的 el-menu-item，字号/间距未单独定义 | `frontend/src/layouts/components/main-layout/SidebarMenu.vue:59-68`；分组逻辑 `useLayoutMenu.ts:95-132` |

规模读数：`frontend/src/views` 下 115 个 `.vue`（admin 13 / user 10 / counselor 7 / 公共 2 / login 2）；`frontend/src` 合计 148 个 `.vue`。硬编码 6 位 hex 共 430 处（其中 `styles/` 占 235，生产代码里 `chartPalette.ts` 12、`AuthBrandPanel.vue` 9、`RiskReportTab.vue` 8）。

## 1. 非目标（明确不做）

- 不换 UI 库（Naive UI / shadcn-vue / Reka UI 一律不引入）
- 不改后端接口、鉴权模型、业务流程与路由结构
- 不改登录/注册/权限守卫逻辑
- 不引入字体包（Inter/Noto Sans SC 不纳入本期，中文字体沿用系统栈）
- 不做响应式重写（只修断点处的明显缺陷）

## 2. 设计决策（暗色优先）

### 2.1 表面层级（暗色）
新增三级表面 token，取代"靠阴影分层"：

```
--surface-1: 卡片面（比页面底色亮一档）
--surface-2: 卡片内嵌面 / 表头 / 弹层内区块
--surface-3: 悬浮 / 强调 / 选中态
--card-border: rgba(255,255,255,0.08)   /* 暗色下用描边代替阴影 */
```

暗色下 `--shadow-*` 系列降级为无或极弱，仅保留 `--shadow-hero` 一处。

### 2.2 语义色收敛
- 主色 `--primary-color` 只用于强调与主指标数值
- 语义色（success/warning/danger）只用于**状态**（正常/异常/降级/熔断），不用于装饰
- 风险等级继续用既有 `--risk-none|mild|moderate|high|critical`，不与语义色混用
- 环比颜色按**指标语义**映射，而不是按数值正负：

| 指标类别 | 上升 | 下降 | 示例 |
|---|---|---|---|
| 容量型（注册用户、评估总量、咨询师数） | 中性（主色） | 中性 | 注册用户 |
| 风险型（今日预警、危机事件） | danger | success | 今日预警 |
| 干预型（干预模板完成度） | success | warning | 干预模板 |

### 2.3 版式规范
- 间距：只用既有 `--spacing-*` 刻度（base 8px）
- 圆角：卡片统一 `--radius-lg`，控件 `--radius-md`，标签 `--radius-sm`
- 栅格：统计区候选 A「四卡等宽一行」/ B「Hero 保留大卡但与副卡组同高」——**A/B 样张在 UI-B2 产出后由你选**
- 侧栏分组标题：独立字号/字重/上下间距，不复用菜单项样式

## 3. 依赖引入清单（全部 MIT，版本已核实）

| 包 | 版本 | 许可 | 用途 | 引入批次 |
|---|---|---|---|---|
| `@iconify/vue` | 5.0.5（peer vue >=3） | MIT | 图标渲染 | UI-B3 |
| `@iconify-json/tabler` | 1.2.43 | MIT | Tabler 图标集（6200+） | UI-B3 |
| `@formkit/auto-animate` | 0.10.0 | MIT | 列表/卡片增删动效 | UI-B5 |
| `vue-echarts` | 8.3.2（peer echarts ^6.0.0） | MIT | ECharts 的 Vue 封装 | UI-B4 |

注意：auto-animate 在 npm 上的包名是 `@formkit/auto-animate`，`auto-animate` 这个名字查无此包（npm E404）。
`echarts` 保持现有 6.1.0 不升级。

## 4. 批次计划

每批一个独立 commit，附：改动文件清单、验证命令与读数、浏览器对照截图（`outputs/ui-refresh/<批次>/<页面>-<主题>.png`）、回滚方式。

### UI-B0 基线与门禁加固（无视觉改动）
**目标**：让"改坏了"能被机器拦住，而不是靠肉眼。

- 产出改造前基线截图：管理端 6 个页面 × 明/暗 × 1440×900（`outputs/ui-refresh/B0-baseline/`）
- 修 `frontend/src/test-setup.ts:26-31`：目前 5 个变量是硬编码注入，导致 `styles/styles.test.ts` 的断言是假的 → 改为真读 `variables.scss` 编译产物，或明确标注为契约测试
- 记录当前全量 `vitest` 用例数与通过数，作为后续批次的基线读数
- **执行偏差**：契约测试 `tokens.contract.test.ts` 改到 B1 落地（而不是 B0 先提交一个已知为红的门禁）。理由：每个批次提交时测试必须全绿；守门作用从暗色令牌补齐的那一刻起就生效，不需要一个红的中间态。
- **验收**：基线截图齐备（12 张）；样式门禁改为真读 SCSS；全量基线读数在案（113 文件 / 1367 通过 / 4 跳过 / 1371）
- **回滚**：`git revert <sha>`

### UI-B1 暗色表面层级与语义色收敛
**目标**：卡片与页面拉开层级，色彩回到语义。

- `frontend/src/styles/theme.scss` 的 `html.dark` 块补齐：`--bg-page`、`--bg-hover`、`--border-extra-light`、`--text-regular`、`--text-placeholder`、`--gradient-surface`、`--chart-color-*`（7 个）；同时补齐 `--bg-active`、`--border-lighter`、语义色浅底、阴影/焦点环/光晕等实际在用的令牌
- 新增 §2.1 的 `--surface-1/2/3`、`--card-border`；同步浅色 `:root` 定义（`variables.scss`）
- 新增 `frontend/src/styles/tokens.contract.test.ts`：断言暗色必须覆盖的 37 个令牌、33 个令牌暗浅值必须不同、表面层级亮度递增、正文对比度 ≥4.5:1、图表色 ≥3:1
- 语义色映射表落地到 `useAdminDashboardData.ts:44-89`（`trendToneFor(kind, delta)` 查表；评估总量改中性色，不再按卡片位置发红）
- 顺带修正浅色 `--chart-color-warning`：`#d4923a` 对白底仅 2.63:1，改为 `#c07f26`（3.33:1）
- 收敛重复加载：删除 `useTheme.ts` 里对 Element Plus 暗色 CSS 的动态 import，保留 `main.ts` 静态引入（动态 import 会 FOUC）
- 抽样验证 12 类 Element Plus 组件在暗色下的实际观感：el-card / el-table / el-dialog / el-select / el-date-picker / el-tabs / el-form / el-input / el-button / el-tag / el-progress / el-descriptions
- **验收**：tokens.contract.test.ts 转绿；管理端仪表盘明/暗各 1 张截图；对比度满足 WCAG AA（正文 ≥4.5:1，大字/非文本 ≥3:1）
- **门禁**：`useTheme.test.ts`（12 用例，切换逻辑不动）、`styles.test.ts`、`i18n.test.ts`
- **回滚**：`git revert <sha>`

### UI-B2 版式规范与仪表盘栅格
**目标**：解决"大卡空、密排挤"。

- 出 A/B 两版样张（纯 CSS 改动，不引依赖）：A 四卡等宽一行；B Hero 保留大卡但与副卡组同高 → **已选 B（2026-11-01）**
- `StatCardsSection.vue:114-119` 栅格与 `:121-125` 副指标网格按选定方案重排；`:210-228` 响应式断点同步
- `AdminDashboard.vue:142-146` 底部栅格（1.85fr 1fr）与 `:149-153` 响应式同步
- 卡片统一：圆角、描边、内边距、标题字重/字阶
- 侧边栏分组标题独立样式（`SidebarMenu.vue:59-68`），折叠态分隔线（`:70-75`）对齐
- **实施结果**：统计区 `minmax(0,1.4fr) / repeat(3,minmax(0,1fr))`；底部 `minmax(0,1.85fr) / minmax(0,1fr)`；卡片统一 `--surface-1` + `--card-border` + `--radius-lg` + `--spacing-lg` + `--shadow-light`，hover 用 `--shadow-card-hover`；标题字阶 `--font-size-medium` / `--font-weight-semibold`
- **验证中修掉的两个真实缺陷**：① 侧栏分组标题用 `el-menu-item disabled`，Element Plus 强制 `opacity: .25` 且首个分组因 index 命中当前路由而吸附激活色；改为纯展示 `<li>`，对比度 6.01:1（浅）/ 7.42:1（深）。② 侧栏被菜单内容撑到 1080px，页脚盖住末尾导航项；改为 `sticky + 100dvh`，菜单区 `min-height:0` 可滚动并预留 72px 页脚高度
- **验收**：仪表盘明/暗各 2 张截图（A/B 样张 + 定稿）；顶栏/侧栏/内容区三处高度与间距对齐
- **门禁**：`p1-15-stats-cards.test.ts`（9 个统计卡组件断言）、`AdminDashboard.test.ts`
- **回滚**：`git revert <sha>`

### UI-B3 图标系统
**目标**：图标从"能用"到"精致"。

- 新增 `frontend/src/components/common/AppIcon.vue`：封装 `@iconify/vue` 的 `Icon`，统一 size/色 token 用法
- 替换顺序（按感知强度）：`LayoutHeader.vue`(7 处) → `SidebarMenu.vue` → 管理端 4 个 dashboard 组件 → `HelpCenter.vue`(9) → `CounselorDashboard.vue`(11) → `RiskReportTab.vue`(6) → `ThemeSwitcher.vue`(5)
- Element Plus 组件内部图标（select 箭头、dialog 关闭）保持不动
- 现有 13 处内联 SVG：保留品牌与插画类（`AuthBrandPanel.vue`、`SidebarMenu.vue`、5 个 `illustrations/*`），其余按语义迁到 Iconify
- **实施结果**：不引入完整 Tabler 集合（完整集合约 350KB gzip，远超预算），改为 `frontend/scripts/gen-tabler-subset.mjs` 从 `@iconify-json/tabler` 生成 30 图标静态子集（`src/icons/tabler-subset.ts`），`AppIcon.vue` 运行时 `addCollection`，短名自动补 `tabler:` 前缀；图标 chunk 7.9KB raw / 2.1KB gzip
- **实际替换范围**：`LayoutHeader`(7) / `SidebarMenu`(菜单图标 + 折叠按钮) / `useLayoutMenu`(图标名改字符串) / `StatCardsSection`(趋势箭头) / `HelpCenter`(9) / `ThemeSwitcher`(5) / `CounselorDashboard`(11) / `RiskReportTab`(6)；管理端其余 dashboard 组件与 Element Plus 内置图标不动
- **验收**：管理端 12 页 + 咨询师/用户仪表盘明暗各 1 张截图；图标尺寸探针：头部小按钮 12px、普通按钮 14px、侧栏 18px；build 体积增量在 §7.1
- **门禁**：`eslint`、`typecheck`、全量 `vitest`；新增 `AppIcon.test.ts`（短名/全名与 aria-hidden）
- **回滚**：`git revert <sha>`（依赖在 package.json 同一提交内）

### UI-B4 图表统一
**目标**：图表与页面同一套 token，取代两套色板。

- 引入 `vue-echarts@8.3.2`；保留 `frontend/src/utils/echarts.ts` 的按需注册结构不动（`perf-p2-bundle.test.ts:29-32,46-59` 直接读该文件源码断言）
- `frontend/src/components/charts/BaseChart.vue` 从手写 `echarts.init` 迁到 `<v-chart>`，保留 resize/dispose/tooltip formatter 行为
- 逐步迁移：`ModelPerformanceChart` / `RiskTrendChart` / `SystemHealthChart` → `views/user/components/experiment-charts/*`(4 个)
- 图表配色改为读 `--chart-color-*`（`utils/chartTheme.ts:14-18,40-54` 已有读取逻辑），暗色覆盖在 B1 已补齐；`utils/chartPalette.ts` 静态色板降级为兜底
- **实施结果**：`BaseChart.vue` 改为 `<VChart v-if="active && hostReady">`，宿主测量到非零尺寸后才挂载（避免 0 尺寸 init 警告；测试模式直接挂载）；keep-alive 停用时卸载、激活时重挂，`updateOptions: { notMerge: true }` 保持旧的整份替换语义；`theme` 支持传入 ECharts 主题对象，默认由 `chartEchartsTheme()` 按令牌生成；`aria`/键盘高亮/`defineExpose` 导出 API 全部保留
- **色板同源**：`chartTheme.ts` 新增 `chartSeriesColors()`（primary/success/warning/danger/info/primaryLight）、`chartEchartsTheme()`（axis/legend/tooltip 文本色）与 `useChartColors()`/`useChartSeriesColors()`；`MutationObserver` 监听 `html.class` 自增版本号，暗色切换时 canvas 重绘。`chartPalette.ts` 只作 CSS 变量缺失时的兜底
- **实际迁移范围**：管理端 `AdminMonitoringPage`（成功率折线）、用户端 `UserReportsPage`（趋势折线 + 因子环形图）、`ExperimentTab` 四图（Loss/Accuracy/Compare/Confusion）、user-dashboard `RiskTrendChart`；未被任何视图引用的 `ModelPerformanceChart` / `SystemHealthChart` / `charts/RiskTrendChart` 一并迁移，避免两套写法并存。同时删除实验图表中的静态色 `#d4923a`、环形图硬编码白描边与重复色板常量
- **验证说明**：jsdom 无 canvas，`BaseChart.test.ts` 与 `ExperimentTab.test.ts` 用 `vue-echarts` 桩验证 props/事件/生命周期；真实渲染由 Playwright 路由注入成功率、报告/趋势、对比结果后采集明暗截图，确认坐标轴文本、折线与柱色随主题切换
- **验收**：3 个页面（系统监控 / 评估报告 / 模型评估对比）× 明暗共 6 张截图；图表色板与页面主色同源
- **门禁**：`perf-p2-bundle.test.ts`、`components/charts/charts.test.ts`、`useECharts.test.ts`、`views/user/UserRiskPage.report.test.ts`；全量 `vitest`、`typecheck`、`build`
- **回滚**：`git revert <sha>`（依赖在 package.json 同一提交内）

### UI-B5 动效
**目标**：列表与卡片的增删有连续性。

- 引入 `@formkit/auto-animate@0.10.0`；封装 `frontend/src/directives/autoAnimate.ts`
- 与既有 `styles/transitions.scss`（375 行 Vue transition 库）划界：**既有 transition 保留**，auto-animate 只用于 v-for 列表增删、Tab 切换、弹层进出
- 尊重 `prefers-reduced-motion`（须在 directive 内显式关闭）
- **验收**：列表增删、Tab 切换无闪烁；reduced-motion 下无动画
- **门禁**：全量 `vitest`、`eslint`
- **回滚**：`git revert <sha>`

### UI-B6 全端铺开
**目标**：把 B1–B5 的规范套到 user（10 页）与 counselor（7 页）端。

- 顺序：公共组件（`components/common/` 24 个）→ user dashboard 7 个子组件 → user 业务页 → counselor 页
- 不做页面结构重写，只套 token / 卡片规范 / 图标 / 图表
- **验收**：user 与 counselor 主路径页面明/暗截图；`e2e/alignment-smoke.spec.ts` 与 13 个 Playwright spec 全绿
- **回滚**：`git revert <sha>`

### UI-B7 收口
- `tokens.contract.test.ts` 扩到全量 token（暗浅两套）
- 加一条对比度回归脚本（WCAG AA，对 `--text-*` 与 `--surface-*` 组合）
- 清理生产代码硬编码 hex：优先 `chartPalette.ts`、`AuthBrandPanel.vue`、`RiskReportTab.vue`、`sharedChartUtils.ts`、`chartTheme.ts`（合计约 43 处），其余登记台账不强制
- 截图基线对比：改造前 vs 改造后并排存档到 `outputs/ui-refresh/final/`
- 文档：`frontend/src/styles/README.md`（若不存在则新建）写明"新增组件该用哪些 token"的规约
- **验收**：`lint` / `typecheck` / `vitest` / `build` / `e2e` 全绿；契约与对比度测试通过

## 5. 每批通用验证清单

```bash
cd frontend
npm run lint
npm run typecheck            # 或 npm run typecheck:baseline 与基线对比
npx vitest run               # 全量，记录用例数与通过数
npm run build                # 记录产物体积与 chunk 变化
npx playwright test          # 涉及交互的批次必跑
```

外加：浏览器手动截图（明/暗 × 1440×900）存档，并对照上一批截图。

## 6. 已知门禁与雷区

| 风险点 | 位置 | 处置 |
|---|---|---|
| 样式测试是假的（硬编码注入变量） | `src/test-setup.ts:26-31`、`src/styles/styles.test.ts` | UI-B0 先修，否则后续 token 改动无人守门 |
| 暗色切换逻辑有 12 个用例 | `src/composables/useTheme.test.ts` | 全部批次**不改** `useTheme.ts` 的切换语义 |
| 图表按需引入被源码断言 | `src/config/perf-p2-bundle.test.ts:29-59` | UI-B4 保留 `utils/echarts.ts` 现有结构，只在组件层迁移 |
| 覆盖率阈值 50%/40% | `frontend/vitest.config.ts:36-41` | 新增组件需带测试，避免掉线 |
| Element Plus 暗色覆盖不全 | `theme.scss:105-167` | UI-B1 抽样 12 类组件逐个看图 |
| Element Plus 禁用态强制 `opacity: .25` | `el-menu-item.is-disabled` 等 | 需要可读文字时不要复用 `disabled`，改用纯展示元素（UI-B2 侧栏分组标题已按此修正） |
| 暗色 CSS 被加载两次 | `main.ts:24` 静态 + `useTheme.ts:42` 动态 | UI-B1 顺带收敛为一处 |
| 硬编码 hex 430 处 | `frontend/src` 全量 | UI-B7 清理 43 处生产代码，其余登记不强制 |
| Iconify 完整集合超体积预算 | `@iconify-json/tabler` | 只登记用到的图标，跑 `scripts/gen-tabler-subset.mjs` 重新生成子集（UI-B3 已按此落地） |

## 7. 进度表（执行时逐行填写）

| 批次 | 提交 SHA | 验证读数（vitest/build/e2e） | 截图目录 | 状态 |
|---|---|---|---|---|
| UI-B0 | `4b50a47` | vitest 113 文件 / 1367 通过 / 4 跳过；基线读数在 §7.1 | `outputs/ui-refresh/B0-baseline/`（12 张，gitignored） | 已完成 |
| UI-B1 | `d69479c` | vitest 114 文件 / 1445 通过 / 4 跳过；typecheck 0；build 0；契约 78 用例全绿 | `outputs/ui-refresh/B1-dark-surfaces/`（主页面 12 张 + EP 组件 7 张） | 已完成 |
| UI-B2 | `0feeb11` + `be79425` | vitest 114 文件 / 1445 通过 / 4 跳过；typecheck 0；build 0；lint 0；栅格/对比度探针见 §7.1 | `outputs/ui-refresh/B2-ab/`（A/B 样张 4 张）+ `B2-hero-grid/`（12 张） | 已完成 |
| UI-B3 | `13a83f0` | vitest 115 文件 / 1447 通过 / 4 跳过；typecheck 0；build 0；lint 0；图标 chunk 2.1KB gzip | `outputs/ui-refresh/B3-icons/`（12 张）+ `B3-icons/roles/`（4 张） | 已完成 |
| UI-B4 | `94673a8` | vitest 115 文件 / 1449 通过 / 4 跳过；typecheck 0；build 0；lint 0；charts chunk 698.30KB | `outputs/ui-refresh/B4-charts/`（6 张，gitignored） | 已完成 |
| UI-B5 | | | | 待开始 |
| UI-B6 | | | | 待开始 |
| UI-B7 | | | | 待开始 |

### 7.1 读数明细

| 批次 | 命令 | 读数 |
|---|---|---|
| B0 基线 | `npx vitest run --silent` | 113 文件 / 1367 通过 / 4 跳过 / 1371，65.03s |
| B1 回归 | `npx vitest run --silent` | 114 文件 / 1445 通过 / 4 跳过 / 1449，47.30s |
| B1 类型 | `npm run typecheck` | exit 0 |
| B1 构建 | `npm run build` | exit 0 |
| B1 样式契约 | `npx vitest run src/styles/tokens.contract.test.ts` | 78/78 通过（37 覆盖 + 33 明暗分叉 + 8 层级/对比度） |
| B2 回归 | `npx vitest run` | 114 文件 / 1445 通过 / 4 跳过 / 1449，52.03s |
| B2 类型 | `npm run typecheck` | exit 0 |
| B2 构建 | `npm run build` | exit 0（19.61s，PWA precache 148 项） |
| B2 布局探针 | Playwright 1440×900 | 四卡同排 y=195 / h=194；Hero 405px、副卡 234px×3；底部 750/406；overflowX 0；aside 900px；菜单 scrollH 1087 > clientH 843；滚到底部最后一项 bottom 826 < 页脚 top 835 |
| B2 对比度 | 相对亮度计算 | 侧栏分组标题 6.01:1（浅 #5a6470/白）/ 7.42:1（深 #a0a8b4/#131820） |
| B3 回归 | `npx vitest run` | 115 文件 / 1447 通过 / 4 跳过 / 1451，53.64s |
| B3 类型 | `npm run typecheck` | exit 0 |
| B3 构建 | `npm run build` | exit 0（20.20s，PWA precache 150 项 / 9265.81 KiB；B2 为 148 项 / 9250.72 KiB） |
| B3 图标体积 | 产物统计 | `dist/assets/AppIcon-*.js` 7,912B raw / 2,114B gzip；完整 Tabler 集合约 350KB gzip，故采用 30 图标子集 |
| B3 尺寸探针 | Playwright 1440×900 | 头部小按钮 12px、普通按钮 14px、侧栏菜单 18px；`aria-hidden="true"` 正常 |
| B4 回归 | `npx vitest run` | 115 文件 / 1449 通过 / 4 跳过 / 1453，58.56s（B3 为 1447） |
| B4 图表定向 | `npx vitest run src/components/charts src/composables/useECharts*` | 57/57 通过（BaseChart 7、charts 28、useECharts 22） |
| B4 类型 | `npm run typecheck` | exit 0 |
| B4 构建 | `npm run build` | exit 0（18.80s，PWA precache 151 项 / 9281.12 KiB；B3 为 150 项 / 9265.81 KiB；charts chunk 698.30KB） |
| B4 渲染验证 | Playwright 1440×900 | 系统监控成功率折线、评估报告趋势折线 + 因子环形图、模型评估对比柱 × 明暗 6 张；暗色下轴文本/图例/描边随令牌切换，无 canvas 0 尺寸告警 |

B1 暗色抽检覆盖：el-card、el-table、el-dialog、el-select、el-date-picker、el-tabs、el-form、el-input、el-button、el-tag、el-progress、el-descriptions。抽检截图在 `outputs/ui-refresh/B1-dark-surfaces/ep/`；报告页任务列表原本为空，`el-progress` 用 Playwright 路由注入一条 42% 的进行中任务后采集。

## 8. 已确认项

UI-B2 仪表盘栅格采用**方案 B（Hero 保留大卡，与三张副卡同排同高）**，已于 2026-11-01 确认并落地。当前无待确认的开放项。
