# P2-R47（ROUND_19 M 批 2）：统计口径 + 配置生效 + 事件时序六条修复

> 日期：2026-10-20｜基准 HEAD：`713ead5`（= origin/main，ROUND_22 CI 红项修复之后）
> 来源：审查报告 `outputs/CODE_REVIEW_2026-10-20.md` §二 M10–M16（六条）
> 边界：只修审查报告点名的六条 + 回归连带发现；不动现役预测主路径、不改历史读数快照。
> 铁律：M12 双栏记账（改前行为/改后行为）；M14 用**事件计数**断言；M12 若接线须走
> `record_silent_degradation`（本轮未接线，见 §三）。

---

## 〇、开工前置（先实测）

1. **HEAD 与工作区**：`git rev-parse HEAD` = `713ead5` = `origin/main`（ROUND_22 推送后 CI 10/10 全绿）。
   开工时工作树已带 ROUND_19 的未提交修改（六条修复的代码早已写完，本轮做收工：
   回归、变异、记账、提交）。
2. **六条修复的代码状态**：`backend/app` 下 11 个文件已改、2 个新模块未入库
   （`app/core/datetime_params.py`、`app/core/pending_events.py`），
   守护测试 `tests/test_p2_47_round19_m_batch2.py` 已写好但**尚未跑过全量回归与变异**。
3. **既有闸门面**：#35 桶 W=109 / X=116 / 总数 341（ROUND_18 起口径，
   `test_p2_11::TestP235Round13Batch6Wiring` 实测复算值）；
   #34 raise 分类 HTTPException=214 / ServiceError=38 / other_raise=354（ROUND_18 记录值）；
   BE 全称注释棘轮 101 条。

---

## 一、六条修复总表

| # | 问题（改前） | 修复（改后） | 判据（不变量） | 守护测试类 |
|---|---|---|---|---|
| M10 | `end_date=2026-10-20` 解析成当天 00:00，`created_at <= end` 把当日数据整体排除 | date-only 的 end 扩张到当天 23:59:59.999999；口径收敛到单一模块 | 日期型终点 = 当天结束；datetime 型不扩张；aware → naive UTC | `TestM10EndDateInclusive` |
| M11 | 完成率分子 = 执行记录条数，daily 任务打卡 3 天即 300% | 分子 = 至少完成过一次的任务数（与 `get_stats` 的 `count(distinct task_id)` 同源） | 完成率恒 ∈ [0, 100]（结构性 + 钳制纵深防御） | `TestM11CompletionRate` |
| M12a | `risk_level >= 2` 硬编码判定，threshold_level 只做上限比较——设 1 永远不预警 | 阈值先读设置再判定，判定与文案同一个 threshold | threshold_level=1 时 1 级即预警 | `TestM12ThresholdLevelEffective` |
| M12b | quiet_hours_* / notify_channels 能存能读能回显但无任何分发链路消费 | 保留字段 + **显式不生效声明**（API effective 字段 + 日志告警 + 审计 detail 三处一致） | 声明集合恒定三项；threshold_level 不在其中 | `TestM12NotEffectiveDeclared` |
| M14 | `warning.created` 在 `flush()` 后、调用方 `commit()` 前发布 | `schedule_after_commit` 登记，`after_commit` 钩子发布；回滚则事件随事务消失 | 事件只在提交后发出（计数断言）；回滚后计数不增 | `TestM14EventAfterCommit` |
| M15 | 管理统计把已匿名化（status=deleted）用户计入总数/咨询师数 | 人数口径显式排除 `USER_STATUS_DELETED` | 匿名化后 total_users / total_counselors 同步下降 | `TestM15StatsExcludeAnonymized` |
| M16 | GDPR 导出漏 6 个核心个人数据表（导出时拿不到、删除后永远拿不到） | 补齐 6 个 section，与匿名化覆盖面对齐；流式与一次性同清单 | 导出清单 ⊇ 匿名化清单；两条路径一致 | `TestM16GdprExportCoverage` |

---

## 二、逐条改前 / 改后双栏

### M10 `end_date` 当日数据被整体排除

| | 改前 | 改后 |
|---|---|---|
| 解析 | `datetime.fromisoformat(end_date)` → 当天 `00:00:00`；时区归一化各调用方各写一份（其中一份漏掉） | 新模块 `app/core/datetime_params.py`：date-only → 当天 `23:59:59.999999`；datetime 型按字面；aware → naive UTC；口径只有一处实现 |
| 调用方 | `user_data.py` / `review.py` 各写一份解析 | 统一走 `parse_range_params` / `parse_datetime_param` |
| 错误响应 | 422 `detail="日期格式必须为 ISO8601"` | 422 固定文案 `start_date/end_date 必须为 ISO 8601 格式（YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS）`（不带异常原文，见 §五） |

用户可见变化：选「10-01 ~ 10-20」现在包含 10-20 当天（改前实际只到 10-19 23:59）。
管理端危机事件列表（`review.py` 的 `_parse_date_param`）同口径修复。

### M11 干预完成率可超过 100%

| | 改前 | 改后 |
|---|---|---|
| 分子 | `len([x for x in executions if x.status == "completed"])`（执行记录条数） | `len({x.task_id for x in executions if x.status == "completed"})`（至少完成过一次的任务数） |
| 分母 | `InterventionTask` 条数（`get_stats` 路径为 `count(distinct task_id)`，两路径不同源） | 同一口径，`get_stats` 的 SQL 聚合同步改为 `count(distinct TaskExecution.task_id)` |
| 越界 | 无防护，daily 任务连续打卡 3 天算出 300% | 结构性保证 ∈ [0,100]（分子是分母集合的子集计数）+ `_completion_rate_percent` 钳制与 `record_silent_degradation("services.intervention_service.completion_rate")` 记账作为纵深防御 |

咨询师据"依从性"判断会得到相反结论——这是本条的用户可见影响。

### M12 预警设置三项

#### M12a threshold_level 被硬编码下限架空

| | 改前 | 改后 |
|---|---|---|
| 判定 | `should_warn = current_risk.risk_level >= 2`（硬编码），读完设置后只用 threshold 做一次上限比较（`< threshold` 才 return） | `should_warn = current_risk.risk_level >= threshold`，threshold 先读设置（无设置回落 `DEFAULT_WARNING_THRESHOLD = 2`） |
| 效果 | 只能把阈值调高、不能调低：seed 里 threshold_level=1 的用户永远收不到 1 级预警 | threshold_level=1 ⇒ 1 级即预警；设 10 ⇒ 10 级才预警（不再被静默压到 4） |
| 钳制 | `> 4` 静默压到 4（与 schema `ge=0 le=10`、CheckConstraint 0..10 不一致，且会把"设 10 = 永不预警"偷偷改成"4 级就预警"） | 与 schema/约束对齐：`> 10` 才压到 10 |
| 日志 | 无 threshold 字段 | `risk.judgement` 增加 `threshold=%s`，判据可追溯 |

#### M12b quiet_hours_* / notify_channels 无人消费

| | 改前 | 改后 |
|---|---|---|
| 存储/读取 | 能存、能读、能回显 | 不变（字段保留，向后兼容） |
| 消费 | 无任何分发链路读取（全仓只有写入与回显） | **不接线**（产品决策：免打扰一条危机预警该"推迟"还是"照发"涉及临床安全），但把状态说清楚 |
| 声明 | 无——用户会以为已经生效 | 三处一致：① API `GET /user/warning-settings` 返回 `effective{threshold_level:true, quiet_hours:false, notify_channels:false}` + `not_effective_notice`；② 更新时 `logger.warning("warning_setting.not_effective ...")`；③ 审计 detail 增加 `not_effective` 字段 |
| 登记表 | 无 | `warning_service._NOT_EFFECTIVE_KEYS = frozenset({"quiet_hours_start","quiet_hours_end","notify_channels"})`，`threshold_level` 明确不在其中（它已真正参与判定）；未来接线必须同步移除并补用例 |

### M14 `warning.created` 事务提交前发布

| | 改前 | 改后 |
|---|---|---|
| 时机 | `_check_warning_trigger` 内 `flush()` 后立即 `event_bus.publish(...)`，`commit()` 由调用方稍后执行 | 服务层只 `schedule_after_commit(self.db, "warning.created", {...})` 登记；`after_commit` 会话钩子统一发布 |
| 读空行 | 订阅方用独立 session 回查 `warning_id` 读到空行（行还没提交） | 提交后才发布，回查必然命中 |
| 回滚 | 事件已发、数据不存在（"幽灵预警"进指标） | `after_rollback` 钩子丢弃待发布事件，永不发布 |
| 基础设施 | 无（`review_service` 是单点"先 commit 再 publish"写法，3 个调用方记不住） | 新模块 `app/core/pending_events.py`：`WeakKeyDictionary[Session, list]` 登记（不用 `id()`，避免复用串话）；`event_bus.publish_sync` 抽出（`publish` body 本就是同步的）供同步钩子使用 |

### M15 管理统计计入已匿名化用户

| | 改前 | 改后 |
|---|---|---|
| total_users | `count(User)` 全表 | `.where(User.status != USER_STATUS_DELETED)` |
| total_counselors | `where(User.role == COUNSELOR)` | `where(role == COUNSELOR, status != DELETED)` |
| 依据 | 匿名化只置 `status='deleted'` 不删行（`gdpr_service_anonymize`）⇒ 仪表盘人数只增不减、高风险数包含已行使被遗忘权的主体 | 人数口径一律排除；`_DELETED_STATUS` 常量收口 |

### M16 GDPR 导出漏核心个人数据

| | 改前 | 改后 |
|---|---|---|
| 一次性导出 | 6 个表漏导：structured_assessments / text_entries / physiological_records / consultation_records / task_executions / data_drafts | `gdpr_service.py` 补 6 个 `_*_to_dict` 序列化函数 + 6 个 section |
| 流式导出 | 同样漏（`_stream_user_data` 的 section 清单不同步） | `api/v1/gdpr.py` 同步补齐 6 个 `iter_*`，与一次性导出同清单 |
| 用户影响 | 导出时拿不到、匿名化后**永远**拿不到——可携权（Article 20）形同虚设 | 导出清单 ⊇ 匿名化覆盖面对齐（`test_export_coverage_matches_anonymization` 锁死） |

---

## 三、M12 配置项生效状态对照表（双栏记账）

| 配置项 | 能存 | 能读 | 能回显 | **能被消费** | 生效状态（改后口径） | 证据 |
|---|---|---|---|---|---|---|
| `threshold_level` | ✅ | ✅ | ✅ | ✅ `risk_service_warning._check_warning_trigger` 真正参与判定 | **生效**（API `effective.threshold_level = true`） | `TestM12ThresholdLevelEffective` 4 条 |
| `quiet_hours_start` / `quiet_hours_end` | ✅ | ✅ | ✅ | ❌ 无任何分发链路读取 | **不生效**（显式声明：API + 日志 + 审计三处） | `TestM12NotEffectiveDeclared` 3 条 |
| `notify_channels` | ✅ | ✅ | ✅ | ❌ 无任何分发链路读取 | **不生效**（同上） | 同上 |

接线决策记录：免打扰/渠道过滤未接线是**产品决策**而非遗漏——一条危机预警在免打扰时段该"推迟"还是"照发"涉及临床安全，本轮选③（保留字段 + 把状态说清楚）。若未来接线：必须同步从 `_NOT_EFFECTIVE_KEYS` 移除、补生效路径用例、把 API `effective` 对应项改 `true`；闸门 `test_not_effective_registry_excludes_threshold_level` 与 `test_get_response_declares_effectiveness` 会盯着这个集合与声明的一致性。

**未走 `record_silent_degradation`**：M12b 是配置消费面缺失，不是 except 降级路径；按 #35 桶纪律不登记为 W/X，以「显式不生效声明」交付（审计 detail 可追溯）。

---

## 四、新模块登记（README 核心模块 69 → 71）

| 模块 | 职责 | 为何在 core |
|---|---|---|
| `app/core/datetime_params.py` | 日期/时间范围查询参数解析的唯一事实来源（M10） | 两个调用方（`user_data.py` / `review.py`）原先各写一份、其中一份漏时区处理；口径必须只有一处实现 |
| `app/core/pending_events.py` | 事务提交后发布事件的登记与钩子（M14） | 3 个调用方提交时机各异，不能在服务层各自记得"publish 前先 commit"；`after_commit` / `after_rollback` 双钩子 + WeakKeyDictionary 防跨会话串话 |

---

## 五、回归中抓到并修复的两处缺陷（本轮连带）

回归（先跑受影响既有测试）抓到两处**真缺陷**，均已修复并有守护：

1. **`api/v1/user_data.py:151` detail 带异常原文**（P2_12 泄漏闸门
   `TestP234LeakConvergence`）：`detail=str(exc)` 会把 `datetime.fromisoformat`
   的异常原文（含用户输入回显）带进响应体。修为固定文案（见 §二 M10 表）。
2. **`api/v1/review.py:52` 两个问题**：
   a. `_parse_date_param` 委托新模块后 `ValueError` 直接泄成 500——原 M-API-2 行为是
      400。补 `try/except ValueError → HTTPException(400, f"无效的日期格式: {value}")`，
      恢复原 400 行为；
   b. 补回 `from datetime import datetime`（注解需要，此前被连带删除）。

连带计数影响：#34 raise 分类 HTTPException=214 不变（user_data.py 422→422 同桶替换，
review.py 400 处为原有站点）；other_raise 354→355（新模块 `datetime_params.py` 的
`ValueError` 1 处）；详见 `docs/P2_11_ROUND11_AUDIT.md` 附：ROUND_19 段。

---

## 六、闸门与计数同步（登记面，非行为变化）

| 闸门 | 变化 | 理由 |
|---|---|---|
| `test_p2_10::test_inventory_ratchet_be` | 101 → 107 | 六条修复的注释各含全称词（保证/永远/不会/只有），逐条登记见 `docs/P2_10_ROUND10_AUDIT.md` 附录 ROUND_19 段 |
| `test_p2_11::TestP234RaiseClassificationSynced` | other_raise 354→355 | §五 连带计数 |
| `test_p2_11::TestP235Round13Batch37Wiring` | CANDIDATES `event_bus.py` 141→149 | `publish_sync` 自 `publish` 抽出致行号平移 |
| `test_p2_11::TestP235Round13Batch35Wiring` | 删除 `(RISKW_REL, 136, ...)` 候选 | M14 后该 handler 不再存在（候选失效，删除而非留假锚） |
| `test_p2_11::TestP235Round13Batch16` | DECLINED_MARKERS 锚点搬迁至 `core/pending_events.py` | after_commit 发布失败的处理随新模块搬迁 |
| `test_p2_11::TestP235Round13Batch16`（E5） | 改为在 `publish` / `publish_sync` 两个函数里找 `asyncio.QueueFull` 捕获 | 函数拆分后同步路径也要看 |
| #35 桶计数 | W=109 / X=116 / 总数 341 **不变** | 六条修复不新增 except 降级点（M12b 为消费面声明、M14 改发布时机）；M14 把 `risk_service_warning` 原有的 publish try/except（X 候选）替换为 `pending_events._publish_after_commit` 的同形 handler（同为 X 桶），一撤一增净 0 |
| 三处注释里的失效测试文件名引用 | 修正为 `tests/test_p2_47_round19_m_batch2.py` | 原引用三个不存在的文件名 |

---

## 七、变异见证（7/7 RED-OK）

脚本 `backend/tests/tools/mutate_p2_47_round19.py`，日志
`mutate_p2_47_round19_result.log`。每条变异指名一条 ROUND_19 测试，失败输出里必须出现
该用例名（防连带报红）；每处先存字节快照、`finally` 还原，收尾验证字节一致 + 全绿。

| 变异 | 目标实现 | 指名用例 | 结果 |
|---|---|---|---|
| M11 | `if rate < 0 or rate > 100:` → `if False:` | `test_out_of_range_is_clamped_and_counted` | RED-OK |
| M12a | threshold 三元写死 `DEFAULT_WARNING_THRESHOLD` | `test_threshold_1_warns_at_level_1` | RED-OK |
| M12b | `_NOT_EFFECTIVE_KEYS` 掏空为 `frozenset(set())` | `test_update_warns_and_audits_not_effective` | RED-OK |
| M14 | 登记改为 `event_bus.publish_sync` 立即发 | `test_event_published_only_after_commit` | RED-OK |
| M15 | 删 total_users 的 `.where(User.status != DELETED)` | `test_anonymized_user_drops_out_of_totals` | RED-OK |
| M16 | 删 `"text_entries"` section 行 | `test_export_contains_previously_missing_sections` | RED-OK |
| M10 | `inclusive_end=True` → `False` | `test_date_only_end_expands_to_end_of_day` | RED-OK |

**收尾读数**：`residual_clean=True`、`final_green=True`（还原后 26 passed）。

**第一轮 M12b 被判 WRONG-TARGET 的记账**：首轮变异把 `_NOT_EFFECTIVE_KEYS` 那行注释
成 `/_NOT_EFFECTIVE_KEYS: ...`（行首 `/`）——**语法非法的变异**，模块 import 即炸，
闸门红在收集错误而非断言变红，被脚本的指名判据正确抓获（"红了但不是这一条"）。
修成语法合法的掏空形式后重跑通过。这条记账保留的原因：它证明指名判据真的在区分
"断言红"与"import 炸"，变异脚本的自检有效。

---

## 八、测试清单

- `tests/test_p2_47_round19_m_batch2.py`：**26 passed**（M10×6 / M11×5 / M12a×4 /
  M12b×3 / M14×3 / M15×2 / M16×3，含参数化展开）。
- 受影响既有测试回归：part1 238 passed；part2 179 passed（修复 §五 两处缺陷后）。
- 登记面闸门：`test_p2_10_round10.py` + `test_p2_11_round11.py` 243 passed。

---

## 九、未验证记账

- 全量后端套件（约 37 分钟）未在本机跑完即提交；交 CI `backend-coverage` 实测
  （push 后 `tests/tools/watch_ci.py <sha>` 盯总数）。
- M12b 的"未来接线"路径（免打扰/渠道真正接入分发）无用例——按产品决策本轮不接线，
  接线时须按 §三 清单同步四项（移除登记、补用例、改 API 声明、更新本文档）。
- 流式导出（`_stream_user_data`）的 6 个新 `iter_*` 只经过合同级测试（清单对齐），
  未经大账流式端到端压测。
