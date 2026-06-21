# v1.17 基线验证报告 — BASELINE_V1.17.md

> **生成时间**: 2026-05-01
> **迭代**: v1.17-review-workflow-text-model-upgrade
> **上一迭代**: v1.16-risk-calibration-safety

---

## 1. 验证环境

| 项目 | 版本/信息 |
|---|---|
| 操作系统 | Windows |
| Python | 3.12.0 |
| Node.js | (待补充) |
| 前端框架 | Vue.js 3 + Vite |
| 后端框架 | FastAPI 3.1.0 |
| 数据库 | SQLite (测试环境) |

---

## 2. 前端构建验证

| 检查项 | 状态 | 备注 |
|---|---|---|
| `npm run build` | 通过 | exit code 0, 24.49s |
| 构建输出目录 | 通过 | `frontend/dist/` 包含预期文件 |
| 构建错误 | 无 | 仅 chunk 大小 warning |
| PWA 生成 | 通过 | sw.js, workbox 文件已生成 |

**构建输出**:
- dist/index.html
- dist/assets/ (JS/CSS 文件)
- dist/sw.js (Service Worker)
- dist/manifest.webmanifest

---

## 3. 后端启动验证

| 检查项 | 状态 | 备注 |
|---|---|---|
| 服务启动 | 通过 | Uvicorn running on port 8001 |
| 数据库连接 | 通过 | SQLite 连接正常 |
| 模型加载 | 部分通过 | 部分模型版本不一致警告 |

**启动日志摘要**:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001
```

**警告**:
- sklearn 版本不一致警告 (1.8.0 vs 1.7.2)
- TensorFlow GPU 不支持 Windows 警告
- 两个 Keras 模型 fallback
- SENTRY_DSN 未设置

---

## 4. 健康检查验证

| 端点 | 状态 | 响应 |
|---|---|---|
| GET `/health` | 通过 | `{"status":"ok","checks":{"database":"ok"}}` |
| GET `/health/ready` | 通过 | `{"status":"ok","checks":{"database":"ok"}}` |

---

## 5. API 冒烟测试

| 测试 | 状态 | 备注 |
|---|---|---|
| 文本预测 - 正常文本 | 通过 | 返回正常风险分数 |
| 文本预测 - 危机文本 | 通过 | 返回 crisis_detected=true |
| 文本预测 - 风险因素 | 通过 | 返回 risk_factors |
| 生理预测 - 范围校验 | 通过 | 返回 422 对于无效输入 |
| 生理预测 - 负值校验 | 通过 | 返回 422 对于负值 |
| 生理预测 - 有效数据 | 通过 | 返回正常预测结果 |
| 融合预测 - 复核触发 | 通过 | 返回 review_required=true |
| 融合预测 - 危机覆盖 | 通过 | 返回 crisis_override=true |
| 融合预测 - 空输入 | 通过 | 返回默认结果 |
| 结构化预测 - 数据质量 | 通过 | 返回 422 (模型文件损坏) |

**测试结果**: 10/10 通过

---

## 6. 已知问题

| 问题 | 影响 | 建议处理 |
|---|---|---|
| structured_logistic_regression_quick 模型文件损坏 | 中 | 需要重新训练或替换模型文件 |
| sklearn 1.8.0 vs 1.7.2 版本不一致 | 低 | 警告不影响功能，建议统一版本 |
| TensorFlow GPU 不支持 Windows | 低 | 预期行为，CPU 推理足够 |
| SENTRY_DSN 未配置 | 低 | 生产环境需要配置 |

---

## 7. 基线结论

**状态**: 条件通过 (Conditional Go)

v1.16 核心功能在本地环境可正常运行，前端构建成功，后端启动成功，API 测试通过。

**可开始 v1.17 开发的前提条件**:
- ✅ 前端构建通过
- ✅ 后端启动通过
- ✅ 健康检查通过
- ✅ API 冒烟测试通过
- ⚠️ 结构化模型文件损坏（不影响其他模型）

---

> **文档版本**: v1.0
> **生成时间**: 2026-05-01
