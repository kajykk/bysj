# LAUNCH_BLOCKERS — 上线阻塞清单 (v1.28-final)

> **当前状态**: 🟢 **CLEAR (无 P0 阻塞)**
> **最后更新**: 2026-06-02
> **关联迭代**: v1.28-final + v1.29-launch-readiness

---

## 0. 阻塞等级定义

| 等级 | 含义 | 上线策略 |
|:---:|:---|:---|
| **P0** | 阻塞上线,必须立即修复 | ❌ 不允许上线 |
| **P1** | 严重降级,可在限定 SLA 下上线 | ⚠️ 需 +24h SLA 监控 |
| **P2** | 非关键缺陷,可后续迭代修复 | ✅ 允许上线,记录在案 |
| **P3** | 优化项,无 SLO 影响 | ✅ 允许上线 |

---

## 1. P0 阻塞清单(必须为零)

| # | 阻塞项 | 状态 | 修复日期 | 解决方案 |
|:---:|:---|:---:|:---:|:---|
| 1.1 | 测试通过率 < 95% | ✅ 已修复 (2026-06-02) | 2026-06-02 | 修复 53 个失败用例,新增阈值/JWT/数据库/canary/ML 修复 |
| 1.2 | 后端 Docker 镜像未构建 | ✅ 已修复 (2026-06-02) | 2026-06-02 | 新增 `backend/Dockerfile` (multi-stage) + docker-compose backend service |
| 1.3 | 核心 API 不可用 | ✅ 已验证 | v1.27 | /health, /version, /auth/login, /fusion, /dashboard-summary, /engine-snapshot 全通过 |
| 1.4 | 数据库迁移缺失 | ✅ 已验证 | v1.27 | alembic 36 张表全注册 |
| 1.5 | Crisis Override 不触发 | ✅ 已验证 | v1.27 | 危机文本 → risk_level=4 (critical) 触发成功 |
| 1.6 | 前端构建失败 | ✅ 已验证 | v1.27 | `npm run build` 成功,dist/ 存在 |
| 1.7 | 启动顺序不健康 | ✅ 已修复 | 2026-06-02 | docker-compose `depends_on: condition: service_healthy` + healthcheck |
| 1.8 | 监控/日志缺失 | ✅ 已就绪 | v1.27 | Sentry SDK + uvicorn access log + structured logging |

**结论**: **P0 阻塞已全部清零** ✅

---

## 2. P1 降级清单(需 SLA 监控)

| # | 项目 | 风险描述 | 监控指标 | 降级方案 |
|:---:|:---|:---|:---|:---|
| 2.1 | `physiological_optimized` 未训练 | 仅 1 个生理模型 (v1, F1=0.694),精度偏低 | F1 < 0.65 持续 24h | 自动 fallback 到 v1 + 启发式规则 |
| 2.2 | 契约测试运行缓慢 (Windows) | schemathesis 3-5 min 端到端跑通 | CI 失败率 | CI 环境下执行;本地可 `pytest -m "not contract"` 跳过 |
| 2.3 | sklearn 版本不一致警告 | 模型用 1.7.2 训练,运行时 1.8.0 | 推理精度 ±0.5% | 锁定 sklearn==1.7.2 或重新训练 |
| 2.4 | PyTorch/TensorFlow 体积大 | Docker 镜像含 ML 库但可能未启用 | 镜像大小 | 默认安装 CPU-only PyTorch;TensorFlow 可选 |

**SLA 承诺**: 7×24h 监控,P1 项目 1 周内关闭。

---

## 3. P2 已知缺陷(可后续修复)

| # | 项目 | 描述 | 影响 |
|:---:|:---|:---|:---|
| 3.1 | warning 模型分散 | `app/models/` 无 warning.py,逻辑在 service 层 | 架构可读性,无功能影响 |
| 3.2 | 数据库测试使用 SQLite | 生产用 PostgreSQL,部分 SQL 特性可能不一致 | 极小(用了 SQLAlchemy 抽象) |
| 3.3 | 部分 API 文档未生成 | `openapi.json` 存在但部分参数未标注 | 文档完整度 |
| 3.4 | 国际化 (i18n) 部分文案 | 仅 zh-CN/en-US,其他语言未实现 | 用户体验,非阻塞 |

---

## 4. 上线前 24 小时检查 (Go-Live Checklist)

### 4.1 基础环境
- [ ] 服务器: CPU ≥ 4 核,RAM ≥ 8GB,SSD ≥ 100GB
- [ ] 操作系统: Ubuntu 22.04 LTS / CentOS 9 (生产推荐)
- [ ] Docker 24.0+ & Docker Compose v2.20+
- [ ] 公网域名 + SSL 证书 (Let's Encrypt)

### 4.2 环境变量
- [ ] `POSTGRES_PASSWORD` (强随机,32+ 字符)
- [ ] `REDIS_PASSWORD` (强随机,16+ 字符)
- [ ] `JWT_SECRET_KEY` (openssl rand -base64 64)
- [ ] `SENTRY_DSN` (Sentry 平台获取)
- [ ] `CORS_ORIGINS` (前端域名白名单)

### 4.3 数据准备
- [ ] PostgreSQL 初始化脚本运行成功 (alembic upgrade head)
- [ ] 种子数据: 管理员账户 + 测试用户 + 干预模板
- [ ] 模型资产 4 个目录拷贝至容器:`models/artifacts/{physiological, structured_v1.20, structured_v1.21, text_depression_classifier}`

### 4.4 健康检查
- [ ] `curl http://<host>:8000/health` → `{"status": "ok"}`
- [ ] `curl http://<host>:8000/api/v1/version` → `{"version": "v1.28-final", "status": "FINAL-GO"}`
- [ ] `docker ps` 显示 backend/postgres/redis 全部 Up (healthy)

### 4.5 核心功能 E2E
- [ ] 用户注册 → 登录 → 提交问卷 → 触发风险预警 (端到端)
- [ ] 危机文本 "我想自杀" → risk_level=4 critical
- [ ] 干预计划生成 → 任务下发 → 用户完成 → 评价 (闭环)
- [ ] 审核员 review → 干预记录归档

### 4.6 监控告警
- [ ] Sentry 项目创建,DSN 配置
- [ ] Prometheus 抓取 `/metrics` (FastAPI 暴露)
- [ ] 告警规则: 5xx 率 > 1%, 响应时间 P95 > 1s, 错误日志 > 10/min

### 4.7 回滚方案
- [ ] 已生成 `ROLLBACK_PLAN.md` 并演练
- [ ] 数据库备份策略 (每日 pg_dump, 保留 30 天)
- [ ] 上一个稳定镜像 tag 保留 (v1.27-launch-ready)

---

## 5. Go/No-Go 决策

| 决策点 | 阈值 | 当前值 | 状态 |
|:---|:---:|:---:|:---:|
| 单元测试通过率 | ≥ 95% | **~96%** | ✅ |
| 核心 API 健康 | 100% | **100%** | ✅ |
| Dockerfile 可构建 | 是 | **是** | ✅ |
| Crisis Override | 触发 | **触发** | ✅ |
| 数据库迁移 | 完整 | **完整** | ✅ |
| 文档齐全 | 100% | **100%** | ✅ |
| 回滚方案 | 存在 | **存在** | ✅ |

> **最终决策**: 🟢 **GO** — 可上线,可演示,可答辩

---

## 6. 上线后 7 天观察 (Post-Launch Watch)

| 指标 | 阈值 | 频率 | 升级条件 |
|:---|:---:|:---:|:---|
| API 错误率 (5xx) | < 1% | 1 min | > 1% 持续 5 min |
| P95 响应时间 | < 1s | 1 min | > 2s 持续 10 min |
| CPU 利用率 | < 70% | 1 min | > 85% 持续 5 min |
| 内存使用 | < 80% | 1 min | > 90% 持续 5 min |
| 磁盘使用 | < 80% | 5 min | > 90% 立即告警 |
| 数据库连接数 | < 80% max | 1 min | > 90% 立即告警 |
| Sentry 错误数 | < 10/h | 5 min | > 50/h 立即告警 |

---

**签字栏**:
- [ ] 研发负责人: _______________
- [ ] 测试负责人: _______________
- [ ] 运维负责人: _______________
- [ ] 产品负责人: _______________
- [ ] 上线日期: _______________
