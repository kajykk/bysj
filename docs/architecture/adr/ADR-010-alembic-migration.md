# ADR-010: 使用 Alembic 而非 SQLAlchemy create_all 进行数据库迁移

## 状态 (Status)
Accepted

## 日期 (Date)
2026-07-03

## 上下文 (Context)
DWS 系统数据库涉及 30+ 张表, 包含:
- PII 加密字段 (email/phone/emergency_*) 与对应的 `email_hash` 索引列;
- 多种枚举类型 (risk_level、alert_status、intervention_state、crisis_event_state);
- 复合外键约束与 `ON DELETE` 策略 (例如 crisis_event → user, alert → user);
- 多列复合索引 (operation_logs 的 (user_id, created_at) 等);
- 跨环境兼容: 开发环境 SQLite、测试环境 PostgreSQL、生产环境 PostgreSQL。

随着迭代推进 (v1.0 → v1.40), schema 持续演进, 几乎每个版本都涉及表结构变更。需求:
1. **版本化**: 每次 schema 变更可追溯, 可回滚到任意历史版本;
2. **CI/CD 自动执行**: 部署流水线自动 `alembic upgrade head`, 无需人工 SQL;
3. **多环境一致**: 同一份迁移脚本在 SQLite/PostgreSQL 上均可运行;
4. **数据迁移**: 不仅是 DDL, 还需支持数据迁移 (例如 PII 加密上线时, 需把存量明文字段批量加密回填);
5. **团队协作**: 多人并行开发时, 迁移文件冲突可检测、可合并。

## 决策 (Decision)
采用 Alembic 作为数据库迁移工具, 迁移脚本与 SQLAlchemy 2.0 ORM 模型分离管理。

### 配置与目录结构
- 配置文件: `backend/alembic.ini`;
- 迁移脚本目录: `backend/alembic/versions/` (已包含 15+ 个版本化迁移);
- `env.py` 配置 async SQLAlchemy engine, 支持在线与离线两种迁移模式;
- 模型定义在 `backend/app/models/`, Alembic 通过 `target_metadata = Base.metadata` 自动检测模型变更 (autogenerate)。

### 部署集成
- **docker-compose**: `alembic-migrate` 服务在 `backend` 服务启动前执行 `alembic upgrade head`, 完成后退出 (zero-shot sidecar 模式);
- **应用启动**: `backend/app/main.py` 在生产模式跳过 `Base.metadata.create_all()`, 仅依赖 Alembic 迁移 (第 67 行日志: "Production mode: skipping create_all, ensure 'alembic upgrade head' is run before startup");
- **CI/CD**: GitHub Actions 在 `contract-tests.yml` / `coverage.yml` / `pr-quality-gates.yml` 中均执行 `alembic upgrade head` 校验迁移可正确执行。

### 命名规范
- 迁移文件名采用 `<revision_id>_<description>.py` 格式, 例如 `h9d4e5f6a7b8_add_pii_encryption_email_hash.py`;
- revision_id 使用 12 位十六进制随机串, 避免人名/日期歧义;
- 描述部分使用 `add_<table>_<feature>` / `fix_<table>_<issue>` / `drop_<column>` 等动词前缀。

### 数据迁移
- DDL 与数据迁移可在同一迁移文件中混合编写;
- PII 加密上线迁移 (`h9d4e5f6a7b8`) 不仅添加列, 还通过 `op.execute` + Python 脚本批量加密回填存量数据;
- 危机事件索引修复迁移 (`f7b2c3d4e5f6`) 同时调整外键 `ON DELETE` 策略。

### 多 head 合并
- 多人并行开发产生多 head 时, 通过 `alembic merge -m "merge_dual_heads_v1_20" head1 head2` 生成 merge 迁移 (见 `6e25d8827741_merge_dual_heads_v1_20.py`);
- CI 中 `alembic heads` 必须为单一 head, 否则阻断合入。

## 替代方案 (Alternatives Considered)
1. **`Base.metadata.create_all()`** — SQLAlchemy 内建, 启动时根据模型自动建表。优点: 零配置; 缺点: 无版本控制, 无法回滚; 只能创建新表, 无法修改已有表结构 (加列/加索引/改约束); 无法执行数据迁移; 多人开发时 schema 漂移不可见。已明确在生产模式禁用 (main.py:67)。
2. **手动 SQL 脚本** — 维护 `migrations/001_init.sql`, `002_add_pii.sql` 等纯 SQL 文件。缺点: 易出错 (手写 SQL 无类型检查), 难以追踪当前已执行版本 (需自建版本表), 多数据库方言不兼容 (SQLite 与 PostgreSQL DDL 差异大), 数据迁移需另写脚本。
3. **Flyway / Liquibase** — 成熟的数据库迁移工具, 但属 Java 生态, 需引入 JVM 运行时; Python 项目中使用需额外维护 Java 依赖, 团队技能栈不匹配。Liquibase 的 YAML/XML 变更集对 Python 开发者不友好。
4. **Django migrations** — Django ORM 自带的迁移系统成熟稳定, 但引入 Django 等于重写整个后端框架 (当前为 FastAPI), 代价不可接受。
5. **不迁移, 直接重建库** — 每次部署 drop & create。仅适用于开发环境, 生产数据不可丢。

## 后果 (Consequences)
- **正面**:
  - 版本化迁移: 每次 schema 变更对应一个 revision, `alembic history` 可追溯, `alembic downgrade -1` 可回滚;
  - CI 自动执行: 部署流水线 `alembic upgrade head` 一键完成, 无需 DBA 介入;
  - 多数据库兼容: 同一份迁移脚本通过 SQLAlchemy 方言层适配 SQLite/PostgreSQL (autogenerate 生成的 `op.create_index` 等操作跨库通用);
  - 数据迁移与 DDL 统一管理: PII 加密回填、索引重建等数据操作可在迁移文件中完成;
  - autogenerate 减少手写负担: `alembic revision --autogenerate -m "..."` 自动对比模型与数据库差异生成迁移;
  - 多 head 检测: CI 强制单一 head, 避免分支迁移分叉。
- **负面**:
  - 迁移脚本编写需谨慎, 特别是数据迁移: 错误的数据迁移可能损坏生产数据, 必须在 staging 验证 + 备份后执行;
  - 多人协作时迁移文件冲突: 不同分支生成相同 revision_id 或修改同一表时需手动 merge, 偶尔需要 `alembic merge`;
  - autogenerate 不完美: 对枚举类型、约束重命名、列重命名等场景识别不准, 需人工校对生成的脚本;
  - 迁移文件累积无上限, 长期项目需定期「squash」(合并历史迁移为单一 baseline)。
- **中性**:
  - 需建立迁移命名规范与 PR review checklist: 每个迁移必须有 `upgrade()` 与 `downgrade()`, 必须在 SQLite + PostgreSQL 双环境测试;
  - 生产部署前必须备份, `alembic upgrade head` 失败时需有回滚 runbook (`docs/EMERGENCY_RUNBOOK.md`);
  - 开发环境可 `alembic downgrade base` 重置, 但生产严禁 `downgrade` (仅作为应急手段)。

## 关联 (Related)
- 配置: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`
- 迁移脚本: `backend/alembic/versions/` (15+ 版本化迁移)
- 应用集成: `backend/app/main.py:67` (生产模式跳过 create_all)
- CI: `.github/workflows/contract-tests.yml:38`, `.github/workflows/pr-quality-gates.yml:81,121,164`
- 部署: `docs/architecture.md:258` (alembic_migrate 服务), `docs/DEPLOYMENT_GUIDE.md:44`
- 应急: `docs/EMERGENCY_RUNBOOK.md`, `docs/planning/v1.28-final-delivery/ROLLBACK_PLAN.md`
- 关键迁移: `h9d4e5f6a7b8_add_pii_encryption_email_hash.py` (PII 加密上线), `eab25055097a_consolidated_initial_schema.py` (初始 schema), `6e25d8827741_merge_dual_heads_v1_20.py` (多 head 合并示例)
- 相关 ADR: ADR-007 (Fernet PII 加密 — 加密字段通过 Alembic 迁移引入), ADR-008 (startup 探针校验 alembic_version 表)
