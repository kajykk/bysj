# 🧠 心理健康风险评估系统 (Depression Warning System, DWS)

> 基于多模态 ML 融合 + 异步任务调度 + 全链路可观测性的生产级全栈系统
> **全程由 AI 编程工具 (Trae / Cursor / Claude Code) 独立完成开发与交付**

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org)
[![Vue 3.5](https://img.shields.io/badge/Vue-3.5-brightgreen.svg)](https://vuejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com)
[![Code with AI](https://img.shields.io/badge/Built%20with-Trae%20AI-ff6b6b.svg)](#-ai-全流程开发)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#-contributing)

[📖 架构文档](docs/architecture.md) · [📊 审计报告](docs/FULL_AUDIT_REPORT.md) · [🐛 提交 Issue](https://github.com/kajykk/bysj/issues) · [📝 变更日志](CHANGELOG.md)

---

## ✨ 项目简介

DWS 是一个面向高校的心理健康筛查与干预平台，针对传统人工筛查**覆盖率低、标准化不足、响应延迟**三大痛点，通过 AI 驱动的多模态风险评估引擎，将筛查→预警→干预→复盘全流程数字化、自动化。

| 维度 | 关键能力 |
|---|---|
| 🤖 多模态评估 | 结构化问卷 + 文本分析（BERT/TF-IDF）+ 生理信号三模态加权融合 |
| ⚡ 实时预警 | WebSocket + Redis pubsub 实时推送，告警生命周期管理（New→Confirmed→Fixing→Pending Review→Closed） |
| 🧠 模型治理 | 金丝雀发布 + 漂移检测（PSI/KL）+ 自动回滚（成功率<98%触发）+ 4 层回退策略 |
| 📊 可观测性 | Prometheus + Grafana 11.6 + Sentry + 分布式链路追踪 + Core Web Vitals |
| 🔒 合规安全 | GDPR 数据导出/被遗忘权 + PII Fernet 加密 + CSP/XSS/速率限制 + 路径遍历防护 |
| 🧪 全链路测试 | ~2000 测试用例（后端 860 + 前端 1111，单元/集成/契约/E2E/性能/稳定性），12 条 GitHub Actions 流水线 |

**项目规模**：24 个 API 路由 · 46 个核心模块 · 30+ 张数据表 · 33 个业务服务 · 27 个 ML 文件 · 9 个 Docker 服务 · 契约测试 100% 通过（620/620）

---

## 📸 系统截图

> 5 张关键页面展示，均为项目实际运行截图。源码位于 `frontend/src/views/`

### 1. 用户仪表盘

<img src="frontend/public/screenshots/01-user-dashboard.png" width="800" alt="用户仪表盘"/>

### 2. 多模态风险评估

<img src="frontend/public/screenshots/02-risk-assessment.png" width="800" alt="风险评估页面"/>

### 3. 实时预警监控

<img src="frontend/public/screenshots/03-real-time-warning.png" width="800" alt="实时监控"/>

### 4. ML 训练与实验中心

<img src="frontend/public/screenshots/04-model-training.png" width="800" alt="ML 训练与实验中心"/>

### 5. 报告中心（PDF/Excel 导出）

<img src="frontend/public/screenshots/05-report-center.png" width="800" alt="报告中心"/>

---

## 🛠️ 技术栈

### 后端
- **语言/框架**: Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) · Pydantic 2.7
- **数据库**: PostgreSQL 15 (生产) · SQLite (开发) · Alembic 迁移
- **缓存/Broker**: Redis 7（缓存 + Celery broker + WebSocket pubsub）
- **异步任务**: Celery 5.4 + Celery Beat
- **ML**: scikit-learn 1.8 · PyTorch (可选) · Transformers (BERT) · NumPy/Pandas
- **可观测性**: Prometheus · Grafana 11.6 · Sentry SDK · OpenTelemetry

### 前端
- **框架**: Vue 3.5 (Composition API) · TypeScript 5.6 · Vite 6
- **UI 库**: Element Plus 2.8 · ECharts 5.5
- **状态/路由**: Pinia · Vue Router 4
- **PWA**: vite-plugin-pwa · Workbox
- **测试**: Vitest · Playwright · Lighthouse CI

### DevOps
- **容器化**: Docker + docker-compose（9 个服务）
- **CI/CD**: GitHub Actions（12 条流水线：contract-tests / e2e / lighthouse / coverage / 容器扫描 / 依赖扫描）
- **质量门禁**: ESLint · Prettier · Ruff · mypy · Codecov

---

## 🤖 AI 全流程开发

> **对齐岗位加分项**：使用 AI 工具完整交付至少一个模块或项目
> **对齐岗位要求**：AI 编码工具重度用户 · 端到端全栈交付 · 从想法到上线的全过程加速

**本项目最大亮点：使用 Trae AI 编程工具 + 个人 Skill 库独立完成从需求到上线的全流程开发**

### 工具栈

| 工具 | 角色 | 典型场景 |
|---|---|---|
| **Trae IDE** | 主开发环境 | Skill 化 Prompt、Agentic Workflow、内置 Agent 调度 |
| **Cursor** | 代码生成/重构 | 跨文件重构、批量修改、智能补全 |
| **Claude Code** | 复杂逻辑推理 | 架构设计、代码审查、长上下文任务 |
| **GitHub Copilot** | 实时补全 | 单元测试模板、Boilerplate 代码 |

### 个人 Skill 库（`.trae/skills/`）

基于项目实践沉淀的 30+ 个 AI 协作 Skill，让 AI 不是"补全工具"而是"工程伙伴"：

- **Ralph 系列**: 6 阶段规划（需求 → 架构 → 任务 → 实现 → 测试 → 验收）
- **Sysopt 系列**: 5 维度系统优化（性能/稳定性/可维护性/资源/安全）
- **Superpowers 系列**: 12 个工程方法论 Skill（brainstorming / TDD / verification 等）
- **设计/美化系列**: 8 个前端设计 Skill（minimalist / brutalist / taste 等）
- **审计协调器**: 6 阶段审计闭环（准备 → 静态审查 → 功能走查 → 专项审查 → 修复回归 → 验收交付）

### 六阶段 AI 驱动开发流程

```
需求拆解 (Brainstorming) → 架构设计 (C4 + ADR) → 任务规划 (Atomic Tasks)
       ↓
实现 + 测试 (TDD + Schemathesis) → 审计 (Multi-Dim) → 验收 (E2E + Lighthouse)
```

### AI 工具关键贡献案例

- 🛡️ **安全审计闭环**: AI 驱动 6 阶段审计发现 164 个问题，关闭 121 个（P0/P1/P2 全部清零），详见 [审计状态文档](docs/planning/v1.40-audit-beautify/AUDIT_STATE.md)
- 🔄 **金丝雀发布引擎**: AI 辅助完成 200+ 行 ML 治理代码，含 PSI/KL 漂移检测、自动回滚、断路器熔断
- 📊 **可观测性集成**: AI 设计 Prometheus metrics schema + Grafana dashboard JSON + Sentry 告警规则
- 🧪 **契约测试修复**: AI 修复 Schemathesis 契约测试，从大量失败提升到 100% 通过（620/620）
- 🎨 **前端性能优化**: AI 辅助虚拟列表、懒加载、骨架屏，Lighthouse Performance 35→98、Accessibility 100
- 🔒 **安全修复**: 路径遍历防护、TOCTOU 竞态修复（原子 UPDATE）、PII Fernet 加密、Dropout 线程安全

### 交付质量证据

| 维度 | 指标 | 证据 |
|---|---|---|
| 测试覆盖 | 后端 860 + 前端 1111 = ~2000 用例 | `pytest` + `vitest` 全通过 |
| 契约测试 | 620/620 = 100% | Schemathesis 契约验证 |
| 审计闭环 | 164 问题 / 121 关闭 / P0-P2 清零 | [AUDIT_STATE.md](docs/planning/v1.40-audit-beautify/AUDIT_STATE.md) |
| 性能验收 | Lighthouse Performance 98 / A11y 100 | FCP 0.8s / LCP 1.0s / TBT 10ms |
| 手工回归 | 37/37 API 测试通过 | 3 角色登录 + 业务流 + 权限隔离 |
| 越权测试 | 跨角色访问全部 403 | User→Admin / Counselor→Admin 等 |

---

## 🚀 快速开始

### 前置依赖

- Python 3.12+
- Node.js 20+
- npm 10+
- (可选) Docker + Docker Compose

### 方式 A：本地开发模式

#### 1. 克隆仓库
```bash
git clone https://github.com/kajykk/bysj.git
cd bysj
```

#### 2. 启动后端
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt

# 复制环境变量模板
cp .env.example .env
# 编辑 .env 填入数据库连接等

# 启动开发服务器
uvicorn app.main:app --reload
```

后端服务将运行在 `http://localhost:8000`，API 文档：`http://localhost:8000/docs`

#### 3. 启动前端
```bash
cd frontend
npm install
npm run dev
```

前端将运行在 `http://localhost:5173`

### 方式 B：Docker 一键启动

```bash
docker-compose up -d
```

启动后访问：
- 前端: `http://localhost:8080`
- 后端: `http://localhost:8000`
- Grafana: `http://localhost:3000`（admin/admin）
- Prometheus: `http://localhost:9090`

### 默认账号

| 角色 | 用户名 | 密码 |
|---|---|---|
| 管理员 | admin | E2E@Admin123 |
| 咨询师 | dr_wang | E2E@Counselor123 |
| 普通用户 | user_moderate | E2E@User123 |

⚠️ **生产环境请务必修改默认密码**

---

## 🏗️ 架构

### 系统架构图（C4 Level 2 - Container）

```
┌──────────────────────────────────────────────────────────┐
│  Frontend (Vue 3 + TS)        │  Nginx (reverse proxy)  │
│  Port 5173                    │  Port 80/443            │
└────────────┬──────────────────┴──────────────┬───────────┘
             │                                 │
             ▼                                 ▼
┌─────────────────────────────────────────────────────────┐
│  Backend (FastAPI + async)                              │
│  Port 8000                                               │
│  - 24 API endpoints                                      │
│  - 33 business services                                  │
│  - 46 core modules                                       │
└─────┬─────────────┬─────────────┬──────────────┬────────┘
      │             │             │              │
      ▼             ▼             ▼              ▼
  ┌──────┐    ┌──────────┐   ┌────────┐    ┌──────────┐
  │ PG15 │    │ Redis 7  │   │Celery  │    │ ML Stack │
  │      │    │(cache+pubsub)│  Worker│    │(sklearn  │
  │      │    │          │   │        │    │ +BERT)   │
  └──────┘    └──────────┘   └────────┘    └──────────┘
                                                    │
      ┌─────────────────────────────────────────────┘
      ▼
  ┌─────────┐   ┌────────┐   ┌─────────┐
  │Prometheus│ → │Grafana │ ← │ Sentry  │
  └─────────┘   └────────┘   └─────────┘
```

完整 C4 模型（Context / Container / Component / Code）见 [docs/architecture/](docs/architecture/)。

---

## 📂 项目结构

```
bysj/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/            # 24 个 API 路由
│   │   ├── core/              # 46 个核心模块（配置、鉴权、断路器等）
│   │   ├── services/          # 33 个业务服务
│   │   ├── schemas/           # Pydantic Schema
│   │   ├── ml/                # 27 个 ML 文件（融合、漂移、回退）
│   │   ├── tasks/             # Celery 异步任务
│   │   └── main.py
│   ├── tests/                 # 测试（~860 用例）
│   │   ├── api/              # API 集成测试
│   │   ├── contract/         # Schemathesis 契约测试
│   │   ├── ml/               # ML 单元测试
│   │   └── e2e/              # 端到端测试
│   ├── alembic/              # 数据库迁移
│   ├── requirements.txt
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/                  # Vue 3 前端
│   ├── src/
│   │   ├── api/              # API 客户端
│   │   ├── components/       # 通用组件
│   │   ├── views/            # 页面（用户/咨询师/管理员）
│   │   ├── stores/           # Pinia 状态管理
│   │   ├── router/           # Vue Router
│   │   ├── i18n/             # 国际化（中/英）
│   │   └── composables/      # 组合式函数
│   ├── tests/                # Vitest + Playwright
│   ├── package.json
│   └── vite.config.ts
├── docs/                      # 项目文档
│   ├── architecture/         # C4 架构图
│   ├── api/                  # API 文档
│   └── planning/             # 规划文档
├── .github/workflows/         # 12 条 CI 流水线
├── .trae/                     # Trae AI Skill 库
├── docker-compose.yml
├── README.md                  ← 你正在读
├── LICENSE                    # MIT
└── CHANGELOG.md
```

---

## 🧪 测试

```bash
# 后端单元/集成测试
cd backend
pytest -v

# 后端契约测试（Schemathesis）
pytest tests/contract/ -v

# 前端单元测试
cd frontend
npm test

# 前端 E2E（Playwright）
npm run test:e2e

# 性能测试（Lighthouse CI）
npm run lighthouse:ci

# 全套测试
npm run test:all
```

**测试覆盖**：
- 后端：单元 + 集成 + 契约（100% 通过率，620/620）+ 性能 + 稳定性
- 前端：单元（Vitest 1111 通过）+ E2E（Playwright）+ Lighthouse

---

## 📊 性能指标

| 指标 | 数值 |
|---|---|
| API 平均响应时间 | < 100ms (P95 < 500ms) |
| 风险评估端到端延迟 | < 2s |
| 实时预警推送延迟 | < 200ms |
| 前端首屏加载（FCP） | 0.8s |
| LCP（最大内容绘制） | 1.0s |
| TBT（总阻塞时间） | 10ms |
| Lighthouse 评分 | Performance 98 / Accessibility 100 / Best Practices 100 |
| 并发能力 | 1000+ QPS（Locust 压测） |

---

## 🤝 Contributing

欢迎贡献！流程：

1. Fork 本仓库
2. 创建 feature 分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

请确保：
- 通过所有 CI 检查（lint / type / test / contract）
- 补充新功能的测试用例
- 更新相关文档

---

## 📜 License

本项目采用 [MIT License](LICENSE) 开源。

---

## 👤 作者

**邝振华** · 数据科学与大数据技术 · 湖北商贸学院 · 2026 届

- 📧 Email: 1754902912@qq.com
- 📱 Phone: 15623089361
- 🐙 GitHub: [@kajykk](https://github.com/kajykk)

**求职意向**：全栈开发实习生（AI 编程方向）· 可实习时长 6 个月（满足 ≥3 个月全职要求）

---

## 🙏 致谢

- 感谢 [FastAPI](https://fastapi.tiangolo.com) / [Vue.js](https://vuejs.org) / [Element Plus](https://element-plus.org) 等优秀开源项目
- 感谢 [Trae IDE](https://trae.ai) 提供的 AI 编程能力支持
- 感谢所有为本项目贡献代码和反馈的同学

---

<p align="center">
  <sub>🤖 本项目 95%+ 代码由 AI 编程工具辅助生成，质量由人类工程师把关</sub>
</p>
