# 样式令牌使用规约

本目录是前端颜色的唯一入口。组件里不要再写 hex / rgb 硬编码；
需要新颜色时先加令牌，再在组件里 `var(--token)` 引用。

## 1. 文件与加载顺序

| 顺序 | 文件 | 职责 |
|---|---|---|
| 1 | `variables.scss` | 浅色默认值 + 主题无关令牌（间距/圆角/字体/动效/品牌面板） |
| 2 | `theme.scss` | 浅色 `:root` 覆盖 + `html.dark` 全套暗色覆盖 + Element Plus 映射 |
| 3 | `mixins.scss` / `utilities.scss` / `transitions.scss` | 工具类与动效 |

`main.ts` 按上表顺序加载，同名令牌后加载者生效。
`tokens.contract.test.ts` 按同一顺序解析源码，保证测试口径与浏览器一致。

## 2. 组件选色速查

### 表面与文字

| 场景 | 令牌 |
|---|---|
| 页面底色 | `--bg-page` |
| 一级卡片 / 面板 | `--surface-1` + `--card-border` + `--shadow-card` |
| 大卡片圆角 / 小卡片圆角 | `--radius-xl` / `--radius-lg` |
| 卡内次级块 | `--surface-2` |
| 悬浮 / 选中块 | `--surface-3` / `--bg-hover` |
| 标题 | `--text-primary` |
| 正文 | `--text-regular` |
| 辅助说明 | `--text-secondary` |
| 占位 / 禁用 | `--text-placeholder` / `--text-disabled` |
| 边框 | `--border-color` / `--border-light` |

正文（`--text-primary` / `--text-regular` / `--text-secondary`）在
`--surface-1` / `--surface-2` / `--surface-3` / `--bg-page` 上必须 ≥ 4.5:1，
契约测试逐组合断言。

### 语义色与风险色

| 场景 | 令牌 |
|---|---|
| 品牌 / 成功 / 警告 / 危险 / 信息 | `--primary-color` / `--success-color` / `--warning-color` / `--danger-color` / `--info-color` |
| 对应的浅色底 | `--success-light` / `--warning-light` / `--danger-light` / `--info-light` |
| 浅色底上的正文 | `--success-strong` / `--warning-strong` / `--info-strong` |
| 风险等级 | `--risk-none` / `--risk-mild` / `--risk-moderate` / `--risk-high` / `--risk-critical` |

语义浅底上不要直接用 `--success-color` 当正文色——它在浅底上达不到 4.5:1；
用对应的 `*-strong`。

### 强调底上的文字

| 底 | 文字令牌 |
|---|---|
| 品牌蓝渐变 / 实色（`--gradient-primary`、`--primary-color`） | `--text-on-accent`（跟随主题：浅色白字、暗色深墨） |
| 绿 / 金渐变（`--gradient-green`、`--gradient-gold`） | `--text-on-light-accent`（两套主题固定深墨） |
| 登录品牌面板（始终深色） | `--brand-panel-text` / `--brand-panel-text-muted` / `--brand-panel-text-dim` |

暗色主题的品牌蓝被提亮成浅蓝，白字只有 3.0:1，所以 `--text-on-accent`
在暗色下是深墨色。不要假设它永远是白色；如果底色始终是深色，
应使用固定深底专用的令牌，而不是 `--text-on-accent`。

### 图表

ECharts canvas 读不了 CSS 变量，图表颜色统一走：

- `chartColors()` / `useChartColors()` / `useChartSeriesColors()`
- `chartEchartsTheme()`
- 静态兜底只允许放在 `src/utils/chartPalette.ts`

`chartPalette.ts` 的静态值是对浅色令牌的镜像，`tokens.contract.test.ts`
会逐项比对，令牌改了而镜像没改会直接红。

### 间距、圆角、字体、动效

| 场景 | 令牌 |
|---|---|
| 间距 | `--spacing-xs` / `--spacing-sm` / `--spacing-md` / `--spacing-lg` / `--spacing-xl` / `--spacing-2xl` |
| 圆角 | `--radius-sm` / `--radius-md` / `--radius-lg` / `--radius-xl` |
| 字号 | `--font-size-micro` → `--font-size-stat` |
| 阴影 | `--shadow-card` / `--shadow-card-hover` |
| 动效 | `--transition-fast` / `--transition-duration` / `--duration-*` / `--ease-*` |

## 3. 新增 / 修改令牌的规矩

1. **浅色**写入 `variables.scss` 或 `theme.scss` 的 `:root`。
2. **暗色**写入 `theme.scss` 的 `html.dark`，且值不得原样复制浅色；
   确需相同文本值时，只能是对 `var()` 的间接引用并登记到契约测试的
   `SAME_VALUE_ALLOWED`。
3. **主题无关**的令牌（间距/圆角/字体/动效/固定品牌面板）不用在暗色重复，
   但要登记到 `tokens.contract.test.ts` 的 `THEME_INVARIANT_*` 并写明理由。
4. Element Plus 的 `--el-*` 令牌必须明暗两套齐全。
5. 文字/表面类令牌要同时补对比度断言；阈值：
   - 正文 / 辅助文字 ≥ 4.5:1
   - 强调底文字 ≥ 4.5:1
   - 图表色对背景 ≥ 3:1
6. 改完至少跑：

```bash
npx vitest run src/styles/tokens.contract.test.ts
npm run lint
npm run typecheck
```

## 4. 硬编码色台账（UI-B7 盘点）

生产代码（`src/**/*.{vue,ts}`，排除测试、图标子集、样式目录）中仍保留的
31 处 6 位 hex 全部登记如下。新增硬编码色必须先说明属于哪一类，
否则应改用令牌。

| 类别 | 文件 | 数量 | 原因 |
|---|---|---|---|
| 图表静态镜像 | `src/utils/chartPalette.ts` | 14 | canvas 无法解析 CSS 变量；镜像由契约测试守护 |
| 风险分数数据色板 | `src/utils/riskFormatters.ts` | 4 | 作为 el-tag 背景色使用，值与 `--risk-*` 对齐；改动需同步两张表 |
| 用户可编辑数据默认值 | `src/views/admin/components/admin-settings-page/ThresholdsTab.vue`、`src/views/counselor/CounselorUserDetailPage.vue` | 6 | 颜色选择器默认值，会提交给后端持久化，不能是 `var()` |
| 动态风险标签背景 | `src/views/admin/components/admin-crisis-events/CrisisEventsTable.vue`、`.../sharedCrisisEventsUtils.ts` | 2 | 背景由风险分数动态注入；白字/深字需随色板单独评估 |
| 角色头像装饰渐变 | `src/layouts/components/main-layout/LayoutHeader.vue` | 5 | 纯装饰性头像底色，文字为首字母；后续做头像对比度专项时收敛 |

另有两类**不计入台账**的写法：

- `var(--token, #fallback)` 的兜底值：令牌是唯一来源，兜底只防首屏变量未就绪；
  新代码建议直接用 `var(--token)`，由 `:root` 保证存在。
- SVG data URI、装饰性 `rgba()` 光晕/噪点：不是主题语义色，不参与明暗切换。

## 5. 契约测试覆盖范围

`src/styles/tokens.contract.test.ts` 当前覆盖：

- 浅色每个令牌都有暗色落点或主题无关豁免，豁免清单不得有失效条目
- 暗色不得出现浅色未定义的令牌
- Element Plus 令牌明暗齐全
- 暗色覆盖不得原样复制浅色值（登记的 `var()` 间接引用除外）
- 表面层级顺序、正文 × 表面、强调底文字 × 渐变、语义浅底 × `*-strong`、
  图表色 × 背景的全部对比度阈值
- `chartPalette.ts` 静态镜像与浅色令牌逐项一致
