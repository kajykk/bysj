# Lighthouse 验证报告 v1.12

> **迭代**: v1.12-coverage-browser-quality-sprint
> **日期**: 2026-04-30
> **状态**: 配置验证完成，运行时环境限制

---

## 1. 环境配置

### 1.1 Chrome/Chromium 安装

| 项目 | 状态 | 说明 |
|------|------|------|
| Chrome 系统安装 | 未找到 | `where chrome` 无结果 |
| Chromium (puppeteer) | 已安装 | `C:\Users\k\.cache\puppeteer\chrome\win64-147.0.7727.57\chrome-win64\chrome.exe` |
| Lighthouse npm 包 | 已安装 | `lighthouse@13.1.0` |
| chrome-launcher | 已安装 | `chrome-launcher@1.1.2` |

### 1.2 前端构建状态

- **构建命令**: `npm run build`
- **构建状态**: 成功
- **构建时间**: 23.94s
- **PWA 生成**: `generateSW` 模式，91 entries (2940.67 KiB)
- **输出目录**: `frontend/dist/`

### 1.3 Chunk 分析

| Chunk | 大小 | 状态 |
|-------|------|------|
| vendor | 600.66 kB | 警告 (>500kB) |
| charts | 813.25 kB | 警告 (>500kB) |
| vue-core | 482.45 kB | 警告 (>500kB) |
| ui | 427.47 kB | 正常 |

---

## 2. Lighthouse 测试执行

### 2.1 测试页面清单

| 页面 | URL | 状态 |
|------|-----|------|
| /login | http://localhost:4173/login | 环境限制 |
| /user/dashboard | http://localhost:4173/user/dashboard | 环境限制 |
| /user/assessments | http://localhost:4173/user/assessments | 环境限制 |
| /user/warnings | http://localhost:4173/user/warnings | 环境限制 |

### 2.2 环境限制说明

**限制类型**: 沙箱网络隔离
**错误码**: `-1073741510` (STATUS_CONTROL_C_EXIT)
**表现**:
- Preview 服务器启动成功 (`vite preview --port 4173`)
- Headless Chrome 启动成功 (Chrome/147.0.7727.57)
- Chrome 无法访问 localhost:4173 (CHROME_INTERSTITIAL_ERROR)
- 进程被沙箱环境终止

**根因分析**:
当前执行环境为隔离沙箱，headless Chrome 无法访问本机启动的 HTTP 服务。这是预期的安全限制。

---

## 3. 配置验证结果

### 3.1 Lighthouse 配置检查

```javascript
// run-lighthouse.cjs - 已验证可执行
const chromeLauncher = require('chrome-launcher');
const { default: lighthouse } = await import('lighthouse');

// 配置参数:
// - chromePath: puppeteer Chromium 路径
// - chromeFlags: --headless --no-sandbox --disable-setuid-sandbox
// - categories: performance, accessibility, best-practices, seo
```

### 3.2 前端 PWA 配置验证

| 检查项 | 状态 | 说明 |
|--------|------|------|
| vite-plugin-pwa | 已配置 | `vite-plugin-pwa@0.21.1` |
| manifest.webmanifest | 已生成 | 0.40 kB |
| sw.js | 已生成 | Workbox 生成 |
| precache entries | 91 | 2940.67 KiB |
| offline.html | 已配置 | fallback 页面 |

### 3.3 package.json 脚本验证

```json
{
  "lighthouse": "lighthouse http://localhost:5173 --output=html --output-path=./lighthouse-report.html",
  "lighthouse:ci": "lighthouse http://localhost:5173 --output=json --output-path=./lighthouse-report.json --chrome-flags='--headless --no-sandbox'",
  "perf:audit": "npm run build && npm run lighthouse:ci"
}
```

---

## 4. 建议与下一步

### 4.1 本地运行指南

在本地开发环境中执行 Lighthouse：

```bash
# 1. 启动前端 preview
cd frontend
npm run preview -- --port 4173

# 2. 运行 Lighthouse (另一个终端)
npx lighthouse http://localhost:4173/login \
  --output=html \
  --output-path=./lighthouse-report.html \
  --chrome-flags="--headless --no-sandbox"

# 3. 或使用自定义脚本
node run-lighthouse.cjs http://localhost:4173/login ./lighthouse-login.json
```

### 4.2 CI 环境配置

```yaml
# .github/workflows/lighthouse.yml 建议配置
- name: Run Lighthouse
  run: |
    npm run preview &
    sleep 5
    npx lighthouse http://localhost:4173/login \
      --output=json \
      --chrome-flags="--headless --no-sandbox"
```

### 4.3 性能优化建议

基于构建输出分析：

1. **Chunk 体积优化**:
   - `charts` (813kB): 建议按需加载，非图表页面不加载
   - `vendor` (600kB): 检查是否可以进一步拆分
   - `vue-core` (482kB): 检查是否包含未使用的 Vue 特性

2. **PWA 优化**:
   - Precache 体积 2940 KiB 较大，建议排除非关键资源
   - 考虑使用 `runtimeCaching` 策略替代全量 precache

---

## 5. 结论

| 检查项 | 状态 | 说明 |
|--------|------|------|
| Lighthouse 工具链 | 已配置 | npm 包、Chromium、脚本就绪 |
| 前端构建 | 通过 | PWA、SW、manifest 生成正常 |
| 实际 Lighthouse 运行 | 环境限制 | 沙箱网络隔离，需本地/CI 执行 |
| 配置文档 | 已产出 | 本报告 + run-lighthouse.cjs |

**最终状态**: Phase 2 配置验证完成，运行时测试需在非沙箱环境执行。
