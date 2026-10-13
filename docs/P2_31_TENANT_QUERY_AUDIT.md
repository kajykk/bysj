# P2-31 租户敏感查询路径全仓审计清单

- 生成时间：2026-10-13 08:26 UTC｜仓库 HEAD：`431788d`
- 机制：执行层闸门 `app/core/tenant_guard.py`（before_execute，不可绕过）+ 静态扫描 `scan_unscoped_protected_queries`（CI 期，`tests/test_p2_31_tenant_guard.py::TestMechanizedAuditGate` 常驻）
- 受保护对象：`review_tasks` / `crisis_events`（无 tenant_id 列，租户归属沿 user_id JOIN `users.tenant_id` 推导）
- 计入口径：仅**查询构造语句**（形态 A_select `select(<Model>...)` / A_helper `user_tenant_scoped_query(...)` 等 SSOT 构造 / B_table `<Model>.__table__` / C_text SQL 样子且含表名的 `text()` / E_write ORM 构造器 `Model(...)`）；类型注解、docstring、链式 refine 续行（``query = query.where(...)``）、字典键不计入。
- 分类：**helper** = SSOT `user_tenant_scoped_query` 或 `tenant_scoped_filter`；**tenant_id_attr** = 直写 `.tenant_id` 谓词；**exempt** = 语句级 `tenant_exempt=` 已登记豁免；**helper_chain** = 语句级无特征，约束在同函数上游语句（链式写法，函数级粒度）；**unscoped** = 无约束（必须为 0）；**write** = INSERT/UPDATE/DELETE（范围外）。

## 汇总

| 机制 | 条数 |
|---|---|
| helper | 7 |
| tenant_id_attr | 0 |
| exempt | 13 |
| helper_chain | 1 |
| unscoped | 0 |
| write | 2 |
| **合计** | **23** |

**无约束查询路径：0 条**（新增即被闸门测试与执行层双拦）

## 逐条清单（按文件:行号）

| # | 位置 | 模型 | 形态 | 机制 | 说明 | 证据（源码首行） |
|---|---|---|---|---|---|---|
| 1 | `backend/app/api/v1/ops_dashboard.py:144` | ReviewTask | A_select | exempt | tenant_exempt=['platform_admin_ops_dashboard'] | `status_counts_raw = (` |
| 2 | `backend/app/api/v1/ops_dashboard.py:154` | ReviewTask | A_select | exempt | tenant_exempt=['platform_admin_ops_dashboard'] | `recent_count = (` |
| 3 | `backend/app/api/v1/ops_dashboard.py:164` | ReviewTask | A_select | exempt | tenant_exempt=['platform_admin_ops_dashboard'] | `resolved_rows = (` |
| 4 | `backend/app/api/v1/ops_dashboard.py:189` | ReviewTask | A_select | exempt | tenant_exempt=['platform_admin_ops_dashboard'] | `crisis_pending = (` |
| 5 | `backend/app/api/v1/ops_dashboard.py:215` | CrisisEvent | A_select | exempt | tenant_exempt=['platform_admin_ops_dashboard'] | `count_24h = (` |
| 6 | `backend/app/api/v1/ops_dashboard.py:225` | CrisisEvent | A_select | exempt | tenant_exempt=['platform_admin_ops_dashboard'] | `count_7d = (` |
| 7 | `backend/app/api/v1/ops_dashboard.py:235` | CrisisEvent | A_select | exempt | tenant_exempt=['platform_admin_ops_dashboard'] | `status_raw = (` |
| 8 | `backend/app/services/crisis_export_service.py:94` | CrisisEvent | A_select | exempt | tenant_exempt=['platform_admin_crisis_export'] | `stmt = (` |
| 9 | `backend/app/services/crisis_export_service.py:109` | CrisisEvent | A_helper | helper | ['tenant_scoped_filter'] | `stmt = stmt.join(User, User.id == CrisisEvent.user_id).where(` |
| 10 | `backend/app/services/gdpr_service_anonymize.py:250` | CrisisEvent | A_select | exempt | tenant_exempt=['data_subject_gdpr'] | `crisis_events = (` |
| 11 | `backend/app/services/gdpr_service_export.py:131` | CrisisEvent | A_select | exempt | tenant_exempt=['data_subject_gdpr'] | `crisis_events = (` |
| 12 | `backend/app/services/gdpr_service_export.py:379` | CrisisEvent | A_select | exempt | tenant_exempt=['data_subject_gdpr'] | `rows = (` |
| 13 | `backend/app/services/review_service.py:67` | ReviewTask | A_select | exempt | tenant_exempt=['system_internal_idempotency_check'] | `existing = await self.db.execute(` |
| 14 | `backend/app/services/review_service.py:92` | ReviewTask | E_write | write | ReviewTask(...) ORM 构造器（INSERT 路径） | `task = ReviewTask(` |
| 15 | `backend/app/services/review_service.py:152` | ReviewTask | A_helper | helper | ['user_tenant_scoped_query'] | `query = user_tenant_scoped_query(ReviewTask, tenant_id)` |
| 16 | `backend/app/services/review_service.py:191` | ReviewTask | A_helper | helper | ['user_tenant_scoped_query'] | `stmt = user_tenant_scoped_query(ReviewTask, tenant_id).where(` |
| 17 | `backend/app/services/review_service.py:204` | ReviewTask | A_select | helper | ['tenant_scoped_filter'] | `stmt = (` |
| 18 | `backend/app/services/review_service.py:235` | ReviewTask | A_select | exempt | tenant_exempt=['tenant_checked_upstream_same_transaction'] | `result = await self.db.execute(` |
| 19 | `backend/app/services/review_service.py:377` | ReviewTask | B_table | helper_chain | 函数级：同函数上游 tenant_scoped_filter() | `stats_query = stats_query.select_from(` |
| 20 | `backend/app/services/review_service.py:430` | CrisisEvent | E_write | write | CrisisEvent(...) ORM 构造器（INSERT 路径） | `event = CrisisEvent(` |
| 21 | `backend/app/services/review_service.py:471` | CrisisEvent | A_helper | helper | ['user_tenant_scoped_query'] | `query = user_tenant_scoped_query(CrisisEvent, tenant_id)` |
| 22 | `backend/app/services/review_service.py:514` | CrisisEvent | A_helper | helper | ['tenant_scoped_filter'] | `stmt = (` |
| 23 | `backend/app/services/review_service.py:686` | CrisisEvent | A_helper | helper | ['user_tenant_scoped_query'] | `stmt = user_tenant_scoped_query(CrisisEvent, tenant_id).where(` |

## 豁免登记（EXEMPTION_REGISTRY）

- **platform_admin_ops_dashboard**（7 个使用点）：运营看板 GET /ops-dashboard/*（app/api/v1/ops_dashboard.py）由 require_platform_admin() 把关（角色 + 用户须属 DEFAULT_TENANT_ID），跨租户聚合是有意的平台运营视角，见该模块文件头。
  - `backend/app/api/v1/ops_dashboard.py:144`
  - `backend/app/api/v1/ops_dashboard.py:154`
  - `backend/app/api/v1/ops_dashboard.py:164`
  - `backend/app/api/v1/ops_dashboard.py:189`
  - `backend/app/api/v1/ops_dashboard.py:215`
  - `backend/app/api/v1/ops_dashboard.py:225`
  - `backend/app/api/v1/ops_dashboard.py:235`
- **platform_admin_crisis_export**（1 个使用点）：平台管理员危机事件 CSV 导出（admin.py export_crisis_events → CrisisExportService.iter_export_crisis_csv）。tenant_id=None 表示有意全量导出，实际范围写入审计日志；租户 B 的 admin 被 require_platform_admin 拦在 403，到不了这条语句。
  - `backend/app/services/crisis_export_service.py:94`
- **data_subject_gdpr**（3 个使用点）：GDPR 数据主体导出/匿名化（gdpr_service_export / gdpr_service_anonymize）按 user_id 取数：scope 是数据主体本人（export_my_data / delete_my_account）或平台管理员对任意主体的 Article 15/17 履行，不按租户切分。
  - `backend/app/services/gdpr_service_anonymize.py:250`
  - `backend/app/services/gdpr_service_export.py:131`
  - `backend/app/services/gdpr_service_export.py:379`
- **system_internal_idempotency_check**（1 个使用点）：ReviewService.create_review_task 的 pending 存在性检查：系统内部写路径前置查询，按 user_id 幂等去重，不向租户用户返回数据。
  - `backend/app/services/review_service.py:67`
- **tenant_checked_upstream_same_transaction**（1 个使用点）：ReviewService.assign_review 的 FOR UPDATE 按主键取行：同事务内 _ensure_review_in_tenant 已完成租户校验；review_tasks.user_id 不可变、租户归属不随并发变化，前置校验后按主键加锁是安全的（原注释 :226-229）。
  - `backend/app/services/review_service.py:235`
- **test_row_verification**（2 个使用点，其中 tests/ 2 个）：测试夹具回读整行以断言后置状态（如 tests/api/test_review_assign_auth.py 的 _reload），非生产数据面；夹具不构成跨租户暴露路径。
  - tests/ 下 2 处（见 TestExemptionRegistry 把守）

## 范围外与已知局限（如实记账）

1. **写路径不拦**：INSERT/UPDATE/DELETE 触及受保护表不过闸 —— 写路径的租户约束语义与服务层不同（如 `assign_review` 的 FOR UPDATE 由同事务前置校验保障），由服务层 `tenant_id` 必填关键字参数负责（反向闸门：`TestReverseGates::test_tenant_id_is_required_keyword` 等两条）。
2. **ORM 刷新放行**：`session.refresh` / 过期属性重载读的是 identity map 里已加载实例（先前加载已过闸，主键不可变），按 `_sa_orm_load_options._refresh_state` 识别后放行；全新 `session.get(Model, id)`（identity map 未命中）照拦（A-01 形态，`test_by_pk_get_blocked` 把守）。
3. **链式语句函数级粒度**：`stmt = (...)` 构造后多行 refine 的写法，约束特征在构造语句；`helper_chain` 分类即此类，粒度到函数。
4. **别名锚点从严**：锚点只认 `users.tenant_id` 限定名，不认别名 —— 漏放行（假红）可修，错放行（漏报）是闸门失效。
5. **最终兜底在执行层**：静态扫描看不到的形态（动态构造、字符串拼接 SQL）只要真的跑到引擎，`before_execute` 一律过闸。
