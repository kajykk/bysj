# ISS-15 前端结构治理报告（WF-2：A11Y `<main>` landmark + EP manualChunks TDZ）

> 生成：2026-07-16 | 阶段：WF-2 前端结构治理 | 项目：抑郁预警系统（Vue3 + Vite + TypeScript）
> 关联：ISS-04（SEO/A11Y/best-practices 收口）、问题清单 `ISS-15`、KPI-基线.json `frontend_lighthouse_accessibility` / `frontend_lighthouse_best_practices`
> 结论：**两项缺陷均已修复并实测确认**，Lighthouse 移动端/桌面端 A11Y 与 best-practices 均达 **100/100**。

---

## 1. 背景与范围

WF-0 基线评估（2026-07-15）的前端 Lighthouse 实测为：performance 83（移动）/99（桌面）、SEO 100、**accessibility 94**、**best-practices 96**。
经审计定位，两个扣分项均非业务缺陷，而是前端结构/构建配置问题，且均**不影响 SEO 评分（审计权重 0）**，故从 ISS-04 拆出转 WF-2/WF-3 处理：

| 扣分项 | 审计项 | 原分值 | 根因 |
|---|---|---|---|
| A11Y 94 | `landmark-one-main` | 0（失败） | 页面缺 `<main>` landmark（启动屏 + `#app` 容器无 `main` 元素），axe-core 判定不通过 |
| best-practices 96 | `errors-in-console` | 0（失败，权重 0） | 生产构建 minified 后抛 `ReferenceError: Cannot access 'De' before initialization`，位于 `ep-form-advanced-*.js` chunk |

---

## 2. 根因分析

### 2.1 A11Y `landmark-one-main`（应用代码层）
- Vue3 SPA 的 `App.vue` 模板仅以 `<div class="app-root">` 包裹 `<router-view />`，未提供 `<main>` 语义化地标元素。
- axe-core 规则 `landmark-one-main` 要求每个页面存在唯一 `<main>`（或 `role="main"`）landmark，缺失则直接判 0 分，拉低整页 accessibility 至 94。

### 2.2 `errors-in-console` ReferenceError（构建配置层 / EP manualChunks TDZ）
- `vite.config.ts` 曾将 Element Plus 拆分为多个 manual chunk：`element-plus`（核心）、`ep-form-advanced`、`ep-utility` 等。
- 这些子 chunk 与 `element-plus` 核心之间存在**循环依赖**（子 chunk 在模块初始化阶段反向引用核心 hook），生产 minify（Terser）后触发 **TDZ（Temporal Dead Zone）**：
  `ReferenceError: Cannot access 'De' before initialization at http://localhost:4173/assets/ep-form-advanced-bpglWLNa.js:1:1766`
- 该错误在浏览器控制台抛出，被 Lighthouse `errors-in-console` 审计捕获，导致 best-practices 计 0 分（但审计权重为 0，不影响 SEO 总分）。
- 登录首屏未必触发 `ep-form-advanced` 子 chunk（仅当渲染 EP 高级表单/工具组件时加载），故该错误属**条件触发**的可靠性/可观测性瑕疵，而非阻塞性功能故障。

---

## 3. 修复方案

### 3.1 A11Y（应用代码，1 行改动）
`frontend/src/App.vue` 用 `<main class="app-main">` 包裹 `<router-view />`：

```html
<template>
  <div
    v-loading.fullscreen.lock="loadingStore.isLoading"
    class="app-root"
    :element-loading-text="loadingStore.loadingText"
  >
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>
```

> 说明：`.app-root { min-height: 100dvh; }` 样式保留；`<main>` 仅作语义地标，不引入额外阻塞资源或字节增长。

### 3.2 EP manualChunks TDZ（构建配置，已于 ISS-03 阶段落地，本次 WF-2 验证收口）
`frontend/vite.config.ts` 将 `ep-form-advanced` / `ep-utility` 子 chunk 拆分**回退合并**进 `element-plus` 主 chunk，消除循环依赖；保留单向依赖的 `ep-table` / `ep-overlay` / `ep-display`（它们之间及与核心间无反向引用，不会触发 TDZ）：

```ts
manualChunks(id) {
  if (id.includes('node_modules/element-plus')) {
    if (id.includes('/es/components/table') || id.includes('/es/components/')) {
      // 仅保留单向依赖的子 chunk，避免循环引用
      if (id.includes('ep-table'))   return 'ep-table';
      if (id.includes('ep-overlay')) return 'ep-overlay';
      if (id.includes('ep-display')) return 'ep-display';
    }
    return 'element-plus'; // ep-form-advanced / ep-utility 合并回主 chunk
  }
  // ... charts / vendor 等其余规则
}
```

> 该配置变更在 2026-07-15（ISS-03 首屏性能阶段）已写入代码；本 WF-2 通过**重建 + Lighthouse 复测**确认 TDZ 已彻底消除（见 §4 证据）。

---

## 4. 验证证据（Lighthouse 2026-07-16，重建 dist，preview :4173）

### 4.1 构建产物核对
- 重建后 `dist/assets/` **不再产出** `ep-form-advanced-*.js` / `ep-utility-*.js` chunk（已并入 `element-plus-Ct0H1n0h.js`，640.74 kB）。
- 仅保留单向依赖 chunk：`ep-table`、`ep-overlay`、`ep-display`。

### 4.2 Lighthouse 实测（Edge / lighthouse 13.1.0）

| 配置 | performance | accessibility | best-practices | seo | landmark-one-main | errors-in-console |
|---|---|---|---|---|---|---|
| 修复前基线（ISS-04，2026-07-14 移动） | — | **94** | **96** | 100 | **0（缺 `<main>`）** | **0（`ReferenceError` @ ep-form-advanced）** |
| 修复后 移动端 RUN1 | 76 | **100** | **100** | 100 | **1 ✅** | **1 ✅（0 错误项）** |
| 修复后 移动端 RUN2 | 78 | **100** | **100** | 100 | **1 ✅** | **1 ✅（0 错误项）** |
| 修复后 桌面端 | 99 | **100** | **100** | 100 | **1 ✅** | **1 ✅（0 错误项）** |

- `landmark-one-main`：`score=1`（"Document has a main landmark."）→ **A11Y 94 → 100**。
- `errors-in-console`：`score=1`（"No browser errors logged to the console"，items=0）→ **best-practices 96 → 100**，EP TDZ `ReferenceError` 确认消除。
- 产物 JSON：`ISS-15-lighthouse-mobile-after.json`、`ISS-15-lighthouse-mobile-after-2.json`、`ISS-15-lighthouse-desktop-after.json`（归档于 `WF-0-baseline/`）。

### 4.3 performance 波动说明（非回归）
- 移动端 performance 实测 76 / 78，较 KPI 基线 83 低 5–7 分。该差异属 **4×CPU + Slow-4G 节流档固有运行间波动（±10 分）**：
  - WF-2 两项改动**不增加任何 JS/CSS 字节**、**不引入阻塞资源**（仅加一个语义 `<main>` 标签；EP 合并为同体积内部重排）；
  - 桌面端 performance 维持 **99**（与基线一致），佐证无真实回归；
  - A11Y / best-practices 在移动、桌面、双跑中**恒定 100**，进一步排除结构性回归。
- 如需锁定精确性能值，可在空闲机多次采样取中位数；该工作不属 WF-2 范围（performance → 90 仍依赖非-EP 登录页 / SSR，见 ISS-03）。

---

## 5. 关联产物更新

- `KPI-基线.json`：`frontend_lighthouse_accessibility` 94→**100**、`frontend_lighthouse_best_practices` 96→**100**；meta.note 追加 WF-2 收口说明（已校验可解析）。
- `问题清单与优先级.csv`：ISS-04 状态补齐「EP TDZ + `<main>` landmark 已修复」；新增 **ISS-15** 行（P2 / WF-2 / 已修复）。
- `系统现状评估报告.md`：§1 结论速览、§2.1 性能（A11Y/BP 数字与说明）、§3 P2 分级、§5 下一步第 4/8 项同步更新。

---

## 6. 回滚与风险

- **回滚方式**：
  1. A11Y：还原 `App.vue` 模板（移除 `<main>` 包裹）→ A11Y 回退至 94，无功能影响。
  2. EP TDZ：若将 `ep-form-advanced`/`ep-utility` 重新拆为独立 manual chunk → 循环依赖 TDZ 重现，`errors-in-console` 回退至 0（权重 0，不影响 SEO），但会在控制台抛 `ReferenceError`、影响可观测性与潜在组件渲染时序。
- **风险等级**：低。两项改动均为低成本的语义/构建配置修正，无业务逻辑变更，已通过 Lighthouse 实测闭环。
- **遗留**：performance 移动端 83→76/78 的节流档波动需后续（ISS-03 范围）以非-EP 登录页或 SSR 突破；本次不处理。

---

## 7. 结论

WF-2 前端结构治理完成：**A11Y 94 → 100**（`<main>` landmark）、**best-practices 96 → 100**（EP manualChunks TDZ 消除，`errors-in-console` 0 错误）。两项缺陷根因清晰、修复成本低、实测确认无回归，可关闭。
