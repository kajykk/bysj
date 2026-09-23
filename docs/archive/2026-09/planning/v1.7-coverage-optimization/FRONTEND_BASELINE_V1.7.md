# 前端构建基线报告

> **迭代**: v1.7-backend-contract-coverage-hardening
> **日期**: 2026-04-29
> **状态**: 基线已确认

---

## 1. 前端构建状态

| 指标 | 当前状态 | 说明 |
|------|---------|------|
| type-check | 环境限制无法验证 | v1.6 报告: 100 个 TS 错误需修复 |
| build | 环境限制无法验证 | 需验证 |
| ESLint | 未安装 | v1.7 P1 目标 |
| Prettier | 未安装 | v1.7 P1 目标 |

## 2. 前端依赖状态

### 2.1 已安装 (package.json)

| 依赖 | 版本 |
|------|------|
| vue | ^3.5.13 |
| vite | ^5.4.8 |
| typescript | ^5.6.3 |
| vue-tsc | ^3.2.7 |
| sass | ^1.77.8 |
| echarts | ^5.5.1 |
| element-plus | ^2.8.4 |

### 2.2 未安装 (v1.7 需安装)

| 依赖 | 用途 |
|------|------|
| eslint | 代码检查 |
| prettier | 代码格式化 |
| @vue/eslint-config-typescript | Vue TS 规则 |
| eslint-plugin-vue | Vue 规则 |
| @typescript-eslint/parser | TS 解析 |
| @typescript-eslint/eslint-plugin | TS 规则 |

## 3. Bundle 基线 (v1.6)

| Chunk | 体积 | v1.7 目标 |
|-------|------|----------|
| charts | ~812KB | 降低 20%+ 或说明原因 |
| vendor | ~620KB | 降低 15%+ 或说明原因 |

## 4. 已知问题

| 问题 | 来源 | v1.7 处理 |
|------|------|----------|
| Sass Legacy API warning | sass ^1.77.8 | P2 溯源并记录 |
| 100 个 TypeScript 错误 | v1.6 报告 | 需修复 |
| ESLint/Prettier 缺失 | 未配置 | P1 配置完成 |

## 5. Vite 配置现状

- `manualChunks` 已配置（vue-core, router, state, ui, icons, charts, datetime, security, http, i18n, vendor）
- `cssCodeSplit: true`
- `minify: 'terser'`
- `drop_console: true`, `drop_debugger: true`

---

> **文档状态**: 已产出
> **下一步**: T-FE-001 (ESLint 配置)
