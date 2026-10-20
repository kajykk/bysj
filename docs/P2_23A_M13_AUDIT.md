# P2_23A · ROUND_23a 审计：M13 干预计划并发唯一性

> 轮次：ROUND_23（23a）。HEAD 起点 `6ce0ac6`，本文档随 23a 提交入库。
> 审查报告条目：M13（干预计划并发重复 active）。边界：只加「active 唯一」一条
> 约束 + 兜底路径，不改业务状态机；存量重复只「检测 + 中止」，处置属人工决策。

## 一、根因（先实测，再定论）

写入路径是 check-then-act（`risk_service_warning._auto_generate_intervention`：
先 SELECT status='active'，查不到才 `_create_plan_from_template` 插入）。
ISS-014 的 `with_for_update()` **不是解**——行锁只锁已存在的行：

- 空表（或该用户历史计划都已 cancelled）时，两个并发事务都查不到 active ⇒
  都无行可锁 ⇒ 都 INSERT ⇒ 同一 user_id 两条 active。
- 并发入口真实存在：文本/生理两路评估各自起**独立 `AsyncSessionLocal`**
  （`services/risk_service.py::_trigger_warning_and_intervention`，
  fire-and-forget 后台任务），两个独立事务各自 commit。

后果（实测影响链）：干预任务按 active 计划发放
（`InterventionService.get_active`）⇒ 任务重复发放、完成率分子膨胀
（ROUND_19 M11 刚修的口径被再次污染）、咨询师工作台同一学生列两次。

**判据**：唯一性只能由数据库约束保证；应用层「先查再插」是原 bug 的另一种
写法，不作为修复证据。

## 二、修复三件套

### 2.1 迁移 `alembic/versions/r2a3b4c5d6e7_add_intervention_active_unique.py`

- `CREATE UNIQUE INDEX uq_intervention_plans_active_per_user
  ON intervention_plans (user_id) WHERE status = 'active'`
  （部分索引：status 的 cancelled/completed 历史值不冲突；PG 9.0+/SQLite 3.8.0+
  均支持）。
- **数据前置**：`find_duplicate_active_plans(bind)` 先检测存量重复；
  有冲突 ⇒ `RuntimeError` 中止升级并打印 `user_id / active_count / plan_ids`
  冲突清单。**不静默删除、不任意保留**——保留哪条关联在途任务与完成率
  历史，属业务决策。
- **与 `m1a2b3c4d5e6` 的刻意分歧**（docstring 已写明）：那个迁移对 is_latest /
  告警去重的存量重复是静默清理；本迁移中止。同一仓库两种哲学并存是有意的：
  后者涉及「哪条 active 更可能在途」的业务判断，迁移无权代劳。
- `_ACTIVE_WHERE` 传 `sa.text` 未编译表达式——沿用 `m1a2b3c4d5e6` docstring
  记录的教训（`.compile(dialect=...)` 传给 `postgresql_where` 会抛
  ArgumentError，索引根本不会被创建）。
- `downgrade`：`op.drop_index`。

### 2.2 model 双声明 `app/models/intervention.py`

`__table_args__` 同步声明
`Index("uq_intervention_plans_active_per_user", "user_id", unique=True,
postgresql_where=text("status = 'active'"), sqlite_where=text("status = 'active'"))`。
测试库走 `Base.metadata.create_all`（conftest），**model 不声明 = 测试库无
约束 = 假绿**；生产走 upgrade。两边口径一致才不会「测试绿、生产炸」。

实测验证（非转引）：SQLite `create_all` 后 `sqlite_master` 中该索引
`CREATE UNIQUE INDEX ... WHERE status = 'active'` 确认存在。

### 2.3 服务层 `app/services/risk_service_warning.py`

- `with_for_update()` **保留**（仍有价值：把冲突窗口从「秒级」缩到「毫秒
  级」），docstring 明确声明「不是唯一性保证」。
- `_create_plan_from_template` 的插入改 **savepoint + 回查**（C-2 同款范式）：
  `begin_nested()` 内 add + flush；`except SAIntegrityError` ⇒ 回查已存在
  的那条 active（带 `with_for_update`：PG 下插入方在唯一索引上等待、flush
  抛错时对方已提交；SQLite 写锁串行化同理）⇒ 返回已有计划，不重复插入、
  不产生孤儿任务。
- 回查命中 ⇒ `record_silent_degradation(
  "services.risk_service_warning.active_plan_conflict_recovered")` ——
  并发冲突不是错误，但不能无痕（/metrics 可观测）。
- 回查仍空 ⇒ 原样上抛，由调用方既有降级分支
  （`services/risk_service` 的 `intervention_generation_failed`）记账。

## 三、升级路径交互（M17 语义保持）——本轮抓到的真缺陷

约束上线后暴露的新冲突面：原升级路径是「先建新计划、成功后再取消旧计划」
（M17：避免无模板时用户失去所有干预）——**插入新 active 时旧 active 仍在
⇒ 撞唯一约束** ⇒ savepoint 回滚 ⇒ 旧计划恢复 active ⇒ 测试
`test_existing_plan_level_elevated_creates_new` 红（新 id == 旧 id）。

修复（方案 F）：升级分支的「取消旧 + 插新」收进**同一 savepoint**：

- savepoint 内先 UPDATE（旧计划置 cancelled 让位）→ flush → 插新；
  同一连接按语句序执行，新插入不撞自己的约束；
- 插入失败（并发冲突/DB 错误）⇒ savepoint 自动回滚，旧计划恢复 active
  ⇒ 不会「升级失败反而失去所有干预」；
- 无模板（`_create_plan_from_template` 返回 None）⇒ **撤销式恢复**
  （内存改回 active + flush，**不 `sp.rollback()`**——rollback 会剥离 ORM
  对象，异步上下文访问属性即 `DetachedInstanceError`/MissingGreenlet），
  保持 M17 原语义（旧计划不被取消、原样返回）。

## 四、门槛用例（`tests/test_p2_48_round23a_m13_intervention_unique.py`，10 passed）

| 用例 | 判据 |
|---|---|
| `test_concurrent_assessments_yield_single_active_plan` | **真并发**：4 协程同时评估同一用户（文本+生理两路路径），assert active 恰 1 条 |
| `test_second_writer_recovers_from_unique_conflict` | **确定性交错**：A 持写锁未提交期间 B 完成 select→insert，强制撞约束 ⇒ B 不抛、active 恰 1 条、全库 plan 数=1（证明 B 未插第二行）⇒ 兜底路径真被测到（防「SQLite 串行化 ⇒ 后续协程看到 active 根本没走 except」的假绿） |
| `test_second_active_plan_violates_unique_index` | **约束存在性**：直接 INSERT 第二条 active ⇒ IntegrityError（证明约束真在，非应用层假绿） |
| `TestM13MigrationAbortsOnDuplicate` ×4 | **存量重复**：真库检测 / monkeypatch 冲突列表 ⇒ upgrade 抛 RuntimeError 且**索引未创建** / 无冲突 ⇒ 正常创建 / downgrade 可回滚 |
| `test_level_elevation_without_template_keeps_old_plan` | 升级路径：无模板 ⇒ 旧计划保持 active（撤销式恢复生效） |
| `test_level_elevation_with_template_creates_new_and_cancels_old` | 升级路径：有模板 ⇒ 新 active 1 条 + 旧 cancelled（M17 语义不失） |

并发用例用独立 `TestingSessionLocal`（seed 数据须已提交可见；db_session 的
commit 被换成 flush，外层事务 rollback 即消失，不能用于并发协程间可见性）。

## 五、变异见证（`tests/tools/mutate_p2_48_round23a.py`，4/4 RED-OK）

| 组 | 变异 | 指名用例 | 结果 |
|---|---|---|---|
| T1 | 删部分唯一索引声明（model `__table_args__`） | `test_concurrent_assessments_yield_single_active_plan` | RED-OK（连带红 3 条：并发×2 + 约束存在性） |
| T2 | except 分支改回直接上抛（不回查） | `test_second_writer_recovers_from_unique_conflict` | RED-OK（连带红并发 gather） |
| T3 | 迁移 `if conflicts:` 恒假（upgrade 无视冲突结果） | `test_upgrade_aborts_on_conflicts_without_creating_index` | RED-OK |
| T4 | 升级路径去掉 savepoint 原子化（恢复「先插后取消」） | `test_level_elevation_without_template_keeps_old_plan` | RED-OK |

- 机制：字节快照 + try/finally 还原；`residual_clean=True`；还原后 10 passed。
- **T3 首轮设计失误记账**：初版变异 `find_duplicate_active_plans` 恒返回
  `[]`，但指名用例 monkeypatch 掉了该函数 ⇒ 源码变异被 patch 覆盖，红的是
  另一条真库用例 ⇒ WRONG-TARGET。修正为变异「upgrade 对冲突结果的使用」
  （`if conflicts:` 恒假）后指名用例才真正检验「upgrade 会用 find 的结果
  中止」。这与 ROUND_19 M12b 的「指名断言抓无效变异」是同一机制的两次
  实战，确认该机制有效。

## 六、回归与读数（实数）

- `tests/test_p2_48_round23a_m13_intervention_unique.py`：**10 passed**
- `tests/services/test_risk_service.py` + p2_48 合计：**98 passed**
- `tests/services/test_intervention_service.py` + `test_p2_10_round10.py`：**69 passed**
- `test_p2_10 + test_p2_11`：**243 passed**（含下述闸门同步后复跑）
- 数字自检（check_portfolio_numbers）：**21/21**
- 迁移端到端脚本 `scripts/test_migration_compat.py` 本地失败——
  **存量问题，与本轮无关**（对照实验：挪走本迁移 + stash 本轮 model/service
  改动后同样失败；炸点在存量迁移的 `add_constraint`，SQLite 不支持）。
  CI 的 `migration-tests.yml` 第 48 行明确 `echo "standalone script not
  tracked; e2e covered by pytest step"`——该脚本不在 CI 覆盖范围，CI 只跑
  `test_stab_p2_008_migration_compat.py`（本轮已过）。记账不动。

## 七、闸门同步（登记，非削弱）

1. **全称注释棘轮** 107→112（`test_p2_10_round10.py::test_inventory_ratchet_be`）：
   净增 5 条（model×2 + risk_service_warning×3），逐条登记见
   `docs/P2_10_ROUND10_AUDIT.md` 附二；另有 1 条存量注释行号漂移
   （:53→:55，ROUND_19 M12a 的「死配置」注释，内容未变）。
2. **#35 桶计数**：新增的 except 分支带 `record_silent_degradation`
   （W 型：显式记账的已知降级），不走 X（真降级）——`scan_p2_35` 快照与
   桶计数测试未受影响（W=109 / X=116 / 总数 341 不变）；登记语义记入
   本文档 §2.3。
3. **raise 分类计数**：无新增 raise（except 不改变三桶），
   `test_p2_11` 的 #34 计数不变。

## 八、未验证记账

- 全量后端套件（约 37 分钟）未在本机跑完即提交，交 CI `backend-coverage`
  实测（push 后 `tests/tools/watch_ci.py <sha>` 盯总数）。
- 迁移的 PG 路径（`string_agg` / `postgresql_where`）只在 SQLite 实测；
  PG 语法未经真库执行（CI 无 PG 迁移作业）。
- 「并发冲突恢复」指标目前无消费方断言（只验证 /metrics 可观测性由既有
  测试覆盖）。
