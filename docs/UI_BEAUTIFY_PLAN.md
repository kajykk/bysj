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
- 与既有 `styles/transitions.scss`（375 行 Vue transition 库）划界：**既有 transition 保留**；auto-animate 只负责「同一容器内子节点增删/移动」，Element Plus 弹层/页签的进出过渡仍由组件自身接管（避免重复动画）
- 尊重 `prefers-reduced-motion`（须在 directive 内显式关闭）
- **实施结果**：指令在挂载时创建控制器并读取 `matchMedia('(prefers-reduced-motion: reduce)')`；命中减动效或绑定 `false` 即 `controller.disable()`，并监听媒体查询变化实时启停；`duration/easing` 只在挂载时生效（auto-animate 无更新配置 API，重建会叠加 observer）；无 Web Animations API 的环境（jsdom/老浏览器）直接不挂 observer
- **实际接入范围**：`TaskProgressNotification` 任务栈（220ms）、`AdminSilencesPage` 生效静默标签（180ms）、`AdminAuditLogsPage` 分类标签（180ms）。三处均为「容器先存在、子项后续增删」的真实动态列表；首屏整块进出继续由既有 Vue `Transition` 负责
- **验证**：浏览器内点击「关闭」移除一条任务，正常模式下 `.task-progress-item` 检测到 WAAPI 动画；`page.emulateMedia({ reducedMotion: 'reduce' })` 下同一动作动画数为 0
- **验收**：列表增删、Tab 切换无闪烁；reduced-motion 下无动画
- **门禁**：全量 `vitest`、`eslint`、`typecheck`、`build`；新增 `autoAnimate.test.ts`（7 例：参数过滤/disabled 切换/减动效启停/布尔绑定/绕过防护/卸载清理/无 WAAPI 兜底）
- **回滚**：`git revert <sha>`（依赖在 package.json 同一提交内）

### UI-B6 全端铺开
**目标**：把 B1–B5 的规范套到 user（10 页）与 counselor（7 页）端。

- 顺序：公共组件（`components/common/` 24 个）→ user dashboard 7 个子组件 → user 业务页 → counselor 页
- 不做页面结构重写，只套 token / 卡片规范 / 图标 / 图表
- **实施结果（令牌缺口）**：暗色补 `--risk-none/mild/moderate/high/critical`（浅色深值在暗底不可读，`--risk-critical` 此前完全无暗色覆盖）、`--text-on-accent`（渐变卡文字不随 `--text-inverse` 反转）、`--success/warning/info-strong`（语义色底正文）；`tokens.contract.test.ts` 的 REQUIRED/MUST_DIVERGE 扩到 97 例，并新增「语义底上正文 ≥4.5:1」断言
- **色值归 token**：清理 user/counselor/公共组件中带主题风险的硬编码色（`RiskReportTab`、`StructuredResultPanel`、`UserRiskPage`、`TrainingSidePanel`、`TrainingStatsRow`、`ExperimentTab`/`PhysioTab`/结构化步骤、咨询师统计卡 `#b5384a`→`--risk-critical`、`ErrorCell`/`TrendArrow`）；保留 `readChartVar` 兜底 hex、咨询师 `color_tag` 数据默认值与 `AuthBrandPanel` 固定深色品牌面板（后者留 B7）
- **卡片规范**：user dashboard 7 张卡由 `--bg-primary`/`--border-extra-light`/`1.25rem`/私有阴影改为 `--surface-1`/`--card-border`/`--radius-xl`/`--shadow-card(-hover)`；训练卡 16/18px 圆角与报告摘要卡统一到 `--radius-lg/xl`
- **图标**：Tabler 子集新增 `info-circle`、`upload`（32 图标）；`RiskStatusCard` 趋势箭头、`UserRiskPage` 危机热线、`BindingCard` 提示、`FileUploadCard` 上传区由 Element 图标迁到 `AppIcon`
- **e2e 适配**：`seed.spec.ts` 后端地址支持 `E2E_BACKEND_URL`（CI 仍默认 8000）；本机 8000 被其他服务占用时用 8001 覆盖
- **验证**：lint 0 error；typecheck 0；vitest 116 文件 / 1475 通过 / 4 跳过；build 16.51s，precache 152 项 / 9291.11 KiB；Playwright 13 spec / 32 用例，`--workers=1` 下 27 通过 / 5 跳过 / 0 失败（本地默认并发会因多个 spec 共用种子账号触发 refresh token 轮换竞争，CI 本身固定 workers=1）
- **遗留（B7）**：训练页三张渐变卡仍为白字，`--gradient-gold` 上对比度不足 4.5:1，B7 对比度回归时一并处理；`AuthBrandPanel` 固定品牌色与 `chartPalette` 兜底 hex 留 B7 清理
- **验收**：user 与 counselor 主路径页面明/暗截图；`e2e/alignment-smoke.spec.ts` 与 13 个 Playwright spec 全绿
- **回滚**：`git revert <sha>`

### UI-B7 收口
- `tokens.contract.test.ts` 扩到全量 token（暗浅两套）
- 加一条对比度回归脚本（WCAG AA，对 `--text-*` 与 `--surface-*` 组合）
- 清理生产代码硬编码 hex：优先 `chartPalette.ts`、`AuthBrandPanel.vue`、`RiskReportTab.vue`、`sharedChartUtils.ts`、`chartTheme.ts`（合计约 43 处），其余登记台账不强制
- 截图基线对比：改造前 vs 改造后并排存档到 `outputs/ui-refresh/final/`
- 文档：`frontend/src/styles/README.md`（若不存在则新建）写明"新增组件该用哪些 token"的规约
- **实施结果（契约，127 例）**：重写为全量口径——解析 `variables.scss` / `theme.scss` 的 `:root` 与 `html.dark`，建立「浅色全集 / 暗色覆盖 / 生效暗色」三张表；浅色每个令牌必须有暗色落点或显式主题无关豁免（前缀 + 精确名单，失效豁免会被抓出）；暗色不得出现浅色未定义的孤儿；Element Plus `--el-*` 明暗全量对齐；暗色不得原样复制浅色（`var()` 间接引用登记到 `SAME_VALUE_ALLOWED`）；原有 REQUIRED / MUST_DIVERGE 保留并把 `--text-on-accent` 纳入
- **对比度回归**：正文三级（primary / regular / secondary）× 四个表面（surface-1/2/3 + bg-page）≥4.5:1；表面层级亮度严格递减；强调底文字 × 渐变两端 ≥4.5:1；语义浅底 × `*-strong` ≥4.5:1；图表色 × 背景 ≥3:1；`chartPalette.ts` 静态镜像与浅色令牌逐项一致
- **强调底文字修正**：新增 `--text-on-accent`（浅色白字 / 暗色 `#0b0f14`）与 `--text-on-light-accent`（两套主题固定 `#0b0f14`）。暗色品牌蓝渐变原来的白字只有 3.0:1，改深墨后最差 4.74:1；浅色蓝渐变白字最差 4.62:1；绿 / 金渐变两套主题共用深墨，最差 5.84 / 7.30:1。训练页三张统计卡、侧栏徽标、风险报告建议序号改用新令牌
- **hex 收口**：`AuthBrandPanel` 的 8 个固定品牌色收敛到 `--brand-panel-*`（登录面板始终深色，登记为主题无关令牌）；`chartTheme`、`reportTrendOption`、`RiskTrendChart`、`UserReportsPage` 的分散兜底色统一到 `chartPalette.STATIC_FALLBACK_COLORS`（唯一允许的静态镜像）；路由进度条 `#409eff` → `--primary-color`；`riskFormatters` 色板注释声明为 `--risk-*` 的 el-tag 背景镜像。优先文件 `RiskReportTab.vue`、`sharedChartUtils.ts` 检查时已无 hex。生产代码 6 位 hex 53 → 31，全部登记 README 台账
- **文档**：新增 `frontend/src/styles/README.md`——加载顺序、表面 / 文字 / 语义 / 强调底 / 图表 / 间距选色速查、新增令牌四条规矩、31 处存量 hex 台账、契约覆盖范围
- **验证**：契约 127/127；全量 vitest 116 文件 / 1505 通过 / 4 跳过 / 1509，49.16s（B6 为 1475）；typecheck 0；lint 0 error；build 17.84s，precache 152 项 / 9291.65 KiB（B6 为 9291.11 KiB）；Playwright 13 spec / 43 用例（3 个 project），`--workers=1` 下 36 通过 / 7 跳过 / 0 失败，1.5m
- **截图存档**：`outputs/ui-refresh/final/`——14 个主路径页面（admin 6 + user 5 + counselor 3）× 明暗 28 张 fullPage；before 取自 B0 基线（admin）与 B6 铺开（user / counselor），生成 28 组并排对照（`pairs/*-before-after.png` + 28 个查看页）；`manifest.json` 记录每张生效令牌，训练卡探针证明浅色蓝卡白字、绿 / 金卡深墨，暗色三卡均深墨
- **遗留**：Element Plus 内置实色按钮（`type="success" / "warning" / "info"`）仍为白字，对当前 `#5a9e3a` / `#d4923a` / `#909399` 仅 3.29 / 2.63 / 3.08:1，暗色更差（2.45 / 2.13:1）；属组件库默认样式，统一改文字色会改全站按钮观感，另开专项处理，不在本批夹带
- **验收**：`lint` / `typecheck` / `vitest` / `build` / `e2e` 全绿；契约与对比度测试通过
- **回滚**：`git revert cd890c4`

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
| 硬编码 hex 430 处 | `frontend/src` 全量 | UI-B7 后生产代码剩 31 处，已登记 `src/styles/README.md` 台账；新增硬编码色必须说明类别 |
| Element Plus 实色按钮白字 | `el-button type="success"/"warning"/"info"` | 组件库默认白字对当前令牌仅 2.13–3.29:1，低于 AA；B7 已记录，另开专项统一处理 |
| Iconify 完整集合超体积预算 | `@iconify-json/tabler` | 只登记用到的图标，跑 `scripts/gen-tabler-subset.mjs` 重新生成子集（UI-B3 已按此落地） |

## 7. 进度表（执行时逐行填写）

| 批次 | 提交 SHA | 验证读数（vitest/build/e2e） | 截图目录 | 状态 |
|---|---|---|---|---|
| UI-B0 | `4b50a47` | vitest 113 文件 / 1367 通过 / 4 跳过；基线读数在 §7.1 | `outputs/ui-refresh/B0-baseline/`（12 张，gitignored） | 已完成 |
| UI-B1 | `d69479c` | vitest 114 文件 / 1445 通过 / 4 跳过；typecheck 0；build 0；契约 78 用例全绿 | `outputs/ui-refresh/B1-dark-surfaces/`（主页面 12 张 + EP 组件 7 张） | 已完成 |
| UI-B2 | `0feeb11` + `be79425` | vitest 114 文件 / 1445 通过 / 4 跳过；typecheck 0；build 0；lint 0；栅格/对比度探针见 §7.1 | `outputs/ui-refresh/B2-ab/`（A/B 样张 4 张）+ `B2-hero-grid/`（12 张） | 已完成 |
| UI-B3 | `13a83f0` | vitest 115 文件 / 1447 通过 / 4 跳过；typecheck 0；build 0；lint 0；图标 chunk 2.1KB gzip | `outputs/ui-refresh/B3-icons/`（12 张）+ `B3-icons/roles/`（4 张） | 已完成 |
| UI-B4 | `94673a8` | vitest 115 文件 / 1449 通过 / 4 跳过；typecheck 0；build 0；lint 0；charts chunk 698.30KB | `outputs/ui-refresh/B4-charts/`（6 张，gitignored） | 已完成 |
| UI-B5 | `4dc11d7` | vitest 116 文件 / 1456 通过 / 4 跳过；typecheck 0；build 0；lint 0；precache 152 项 / 9290.78 KiB | `outputs/ui-refresh/B5-motion/`（4 张，gitignored） | 已完成 |
| UI-B6 | `e5a5d30` | vitest 116 文件 / 1475 通过 / 4 跳过；typecheck 0；build 0；lint 0；e2e 27 通过 / 5 跳过 / 0 失败（workers=1）；precache 152 项 / 9291.11 KiB | `outputs/ui-refresh/B6-rollout/`（16 张：user 5 页 + counselor 3 页 × 明暗，gitignored） | 已完成 |
| UI-B7 | `cd890c4` | vitest 116 文件 / 1505 通过 / 4 跳过；typecheck 0；build 0；lint 0；e2e 36 通过 / 7 跳过 / 0 失败（workers=1）；契约 127/127；precache 152 项 / 9291.65 KiB | `outputs/ui-refresh/final/`（14 页 × 明暗 28 张 + 28 组并排 before/after，gitignored） | 已完成 |

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
| B5 回归 | `npx vitest run` | 116 文件 / 1456 通过 / 4 跳过 / 1460，42.18s（B4 为 1449） |
| B5 类型 | `npm run typecheck` | exit 0 |
| B5 构建 | `npm run build` | exit 0（16.97s，PWA precache 152 项 / 9290.78 KiB；B4 为 151 项 / 9281.12 KiB；新增 auto-animate 单文件 8,406B raw） |
| B5 动效验证 | Playwright 1440×900 | 移除任务：正常模式 `.task-progress-item` 动画数 >0；`reducedMotion: reduce` 下同动作动画数 = 0；静默标签明暗渲染正常 |
| B6 样式契约 | `npx vitest run src/styles/tokens.contract.test.ts` | 97/97 通过（新增 5 级风险色、on-accent、3 个语义强色与语义底对比度） |
| B6 回归 | `npx vitest run` | 116 文件 / 1475 通过 / 4 跳过 / 1479，47.43s（B5 为 1456） |
| B6 类型 | `npm run typecheck` | exit 0 |
| B6 构建 | `npm run build` | exit 0（16.51s，PWA precache 152 项 / 9291.11 KiB；B5 为 9290.78 KiB；charts chunk 698.30KB 不变） |
| B6 e2e | `npx playwright test --project=chromium --workers=1` | 13 spec / 32 用例：27 通过 / 5 跳过 / 0 失败，1.1m；默认并发下 `key-flows` token 刷新用例会与同账号其他 spec 竞争，串行（CI 口径）稳定全绿 |
| B6 明暗截图 | 临时 Playwright 脚本（采集后删除） | user dashboard/risk/reports/intervention/model-training + counselor dashboard/warnings/users × 明暗 16 张；暗色侧栏底部白块经视口截图与 `elementsFromPoint` 排除，确认为 fullPage 对 sticky 侧栏的拼接伪影 |
| B7 样式契约 | `npx vitest run src/styles/tokens.contract.test.ts` | 127/127 通过（全量明暗覆盖、暗色孤儿、豁免失效、EP 对齐、明暗分歧、文字 × 表面、强调底 × 渐变、语义浅底、图表 3:1、静态镜像） |
| B7 回归 | `npx vitest run` | 116 文件 / 1505 通过 / 4 跳过 / 1509，49.16s（B6 为 1475，+30） |
| B7 类型 | `npm run typecheck` | exit 0 |
| B7 构建 | `npm run build` | exit 0（17.84s，PWA precache 152 项 / 9291.65 KiB；B6 为 9291.11 KiB） |
| B7 lint | `npm run lint` | 0 error（仅存量 warning；顺带清掉 3 个未使用导入） |
| B7 e2e | `npx playwright test --workers=1` | 13 spec / 43 用例（chromium + smoke + regression）：36 通过 / 7 跳过 / 0 失败，1.5m |
| B7 对比度探针 | Playwright computed style + 相对亮度计算 | 训练卡文字：浅色蓝白字 5.31–4.62:1、绿 5.84–7.85:1、金 7.30–10.10:1；暗色蓝深墨 6.36–4.74:1、绿 7.84–5.84:1、金 9.02–7.30:1 |
| B7 明暗截图 | 临时 Playwright 脚本 | 14 路由 × 明暗 28 张 fullPage；`manifest.json` 记录生效令牌；`pairs/` 28 组并排对照由 B0（admin）与 B6（user/counselor）before + B7 after 合成 |

B1 暗色抽检覆盖：el-card、el-table、el-dialog、el-select、el-date-picker、el-tabs、el-form、el-input、el-button、el-tag、el-progress、el-descriptions。抽检截图在 `outputs/ui-refresh/B1-dark-surfaces/ep/`；报告页任务列表原本为空，`el-progress` 用 Playwright 路由注入一条 42% 的进行中任务后采集。

## 8. 已确认项

UI-B2 仪表盘栅格采用**方案 B（Hero 保留大卡，与三张副卡同排同高）**，已于 2026-11-01 确认并落地。当前无待确认的开放项。
