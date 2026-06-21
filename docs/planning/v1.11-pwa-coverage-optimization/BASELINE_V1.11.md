# Baseline Report v1.11

> **迭代**: v1.11-production-readiness-hardening
> **日期**: 2026-04-29
> **状态**: Phase 0 基线确认完成
> **基线来源**: v1.10.1 质量门禁报告 + 代码审查

---

## 1. 前端构建基线

| 指标 | v1.10.1 值 | v1.11 目标 | 状态 |
|------|-----------|-----------|------|
| 构建时间 | 41.74s | 无明显劣化 | 基线已记录 |
| 模块数 | 2541 | 无明显变化 | 基线已记录 |
| sourcemap | 已生成 | 保持生成 | 基线已记录 |
| Vite 版本 | 6.2.6 | 保持 6.x | 基线已记录 |

**Chunk 基线**:

| Chunk | 大小 | 状态 |
|-------|------|------|
| charts | 813 KB | > 500KB (需优化) |
| vendor | 621 KB | > 500KB (需优化) |
| vue-core | 483 KB | > 500KB (临界) |
| ui | 427 KB | 可接受 |
| 其他 | < 100 KB | 可接受 |

**验证状态**: 环境限制无法实际运行 `npm run build`，基线基于 v1.10.1 报告。

---

## 2. 安全扫描基线

| 工具 | v1.10.1 结果 | v1.11 目标 | 状态 |
|------|-------------|-----------|------|
| npm audit | 0 vulnerabilities | 保持 0 | 基线已记录 |
| bandit High | 0 | 保持 0 | 基线已记录 |
| bandit Medium | 9 (B614/B615) | <= 3 或说明 | 基线已记录 |
| bandit Low | 8 | 记录 | 基线已记录 |

**验证状态**: 环境限制无法实际运行 npm audit/bandit，基线基于 v1.10.1 报告。

---

## 3. 测试覆盖率基线

| 模块 | v1.10.1 覆盖率 | v1.11 目标 | 差距 |
|------|---------------|-----------|------|
| app/core/security.py | 100% | >= 80% | 已达标 |
| app/core/contracts.py | 100% | >= 80% | 已达标 |
| app/core/rate_limit.py | 100% | >= 80% | 已达标 |
| app/core/request_id.py | 100% | >= 80% | 已达标 |
| app/core/response.py | 100% | >= 80% | 已达标 |
| app/core/states.py | 100% | >= 80% | 已达标 |
| app/core/middlewares.py | 96% | >= 80% | 已达标 |
| app/core/exceptions.py | 89% | >= 80% | 已达标 |
| app/core/database.py | 74% | >= 80% | +6% |
| app/core/health.py | 42% | >= 80% | +38% |
| **整体** | **28%** | **>= 40%** | **+12%** |

**验证状态**: 环境限制无法实际运行 pytest --cov，基线基于 v1.10.1 报告。

---

## 4. PWA 基线

| 检查项 | v1.10.1 状态 | v1.11 目标 |
|--------|-------------|-----------|
| Service Worker 源码 | 存在 (src/service-worker.ts) | 编译到 dist |
| SW 注册逻辑 | 存在 (src/utils/serviceWorker.ts) | 使用 virtual:pwa-register |
| offline.html | 存在 (public/offline.html) | 预缓存到 SW |
| Web Manifest | 不存在 | 完整配置 |
| vite-plugin-pwa | 未安装 | 安装并配置 |

---

## 5. Lighthouse 基线

| 检查项 | v1.10.1 状态 | v1.11 目标 |
|--------|-------------|-----------|
| lighthouserc.js | 配置完整 | 保持 |
| lighthouserc.json | 配置完整 | 保持 |
| 实际运行 | 环境无 Chrome | 环境可用时运行 |

---

## 6. 环境限制说明

以下命令在当前环境返回 exit code `-1073741510`，标记为环境限制：

- `npm run build`
- `npm audit`
- `bandit -r app`
- `pytest --cov=app`

**处理方式**: 基线基于 v1.10.1 已验证报告，v1.11 开发任务通过代码审查和配置验证完成，最终在 CI 环境执行完整验证。

---

## 7. 基线结论

| 类别 | 基线状态 | 风险 |
|------|---------|------|
| 前端构建 | 已知 (v1.10.1: 41.74s) | 低 |
| Chunk 体积 | charts/vendor > 500KB | 中 |
| 安全扫描 | npm audit 0, bandit High 0 | 低 |
| 覆盖率 | 整体 28%, health 42% | 中 |
| PWA | SW 未编译到 dist | 高 |
| Lighthouse | 配置完整，未实际运行 | 低 |

**v1.11 重点**: PWA 生产闭环、覆盖率提升、chunk 优化。

---

> **产出日期**: 2026-04-29
> **报告状态**: 已归档
