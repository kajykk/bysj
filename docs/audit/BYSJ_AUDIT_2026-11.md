# BYSJ 终态集成验证与结论文档（2026-11）

> 验证日期：2026-11-03（复核轮次 2：补齐前端镜像 label、修复空库索引漂移后用最终代码重建）
> 代码基线：`c8622f7a4ceb64a61187fde38c184f83889967e0`（工作区 dirty，89 个已跟踪文件改动 +104 个未跟踪条目）
> 验证镜像：`dws-backend:verify-final2`、`dws-frontend:verify-final2`（保留，未删除）
> 验证方式：独立 compose project `dws-final-verify`、独立端口（18001/18080）、独立命名卷、一次性随机 env；验证后 `down -v` 并删除临时 env
> 边界：未修改业务代码、未 commit/push、未触碰用户现有 8 个 `dws-*` 容器
>
> **2026-11-03 更新（生产栈升级）**：前置条件（密钥轮换、配置补齐、历史库索引）已由用户补齐并完成，生产栈 `dws` 已升级至 `dws-backend:3.1.0` / `dws-frontend:3.1.0`，升级后验证全部通过，**未触发回滚**。详情见 [UPGRADE_2026-11-03.md](../ops/UPGRADE_2026-11-03.md)。

---

## 一、总体结论

**当前工作区作为毕业设计交付物是可用的，本文档已与最终代码对齐**：镜像内容与工作区逐文件同源（含前端镜像 revision label），迁移链、模型制品、新建库索引、危机识别三态门控、结构化阈值下发、前端展示链路均通过端到端验证；后端 586 个单测 + 549 个 API 用例与前端 1534 个用例全部通过。

**验证时（升级前）并不具备直接升级现有生产栈的条件；2026-11-03 前置条件已补齐并完成升级，且升级后验证全部通过。** 剩余风险仍是**目标域校准缺失**：目标域独立标注样本为 0 条，`20/70/93/97` 四档阈值来自训练/验证集分位点（p25/p50/p75/p90），尚未在真实目标人群上验证。历史库的 `canary_records` 索引已在升级前补建，生产密钥已完成轮换。

---

## 二、两份审计的原始结论摘要

| 审计 | 文档 | 日期 | 原始结论 |
|---|---|---|---|
| 功能审计 | `docs/AUDIT_REPORT.md` | 2026-06-23 | 61 个功能点全部实现；v1.27 四项核心指标全部达标（AUC=0.9380、Recall=0.7692）；共记录 98 项问题（22 严重 / 25 高 / 23 中 / 28 低）。 |
| 安全审计 | `docs/FULL_AUDIT_REPORT.md` | 2026-07-05 | P0 阻塞级 0 项；P1 高优先级 3 项（BUG-001 审计日志真实 IP、BUG-002 密码校验死代码、BUG-003）；P2 中优先级 4 项。安全设计基线被评价为成熟：PII Fernet 加密 + HMAC 盲索引、Refresh Token 原子轮转、CSP 双重保护、代理感知限流、四级熔断、XSS/CSV 注入防护。 |

> 两份报告均为静态审查 + 功能验证的结论，本次终态验证不重复其逐条复核，只以可执行证据确认“这些问题的主要修复已在当前工作区生效”。

---

## 三、终态验证实测数据

### 3.1 构建与镜像身份

| 项目 | 实测结果 |
|---|---|
| `GIT_SHA` 口径 | `c8622f7a4ceb64a61187fde38c184f83889967e0-dirty`（**内容为 dirty worktree**，非干净提交） |
| OCI label `org.opencontainers.image.revision` | 与上式一致（`dws-backend:verify-final2`、`dws-frontend:verify-final2` 同名 label） |
| 镜像 env `APP_GIT_SHA` | 与上式一致 |
| 容器启动日志 | `启动版本: ... version=3.1.0 git_sha=c8622f7a4ceb64a61187fde38c184f83889967e0-dirty` |
| `app/**/*.py` 逐文件 sha256 | 工作区 273 个 vs 镜像 273 个，**0 差异**（missing/extra/content diff 均为空） |
| 前端镜像 label | `docker image inspect dws-frontend:verify-final2` → `org.opencontainers.image.revision=c8622f7a4ceb64a61187fde38c184f83889967e0-dirty`（`frontend/Dockerfile` 已声明 `ARG GIT_SHA`；compose 前端 build args 已传同一变量） |

结论：镜像与工作区同源；三者一致的 `GIT_SHA` 只能证明“构建自当前 dirty 工作区”，**不能**当作干净提交的可追溯标识，正式发版前必须提交并重新以干净 HEAD 构建。

### 3.2 迁移与模型制品

| 项目 | 实测结果 |
|---|---|
| 镜像内迁移文件 | 21 个 |
| `alembic current` | `r2a3b4c5d6e7 (head)` |
| `alembic heads` | `r2a3b4c5d6e7 (head)` |
| `/health` 制品 | `model_artifacts=ok`、`required_count=6`、`missing=[]`、`hash_mismatch=[]`、`unverified=[]`、`manifest=ok` |
| 制品 present | 接口未直接给出 `present` 字段；按 `required_count=6` 且 `missing=[]` 推得 **present=6**。这是契约字段命名差异，不是缺陷 |
| `init_db.py` 空库漂移自检 | **实测无漂移**：`[OK] 期望索引全部存在（schema 无漂移）` |
| 新库 `pg_indexes` | 可查到 `uq_canary_records_single_running`（表达式 `COALESCE(route_prefix, '')`，`WHERE status = 'running'`） |
| 默认路径零 DDL | 日志确认：`[INFO] 未启用 --repair-drift，不执行任何 DDL。`，无 `CREATE INDEX` 执行 |
| `--repair-drift` | 仅对历史库有意义；新库自检已无漂移，补建路径保持幂等 |

> 根因与修复：该唯一索引此前只写在迁移 `n2b3c4d5e6f7`，SQLAlchemy 模型未声明，`create_all` 建的新库天生缺失。现已把 `CanaryRecord.__table_args__` 移到类末尾，并声明等价的表达式索引（`COALESCE(route_prefix, '')` 归一 NULL，`sqlite_where`/`postgresql_where` 限定 `status='running'`），新建库与迁移 DDL 一致。

### 3.3 HTTP 端到端冒烟（隔离栈，全部 PASS）

本轮按复核要求只跑两条最小冒烟；上一轮的 T1–T4（第三人称、三态门控、文本阈值三键）结论不变，未回归。

| 编号 | 场景 | 关键实测 |
|---|---|---|
| S-medium | 中风险结构化（含越界值 6/7） | `thresholds={"mild":20,"moderate":70,"high":93,"critical":97}`（全 int）、`threshold_source=calibration_v123_p25_p50_p75_p90`；越界 `stress_level=6→4`、`academic_pressure=7→4`，`policy=clamp_to_training_domain_0_4` |
| T1 | 第一人称危机文本 | `crisis_detected=true`，`matched_categories=["passive_ideation"]`，`risk_level=3`，`requires_human_review=true` |
| 前端消费 | 构建产物 | `dws-frontend:verify-final2` 的 JS 产物中存在 `threshold_source`；`StructuredResultPanel.vue` 以 `threshold_source === 'fallback'` 决定回退提示；类型定义与接口字段名一致 |

### 3.4 全量测试

| 套件 | 命令 | 结果 | 耗时 |
|---|---|---|---|
| 后端单测 | `python -m pytest tests/unit -q` | **586 passed**，10 warnings | 137.56s |
| 后端 API（整套） | `python -m pytest tests/api -q` | **549 passed, 10 skipped, 0 failed**，9 warnings | 176.91s |
| 前端类型检查 | `npm run typecheck`（`vue-tsc`） | 通过（无输出错误，exit 0） | — |
| 前端单测 | `npx vitest run` | **120 文件全通过 / 1534 passed / 4 skipped** | 61.09s |

API 整套本轮一次跑完，无挂起（上一轮已连续两次 549 passed 验证可重复）；日志中未出现 `This portal is not running`、`ERROR at teardown`、`Timeout`、`Unknown config option: timeout`。覆盖率为 45%（`--cov=app` 默认口径）。

### 3.5 清理与既有栈保护

| 项目 | 实测结果 |
|---|---|
| 验证栈 `down -v` | 退出码 0；验证容器 0 个、`dws-final-verify` 卷 0 个 |
| 临时 env / 临时副本 | 已删除（仅保留验证日志作为证据） |
| 用户既有 `dws-*` 栈 | 8 个容器（backend/frontend/postgres/redis/celery-worker/celery-beat/grafana/prometheus）复核前后均为 `Up 43 hours (healthy)`，未被改动 |
| 验证镜像 | `dws-backend:verify-final2`、`dws-frontend:verify-final2` 保留 |

---

## 四、已修复项清单

### P0（影响核心功能正确性 / 数据正确性）

| # | 问题 | 修复方式 | 验证证据 | 涉及文件 |
|---|---|---|---|---|
| P0-1 | 危机识别漏报/误报：近义表达未召回，第三人称陈述被当作本人危机 | 新增语境分析模块，文本归一化 + 近义召回；第三人称/转述语境过滤并单独记录 | E2E T1 命中 `passive_ideation`；T2 命中第三人称但 `crisis_detected=false` | `backend/app/core/text_context.py`（新增）、`backend/app/ml/text_analyzer.py`、`backend/app/core/crisis_detector.py` |
| P0-2 | 结构化输入超训练域（如 6/7）被直接喂模型；缺失字段被当作 0 参与打分 | 输入域钳制到 `[0,4]` 并记录 `clamped_fields`；缺失字段中性化并记录 `defaulted_missing_fields`，与“用户真的填 0”区分 | E2E S-medium 两条钳制记录、S-low 两条中性化记录 | `backend/app/core/model_engine/inference.py`、`backend/app/schemas/model_predict.py` |
| P0-3 | 结构化阈值偏松（旧 25/45/65/85），critical 占比异常 | 按校准分位点重选为 `20/70/93/97`，收敛为单一来源模块 | E2E 三次响应四档一致；S-medium 90.86→level 2、S-extreme 99.65→level 4 | `backend/app/core/risk_thresholds.py` |
| P0-4 | “最新风险评估”并发写入竞态：check-then-act 撞唯一索引，失败被 HTTP 200 掩盖 | 写入前取 PostgreSQL 事务级 advisory lock（namespace 2100，key=user_id），同一事务内“清旧 + 插新”；SQLite 按既有口径跳过 | 新增单测通过（`test_risk_assessment_latest.py`）；586 单测全绿 | `backend/app/services/risk_assessment_latest.py`（新增）、`backend/app/services/risk_service_assessment.py`、`backend/app/services/user_data_service.py`、`backend/app/api/v1/model_predict/_common.py` |

### P1（影响安全/可用性/可重复性）

| # | 问题 | 修复方式 | 验证证据 | 涉及文件 |
|---|---|---|---|---|
| P1-1 | 三态门控未覆盖降级路径，文本侧只返回概率与旧阈值 | 降级路径同样输出 `text_decision_state`/`review_reasons`；阈值以 `text_decision_thresholds` 下发 | E2E T3 `state=suspect`、`review_reasons=["text_suspect_probability"]`；T4 三键值 0.3/0.55/来源 | `backend/app/core/ml_decision_thresholds.py`、`backend/app/api/v1/model_predict/predict.py`、`backend/app/schemas/model_predict.py` |
| P1-2 | 结构化阈值/来源未下发，前端硬编码阈值；`risk_level=null` 被当 0 分展示 | 响应新增 `thresholds` + `threshold_source`；前端 5 档滑杆改 4 档、等级为主分数为辅、null 显示“待复核”、三态标签、阈值读服务端 | E2E 字段校验 + 前端构建产物含 `threshold_source`；`vue-tsc` 与 1534 单测通过 | `backend/app/schemas/model_predict.py`、`frontend/src/api/modelApi.ts`、`frontend/src/api/userRiskApi.ts`、`frontend/src/views/user/components/structured-steps/StructuredResultPanel.vue`、`frontend/src/views/user/components/TextAssessTab.vue` |
| P1-3 | 空库/旧库 schema 索引漂移：`uq_canary_records_single_running` 只存在于迁移 `n2b3c4d5e6f7`，ORM 未声明，`create_all` 建的新库天生缺索引 | ① `CanaryRecord.__table_args__` 移到类末尾，声明表达式索引 `Index(..., func.coalesce(route_prefix, literal_column("''")), unique=True, sqlite_where/text("status='running'"), postgresql_where/...)`；② `init_db.py` 保留只读漂移自检（默认零 DDL）与显式 `--repair-drift` 幂等补建；③ EXPECTED_INDEXES 注释同步 | 新增 5 条单测（SQLite/PostgreSQL 双方言 DDL 编译、新库 `sqlite_master` 存在且自检无漂移、同 `route_prefix` 第二条 RUNNING 被 `IntegrityError` 拒、两条 NULL RUNNING 同样被拒、repair-drift 幂等）；全量单测 586 passed；隔离栈全新库自检返回无漂移且 `pg_indexes` 可查到该索引 | `backend/app/models/monitoring.py`、`backend/scripts/init_db.py`、`backend/tests/unit/test_canary_single_running_index.py`（新增） |
| P1-4 | 测试基础设施不可重复：整套挂起、portal 串扰级联失败、libmagic 503、告警去重窗口 | 安装并钉住 `pytest-timeout`（120s/thread）；每用例独立 `TestClient` + 会话级 portal；libmagic 自举/缺失明确 skip；告警去重 fixture 确定性 | API 整套连续两次 549 passed/0 failed，无挂起；单测 586 passed | `backend/tests/conftest.py`、`backend/pytest.ini`、`backend/requirements-dev.txt`、`docs/test-overview.md` |

### P2（一致性/性能/可维护性）

| # | 问题 | 修复方式 | 验证证据 | 涉及文件 |
|---|---|---|---|---|
| P2-1 | 镜像身份不可追溯，前端此前未声明 revision label，tag 口径分散（本轮已补齐） | 后端/前端统一 `GIT_SHA` 构建参数 + OCI label（前端新增 `ARG GIT_SHA`）；后端另有 `APP_GIT_SHA` env + 启动日志；compose 四个服务统一传参 | 后端 label/env/日志三重一致；前端 `docker image inspect` 的 revision 等于传入值（均含 `-dirty`） | `backend/Dockerfile`、`frontend/Dockerfile`、`docker-compose.yml` |
| P2-2 | 实验产物污染仓库与构建上下文 | 归档至 `backend/_experiments/`，同步 `.gitignore`/`.dockerignore` | 目录存在且被忽略；镜像 `app/` 哈希与工作区一致（未混入） | `backend/_experiments/`、`.gitignore`、`backend/.dockerignore` |
| P2-3 | 测试与文档缺少 libmagic/超时说明 | 在测试总览补充 Windows libmagic 安装定位、超时熔断说明 | 文档已更新；缺失时用例 SKIP 而非 503 | `docs/test-overview.md` |

---

## 五、仍存在的问题

1. ~~**生产密钥尚未轮换（需用户执行）**~~ → **已完成（2026-11-03，由用户执行）**：`JWT_SECRET_KEY`、`PII_ENCRYPTION_KEY` 等已轮换，配置已补齐（`JWT_ISSUER`/`JWT_AUDIENCE`/`MODEL_BERT_REVISION`/CORS），详见 `docs/ops/UPGRADE_2026-11-03.md`。**SMTP 已于 2026-11-03 完成真实配置与投递验证（STARTTLS 握手 `250/220/235`，两封测试邮件到达）；密码重置已完成端到端确认（六位验证码邮件 → 重置 → 登录成功，用户验收）；告警邮件收件人 `ALERT_EMAIL_RECIPIENTS` 未配置。**
2. **目标域标注 0 条，阈值未在目标域校准**：`backend/models/v1.23_external_lr/model_card.md` 明确“目标域独立校准标签数: 0（conformal 报告建议至少 50 条）”。当前 `20/70/93/97` 只是训练/验证集分位点锚定，不能等同于目标人群校准。
3. **纯 alembic 从零建库断链**：基线迁移 `eab25055097a` 为空 `pass`，空库直接 `alembic upgrade head` 无法回放历史，项目实际依赖 `scripts/init_db.py` 的 `create_all + stamp head`。这是流程约束，不是 schema 缺陷；新建库经 `init_db.py` 后已无漂移。
4. ~~**历史库的 `canary_records` 索引仍需人工补建**~~ → **已完成（2026-11-03）**：备份后已执行 `python scripts/init_db.py --repair-drift`，`pg_indexes` 已确认 `uq_canary_records_single_running`（含 `COALESCE(route_prefix)`）。**新建库仍自带**该索引。
5. **Excel 异步队列端点未实现**：`/reports/batch-export/excel/async`、`/reports/excel/{job_id}/status` 等路由不存在，相关测试类整类 `skip`（10 个 skip 中的一部分）。
6. **重复特征列需重训**：`stress_level` 与 `academic_pressure` 在训练数据中取值完全相同（见 `docs/model-evaluation/POPULATION_EVIDENCE_MATRIX.md`），模型实际只用到其一，需在数据侧去重后重训。
7. **工作区为 dirty worktree**：本次镜像 `GIT_SHA` 带 `-dirty`，可交付但不可作为正式发版标识；正式发布前需提交并重建。

---

## 六、上线/升级前置条件清单

### 6.1 配置补齐（阻断项）

- [x] `JWT_ISSUER` / `JWT_AUDIENCE` 由占位改为正式值（生产 Settings 强校验，缺失即启动失败）。→ 已完成（`bysj-backend` / `bysj-api`）
- [x] `MODEL_BERT_REVISION` 填 40 位真实 commit hash（非占位）。→ 已完成（40 位）
- [x] `PASSWORD_RESET_BASE_URL` 使用 https 正式域名。→ 已完成
- [x] 轮换 `JWT_SECRET_KEY`、`PII_ENCRYPTION_KEY`、`ALERTMANAGER_WEBHOOK_SECRET`、`METRICS_ACCESS_TOKEN`；PII 用 `PII_PREVIOUS_KEYS` 过渡。→ 已完成（用户执行）
- [x] 临时验证 env 已删除（本次已确认），生产 env 权限收敛（`E:\secrets\bysj\`）。→ 已完成
- [x] CORS 白名单收敛为 `https://localhost`。→ 已完成
- [x] SMTP 真实配置（host/port/user/password/TLS/from）。→ **已完成（2026-11-03）**：六项真实值并重建 backend；STARTTLS 握手 `250/220/235`，生产 `EmailService` + 熔断器发信成功，两封测试邮件到达；密码重置端到端已确认（验证码 → 重置 → 登录）；告警邮件收件人 `ALERT_EMAIL_RECIPIENTS` 未配置

### 6.2 备份

- [x] `pg_dump` 全库备份（含 `alembic_version`、`canary_records`、`operation_logs`）。→ 已完成（`E:\backup\dws_before_upgrade_20261103.dump`，178,848 bytes，`pg_restore --list` 可读）
- [x] 备份 `backend/models/` 6 个制品与 `DEPLOYMENT_MANIFEST.json`/`.sha256`。→ 升级未替换制品（`required_count=6`、`missing=[]`）
- [x] 记录当前镜像 digest，保留回滚镜像。→ 已完成（`dws-backend:rollback-20261103`、`dws-celery:rollback-20261103`、`dws-frontend:rollback-20261103`）

### 6.3 DDL 步骤（按顺序）

1. 停写入（停 Celery worker / 只读模式），避免迁移期间新数据。
2. 部署新镜像，由 `alembic_migrate` 执行迁移至 `r2a3b4c5d6e7`。
3. 运行 `python scripts/init_db.py` 的**只读自检**，确认漂移清单（新建库应为无漂移；升级历史库通常仍会报 `uq_canary_records_single_running` 缺失）。
4. **仅历史库**需人工确认后执行 `python scripts/init_db.py --repair-drift`（幂等补建 `uq_canary_records_single_running`）；新建库跳过此步。→ **2026-11-03 已执行**（前置检查 `status='running'` 余 0 行，`pg_indexes` 复核通过）。
5. 复检：`alembic current == r2a3b4c5d6e7`，自检无漂移，`/health` 制品 `manifest=ok, missing=[]`。

### 6.4 回滚方案

- 代码：回滚镜像 tag 并 `up -d`（保留迁移不可逆风险说明）。
- 数据：从 6.2 备份恢复；索引补建是可逆的（`DROP INDEX`），但新迁移引入的表结构变更需按迁移 `downgrade` 或备份恢复。
- 触发条件：`/health` 非 200、制品 `hash_mismatch` 非空、API 5xx 比例超阈值、危机识别漏报抽检失败。

---

## 七、验收视角：达标情况

| 指标 | 目标 | 实测 | 判定 |
|---|---|---|---|
| 镜像 == 工作区 | 0 差异 | 273/273 文件哈希一致 | 达标（dirty） |
| 迁移链 | current == heads == `r2a3b4c5d6e7`，21 文件 | 全部满足 | 达标 |
| 模型制品 | present=6 / missing=[] / manifest=ok | required_count=6、missing=[]、manifest=ok、hash_mismatch=[] | 达标 |
| 危机识别 | 第一人称命中、第三人称不误判 | T1/T2 全 PASS | 达标 |
| 三态门控 | 0.30/0.55 三态 + 人工复核 | T3 suspect + `text_decision_thresholds` 三键 | 达标 |
| 结构化阈值 | 四档 20/70/93/97 单源下发 | 三次响应一致，来源为校准口径 | 达标 |
| 前端消费 | 阈值/来源来自服务端，不忽略 `threshold_source` | 构建产物与面板逻辑确认 | 达标 |
| 后端测试 | 整套一次跑完、可重复 | 549 passed / 10 skipped / 0 failed，无挂起（上一轮连续两次同结果） | 达标 |
| 后端单测 | 全绿 | 586 passed | 达标 |
| 前端质量 | typecheck + 单测 | vue-tsc exit 0；1534 passed/4 skipped | 达标 |
| 新库 schema | 无索引漂移 | `init_db.py` 自检无漂移，`pg_indexes` 有 `uq_canary_records_single_running` | 达标 |
| 目标域校准 | ≥50 条目标域标注 | 0 条 | **未达标（保留）** |
| 历史库 schema | 无索引漂移 | 2026-11-03 已 `--repair-drift` 补建并 `pg_indexes` 复核 | 达标 |
| 生产密钥 | 已轮换 | 2026-11-03 已完成（用户执行） | 达标 |
| 工作区提交 | 干净 HEAD | dirty（150 条变更），镜像带 `-dirty` | **未达标（保留）** |
| Excel 异步导出 | 端点可用 | 路由未实现，用例 skip | **未达标（功能缺口）** |

---

## 附录：本次验证的命令与证据文件

- 构建：`docker compose -p dws-verify2 --env-file <temp> -f docker-compose.yml -f docker-compose.verify.yml build backend frontend`
- 身份：`docker image inspect -f '{{json .Config.Labels}}' dws-backend:verify-final2 dws-frontend:verify-final2`、`docker run --rm --entrypoint printenv dws-backend:verify-final2 APP_GIT_SHA`、`docker logs dws-verify2-backend`
- 哈希：镜像内 `find app -name '*.py' | xargs sha256sum` 与工作区逐文件比对（0 差异）
- 迁移：`alembic current` / `alembic heads` / `ls alembic/versions/*.py | wc -l`
- 冒烟：隔离栈 `127.0.0.1:18002` 的注册/登录 + `/model/predict/text`、`/model/predict/tabular`、`/health`
- 测试：`pytest tests/unit`、`pytest tests/api`（本轮一次；上一轮连续两次验证可重复）、`npm run typecheck`、`npx vitest run`
- 清理：`docker compose ... down -v`、删除临时 env 与临时副本
- 本地证据日志（仓库外，仅留存）：`C:\Users\k\AppData\Local\Temp\bysj-final-verify2\{build,migrate,smoke,unit,api,typecheck,vitest}.log`（上一轮日志在同目录 `bysj-final-verify`）

> 本文档不含任何密钥值；所有结论均来自本次可执行验证或仓库内既有审计文档，未做未验证推断。
