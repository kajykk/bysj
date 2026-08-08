# 心理健康风险评估系统（DWS）

一个面向高校场景的心理健康筛查与预警平台。项目围绕问卷、文本与生理信号的多模态风险评估展开，并补齐了异步任务、实时告警、模型治理、可观测性与安全合规等工程能力，适合作为“AI + 全栈 + DevOps”综合型个人作品集展示。

[架构文档](docs/architecture.md) · [审计报告](docs/FULL_AUDIT_REPORT.md) · [部署指南](docs/DEPLOYMENT_GUIDE.md) · [变更日志](CHANGELOG.md) · [Issues](https://github.com/kajykk/bysj/issues)

---

## 一眼看懂

- 面向高校心理健康筛查、预警与干预管理
- 前后端分离：FastAPI + Vue 3 + TypeScript
- 多模态评估：结构化问卷、文本分析、生理信号融合
- 事件驱动：WebSocket + Redis pubsub + Celery 异步任务
- 可观测性：Prometheus、Grafana、Sentry、OpenTelemetry
- 安全合规：PII 加密、CSP/XSS 防护、限流、审计与导出/删除支持

## 项目亮点

- 面向真实场景：围绕高校心理健康筛查、预警与干预闭环设计
- 多模态融合：结构化问卷、文本分析与生理信号协同评估
- 工程化完善：WebSocket、Redis pubsub、Celery、异步任务链路完整
- 模型治理到位：漂移检测、金丝雀发布、回滚与回退策略齐备
- 可观测性完整：Prometheus、Grafana、Sentry、OpenTelemetry、请求追踪
- 安全合规考虑充分：PII 加密、CSP/XSS 防护、限流、审计与导出/删除支持
- 测试覆盖全面：单元、集成、契约、E2E、性能与稳定性测试均已纳入

## 适合谁

- 需要做心理健康筛查、风险预警或干预管理的高校/机构
- 想看一个“AI + 全栈 + DevOps + 可观测性”完整落地样例的人
- 希望快速了解 FastAPI + Vue 3 + Celery + Redis + PostgreSQL 组合实践，并参考作品集表达方式的人

## 核心功能

- 用户、咨询师、管理员三角色工作台
- 风险评估、预警监控、报告导出与复盘闭环
- 异步任务调度、定时任务与告警处理
- 模型训练、实验、发布、回滚和状态管理
- 监控、告警、审计日志与运行状态可视化

## 为什么这个项目值得看

- 不是只有页面展示，而是把“筛查—预警—干预—复盘”流程做成了完整闭环
- 不只是调用模型，还考虑了回退策略、漂移检测、金丝雀发布与回滚
- 不只是开发功能，还把测试、监控、审计、部署和安全一并纳入交付范围
- 适合作为求职作品集、项目答辩材料或系统设计案例

## 技术栈

### 后端
- Python 3.12 · FastAPI · SQLAlchemy 2.0 · Pydantic 2
- PostgreSQL 15 / SQLite · Redis 7 · Celery 5.4 · Alembic
- scikit-learn · PyTorch（可选）· Transformers · NumPy / Pandas
- 多租户、审计、内容治理、告警与监控相关服务

### 前端
- Vue 3.5 · TypeScript 5.6 · Vite 6
- Element Plus · ECharts · Pinia · Vue Router
- Vitest · Playwright · Lighthouse CI

### 工程化
- Docker / docker-compose
- GitHub Actions
- Ruff · mypy · ESLint · Prettier · Codecov

## 快速开始

### 本地开发

```bash
git clone https://github.com/kajykk/bysj.git
cd bysj

# 后端
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux / Mac
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload

# 前端（新开终端）
cd frontend
npm install
npm run dev
```

- 后端地址：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`
- 前端地址：`http://localhost:5173`

### Docker 启动

```bash
docker-compose up -d
```

- 前端：`http://localhost:8080`
- 后端：`http://localhost:8000`
- Grafana：`http://localhost:3000`
- Prometheus：`http://localhost:9090`

## 默认账号

| 角色 | 用户名 | 密码 |
|---|---|---|
| 管理员 | admin | E2E@Admin123 |
| 咨询师 | dr_wang | E2E@Counselor123 |
| 普通用户 | user_moderate | E2E@User123 |

> 生产环境请务必修改默认密码。

## 测试

### 后端前置条件

- **Redis**：后端测试依赖本地 Redis（`redis://localhost:6379`）。未启动时会因连接重试/退避导致 pytest 挂起：

  ```bash
  docker run -d --name bysj-redis -p 6379:6379 redis:7-alpine   # 之后用 docker start bysj-redis
  ```

- **离线环境**：本机无法访问 HuggingFace 时，文本模型相关用例会因 `from_pretrained` 超时阻塞，运行前需设置：

  ```powershell
  $env:HF_HUB_OFFLINE="1"; $env:TRANSFORMERS_OFFLINE="1"
  ```

### 运行

```bash
cd backend
pytest -v

cd frontend
npm test
npm run test:e2e
npm run lighthouse:ci
```

### Grafana E2E（tests/e2e/test_grafana_e2e.py）

需对接运行中的 Grafana 与后端实例（默认 `localhost:3000` / `localhost:8000`）。本机 8000 端口被其他项目容器占用时，指向 dws 后端（本仓库容器在 8001），并注入凭证：

```powershell
$env:GRAFANA_PASSWORD="<Grafana admin 密码，区别于容器默认 admin/admin>"
$env:BACKEND_URL="http://localhost:8001"
$env:GRAFANA_SA_TOKEN="<从 Grafana API Keys 或 dws-backend 容器环境变量 GRAFANA_SERVICE_TOKEN 获取>"
python -m pytest tests/e2e/test_grafana_e2e.py -v
```

## 项目规模与成果

这个项目由我个人主导完成，AI 负责加速需求拆解、代码生成、测试补齐和文档整理，我负责架构判断、实现确认、联调修正和最终验收。

基于当前仓库内容，项目已经覆盖：

- FastAPI 后端与 Vue 3 前端完整联动
- 多模态风险评估、文本分析与生理信号处理
- 预警、静默、升级、导出和审计相关流程
- 模型训练、评估、回滚、漂移监控与金丝雀发布
- 可观测性、告警联动和仪表盘配置
- 大量单元、集成、契约、E2E 与稳定性测试

已知规模数据：

- 30+ 个 API 路由文件
- 55 个业务服务文件
- 53 个核心模块
- 39 张数据表
- 26 个 ML 文件
- 9 个 Docker 服务
- 契约测试全部通过
- 约 2000 条测试用例覆盖后端和前端

如果你只想快速了解项目，建议优先看：架构文档、审计报告和部署指南。

## 目录结构

```text
bysj/
├── backend/      # FastAPI 后端
├── frontend/     # Vue 3 前端
├── docs/         # 架构与审计文档
├── common/       # 跨端共享资源
├── scripts/      # 运维脚本
├── infra/        # 基础设施配置
├── monitoring/   # 监控配置
├── .github/      # CI/CD 工作流
├── docker-compose.yml
└── README.md
```

## 配置要点

复制 `.env.example` 为 `.env` 后，至少需要配置：

- `DATABASE_URL`
- `REDIS_URL`
- `JWT_SECRET_KEY`
- `PII_ENCRYPTION_KEY`
- `VITE_API_BASE_URL`

此外，仓库还包含后端、前端和基础设施的独立配置文件，适合按模块逐步启动和验证。

## 作者

**邝振华** · 数据科学与大数据技术 · 湖北商贸学院 · 2026 届

- Email：1754902912@qq.com
- GitHub：[@kajykk](https://github.com/kajykk)
- 求职意向：全栈开发实习生（AI 编程方向）
- 作品定位：个人独立完成的 AI 协作全栈项目作品集

## 说明

本项目的定位是“可运行、可验证、可演示”的个人作品集级完整系统示例。当前 README 侧重于 GitHub 首页展示，更多实现细节请见 `docs/`。
