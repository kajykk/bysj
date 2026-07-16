# ISS-03 前端首屏性能报告

> 阶段：WF-0 基线 / WF-1 快速修复 | 维度：性能/前端 | 优先级：P1
> 实测日期：2026-07-15 | 工具：Lighthouse 13.1.0（Microsoft Edge 150 chromium 作为 chrome-path）
> 目标：Lighthouse performance ≥ 90/100

## 1. 结论速览

| 指标 | 原始 KPI 基线 | 当前构建(重测) | 含 zrender 修复后 | 说明 |
|---|---|---|---|---|
| 移动端 perf | **53** | 79 | **83** | 原始 53 为**过期基线**（2026-07-11 旧构建） |
| 桌面端 perf | 未测 | 99 | **99** | 无节流，FCP/LCP 0.8s |
| FCP (移动) | 5.8s | 3.9s | 3.5s | 启动屏优化后大幅改善 |
| LCP (移动) | 6.8s | 3.9s | 3.5s | 同上 |
| TBT (移动) | 380ms | 0ms | 0ms | 启动屏解耦 JS 执行与首屏绘制 |
| CLS | 0 | 0 | 0 | 无布局偏移 |

**核心结论**：ISS-03 的 "perf 53" 问题**主体已被既有 P1-1 优化解决**（启动屏占位 + 移除 Google Fonts 外部 CDN）。当前真实分数为移动端 83 / 桌面端 99。本次额外实施一个安全的拆包修复（zrender 移出 vendor 入口 chunk），将移动端从 79 提升到 83。剩余 83→90 的差距是 CSR（客户端渲染）架构下首屏加载 Element Plus 核心 + form/utility chunk 的固有成本，需架构级改动（非-EP 登录页或 SSR）突破，归入 WF-2/WF-3。

## 2. 原始基线 53 是过期基线（关键发现）

`KPI-基线.json` 中的 `frontend_lighthouse_performance=53` 来自 `frontend/lighthouse-prod.json`（生成于 2026-07-11）。经核对，该报告引用的资源 hash 与**当前 dist 完全不同**：

| | 过期基线报告(lighthouse-prod.json) | 当前 dist |
|---|---|---|
| index 入口 | `index-BZFWLiHr.js` | `index-BFdb1NjB.js` |
| vendor | `vendor-Ckp1-zkt.js` | `vendor-BoGtVtiK.js` |
| element-plus | `element-plus-DUrtBqNi.js` | `element-plus-Dye7fB5v.js` |

当前 dist 的 `index.html` 已包含 P1-1 性能优化注释：
- **移除 Google Fonts 外部 CDN 依赖**（原 52KB 请求导致 FCP 5.8s）；
- **内联启动屏占位内容**（浏览器立即渲染，Vue 挂载后替换，提供可测量 LCP 元素）。

即基线 53 是在**这些优化生效之前**测得的。用**相同 Lighthouse 配置**（mobile / simulate 节流：rttMs 150、cpuSlowdownMultiplier 4）重测当前构建，得到 79——配置一致，对比有效。

## 3. 根因分析

### 3.1 为什么原 53 → 当前 79（FCP 5.8s → 3.9s）
- 原构建在 `<head>` 同步依赖 `fonts.googleapis.com` 外部字体请求，移动端慢速网络下阻塞首次绘制（FCP 5.8s）。
- 当前构建：① 移除外部字体（改用系统字体栈）；② 内联启动屏，HTML 解析完即绘制，JS 执行不再阻塞首屏。
- 结果：TBT 从 380ms 降至 0ms（首屏绘制与 JS 主线程工作解耦），FCP/LCP 同步降至 3.9s。

### 3.2 当前 79 的首屏资源构成（Lighthouse 实测）
登录首屏共加载约 **427.5 KiB gz JS**，最大几项：

| chunk | 传输体积 | 首屏未使用 | 说明 |
|---|---|---|---|
| element-plus | 79.4 KiB | 67.1 KiB (85%) | EP 核心，登录必用少量组件 |
| ep-form-advanced | 62.6 KiB | 54.2 KiB (87%) | Select/DatePicker 等，登录语言选择器拉入 |
| ep-utility | 59.7 KiB | 50.0 KiB (84%) | Tooltip/Menu 等 |
| vendor | 114.7 KiB | **93.8 KiB (82%)** | 含 **zrender**（echarts 渲染器）等图表代码 |
| vue-core / index / i18n / router / http / state / icons | ~50 KiB | 少量 | 框架与基础设施 |

**主线程阻塞时间仅 0.1s**，说明 3.9s FCP 是**模拟移动端 4× CPU + 慢速网络下解析/编译 ~427KB 入口 JS 的成本**，并非代码缺陷。

### 3.3 已实施的修复：zrender 移出 vendor 入口 chunk
`vendor` 中 82% 未使用，根因是 **zrender（echarts 依赖）被误留在 vendor 入口 chunk**，导致图表渲染器在**每个页面（含登录首屏）白白加载**。原 `vite.config.ts` 的 manualChunks 刻意把 zrender 留作 vendor 以让 `charts` chunk 保持 462KB 较小——但代价是首屏白加载 ~50KB gz 的图表代码，并被 Lighthouse 标记为 unused-javascript。

修复：将 `zrender` 显式归入懒加载的 `charts` chunk（`if (id.includes('echarts') || id.includes('zrender')) return 'charts'`）。zrender 仅图表页使用，对首屏无影响。
- vendor chunk：334 KB → **171.57 KB**（raw）
- charts chunk：462.80 KB → 631.40 KB（懒加载，首屏 0 影响）
- 首屏 JS：427.5 → **372.8 KiB**，vendor 未使用 93.8 → **48.7 KiB**
- 移动端 perf：**79 → 83**，FCP/LCP 3.9s → **3.5s**

## 4. 剩余 83→90 差距与突破路径

移动端 83 距目标 90 还差约 7 分。Lighthouse 在 4× CPU 节流下，要把 FCP/LCP 压到 ~2.3s 以内（分数≥0.9），需将首屏 JS 从 ~373KB gz 再砍约 150KB gz。当前首屏剩余大头是 Element Plus：

- element-plus（79KB）+ ep-form-advanced（63KB）+ ep-utility（60KB）≈ **202KB gz**，且其中 84–87% 在登录页"未使用"——这是组件库按 chunk 整包加载的固有特性（登录用了其中几个组件，但整 chunk 必须下载）。

**安全、可逆的快速修复已用尽**。要达到 90，需架构级改动（建议归入 WF-2/WF-3）：

1. **非-Element-Plus 登录页（推荐，成本中）**：登录/落地页用原生 HTML/CSS 或极轻量组件实现，避免拉入 EP 核心+form/utility chunk（可省 ~200KB gz，首屏直逼 90）。需保证与整体设计语言一致。
2. **SSR / 预渲染（成本高）**：对登录或营销路由做服务端渲染或构建期预渲染，首屏 HTML 自带内容，FCP 不再依赖 JS 执行。
3. **Brotli 在生产的真实生效**：dist 已预生成 `.br`（vite-plugin-compression2）。确保生产 nginx 启用 `ngx_brotli` + `brotli_static on` 以实际下发 brotli，进一步降低传输成本（本地 Lighthouse 已按压缩体积计，生产中增益更明显）。
4. **API 预连接（低成本）**：在 `index.html` 增加 `<link rel="preconnect">` 指向 API 源站，缩短首屏首个 API 调用 TTFB。

## 5. 复测数据对比（同一 Lighthouse 配置）

| 配置 | 分数 | FCP | LCP | TBT | Speed Index | 首屏 JS |
|---|---|---|---|---|---|---|
| 过期基线(2026-07-11) | 53 | 5.8s | 6.8s | 380ms | 5.8s | (未记录) |
| 当前构建(修复前) | 79 | 3.9s | 3.9s | 0ms | 3.9s | 427.5 KiB |
| 当前构建(zrender 修复后) | **83** | 3.5s | 3.5s | 0ms | 3.5s | 372.8 KiB |
| 桌面端(无节流, 修复后) | **99** | 0.8s | 0.8s | 0ms | 0.8s | — |

## 6. 交付物
- 构建修复：`frontend/vite.config.ts`（zrender → charts 懒加载 chunk）
- Lighthouse 报告（outputs 目录下）：`ISS-03-lighthouse-mobile-before.json`、`ISS-03-lighthouse-mobile-after.json`、`ISS-03-lighthouse-desktop.json`
- 基线更新：`KPI-基线.json`（perf 53→83，新增桌面 99）、`问题清单与优先级.csv`（ISS-03 状态更新）、`系统现状评估报告.md`（§1/§2.1/§5）

## 7. 风险与回滚
- zrender 拆包为纯构建配置改动，运行时行为不变（charts 仍正常，只是 chunk 边界移动）；如异常可 `git revert vite.config.ts` 并重新 `vite build`。
- 其余为测量与文档更新，无运行时风险。
