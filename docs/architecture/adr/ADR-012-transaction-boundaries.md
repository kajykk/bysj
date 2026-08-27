# ADR-012: 数据库事务边界统一 (R-D)

## 状态 (Status)
Accepted

## 日期 (Date)
2026-08-27

## 上下文 (Context)
DWS 后端 API 层存在大量散落的 `await db.commit()` 调用, 提交点分布不均:

| 模块 | commit 数 | 风险点 |
|---|---|---|
| `silences.py` | 7 | 单请求多次 commit, 中途异常可能产生部分提交 |
| `canary.py` | 6 | 部署状态机 + 审计日志交织, 半提交后状态不一致 |
| `user_intervention.py` | 5 | 任务状态流转 + 反馈写入 |
| `tenant_admin.py` | 4 | 租户生命周期操作 |
| `gdpr.py` / `auth.py` / `content_governance.py` / `counselor.py` | 各 3 | 删除/匿名化等不可逆操作 |
| 其余模块 | 1~2 | 基本符合预期 |

核心问题:
1. **部分提交 (Partial Commit)**: Service 中途抛异常时, 已执行的内层 commit 无法回滚, 业务状态出现"半写入"。
2. **审计日志丢失或脏读**: 部分路径先 commit 业务再写 OperationLog (或反之), 审计与业务不同原子。
3. **事务边界不显式**: commit 位置由"恰好想起来"决定, 新增业务逻辑时无一致约束可循。
4. **savepoint 使用不一致**: 已有 H-2 修复 (alerts webhook) 用 `begin_nested()` 隔离单条失败, 但该模式未推广到其他模块。

## 决策 (Decision)
统一事务边界规则如下:

### 规则 1: commit 只允许出现在两类位置
- **Service 层业务方法末尾**: 业务写入 + 关联审计日志在同一事务提交。
- **基础设施边界**: 流式响应前必须提交 (SEC-P1-003, 避免事务在流式生成期间关闭)、跨请求边界的后台任务。

### 规则 2: OperationLog 与业务写入同事务
- 审计日志 (OperationLog) 与业务写操作在同一事务内 `db.add` + 末尾统一 `commit`。
- 需要"业务回滚但审计保留"的路径 (SEC 场景) 使用 `begin_nested()` savepoint 包裹业务写入,
  失败时仅回滚 savepoint 再提交审计。
- 已应用的范式: `alerts/__init__.py` webhook 的 `_handle_silenced_alert` / `_handle_active_alert` (H-2 修复)。

### 规则 3: 单端点 ≤ 1 commit
- 任何 API 处理函数体最多执行一次 `await db.commit()`。
- 迁移顺序按 commit 数降序: `silences.py (7)` → `canary.py (6)` → `tenant_admin.py (4)` → `gdpr/auth/content_governance/counselor (3)` → 其余。
- 每文件迁移产出: 合并为单一提交点 + "service 中途抛异常 → 断言无部分提交"的契约测试。

### 规则 4: 事务操作函数化
- 需要多个提交点的复合操作 (如"业务提交 + 独立审计提交") 抽为显式命名函数
  (`_commit_with_audit` 等), 禁止散落裸 commit。

## 替代方案 (Alternatives Considered)
1. **保持现状 (逐处 commit)**: 改动最小, 但部分提交风险持续存在, 无法满足审计一致性要求。
2. **Unit of Work (UoW) 框架化**: 引入 uow 模式 + `TransactionContext` 装饰器统一提交。优点: 约束最强; 缺点: 需重构所有 Service 构造方式 (当前直接注入 `db: AsyncSession`), 改动面过大, 与既有代码风格冲突。
3. **全量回滚式 (仅事务装饰器)**: FastAPI 依赖 `get_db` 统一回滚异常请求。当前 `get_db` 已做异常回滚兜底, 但无法阻止"中途已显式 commit"的部分提交; 需配合规则 1/3 的提交点收敛才能生效。

## 后果 (Consequences)
- **正面**:
  - 部分提交风险消除: 业务 + 审计原子提交或显式 savepoint 隔离。
  - 审计一致性: 业务失败不再留下"无审计的操作日志"或"有审计但业务未生效"。
  - 新增代码有明确约束: 提交点收敛到 Service 边界, review 成本下降。
- **负面**:
  - 迁移期间行为变更: 原多次 commit 路径的时序语义变化 (如"先保存配置再写审计"变为"同事务"), 需逐文件回归。
  - 长事务: 合并提交点后单事务存活时间变长, 需关注连接池占用 (当前均为短业务操作, 风险可控)。
- **中性**:
  - 需为每文件补充"中途异常 → 无部分提交"契约测试 (范式: `test_reports_api_extended.py` 的失败路径断言)。
  - 迁移按文件分 PR, 每 PR 附带对应契约测试, 遵守计划红线 6 (回滚保留 shim)。

## 关联 (Related)
- 基线: `docs/REMAINING_TASKS_PLAN_202608.md` R-D 条目
- 既有范式: `app/api/v1/alerts/__init__.py` (H-2 savepoint 隔离), `app/api/v1/reports.py` (SEC-P1-003 流式前提交)
- 事务基础设施: `app/core/database.py` (`get_db` 异常回滚兜底), `app/services/pdf_job_store.py`
- 相关 ADR: ADR-002 (SQLAlchemy async), ADR-010 (Alembic 迁移), ADR-011 (event bus)
