# P2 第十三轮审计清单（#35 X 桶分批接线 + tenant_admin 结案 + prettier 最终决议）

- 生成时间：2026-10-15（HEAD 以 `3e5969d` 为基线；扫描在**无变异窗口**内生成）
- 提示词：`docs/ROUND_13_PROMPT.md`（三项：#35 X 桶分批接线 / tenant_admin 4 处 /
  prettier 决议）
- 闸门：`backend/tests/test_p2_11_round11.py::TestP235Round13Batch1Wiring`（新增）+
  全部 `tests/test_p2_*.py`（默认全跑，不按调用图取 affected）
- 变异证据：`backend/tests/tools/mutate_p2_35_round13_batch1.py` →
  `backend/tests/tools/mutate_p2_35_round13_batch1_result.log`

---

## 〇、开工前置：提示词第 2 项（tenant_admin 4 处）为 stale——实测结账

提示词把 `tenant_admin` 4 处列为「剩余未决（目标租户归属语义待确认）」。
**实测该事项已在第十二轮第六批 `a9926a1` 完成**，本轮只做结账不改码：

| 取证 | 结果 |
|---|---|
| `backend/app/api/v1/tenant_admin.py` 手写 `OperationLog(` 构造点 | **0**（`AFTER_BATCH6=0` 棘轮绿） |
| 4 处 `record_audit` 调用的 `tenant_id` 实参 | `tenant.id`（create）/ `tenant_id`（update/suspend/activate 路径参数）——**目标租户**，非 `current_user.tenant_id` |
| 「归属从列 X 搬到列 Y」对应关系 | 已书面化：`P2_12_ROUND12_AUDIT.md` §6.3（列 tenant_id 迁移前后同为显式目标租户 id；helper 仅 None 时落 `DEFAULT_TENANT_ID`，目标租户主键恒非 None ⇒ 落列值与迁移前完全一致） |
| 归属闸门 | `tests/test_p2_12_round12.py::TestTargetTenantAttribution`（源码侧 + 运行时侧双钉），本轮全量闸门 121 passed 含此项 |

⇒ 提示词该项是**从第十二轮第六批提示词初始状态遗留的过期条目**（第六批提示词
原文即"tenant_admin 4 处最后单独处理……审完再动手"，而第六批执行时已审完并迁完）。
按「历史快照只追加不改」：P2_11 附录追加结案条目（见下），P2_12 §6.3 不动。
**本轮无代码动作。**

---

## 一、#35 X 桶第一批：7 处接线（X 187 → 180）

### 1.1 接线清单（全部原本无任何计数）

| location | 文件 | 降级语义 |
|---|---|---|
| `api.validation.job_store.get.redis_fallback` | `api/v1/validation.py` | 读路径 Redis→内存：任务可能在其它实例/Redis，回退本进程内存后查不到即返回 None，用户侧呈现「任务不存在」假象 |
| `api.validation.job_store.update.redis_fallback` | 同上 | 更新降级：状态只落本进程内存，其它实例轮询读到 Redis 旧值，任务进度看似冻结 |
| `api.validation.job_store.delete.redis_fallback` | 同上 | 删除降级：Redis 删除失败后仅弹本进程内存（通常并无此 job），任务仍在，列表继续呈现已「删除」任务 |
| `api.validation.job_store.list_jobs.redis_fallback` | 同上 | 列表降级：只列本进程内存的任务，其它实例创建的任务整体不可见 |
| `api.validation.job_store.count.redis_fallback` | 同上 | 计数降级：只数本进程内存的任务，统计偏小，与列表接口矛盾时无任何告警 |
| `core.cache.redis_client_init_failed` | `core/cache.py` | **根因性**降级：共享客户端初始化失败后，全仓缓存消费者（观测缓存/告警去重/任务存储）全部静默退回内存层，各消费点只看到「没有客户端」而不知根因 |
| `core.cache.redis_pubsub_client_init_failed` | 同上 | pubsub 客户端初始化失败 → ws.py 订阅回路无法建立，跨实例 WebSocket 推送静默失效 |

选簇依据：审计 6.5 节 Top 簇明序（`api/v1/validation.py` 读路径与写路径同型，
写路径 `create` 已在第十二轮第五批接线）；cache 2 处为全仓根因点，价值高于
单文件簇，故与本簇合并为第一批（5+2=7，符合提示词每批 5–8 处）。

### 1.2 跳过 2 条（书面记账，仍留 X 桶，机器不裁、文档裁）

| 位置 | 跳过理由 |
|---|---|
| `api.validation.job_store._get_redis`（X 清单 line 88） | **生产不可达**：该 handler 的触发条件是 `get_redis_client()` 抛异常，但共享 `_get_redis_client` 内部已吞 `from_url` 失败并返回 None（`_get_redis_url` 亦自带 try），接线即死代码（「报 0 型假闸门」的反向风险）。降级信号由 cache.py 根因接线 + 各操作处理器覆盖 |
| `core.cache._get_redis_url` 内层 except（X 清单 line 298，现 308） | **纯指标上报自身失败的兜底**（提示词规定的跳过类目）：内层 `try: silent_degradation_total.inc(...) except: pass`；外层 handler（第十一轮直调风格）已完成接线，分类器因只读 handler 体、看不到外层 try 而落入 X |

> 记账而非改分类器：本轮不动分类器规则（改规则要重验全部 334 行，blast radius
> 大于本批）。后续批如复审这两条，以本节为凭。

### 1.3 闸门与变异

- 桶计数改钉：`test_batch6_bucket_counts_pinned` 的 `expected` 同步为
  **W=34 / X=180**（其余桶不变，总数 334 不变——扫描器+分类器复跑实测）。
- 新增 `TestP235Round13Batch1Wiring`（3 条）：
  1. `test_locations_wired_in_code_and_doc`：7 对 location↔文件**双向**核对
     （源码字面量 + 审计文档登记，只查一侧会漏「登记了没接线」/「接了没登记」）；
  2. `test_read_path_fallback_increments_counter`：**运行时**——给定必炸 Redis
     客户端真调 `store.get()`，`silent_degradation_total{location}` 必须 +1
     （接线了但计数器不动 = 假接线，与 #35 根因「失败不留痕」同罪）；
  3. `test_cache_client_init_failure_increments_counter`：**运行时**——patch
     `from_url` 抛异常，共享/pubsub 两个 location 各 +1（配全新 `asyncio.Lock`
     避免跨事件循环绑定）。
- 棘轮样式不变：`test_wiring_count` 仍 `>= BASELINE(8)`；精确 pin 由上面的
  location 对 + 桶计数承担。
- **三次真实变异（先审强度，均语义级，非子串逃逸）**，日志
  `mutate_p2_35_round13_batch1_result.log`：

| 变异 | 强度自评 | 结果 |
|---|---|---|
| M1 删 validation.get 整个接线语句 | 强（整句删除） | 红 3/3（locations / 运行时计数器 / 桶计数）→ 恢复绿 |
| M2 改 cache 共享客户端 location 字面量 | 强（整个标识更换，非同串子串） | 红 2/2（locations / cache 运行时计数器；桶计数仍绿——分类器只认调用不认字面量，符合设计）→ 恢复绿 |
| M3 删审计文档一条 location 登记行 | 强（整行删除，文档侧半断言） | 红 1/1（locations）→ 恢复绿 |

### 1.4 实测读数（本地单跑，禁止并发双跑）

| 项 | 读数 |
|---|---|
| `record_silent_degradation(` 调用点 | 26 → **33**（AST/正则同口径，排除 helper 本体） |
| 桶计数（扫描器+分类器复跑） | X 187→**180**，W 27→**34**，总数 334 不变 |
| `test_p2_11_round11.py` | 26 → **29 passed**（+3 新闸门） |
| 全部 P2 闸门（09/10/11/12/31/32 六套件） | **121 passed** |
| affected：`test_validation_api.py` + `test_cache.py` | **42 passed** |
| affected：`test_model_status_cache` + `test_perf_p2_009` + `test_iss02_validation_engine`（后者带 `--basetemp`） | **58 passed** |
| affected：cache 消费者 7 文件（health_extended/dedup_lock/fault_injection/observability_e2e/token_blocklist/ws_pubsub/password_reset_token_one_time） | **127 passed** |
| import 烟测 + AST「调用点⊆导入绑定」复查（validation/cache） | 通过 |
| BE 全称注释净值 | 97 → **98**（`cache.py:152`「只会看到」；两侧账已写 `P2_10_ROUND10_AUDIT.md` 附录，闸门同步改钉） |

### 1.5 未验证 / 待办（如实记账）

- **后端全量本地未跑**（约 37 分钟，历轮同例）：本地跑 affected 227 + 全部闸门
  121 = 348 passed，根目录其余文件由 CI 全量兜底。
- **X 桶余 178 条待接**（第一批后桶内 180 = 已接 7 出桶 + 跳过 2 仍留桶；
  待接 = 180 - 2 = 178）。下一批候选（按审计 6.5 Top 簇续）：
  `core/model_engine/predict.py` 10、`core/model_engine/loading.py` 8、
  `services/auto_rollback_service.py` 7、`tasks/scheduler.py` 7、
  `api/v1/silences.py` 6、`api/v1/alerts/__init__.py` 6、
  `tasks/pdf_report.py` 6。
  > 注：审计 6.5 写的 `loading.py 9 / auto_rollback 9` 与 JSON 实测（8/7）差 1-2 条，
  > 系该节成文时点的快照差异；以 JSON 产物 + 桶计数闸门为权威。
- **alerts 簇预裁定提醒**（下一批取该簇前必读）：`api/v1/alerts/__init__.py` 6 条中，
  `_handle_silenced_alert`/`_handle_active_alert` 的 persist/notify 失败均已由
  H-API-11 计数进 webhook 响应（`failed`/`notify_failed`），属显式失败上报，
  与本批跳过的「可见失败」同型；`alertmanager_webhook` 的 final commit 失败
  （丢整批已持久化告警但响应仍 200/failed=0）与 `list_alert_history` 的
  detail 解析退化为空字段才是候选。逐条过闸，不整簇照接。
- 前端本批零改动，未跑前端全量（无 affected）；提示词收工标准的前端全量 +
  `vue-tsc` 0 错留待本轮有前端改动的批次或收尾轮。
- 分类器精化（把「指标自报失败的内层 except」自动归 S）登记为后续批可选项，
  本轮不改（见 1.2）。

---

## 一之二、#35 X 桶第二批：6 处接线（X 180 → 174）+ 跳过 11 条

### 1.6 接线清单

| location | 文件 | 降级语义 |
|---|---|---|
| `core.model_engine.predict.experimental_v121_scaler_fallback` | `core/model_engine/predict.py` | scaler.transform 失败→未缩放特征算分：实验对照分数看似有效实则失真，响应无任何标识 |
| `core.model_engine.predict.shadow_predict_trigger_failed` | 同上 | 影子触发 fire-and-forget 失败→样本静默丢失，对拍覆盖率悄悄归零（激活校验的依据就是这么缺掉的） |
| `core.model_engine.predict.physiological_cleaner_fallback` | 同上 | cleaner 统计量缺失→特征工程（中位数填充/极端值裁剪/Winsorization）整体跳过，模型拿到未清洗原始输入。**姊妹路径 `predict_lite` 同型失败有 `_incr_fallback` 计数，本路径此前零计数** |
| `core.model_engine.predict.shap_factors_fallback` | 同上 | SHAP 失败→简单特征重要性（dict 路径）：用户/咨询师看到的「特征贡献」实为 \|特征值\| |
| `core.model_engine.predict.shap_factors_array_fallback` | 同上 | 同上（array 路径，无 model_feature_names 时的 feature_order 分支） |
| `services.auto_rollback_service.rollback_savepoint_failed` | `services/auto_rollback_service.py` | 回滚 savepoint 失败后 results 追加的仍是 should_rollback=True 的原始结果——**数据结构在说谎**，坏金丝雀继续生产服务，调用方无从得知 |

### 1.7 跳过 11 条（书面记账，仍留 X 桶）

| 位置 | 跳过理由 |
|---|---|
| `predict._run_experimental_v121`（416）/ `_run_experimental_v123`（484） | V 型：实验 LR 不可用时响应字段置 None，消费者可见（非静默） |
| `predict._run_adapter`（526） | M 型：已有专用计数 `_incr_counter("adapter_miss")` → `get_metrics_snapshot()` 的 `adapter.miss_count`，经 `/api/v1/metrics` 与 monitoring 暴露（实测快照含 adapter.hit/miss_count） |
| `predict._apply_lite_calibration`（734/749） | V 型：返回 `(raw, False)`，响应 `probability_calibrated=False` 且阈值选择已按该标志分支，失败可见 |
| `auto_rollback` 5 处（57/90/123/152/161） | M 型：全部已有专用计数器 `canary_rollback_check_lock_total{outcome="unavailable"}`（`_bump_lock_counter`）；分类器 M 规则只认 `warning_notify_failed_total`/`_incr_fallback` 故落入 X——**分类器盲区，文档裁** |
| `auto_rollback.check_all_canaries`（434） | V 型：健康检查失败时结果显式 `reason="check_error"`，调用方可见 |

### 1.8 闸门、变异与读数

- 新增 `TestP235Round13Batch2Wiring`（3 条）：6 对 location 双向核对 +
  影子触发失败计数器 +1（stub self + 必炸 sink，精确打击同步方法）+
  回滚 savepoint 失败计数器 +1（真 `db_session` + monkeypatch 四件套：
  锁/心跳/健康检查/回滚，只留 savepoint 失败一条路径为真）。
- 桶计数改钉：**W=40 / X=174**（总数 334 不变）。
- 三次真实变异（强度均语义级）：M1 删 auto_rollback 整个接线语句 →
  红 3/3（locations/运行时/桶计数）；M2 换影子触发 location 字面量 →
  红 2/2（locations/影子运行时）；M3 删文档登记行 → 红 1/1。日志
  `mutate_p2_35_round13_batch2_result.log`。
- 实测：全部 P2 闸门六套件 **124 passed**；affected **230 passed**
  （auto_rollback 30 + canary_fallback_monitor 38 + shadow 模式 14 +
  shadow_comparison 11 + nonfinite_guards 61 + structured_parallel 14 +
  predict_text_integration 5 + scheduler 57）；import 烟测 + AST 绑定通过；
  BE 全称注释仍 98（本批新增注释经检测器复核零命中，闸门绿佐证）。
- 环境小插曲（记账）：多文件 pytest 混入一个不存在路径（`tests/test_predict_text_integration.py`
  实际在 `tests/unit/`）→ 静默 0 收集。已按既有教训先 `ls` 核对再跑。

---

## 一之三、#35 X 桶第三批：5 处接线（X 174 → 169）

### 1.9 接线清单（`tasks/pdf_report.py`，第六批 `save_pdf_bytes_failed` 的同族补全）

| location | 降级语义 |
|---|---|
| `tasks.pdf_report.save_job_to_redis_failed` | 任务状态写失败 → 用户轮询查不到任务（报告仍会生成，状态查询在本次 TTL 窗口内拿不到） |
| `tasks.pdf_report.get_job_from_redis_failed` | 读失败返回 None → 与「任务不存在」不可区分（假阴性） |
| `tasks.pdf_report.list_jobs_from_redis_failed` | 列表读失败返回 [] → 报告列表页凭空变空（部分数据） |
| `tasks.pdf_report.get_pdf_bytes_failed` | 字节读失败 → 下载接口拿不到报告（写入侧孪生点第六批已接） |
| `tasks.pdf_report.websocket_progress_notify_failed` | 进度推送 fire-and-forget 丢失 → 进度停在最后推送值（保持 debug 日志级别，靠计数可观测） |

跳过 1 条：`delete_pdf_bytes_from_redis`（C 型清理路径——删失败只留残留字节，
由 `_PDF_BYTES_TTL_SECONDS` 兜底，不影响业务语义）。

### 1.10 闸门、变异与读数

- 新增 `TestP235Round13Batch3Wiring`（2 条）：5 对 location 双向核对 + 一次运行时
  覆盖四个同步存取点（`_get_sync_redis` 换必炸替身后真调四个公开函数，同时断言
  降级返回值形态 = "看不见"：None/None/[]/None）。第五个（进度推送，需 ws 会话
  与 db 查询）由存在性断言守住并记账。
- 桶计数改钉：**W=45 / X=169**。
- 三次真实变异：M1 删 save_job_to_redis 接线 → 红 3/3（locations/运行时/桶计数）；
  M2 换 get_pdf_bytes location 字面量 → 红 2/2；M3 删文档登记行 → 红 1/1。
  日志 `mutate_p2_35_round13_batch3_result.log`。
- 实测：全部 P2 闸门六套件 **126 passed**；affected **93 passed / 10 skipped**
  （tasks/test_pdf_report + test_iss02_tasks_pdf_report + test_pdf_celery +
  test_csp_report_smoke + api/test_reports_api_extended）。
- **全称注释净值处置（0，两侧账不需写）**：本批两条新注释初稿写了「永远等不到
  结果」「进度条永远卡住」，触发 `test_inventory_ratchet_be`（97→98→100）。
  按 #38 纪律复核发现这两个断言本身**过度**——TTL 到期后任务本来就会消失、
  刷新页面会拿到终态，故不是"永远"。**处置：改写注释为精确表述**（"在本次 TTL
  窗口内拿不到""进度停在最后推送值"），棘轮维持 98，不做账也不动闸门。
  ⇒ 推论：**遇到全称注释棘轮变红，先问"这个断言是否站得住"，站不住就改写而非加数。**

---

## 一之四、#35 X 桶第四批：6 处接线（X 169 → 163）

### 1.11 接线清单（`api/v1/silences.py`，向 AlertManager 的同步）

这一簇的共性：**fire-and-forget 到外部系统，失败只记 error 日志，本地事务照常
提交、接口照样返回 200**，于是「静默规则的生效/删除/启停」在告警链路上与管理员
认知分叉。

| location | 端点 | 方向与语义 |
|---|---|---|
| `api.silences.create.am_sync_failed` | POST 创建 | 静默不生效：本地有、AM 没有 → 告警照常推送/通知，管理员却以为已静默 |
| `api.silences.create.am_rollback_failed` | POST 创建（补偿） | **漏预警**：commit 失败后的补偿删除也失败 → AM 留下孤儿静默，规则不存在而告警被继续抑制 |
| `api.silences.update.am_delete_failed` | PUT 更新 | **漏预警且不可补偿**：旧 AM 静默没删，且下面照样把 `am_silence_id` 清空 → 再也无法补偿删除 |
| `api.silences.update.am_push_failed` | PUT 更新 | 静默不生效：新窗口没推上去 |
| `api.silences.enable.am_push_failed` | POST 启用 | 静默不生效：本地 `is_active=True` 而 AM 侧仍按停用处理 |
| `api.silences.delete.am_sync_failed` | DELETE | **漏预警**：本地已删、AM 侧静默仍在，抑制到窗口结束 |

### 1.12 另裁定两簇「0 接线、全部记账跳过」（仍留 X 桶，文档裁）

| 簇 | 条数 | 理由 |
|---|---|---|
| `tasks/scheduler.py` | 7 | 3 条是 `Sentry capture_message/capture_exception` **自身失败**（提示词明令跳过类目）；4 条是清理任务 OSError（uploads unlink / 空目录 rmdir、artifacts stat / rmtree）——F 型保守清理：失败条目本轮跳过、**下轮定时任务按同一 cutoff 重试**，无不可恢复后果（其中一条连日志都没有，但后果仅"空目录残留"） |
| `monitoring/dedup_lock.py` | 6 | 2 条 `try_acquire_lock` 的 Redis 不可用已有 `_stats["fallback"]` 且由 `flush_lock_stats` 落 OperationLog（`dedup_lock_stats`，M 型）；2 条 `release_lock` 仅用于测试/主动清理、锁 TTL 5 分钟自动过期兜底（C 型）；1 条 `flush_lock_stats` 是审计上报自身失败（S 型）；1 条 `_get_redis_url` 回退环境变量属设计内回退 |

### 1.13 闸门、变异与读数

- 新增 `TestP235Round13Batch4Wiring`（2 条）：6 对 location 双向核对 + **端到端**
  行为断言（真调 `POST /api/v1/alerts/silences`，patch AM 推送抛异常，断言
  「接口 200 且计数器 +1」——正是这一簇的隐蔽性所在）。
- 桶计数改钉：**W=51 / X=163**。
- 三次真实变异：M1 删 create 接线 → 红 3/3（locations/端到端/桶计数）；M2 换
  create 的 location 字面量 → 红 2/2；M3 删文档登记行 → 红 1/1。日志
  `mutate_p2_35_round13_batch4_result.log`。
- 实测：全部 P2 闸门六套件 **128 passed**；affected **70 passed**
  （test_am_sync / test_silence / api 三件 alerts·silences）。
- **本批踩坑（已写入 MEMORY.md）**：`Edit` 的 `old_string` 若首行不带完整缩进，
  工具会做**空白模糊匹配**并把原有缩进吃掉 → 一次改 6 处全部
  `SyntaxError: expected 'except' or 'finally' block`。修法：`git checkout --`
  该文件后按各 except 的真实缩进（12/12/8/4/4/8）逐处重做，**每次改完立刻
  `py_compile`**（本批就是靠它当场发现，而不是等到跑测试）。

### 1.14 第四批自我修正：6 处接线 → 1 处（自查发现，随 CI 期间补做）

第四批提交（`0cd4dd4`）后、下一批开工前复核调用链，发现**原判断有 5 处站不住**：

| 项 | 事实 |
|---|---|
| 复核对象 | `app/monitoring/am_sync.py` 的 `push_silence` / `delete_silence` |
| 关键事实 | 两者各自 `except Exception` 捕获 HTTP/连接异常 → 转成返回值（None/False）→ 随后 `_write_sync_log(db=db, ...)` 写 **`am_sync_failed` OperationLog**（含 error 全文） |
| 调用点 | silences 5 个调用点传了 `db=db`（create/update/enable/delete），**真实 AM 失败有审计落点** |
| 结论 | silences 侧那 5 处 `except` 只在「am_sync 调用本身抛异常」的罕见边缘路径触发 → 计数器恒为 0，**指标本身成了误导** |
| 处置 | 移除 5 处接线 + 留改判注释；改记 M/V 型，X 桶回调（**W 46 / X 168**） |

唯一保留 `api.silences.create.am_rollback_failed`：补偿删除用 `db=None` 调用
（`_write_sync_log` 在 db=None 时直接 return ⇒ **无审计落点**），失败后 AM 侧留下
孤儿静默而本地规则已回滚 = 漏预警，这是唯一没有落点的真实降级。

**为什么第一版的门禁没抓到**：端到端测试 patch 的是 `am_sync.push_silence`
**本身**（让它抛异常），恰好绕过了 am_sync 内部的异常捕获——测的是"接线可被
调用"，不是"真实失败会经过这里"。这与本项目此前记录的「验证工具自身失效会伪装
成修复有效」同族。⇒ 教训：**行为断言必须让失败走生产代码的真实路径**，而不是
把被测函数的内部实现替换掉。

**闸门随之改造**（防复发）：
- `test_reclassified_five_have_no_counter`：**反向钉**，这 5 处不得再出现通用计数器
  接线（后人"顺手补个计数"会红）；
- 端到端断言改为**直接调端点函数 + 假 session**（测试环境 `get_db` override 把
  `session.commit` 绑成实例属性 `= session.flush`，类级 patch 拦不住，走 HTTP 也
  无法让 commit 失败——首版就是这么写成"假绿"的：响应仍是 200、计数器没动）；
- 修正变异 3/3 RED-OK/GREEN-OK（N1 删保留接线 → 红 3/3；**N2 把改判掉的一处
  加回来 → 反向钉红**；N3 删文档登记行 → 红 1/1），日志
  `mutate_p2_35_round13_batch4_fix_result.log`。

---

## 二、prettier 最终决议（提示词第 3 项：不允许第三次原样记账）

本轮实测（HEAD `3e5969d`，frontend 3.9.9）：

| 判据 | 第十一轮（记账 1） | 第十二轮（记账 2） | **本轮实测** |
|---|---|---|---|
| `--list-different` 不一致文件（src+scripts） | 437 | 437（未重测，原样转引） | **370**（scripts 0，全部在 src；降 67 全由类型收敛轮有机重排贡献，非专项治理） |
| prettier parser 存量 SyntaxError | 3 个 `.vue` | 3 个（原样转引） | **仍 3 个**：`AdminMonitoringPage.vue`(148:11) / `SilencesTable.vue`(78:9) / `TrainingRegistryCard.vue`(91:11)，HEAD 实测同位置 |
| CI 检查（`.github/workflows/` 对 `prettier`/`format:check`） | 0 命中 | 0 命中（转引） | **0 命中**（13 个 workflow 逐个 grep 复核） |

**决议：书面确认继续不做，但本次是带触发条件的终局决议，不是原样记账。**

新理由（本轮实测支撑）：

1. 3 个 `.vue` 的 SyntaxError 是**模板结构问题**，修它是代码改动（需单独评审 +
   渲染/单测验证），不是格式化任务；不修则全仓 `--write` 也拿不到「全仓一致」终态
   ——「先修 3 个 .vue 再分批 --write」的正确路径第十一轮已写明，但把它并进
   格式决议执行，等于把代码改动伪装成格式改动。
2. 370 文件全量重排的 diff 会使后续任何 bisect/回退/评审成本上升，而收益为零
   （CI 无格式门、无协作者格式冲突报告、毕业设计答辩前不做无收益大 diff）。

触发条件（满足任一即执行，写入 `CODE_REVIEW` 台账；执行方式限定）：

1. CI 增加格式门（`pr-quality-gates.yml` 或新 workflow 调用 `format:check`）；
2. 后续轮次重测不一致文件数**有机降至 < 50**；
3. 项目进入答辩后归档清理阶段且用户显式指令。

执行方式（触发时）：先修 3 个 `.vue` parser 报错（各配渲染验证）→ 按目录分批
`prettier --write`（每批一个独立提交 + 一次前端全量 + `vue-tsc` 0 错）→ 每批
落盘读数。在触发条件满足前，任何轮次不得再原样转引「决定不做」。

---

## 三、口径变化影响面结论

0. **本轮累计状态**（四批 + 一次修正后）：X 桶 **168** 条 = 待接 155 + 已裁定跳过 27
   （第一批 2 + 第二批 11 + 第三批 1 + 第四批 13〔其中 5 处经复核由接线改判〕）；
   已接 **19 处**（7+6+5+1），调用点 26→**45**；W=46。
   下一批候选续：`core/model_engine/loading.py` 8（真候选集中在「侧车哈希不可读
   →完整性锚点缺失」与「审计路径解析失败静默跳过」，其余已有
   `_incr_model_fallback` 计数或 critical 日志）、`api/v1/alerts/__init__.py` 6
   （预裁定后仅 2 条真候选：final commit 失败、detail 解析退化）、
   `training_jobs` 5 ×2、`model_registry_v2` 4、`am_sync` 4、
   `anomaly_detection_service` 4、`canary_fallback_monitor` 4、
   `observability/aggregate` 3、`model_engine/inference` 2 等。
   ⚠️ 取新簇时的前置动作（第四批教训）：**先追调用链确认失败到底落在哪一层**
   ——被调方自己 `except` 并写审计/指标时，接线只会造出恒为 0 的假指标。
1. **桶计数改钉（W 27→34→40 / X 187→180→174）**：只影响 `test_batch6_bucket_counts_pinned`
   的 expected 与 P2_11 附录；总数 334 不变证明无候选丢失/新增。X 桶下降 13 的
   去向全部可逐条指认（1.1/1.6 表），无静默蒸发。
2. **全称注释净值 +1（97→98）**：仅 `cache.py:152` 新增命中（「只会看到」），
   P2_10 附录两侧账已写、闸门同步改钉；validation.py 5 处新注释经检测器复核
   **零命中**（用词避开了全称词），非漏账。
3. **P2_11 附录追加「第十三轮同步」块**：7 个 location + 2 条跳过裁定 + 结案
   条目；按「历史快照只追加不改」，第十一/十二轮既有条目不动。
4. **detail-JSON 下游零影响**：本批只动 `record_silent_degradation`（metrics 计数，
   不写 `OperationLog.detail`），不触及审计 detail 口径；`TestAuditDetailJsonDownstream`
   消费侧清单不变（121 passed 含该项）。
5. **X 桶清单文件（JSON 产物）已随扫描器复跑刷新**：line 号因本批加注释而位移的
   条目以新 JSON 为准；跳过 2 条在新 JSON 中仍为 X（`validation.py:88`、
   `cache.py:308`），与 1.2 记账一一对应。
