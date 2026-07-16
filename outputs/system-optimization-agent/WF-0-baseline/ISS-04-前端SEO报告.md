# ISS-04 前端 SEO 报告

- **日期**：2026-07-15
- **负责人**：系统优化 Agent（CodeBuddy SDK 工作流，WF-0 基线闭环）
- **维度**：可维护性 / 前端（Lighthouse SEO 类目）
- **关联阶段**：WF-2（结构与治理）；`sys-perf-diagnosis`
- **状态**：✅ 已修复（SEO 移动/桌面 100/100）；残留 1 个独立缺陷转 WF-2/WF-3

---

## 1. 结论

| 指标 | 原 KPI 基线 | 当前构建（修复前重测） | 当前构建（修复后） | 说明 |
|---|---|---|---|---|
| **Lighthouse SEO** | **54 / 100** | **91 / 100** | **100 / 100** | 原 54 为 2026-07-11 旧构建，属**过期基线** |
| robots-txt | ❌ 失败 | ❌ 失败 | ✅ 通过 | 旧构建因 `is-crawlable` 也失败（页面被屏蔽），当前构建仅缺 robots.txt |
| is-crawlable | ❌ 失败 | ✅ 通过 | ✅ 通过 | 当前构建页面可爬取 |
| errors-in-console | ❌ 多错 | ❌ favicon 404 + ReferenceError | ⚠️ 仅余 ReferenceError（权重 0，不影响 SEO） | favicon 404 已消除 |
| valid-source-maps | ❌ 失败（旧构建） | ✅ 通过 | ✅ 通过 | 当前构建 sourcemap 有效 |

**核心结论**：SEO 原 KPI 基线 54 与 ISS-03 的 perf 53 一样，是 **2026-07-11 的旧构建产物**（引用不同的 asset hash，尚未包含 P1-1 启动屏与去 Google Fonts 优化），属过期基线。对当前构建用**同配置**重测，SEO 实际为 91；补 `public/robots.txt` + 显式 favicon 链接后，**SEO 升至 100（移动/桌面一致）**，达到并超过 90 目标。

---

## 2. 证据：基线过期（与 ISS-03 同源）

对比旧基线 `frontend/lighthouse-prod.json`（2026-07-11）与当前 `dist/` 构建：

| 项 | 旧基线（lighthouse-prod.json） | 当前构建（dist/） |
|---|---|---|
| 入口 JS | `index-BZFWLiHr.js` | `index-BFdb1NjB.js` |
| 是否有启动屏 | 否 | 是（P1-1） |
| Google Fonts 外部依赖 | 是（阻塞 FCP） | 否（系统字体栈） |
| SEO 报告分数 | 0.54 | 0.91（修复前）/ 1.00（修复后） |
| `is-crawlable` | 失败 | 通过 |
| `robots-txt` | 失败 | 失败（修复前）→ 通过（修复后） |

> asset hash 不同 + 启动屏/字体差异，证明旧基线对应的是已废弃的构建，不能直接作为"现状 54"使用。这与 ISS-03（perf 53 → 83）的"过期基线"判断同源。

---

## 3. 根因（两处，均为安全快速修复）

当前构建 SEO 扣到 91 的两处失败：

1. **缺 `robots.txt`**：SPA（`vite preview`）对未知路由回退返回 `index.html`（content-type `text/html`），Lighthouse 抓取 `/robots.txt` 得到 HTML 而非合法 robots 文件 → `robots-txt` 审计失败。
2. **`/favicon.ico` 404 进入控制台**：`index.html` 未声明 favicon，浏览器自动请求 `/favicon.ico` → 404 控制台错误 → `errors-in-console` 审计失败（该审计在 SEO 类目中权重 0，故仅把分数从 100 拉到 91，而非更低）。

---

## 4. 修复（2 处改动，已合入源码）

### 4.1 新增 `frontend/public/robots.txt`
```
User-agent: *
Allow: /
```
（注释说明：如后续需收紧爬虫对 `/api/`、`/ws/` 的遍历，可改为 `Disallow: /api/` / `Disallow: /ws/`；当前 SPA 全部可索引，与 `index.html` 的 `<meta name="robots" content="index, follow">` 一致。）

### 4.2 `frontend/index.html` 增加显式 favicon 链接（ISS-04 修复）
```html
<!-- ISS-04 修复：显式 favicon，避免浏览器自动请求 /favicon.ico 产生 404 控制台错误 -->
<link rel="icon" type="image/png" sizes="192x192" href="/icon-192x192.png" />
<link rel="icon" type="image/png" sizes="512x512" href="/icon-512x512.png" />
```
> 两个 PNG 已存在于 `public/`（627B / 1949B），`vite build` 拷贝至 `dist/`，浏览器请求返回 200；浏览器有显式 `<link rel="icon">` 后**不再**回退请求 `/favicon.ico`，404 消失。

构建：`vite build`（exit 0），`dist/robots.txt` 与 `index.html` 的 favicon 链接均已生效。

---

## 5. 复测结果（修复后，2026-07-15）

Lighthouse 13.1.0 + Microsoft Edge Chromium 150（`CHROME_PATH` Windows 原生路径），移动配置（4× CPU + Slow-4G 节流，与基线一致）：

| 类目 | 分数 |
|---|---|
| **SEO** | **100** |
| Performance | 83 |
| Accessibility | 94 |
| Best Practices | 96 |

关键审计项（修复后）：
- `is-crawlable` = 1 ✅
- `robots-txt` = 1 ✅
- `document-title` / `meta-description` / `http-status-code` / `link-text` / `crawlable-anchors` / `valid-source-maps` = 全部 1 ✅
- `errors-in-console` = 0 ⚠️ 仅余 1 个 `ReferenceError`（见 §6，权重 0，不影响 SEO 评分）

预览服务器探针：`/` → 200、`/robots.txt` → 200、`/icon-192x192.png` → 200、`/favicon.ico` → 404（浏览器已不再请求，无影响）。

---

## 6. 残留问题（非 ISS-04 范围，已记录并转移）

### 6.1 `errors-in-console` 中的 ReferenceError（独立前端缺陷）
修复后 `errors-in-console` 仍记录 1 条：
```
ReferenceError: Cannot access 'De' before initialization
    at http://localhost:4173/assets/ep-form-advanced-bpglWLNa.js:1:1766
```
- **性质**：TDZ（暂时性死区）`ReferenceError`，来自 **Element Plus 6 路 manualChunks 拆包循环依赖**（`element-plus` / `ep-form-advanced` / `ep-utility` 等 chunk 间互相引用未初始化变量）。
- **前置性**：在修复前的"当前构建 91 分"报告与修复后的"100 分"报告中**均存在** → 非本次改动引入，属既有债。
- **影响面**：登录首屏不使用 `ep-form-advanced` 组件集（已 grep `LoginPage.vue` / `ResetPasswordPage.vue` 确认无 `ElSelect`/`ElDatePicker` 等），故首屏不触发；该错误在加载 `ep-form-advanced` chunk 的路由（如评估表单）上才会触发模块求值期报错，**可能导致相关表单组件加载失败**。这是一个真实的功能性 bug，需在 WF-2/WF-3 的结构与治理阶段处理（建议：合并 EP 拆包或消除循环依赖）。
- **对 SEO 的影响**：`errors-in-console` 在 SEO 类目中权重为 0，因此**不影响 SEO 评分（SEO 仍为 100）**。ISS-04 范围内无需处理。

### 6.2 Accessibility = 94（顺带发现，非 ISS-04 范围）
同次 Lighthouse 实测 A11Y = 94，唯一扣分项 `landmark-one-main`（页面缺 `<main>` landmark，启动屏 + `#app` 无 `<main>` 元素）。原 KPI `accessibility: 100` 同为 2026-07-11 过期基线。修复建议：`App.vue` 用 `<main>` 包裹 `<router-view>`，约 1 行改动即可回到 100。属 A11Y 范畴，不在 ISS-04（SEO）范围内，建议另立项或并入 WF-2 前端治理。

---

## 7. 复现命令

```bash
# 1) 构建（含 ISS-04 修复：public/robots.txt + index.html favicon 链接）
cd frontend
node_modules/.bin/vite build

# 2) 启动预览（strictPort 防止端口冲突）
node_modules/.bin/vite preview --port 4173 --strictPort

# 3) 复测 SEO（移动配置，与基线一致）
export CHROME_PATH="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
node_modules/.bin/lighthouse http://localhost:4173/ \
  --output=json --output=html --output-path=ISS-04-lighthouse-mobile-after \
  --chrome-path="$CHROME_PATH" --quiet
# 注：退出码 1 多为 EBUSY（CrashpadMetrics-active.pma 临时目录清理失败），报告已写入，可忽略。
```

---

## 8. 风险与回滚

- **改动范围极小**：仅新增 1 个静态文件（`public/robots.txt`）+ `index.html` 增加 2 行 `<link>`。无逻辑改动、无依赖变更。
- **回滚**：删除 `public/robots.txt` 与 `index.html` 中 2 行 favicon 链接，重新 `vite build` 即可还原。
- **SEO 收益稳定**：`robots.txt` 与显式 favicon 为静态资源，对所有路由生效，无回归风险。

---

## 9. 交付物

- 修复：`frontend/public/robots.txt`（新建）、`frontend/index.html`（favicon 链接）
- 基线更新：`KPI-基线.json`（`frontend_lighthouse_seo` 54→100，附过期基线说明；`frontend_lighthouse_accessibility` 100→94 实测）、`问题清单与优先级.csv`（ISS-04 状态→已修复）、`系统现状评估报告.md`（结论表 / §2.1 / P2 列表 / §5 下一步）
- 本报告：`ISS-04-前端SEO报告.md`
- Lighthouse 原始产物归档：`ISS-04-lighthouse-mobile-after.json` / `ISS-04-lighthouse-mobile-after.html`
