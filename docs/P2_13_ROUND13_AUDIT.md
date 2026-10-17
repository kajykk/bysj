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

## 一之五、#35 X 桶第五批：6 处接线（X 168 → 163，其中 1 处为非 except 路径）

### 1.15 接线清单（`app/tasks/model_training.py`，Celery worker 侧）

| location | 语义 |
|---|---|
| `tasks.model_training.save_job_to_redis_failed` | 任务状态写失败 → 轮询查不到这个训练任务 |
| `tasks.model_training.get_job_from_redis_failed` | 读失败返回 None，与「任务不存在」不可区分（假阴性） |
| `tasks.model_training.list_jobs_from_redis_failed` | 列表读失败返回 [] → 训练任务列表凭空变空（部分数据） |
| `tasks.model_training.update_job_in_redis_failed` | 状态更新丢失 → 进度停在旧值、完成状态更新不上去 |
| `tasks.model_training.artifact_register_failed` | **本批最高价值**：产物已落盘但注册表里没有它 → 该模型无法激活上线，这次训练等于白跑 |
| `tasks.model_training.artifact_dir_missing` | **非 except 路径**：产物目录不存在时 `logger.warning` + **提前 return**（连 handler 都进不去），训练状态已是 completed 而注册表永远没有该模型。扫描器只看 except handler ⇒ 它不在 X 桶候选里，是本批顺带发现的漏网路径 |

**调用链已逐个追过**（第四批教训）：四处是叶子级 Redis 调用；
`register_training_artifact` → `registry.register_model` 也不吞异常 ⇒ 失败确实
落在这些 handler 里，计数器不会恒为 0。

### 1.16 新增一条全仓闸门：接线不得是死代码

`TestP235WiringIsNotDeadCode`：AST 扫全仓 `app/`，若某 except handler体内出现过
`return`/`raise`，其后的 `record_silent_degradation` 调用即判死。

**这条闸门的由来正是本批真实犯的错**：脚本以「logger 块 + return」为锚点插入时，
`get_job_from_redis` / `list_jobs_from_redis` 两处接线被插到 `return None` /
`return []` **之后** —— 语法合法、`py_compile` 通过、字面量断言也能找到 location，
但**运行时永远执行不到**（与第四批 am_sync 同族的假接线）。
发现方式：运行时断言里 `artifact_register_failed` 没涨 → 顺着查下去才看到
list_jobs 的计数器也没涨。⇒ 又一条「门禁全绿不等于接线有效」的实例：
**存在性断言 + 语法检查都测不出语句顺序错误，只有真跑一次（或 AST 判可达）才行。**
读源码必须用 `utf-8-sig`（`app/api/v1/__init__.py` 带 BOM）。

### 1.17 闸门、变异与读数

- 新增 `TestP235Round13Batch5Wiring`（2 条）：6 对 location 双向核对 + 一次运行时
  覆盖六处（`_get_sync_redis` 换必炸替身 + `TRAINED_ROOT` patch 到 `tmp_path`
  后分别触发「目录缺失」与「注册抛异常」两条产物路径）。
- 桶计数改钉：**W=51 / X=163**（新增的 `artifact_dir_missing` 在非 except 路径，
  不影响 X 桶计数）。
- 三次真实变异：M1 删 save_job 接线 → 红 3/3；**M2 把 list_jobs 接线挪到
  `return []` 之后（复现本批真实错误）→ 死接线闸门 + 运行时计数器双红**；
  M3 删文档登记行 → 红 1/1。日志 `mutate_p2_35_round13_batch5_result.log`。
- 实测：全部 P2 闸门六套件 **132 passed**（test_p2_11 40 + test_p2_10 10 +
  其余四套件 82）；affected **40 passed**（tasks/test_model_training +
  test_iss02_tasks_model_training）。
- 全称注释：两条新注释初稿含「永远」，改写时先换成「不会」**仍命中**
  （`不会` 也在全称词表内）⇒ 二次改写为「进不了注册表」「更新不上去」，
  棘轮维持 98，不做账不动闸门。**推论补充：改写要逐个词避开整张表，
  换同义词未必安全。**

---

## 一之六、#35 X 桶第六批：4 处接线（X 163 → 159，跨三文件）

### 1.18 接线清单

三文件跨层（任务侧快照 + 请求侧 webhook + 观测侧统计），**调用链已按第四批教训逐个追过**：

| location | 所属文件 | 语义 |
|---|---|---|
| `services.model_predict.training_jobs.load_failed` | `services/model_predict/training_jobs.py` | 启动快照读失败 → `TRAINING_JOBS` 为空，重启后所有训练任务在管理端"不存在"（用户以为任务从没跑过）|
| `services.model_predict.training_jobs.save_failed` | 同上 | 快照写失败 → 任务状态只在进程内存，重启即丢（用户可见的任务历史凭空清空）|
| `api.alerts.webhook.final_commit_failed` | `api/v1/alerts/__init__.py` | webhook 末尾 commit 失败 → 本请求逐条 savepoint 落库的告警随这次 commit 一起回滚，但响应仍 200 且 `failed=0`（逐条计数统计不到 commit）——**响应与数据结构双双说谎**，告警审计整批丢失 |
| `services.observability.aggregate.lock_stats_unavailable` | `services/observability/aggregate.py` | `dedup_lock` 统计读失败回填四个 0，观测页当作真实数据展示——**假数据比缺数据更危险**（运维据此判断去重是否正常）|

### 1.19 跳过 8 条（书面记账，仍留 X 桶，机器不裁、文档裁）

`training_jobs` 的 get/list/update 三处失败其实落在第五批刚接线的被调方
（`tasks.model_training.*`）或已有 `storage_degraded` 可见标志；`alerts` 的
detail 解析退化是脏数据且有 warning；`model_registry_v2` 的 promote 失败以 None
上抛（调用方可见）、quarantine 失败属嵌套清理；`model_engine/inference` 的
persist 失败下轮自愈（R 型）、Prometheus 上报失败属 S 型（自报失败）。

### 1.20 闸门、变异与读数

- 新增 `TestP235Round13Batch6Wiring`（3 条）：4 对 location 双向核对（源码+文档）+
  三处运行时覆盖（`training_jobs` 两处用其可注入的 loader/dumper 触发、`aggregate`
  patch `dedup_lock.get_stats` 触发并验证回填的是全 0 假数据）。`alerts` 的 commit
  失败**未做运行时断言**——它在 FastAPI 端点内，测试环境 `get_db` override 把
  `session.commit` 绑成实例属性（第十二轮第四批同类），无法在不伪造整套依赖注入的
  前提下触发，故只由存在性断言守住并记账（同族陷阱见 §1.14「验证工具自身失效会
  伪装成修复有效」）。
- 桶计数改钉：**W=55 / X=159**（总数 334 不变）。
- 三次真实变异：M1 删 `training_jobs` 一处接线 → 双向断言 + 运行时断言双红；
  M2 删 `aggregate` 接线 → 红；M3 删 P2_11 附录登记行 →
  `test_locations_wired_in_code_and_doc` 红。均 RED-OK/GREEN-OK，日志
  `mutate_p2_35_round13_batch6_result.log`。
- 配套工具：`tests/tools/watch_ci.py` 增 `cancelled` 识别（本仓 workflow 带
  concurrency cancel-in-progress，被后续 push 取代的 job 是 cancelled 而非
  failure，不再误判为 CI 失败）。

---

## 一之七、#35 X 桶第七批：2 处接线（X 159 → 157，`model_engine/loading.py`）

### 1.21 接线清单

本簇 8 条里只有这两条经调用链确认是真沉默（余 6 条见 1.22）：

| location | 所属文件 | 语义 |
|---|---|---|
| `core.model_engine.loading.audit_path_resolve_failed` | `core/model_engine/loading.py` | 审计中某模型路径解析失败 → 被 `skipped`，既不进 `missing` 清单，调用方（preload）又**丢弃整个 summary 返回值**——它静默逃过完整性审计（锚点是否存在从此无人再问）|
| `core.model_engine.loading.keras_compat_load_failed` | 同上 | `_load_model` 的 Keras 兼容重载（quantization_config 路径）二次加载失败 → 直接 `return None`，调用方按"没有这个模型"走 fallback（分数通道彻底缺席，却和"从未配置"无法区分）|

### 1.22 跳过 6 条（书面记账，仍留 X 桶，机器不裁、文档裁）

82（侧车不可读）与 425（adapter 加载失败）均已被调用方 `_incr_model_fallback`
计数（**M 型**，侧车来源还区分 `unreadable`/`absent`）；284（PermissionError）/
290（OSError）是 `preload` 的 **critical 日志**（loud，与既有接线口径缺
`missing_file`/`failed` 的 warning 级相对）；588 是本地无缓存→Hub 下载的
**设计内回退**；704 是 sklearn 兼容补丁的 **best-effort**（失败后下游 transform
可见）。

### 1.23 闸门、变异与读数

- 新增 `TestP235Round13Batch7Wiring`（3 条）：2 对 location 双向核对 + 两处运行时
  覆盖（patch **使用方命名空间** `ld.resolve_model_path`；真调 `_load_model` 的
  `.keras` 分支，注入假 `tensorflow`/`keras` 模块 + 探针模型使前置守卫全过，
  第一次 load_model 抛带 `quantization_config` 的 ValueError 进兼容分支、第二次
  抛异常）。
- 桶计数改钉：**W=57 / X=157**（总数 334 不变）。
- 三次真实变异：M1 删 audit 接线 / M2 删 keras 接线 / M3 删 P2_11 登记行，
  均 RED-OK/GREEN-OK，日志 `mutate_p2_35_round13_batch7_result.log`。
- **本批踩坑（已写入 MEMORY.md）**：`loading.py` 用 `from ... import resolve_model_path`
  —— patch **定义方** `model_registry` 对使用方不可见（首版测试假绿）；必须 patch
  **使用方命名空间** `ld`。同理 `_load_model` 有 `MODEL_PATHS`/`is_model_enabled`/
  `_abs_path`/缓存锁多道前置守卫，驱动其内部分支需逐道满足。

---

## 一之八、#35 X 桶第八批：4 处接线（X 157 → 153，`anomaly_detection_service.py`）

### 1.24 接线清单

`detect_all` 聚合 4 个**安全**异常检测器，每个各自 try/except 吞掉异常并继续：

| location | 语义 |
|---|---|
| `services.anomaly_detection.high_frequency_detection_failed` | 高频撞库/爬虫检测整类漏检 |
| `services.anomaly_detection.off_hours_detection_failed` | 非工作时间访问整类漏检（潜在数据外泄）|
| `services.anomaly_detection.cross_region_detection_failed` | 异地访问整类漏检（账号被盗迹象）|
| `services.anomaly_detection.lateral_detection_failed` | 横向越权整类漏检 |

调用方（Celery `scan_anomalies`）只拿到合并后的 findings 列表，"本次没有异常"与
"检测器宕机"**无法区分**——静默安全盲区。

### 1.25 相邻簇留档（`monitoring/notifier.py` 5 条，本轮未接线）

三处 `send` 失败经 `_write_channel_log` 落 `alert_channel_failed` OperationLog
（**M 型**），`_dispatch` 的 except 同样进该落点，`_write_channel_log` 自身失败属
上报失败（**S 型**）。故整簇无新接线价值，留档。

### 1.26 闸门、变异与读数

- 新增 `TestP235Round13Batch8Wiring`（2 条）：4 对 location 双向核对 + 一次运行时
  覆盖（四检测器各 patch 成必炸，断言计数器各 +1 且 `detect_all` 仍返回空列表）。
- 桶计数改钉：**W=61 / X=153**（总数 334 不变）。
- 三次真实变异：M1 删任一接线 / M2 改 location 字面量 / M3 删登记行，均
  RED-OK/GREEN-OK，日志 `mutate_p2_35_round13_batch8_result.log`。

---

## 一之九、#35 X 桶第九批：2 处接线（X 153 → 151，`canary_fallback_monitor.py`）

### 1.27 接线清单

本模块是 **Celery 不可用时的最后安全网**（金丝雀自动回滚的兜底监控）：

| location | 语义 |
|---|---|
| `services.canary_fallback_monitor.rollback_check_failed` | 接管后 `check_all_canaries` 本体失败 → 超阈值金丝雀无人回滚（故障扩大），只记 error 日志 |
| `services.canary_fallback_monitor.loop_unexpected_error` | 循环内未预期异常（含心跳读取失败）→ 本轮接管判定/回滚机会错过而循环继续 |

### 1.28 跳过 2 条（书面记账，仍留 X 桶，机器不裁、文档裁）

67（`_bump_takeover_counter` 自身失败）是 **S 型**；88（breaker 快照失败）走"附加
信号降级为主判据心跳"——连心跳也读不到时落在 `get_check_heartbeat_age` 被调方，
此处不重复计数。

### 1.29 闸门、变异与读数

- 新增 `TestP235Round13Batch9Wiring`（3 条）：2 对 location 双向核对 + 两次运行时
  覆盖（breaker 非 closed 下接管后回滚检查抛异常；心跳读取抛异常走外层 except，
  每次循环用 patch `asyncio.sleep` 抛 CancelledError 截断为一轮）。
- 桶计数改钉：**W=63 / X=151**（总数 334 不变）。
- 三次真实变异：M1 删接线 / M2 改 location 字面量 / M3 删登记行，均
  RED-OK/GREEN-OK，日志 `mutate_p2_35_round13_batch9_result.log`。
- **本批踩坑**：`import app.services.auto_rollback_service as ars` 因包 `__init__`
  同名 from-import 单例而拿到**实例**而非模块——patch 模块级函数必须用
  `importlib.import_module` 拿真模块。这是比第七批（from-import 打使用方）更
  阴险的反例：**import 遮蔽**。

---

## 一之十、#35 X 桶第十批：4 处接线（X 151 → 147，`shadow_comparison_service.py`）

### 1.30 接线清单

影子对拍是训练产物激活前的**质量门**（样本累积 → 一致率 → 激活校验）：

| location | 语义 |
|---|---|
| `...fire_no_event_loop_skipped` | 生产路径无事件循环时该样本对拍直接跳过（长期即统计停滞）|
| `...shadow_check_failed` | 管线内未预期异常，本样本丢失（non-blocking 名义下悄悄发生）|
| `...candidate_load_failed` | 候选产物加载失败，该模型对拍管线实质死亡 |
| `...candidate_predict_failed` | 候选预测失败，样本以 (None, None) 丢弃 |

四处最终都收敛到同一种失效：`is_shadow_acceptable` 恒返回 `(True,
"insufficient_samples(...)")` —— **证据不足放行**，坏模型可直接激活上线。

### 1.31 闸门、变异与读数

- 新增 `TestP235Round13Batch10Wiring`（2 条）：4 对 location 双向核对 + 一次
  运行时覆盖四条路径（① `asyncio.to_thread` 丢进无 loop 线程；② `_load_candidate`
  必炸穿透到 `_shadow_check` 外层；③ 真实坏 `.pkl`；④ predict 抛异常对象。
  ② 之后 `monkeypatch.undo()` 恢复真实 `_load_candidate`，避免干扰 ③）。
- 桶计数改钉：**W=67 / X=147**（总数 334 不变）。
- 三次真实变异：M1 删任一接线 / M2 改 location 字面量 / M3 删登记行，均
  RED-OK/GREEN-OK，日志 `mutate_p2_35_round13_batch10_result.log`。
- **本批踩坑**：async 测试内直接调 `fire_shadow_check` 反而会**成功建 task**
  （循环内 create_task 合法）——触发"无事件循环"分支必须把调用丢进 worker
  线程。这是"测试环境本身改变被测语义"的又一例。

---

## 一之十一、#35 X 桶第十一批：3 处接线（实记录 X 147 → 145，`file_security_service.py`）

### 1.32 接线清单

上传安全网的 fail-open 降级放行（`clamav_fail_open=true` 时未扫描按已扫描处理）：

| location | 语义 |
|---|---|
| `...clamav_dependency_missing_fail_open` | pyclamd 未安装 → 跳过扫描放行（本仓默认即无 pyclamd，此分支真实可达）|
| `...clamav_unavailable_fail_open` | clamd 守护进程不可达 → 跳过扫描放行 |
| `...clamav_error_fail_open` | 扫描抛异常 → 跳过扫描放行 |

### 1.33 不接线（书面记账，仍留 X 桶，机器不裁、文档裁）

- `strip_image_exif` 失败（118）：返回 `(False, ...)`，调用方
  `process_uploaded_file` 直接拒绝保留——调用方可见的 V 型；
- `excel_export_service.py` 3 处：全部返回 `success=False + error_message`
  结构化失败，调用方同样可见。

### 1.34 闸门、变异与读数

- 新增 `TestP235Round13Batch11Wiring`（2 条）：3 对 location 双向核对 + 一次
  运行时覆盖三条 fail-open 路径（另两条注入假 `clamd` 模块驱动）。
- 桶计数改钉：**W=70 / X=145 / P=15**（总数 334 不变）。**口径变化**：本批首次把
  ImportError **探针记录本身**接线（file_security 的 ImportError 探针分支 wired=True
  → W），P 16→15 为合法收缩；实记录 X 147→145（2 处 X→W），W 67→70（+2 实接线
  +1 探针接线）。
- 三次真实变异：M1 删任一接线 / M2 改 location 字面量 / M3 删登记行，均
  RED-OK/GREEN-OK，日志 `mutate_p2_35_round13_batch11_result.log`。

---

## 一之十二、#35 X 桶第十二批：3 处接线（X 145 → 142，`core/model_engine/predict.py`）

### 1.35 接线清单

「分数/对照数据看似有效实则失真，且响应形态与正常态同形」的三条路径：

| location | 语义 |
|---|---|
| `core.model_engine.predict.experimental_v123_unavailable` | v1.23 对照路整路失败（加载或推理抛异常）→ `experimental_external_*` 保持 None、`available=False`，与「该模型未部署」同形，对照数据静默消失 |
| `core.model_engine.predict.lite_calibrator_unavailable` | 校准产物缺失/被禁用 → 保底返回未校准概率，响应 `probability_calibrated=False` 与「校准未启用」同形 |
| `core.model_engine.predict.lite_calibration_apply_failed` | 产物在但执行失败（非 `IsotonicRegression` 且无 `predict_proba` 的路径）→ 同样是未校准概率，成因与上一条不同故分开计数 |

### 1.36 不接线（书面记账，仍留 X 桶，机器不裁、文档裁）

- `_run_adapter`（X 桶）：同一函数内紧邻已有 `adapter_hit` / `adapter_miss`
  专用计数器成对覆盖「适配器不可用」，按 M 桶口径不重复接通用计数器；
- `_run_experimental_v121` 外层（X 桶）：实测
  `get_model_info("structured_v1.21_binary_lr")` 返回 `None`（注册表已移除 v1.21
  四条目），该 `try` 块运行时**不可达** → 接线即死代码，与第五批
  `TestP235WiringIsNotDeadCode` 同族。注：同函数内层的 scaler fallback
  （第二批已接）在模型被重新启用后可恢复可达，与本条不是同一判据。

### 1.37 闸门、变异与读数

- 新增 `TestP235Round13Batch12Wiring`（3 条）：3 对 location 双向核对 + 一次
  运行时覆盖三条路径（`_load_model_async` 必炸驱动 ① / ②；换成无
  `predict_proba` 的假校准器驱动 ③）+ 一条反向钉（已裁定不接线的两个 handler
  用**日志语义锚点** `"v1.24 adapter unavailable"` /
  `"v1.22 experimental real binary LR unavailable"` 定位，不得出现
  `record_silent_degradation`，锚点命中数必须为 2）。
- 桶计数改钉：**W=73 / X=142 / P=15**（总数 334 不变）。本批为纯实记录迁移
  （3 处 X→W），无探针接线，故无桶间口径变化。
- 接线调用点实测 70→73（改前值由「改后 73 − 本批新增 3」得出；第十一批登记的
  69 与本轮实测口径相差 1，历史快照不回改，差异在 P2_11 附录本条记账）。
- 三次真实变异：M1 删任一接线 / M2 改 location 字面量（含闭合引号，防子串
  逃逸）/ M3 删 P2_11 附录登记行，均 RED-OK/GREEN-OK，日志
  `mutate_p2_35_round13_batch12_result.log`。

---

## 一之十三、#35 X 桶第十三批：5 处接线（X 142 → 137，跨三文件）

### 1.38 接线清单

五处都是「安全网失效或部分数据，且**调用方从返回值上看不出来**」：

| location | 语义 |
|---|---|
| `monitoring.escalation.notify_failed` | 升级通知发送失败**不影响本轮提交**：`escalation_level` 照常推进并在循环结束后 commit，告警被标成「已升级」，但没有任何人收到通知。既有的 failure 信号只挂在 `escalation_notify_duration_seconds` 的 result 标签上（顺带记录、非专用失败计数） |
| `core.idempotency.begin_failed_fail_open` | Redis 故障 → 放弃幂等控制返回 `(True, None)`，调用方据此当成首次请求执行，重复 upsert 会真的写两次 |
| `core.idempotency.settle_failed` | 首次响应没写进 Redis → 窗口内重复请求读到 `__PENDING__` 占位被判「处理中」，重放能力静默丢失 |
| `core.idempotency.dismiss_failed` | 失败请求没释放幂等键 → 键残留至 TTL 到期，期间客户端修正后的重试被判「处理中」而拒绝 |
| `services.validation_engine.calculate_metrics_failed` | 指标计算中段抛异常时 `accuracy`/`precision` 等已写入，返回「残缺但看起来合法」的 ValidationMetrics，无字段能表明后半段没算出来 |

### 1.39 不接线（书面记账，仍留 X 桶，机器不裁、文档裁）

- `services/validation_engine.py::_run_model_inference`（`return None`）：
  调用方 `validate_model` 会写入 `result.errors`（"Model inference unavailable …"）；
- `services/validation_engine.py::_compute_baseline_metrics`（`return None`）：
  调用方同样写入 `result.errors`（"Baseline metrics unavailable …"）。
  两条都是**调用方可见的 V 型**，与第十一批「EXIF 剥离失败返回 False、调用方
  直接拒绝保留」同口径。接线只会给"调用方已处理"的路径加计数，是第四批
  silences 教训的反例。
- 另注：`monitoring/escalation.py` 的另外两条 X 候选本轮也裁定跳过 ——
  L101 已有专用计数器 `alert_detail_parse_failed_total.inc(1, stage="escalation")`
  （M 型）；L110 是**该计数自身**上报失败（S 型）。

### 1.40 闸门、变异与读数

- 新增 `TestP235Round13Batch13Wiring`（3 条）：5 对 location 双向核对 + 一次
  运行时覆盖五条路径（① `CompositeNotifier.send` 抛异常，db 用 MagicMock 建模
  AsyncSession 且必须配 `db.flush` —— `record_audit` 内部 await 它；② ③ ④ 注入
  `get_redis_client` 返回全抛的假 Redis；⑤ 把模块级 `roc_auc_score` 换成抛
  `RuntimeError`，穿透内层只吃 `ValueError` 的 try，断言 `accuracy/f1` 有值而
  `auc` 为 None —— 直接把「部分数据」形态钉进测试）+ 一条反向钉（两条 V 型用
  日志语义锚点 `"ValidationEngine: 模型推理失败"` /
  `"ValidationEngine: 加载 baseline dataset 失败"` 定位，锚点命中数必须为 2）。
- **踩到并记录一条第九批同族陷阱**：`import app.services.validation_engine as ve`
  拿到的是 `app/services/__init__.py` 导出的 **ValidationEngine 实例**（包属性遮蔽
  子模块），patch 时报 `AttributeError: 'ValidationEngine' object has no attribute
  'roc_auc_score'`；必须 `importlib.import_module("app.services.validation_engine")`。
- 桶计数改钉：**W=78 / X=137 / P=15**（总数 334 不变）。本批为纯实记录迁移
  （5 处 X→W），无探针接线、无桶间迁移。
- 接线调用点实测 73→78。
- 三次真实变异：M1 删 `core.idempotency.begin_failed_fail_open` 接线（整块删除）
  / M2 改 `monitoring.escalation.notify_failed` location 字面量（含闭合引号）
  / M3 删 P2_11 附录登记行，均 RED-OK/GREEN-OK，日志
  `mutate_p2_35_round13_batch13_result.log`。

## 一之十四、#35 X 桶第十四批：4 处接线（X 137 → 133，跨两文件）

### 1.43 接线清单

四处都是「**保护层的保护罩**掉了，而加载/读取本身照样成功」——与前面批次「业务
结果缺斤少两」不同，本批降级的是**加固本身**：

| location | 所属文件 | 语义 |
|---|---|---|
| `core.safe_pickle.joblib_env_guard_unavailable` | `core/safe_pickle.py` | ISS-006 的「生产环境强制哈希校验」靠 `settings.app_env` 判定；settings 读不到 → 加固整段跳过，`require_hash` 停在调用方传入的 False，函数照常返回模型对象 —— **调用方以为完整性校验过了** |
| `core.safe_pickle.torch_env_guard_unavailable` | 同上 | ISS-046 同理：`weights_only` 停在 False，`torch.load` 走回可执行任意代码的路径并成功返回，与「已启用 weights_only 保护」完全同形 |
| `core.model_registry_v2.registry_file_unparsable` | `core/model_registry_v2.py` | 注册表整体损坏 → 旁路备份后**以空表启动**；`registry` 为空与「全新注册表」一模一样，训练资产记录的历史丢失不在任何返回值里（旁路文件名虽有时间戳，但不是遥测）|
| `core.model_registry_v2.registry_records_dropped` | 同上 | 部分记录结构坏 → 已加载的保留、其余丢弃；registry **非空且可用**，只是少了几条，没有任何字段能表明「本应有更多」|

### 1.44 跳过 1 条 —— fail-closed，不是降级（V 型）

`core/safe_pickle.py::_restricted_unpickler_class` 导入 `joblib.NumpyUnpickler`
失败时返回 `None`，初看像「白名单静默失效」，实际是 **fail-closed**：全仓唯一
调用点在下一句就把 None 翻译成 `raise RuntimeError`（该函数文档串与
`_restricted_joblib_load` 注释都明示「绝不静默退回无白名单的 `joblib.load`」，
并附实测：「退回的后果是恶意载荷会被真的执行」）——调用方必见异常，与第十一批
EXIF 剥离同属 V 型。

反向钉除断言「该 handler 不得出现接线」外，还**额外钉住 fail-closed 判据本身**
（`unpickler_cls is None or validate is None`）：这条判据是「不接线」裁定的前提，
一旦被移除，返回 None 就不再等于拒绝加载，闸门会当场红并强制重审。

### 1.45 同批再确认：两簇历史已裁定，不拔桩

`tasks/scheduler.py` 7 条（前批已判 F 型保守清理：失败条目本轮跳过、下轮按同一
cutoff 重试）与 `model_registry_v2` 的 promote / quarantine 2 条（第六批已判定：
promote 失败以 None 上抛调用方可见、quarantine 失败属嵌套清理）均按「历史快照
不回改」维持 X 桶留档；本批接的 `_load_registry` 两条是**此前未裁过的**两个
handler（空表启动 / 部分加载）。每批开工先做存在性核查这件事本身值得坚持：
本轮因此避开了 9 条已裁定项的重复劳动。

### 1.46 闸门、变异与读数

- 新增 `TestP235Round13Batch14Wiring`（3 条）：4 对 location 双向核对（源码+文档）
  + 一次运行时覆盖四条路径 + 一条反向钉。运行时手法两处值得一提：
  ① 两条 `safe_*_load` 的环境加固分支采用函数内 `from app.core.config import
  settings`，**不必伪造 import machinery** —— 直接把 `app.core.config.settings`
  换成 `app_env` 访问抛异常的对象即可命中（planning 阶段一度以为要 monkeypatch
  `sys.modules`，实测不用）；
  ② 注册表两条各在 tmp_path 造一份损坏 / 缺字段 JSON 后构造 `ModelRegistryV2`，
  并顺带断言「部分加载后 registry 里只有好记录」这一**缺陷形态**本身。
- 扫描器+分类器复跑：X 137→133、W 78→82、P 15 不变，总数 334 不变（纯实记录迁移）。
- 桶计数改钉：**W=82 / X=133 / P=15**；接线调用点实测 **78→82**。
- 四次真实变异：M1 删 safe_pickle.joblib 接线 / M2 改 registry location 字面量
  / M3 删 P2_11 附录登记行 / **M4 反向变异**（给已裁定 fail-closed 的 handler 偷偷
  加接线，反向钉必须红），均 RED-OK/GREEN-OK，日志
  `mutate_p2_35_round13_batch14_result.log`。
- 门禁跑分：P2 六闸门 **155 passed**；affected（含 `test_iss02_safe_pickle` /
  `unit/test_safe_pickle_whitelist` / `test_model_registry_v2` /
  `test_model_registry_atomicity` / `test_training_artifact_registry` 等 10 文件）
  **154 passed**。

**勘误（本批 commit message）**：第十四批提交信息的「未验证」段落里混进一句无
意义病句（"...为其依赖注入 —— 由于部署过程中安装过程依赖于文件"），与本批无关、
不代表任何未验证项。按「禁止 ref 重写」纪律不用 `--amend` 抹除，改为在此书面
勘误：本批真实未验证项只有三条 —— 后端全量由 CI 兜底、前端零改动未跑 vue-tsc、
safe_pickle 两条路径只用假 settings 验证过。

**连带修复（本批发现）**：上一批插入「一之十三」节时把 `## 二、prettier 最终
决议` 的标题行一并替换掉了 —— 文档结构受损但无任何闸门覆盖（无 CI/doc lint）。
本批插入「一之十四」时一并恢复该标题。**记账：Markdown 标题级的编辑事故目前没有
自动防护**，后续插入新节应以「标题行 + 紧邻上下文」为锚点，而不是拿下一节标题当
锚点。

---

## 一之十五、#35 X 桶第十五批：3 处接线（X 133 → 130，跨三文件）+ 12 处不接线

### 1.47 接线清单

三处都是「**失效的东西是别人判断的依据**」——它自己不是结果，却是别人解读结果的
凭据：

| location | 所属文件 | 语义 |
|---|---|---|
| `main.sidecar_audit_skipped` | `main.py` | 启动时模型侧车完整性审计失败 → 整段跳过，「缺失 / 陈旧」的可见性随之消失。启动日志里不再有任何一行说明这次审计没跑过，与「审计通过、全部一致」完全同形 —— 而侧车是 strict 环境下拒绝加载的依据，其完整性从此无人再问 |
| `services.model_predict.fusion.canary_routing_failed` | `services/model_predict/fusion.py` | 灰度路由决策失败 → `canary_routed` 保持 False，本该进灰度的用户静默走 stable 版本，且响应体不会带 `canary_routed` 标记 —— 灰度样本分配失真（灰度组被稳定版污染），而灰度指标自己看不出来 |
| `services.model_predict.inference.model_fingerprint_failed` | `services/model_predict/inference.py` | 模型指纹是 ML 缓存键的版本前缀；计算失败退化为 `"unknown"` 后，「换模型 → 键前缀变化 → 旧缓存自然失效」整套机制失效，用户命中上一个模型版本的缓存结果 |

### 1.48 不接线 12 处（本批大头，三类各自独立取证）

开工按 MEMORY §0 的纪律先做存在性核查，一口气避开 **22 条**已裁定项（loading 6 /
dedup_lock 6 / silences 5 / notifier 5 = 历史批次逐条判过），再对新簇做可达性实测，
又按下 12 处。三类裁定各自的**硬证据**：

**① `core/celery_app.py` 3 条 —— 计数落不到 `/metrics`**（第四批同族陷阱）

三个 request_id 传播回调（`_propagate_request_id` / `_bind_request_id` /
`_unbind_request_id`）的失败确实是静默的，但接线点在 **worker / beat 进程**：
- `docker-compose.yml:201` `celery -A app.core.celery_app worker`、
  `:252` `... beat` —— 与 web 是**独立 service / 独立进程**；
- 全仓 grep `PROMETHEUS_MULTIPROC_DIR` / `MultiProcessCollector` /
  `start_http_server` **零命中** —— 没有多进程收集器，worker 也没有自己的
  metrics 端口。

⇒ 计数只会留在 worker 进程内存里，`/metrics` 永远读不到。**这和第四批「计数器
恒为 0 的指标本身就是误导」是同一条判据**：不接。（若将来引入 multiprocess
collector，这三条要重审。）

**② `ml/unified_model_interface.py` 3 条 —— 生产链路不可达 = 死代码**

`UnifiedModelWrapper.predict/predict_proba` 的失败会退到启发式兜底，形态上像真
降级；但实测它的唯一引用方是 `ml/canary_controller.py`，而 `CanaryController`
自身在 `app/` 下**没有任何实例化点**（只在自己文件与 `ml/__init__.py` 的文档
字符串里出现），`ml/__init__.py` 更明示「按功能分类 re-export（**仅标注，不实际
导入**，避免循环依赖）」。⇒ 与第十二批 `_run_experimental_v121` 同口径：接线即
死代码。

**③ `services/excel_export_service.py` 3 条 —— 调用方可见（V 型）**

三处 `except` 都返回 `ExcelExportResult(success=False, error_message=str(exc))`，
`success` 字段就是显式失败信号，与第十一批 EXIF 剥离同口径。

**其余零散**：`main.py:216` 的 preload 失败写进 `startup_status`，而
`startup_status.to_summary_dict()` 由 `/health/startup` 暴露（可见）；
`fusion.py:157`（指标自增自身失败）、`fusion.py:222`（MonitoringLog 落点失败）、
`inference.py:143`（影子对比旁路失败）均属**观测系统自身上报失败**（S 型）。

### 1.49 闸门、变异与读数

- 新增 `TestP235Round13Batch15Wiring`（**记账更正**：原为 2 条，反向钉在补钉提交
  中补齐，现为 3 条）：3 对 location 双向核对 + 一次运行时覆盖两条路径 +
  一条反向钉（`excel_export_service` 三处 V 型不得接线）。
  ⚠️ 第十五批的 **commit message 写的是「3 条」「158 passed」，与当时实测不符**
  （当时实际 2 条 / 157 passed）。文档（本节与 P2_11 附录）当时写的 2 条是对的。
  按禁止 ref 重写纪律不用 `--amend` 抹除，此处书面对账；反向钉已补，现读数与
  「3 条 / 158 passed」一致。
- 运行时含一条**防假绿**断言：灰度路由那条若只 patch `decide_version` 而不管
  `AsyncSessionLocal`，异常会来自建会话（无 DB）而非路由决策 —— 计数照样 +1，
  测的却不是目标路径。故先 patch 出可用的假会话，并断言 `decide_version` 的
  `seen` 列表非空。
- `main.sidecar_audit_skipped` **未做运行时断言**（记账）：它在 FastAPI
  `lifespan` 内联，触发需跑完整启动链路（init_db / Redis / 模型预加载），与第六批
  `api.alerts.webhook.final_commit_failed` 同口径，只由存在性断言守住。
- 指纹那条用 **只换 inference 命名空间里的 `hashlib`** 来触发（不污染全局 hashlib），
  并先清 `_fingerprint_cache` 绕过 10s 记忆化。
- 扫描器+分类器复跑：X 133→130、W 82→85、P 15 不变，总数 334 不变。

---

## 一之十六、连带修复：两条 UTC 时间炸弹测试（第十五批 CI 红灯根因）

### 1.50 现象

第十五批提交 `e9b474d` 的 CI 里 `backend-coverage` **failure**，两条：

```
FAILED tests/test_anomaly_detection.py::TestDetectOffHours::test_detects_admin_off_hours_access
  assert 0 >= 1
FAILED tests/test_perf_p2_004_risk_trend_sql.py::TestGetRiskTrendMultiDay::test_multi_day_record_count
  AssertionError: assert 4 == 3
2 failed, 6804 passed, 68 skipped
```

两条都不在第十五批改动的文件链路上（本批只动 `main.py` /
`services/model_predict/fusion.py` / `services/model_predict/inference.py`）。

### 1.51 根因（算术可证，非猜测）

- `test_detects_admin_off_hours_access`：种子时间硬编码为**当日 23:05 UTC**，
  而 `detect_off_hours` 的查询窗是 `_utcnow_naive() - (300 + 60)s`（默认 6 分钟）。
  查询只有下界 `created_at >= cutoff`、无上界，因此：
  `now < 23:11 UTC` → 种子落在窗口内（甚至是未来时刻）→ 通过；
  `now ≥ 23:11 UTC` → 种子早于下界 → 恒 0 findings。
  **每天只有 23:11~24:00 UTC 这 49 分钟会红**，CI 跑在 23:26 UTC 正好命中。
- `test_multi_day_record_count`：分桶用 `func.date(created_at)`，`base = now - 3d`
  上又叠加 `+30min` / `+60min`。当 `now` 的 UTC 时刻 ≥ 23:00 时，`base+60min`
  跨到次日午夜 → 多出一个日期桶，3 变 4。同样只在每天最后 1 小时红。

### 1.52 对照实验（证明与本批改动无关）

把本批 3 个源文件临时还原到 `404da34`（本批之前）后本地复跑 —— **两条照样失败**；
还原后立即验证 `git diff` 为空。故判为仓库既有缺陷，不是第十五批引入。

### 1.53 修复

- `tests/test_anomaly_detection.py`：用 `monkeypatch` 把服务内时钟
  `anomaly_detection_service._utcnow_naive` 冻结到固定 `2026-01-02 23:30 UTC`，
  种子取其前 1 分钟 —— 时钟、种子、窗口三者恒一致，与挂钟无关。
- `tests/test_perf_p2_004_risk_trend_sql.py`：`base` 锚定到**当日 01:00 UTC**，
  使 `+30min` / `+60min` 恒不跨午夜（该库其余 `base` 用例都是纯天偏移，不受影响，
  已逐条核对）。
- 两条修复都写在坏时段（23:40 UTC）实测通过：`test_anomaly_detection.py` +
  `test_perf_p2_004_risk_trend_sql.py` **72 passed**；六闸门 **158 passed**。

### 1.54 第二波：同一家族还有 3 条，只是触发窗口不同

修完上面两条后重跑 CI（00:11 UTC 起跑），**又红 3 条**（同一文件、不同用例）：

```
FAILED ...::TestGetRiskTrendSingleDay::test_multiple_records_same_day_primary_selection - assert 2 == 1
FAILED ...::TestGetRiskTrendSingleDay::test_same_day_latest_scores_from_different_records - assert 2 == 1
FAILED ...::TestGetRiskTrendPriorityOrder::test_same_priority_latest_created_at_wins      - assert 2 == 1
```

根因同族、方向相反：这三条用 `now - timedelta(minutes=30)`，在 **UTC 刚过午夜**
（00:29）时减到前一日 → 单日样本裂成两天。教训：**只修「当前窗口在红的那几条」
不够，必须按家族修** —— 同一个文件里「`now ± 分钟偏移」+「按日期分桶」的组合，
在 23:00~00:30 UTC 之间会分批轮流红。

统一根治：新增模块级 `_utc_anchor()`（固定返回当日 **12:00 UTC**），把该文件
18 处挂钟取点全部换成它 —— 锚到中午后 `minutes/hours/days` 各级偏移都不可能跨
午夜。另有一处多行写法（原单条修复留下的 `hour=1`）一并收敛到锚点函数。
实测（坏时段 00:35 UTC）：`test_perf_p2_004_risk_trend_sql.py` **29 passed**，
连同 `test_anomaly_detection.py` **72 passed**；六闸门 **158 passed**。

### 1.55 未决风险（如实记账，未做）

- 全仓还有 **14 个测试文件 / 57 处** `datetime.now(timezone.utc).replace(tzinfo=None)`
  （`services/test_canary_manager.py`、`services/test_risk_service.py`、
  `test_alert_tasks.py`、`test_dedup.py`、`test_escalation.py`、
  `test_iss02_monitoring.py`、`test_mttr_service.py`、`test_p1_audit_2026_10_13_round3.py`、
  `test_p2_11_round11.py`、`test_silence.py`、`test_stab_p2_006_canary_route_prefix.py`、
  `test_auto_rollback_service.py`、`unit/test_password_reset_token_one_time.py` 等）。
  只有「分钟级偏移 + 按日期分桶/按小时判定」的组合才是炸弹，本批**只修已证实在
  CI 红的那一族**，其余未动 —— 全量改属于范围外且风险过高。
- 未加静态闸门（禁止测试里出现挂钟硬编码 / 建议统一走锚点函数）。本仓对这类
  「只在特定挂钟时段失败」的用例**目前无任何自动覆盖**，建议后续补一条。
- 另注：第十五批这轮 CI 里 `backend-coverage` 先出现一次 **cancelled**
  （日志显示 pytest 仍在跑时被外部终止：`Terminate orphan process: pid (3832) (pytest)`；
  workflow 未设 `timeout-minutes`，也无后续 push 与新 Coverage run）—— 按既有
  口径 `cancelled ≠ 失败`，已用 `gh run rerun` 重跑取得结论。

---

## 一之十七、#35 X 桶第十六批：4 处接线（X 130 → 126，跨两文件）+ 9 处不接线

挑簇：续作提示词建议的 `core/ws.py` / `api/v1/*` 方向。先跑 UNJUDGED 批量标记
（X 桶 130 条按 basename+func 去两份审计文档数提及次数），`dedup_lock` 6 条、
`model_engine/inference` 的 persist/Prometheus 在 P2_11 已裁定（M/R 型）跳过；
`api/v1/*` 与 `rate_limit` / `token_blocklist` / `tenant_guard` / `checksum`
等簇逐条存在性核查后，真降级集中在 ws 与 shadow_mode 两簇。

### 1.56 接线清单（4 处）

| location | 文件 | 降级形状 |
|---|---|---|
| `core.ws.local_send_failed` | `core/ws.py` `_local_send_to_user` | 某条连接 `send_text` 失败 → 该用户这一次推送静默丢失；`send_to_user` 继续走 Redis 发布并正常返回，调用方从返回值看不出有一次投递已失败 |
| `core.ws.pubsub_message_handling_failed` | `core/ws.py` `_pubsub_loop` | 单条跨进程消息处理抛异常 → 消息被丢弃、订阅循环照常续跑；投递方（其它 worker 的 publish）早已返回成功 |
| `services.shadow_mode.predictor_unavailable` | `services/shadow_mode_service.py` `_ensure_predictor` | M2 BERT 推理器加载失败 → 对拍停用；生产 TF-IDF 链路毫无变化，一致率数据从此断流，`get_stats` 的拉取式 flag 之外无运行时信号 |
| `services.shadow_mode.compare_failed` | `services/shadow_mode_service.py` `_shadow_predict` | 单次对拍异常被吞 → 该样本从一致率统计中静默消失，影子期切换决策依据出现无痕缺口 |

存在性核查（防 stale 行号）：扫描快照行号与现状逐条对齐（ws.py L169/L282 附近、
shadow_mode_service.py L59/L128 附近）；`shadow_mode_service` 的生产可达性经
`main._init_shadow_sink`（main.py:85-101，启动时 `set_shadow_sink`）证实 ——
不是死代码。`_ensure_predictor` 的接线置于 `return False` **之前**（第五批死接线
闸门同款纪律）。`shadow_mode_service.py` 原无 degradation import，本批新增并做
import 烟测（名字绑定验证，非只查语法）。

### 1.57 不接线 9 处（书面记账，仍留 X 桶，机器不裁、文档裁）

| # | 位置 | 类型 | 理由 |
|---|---|---|---|
| 1 | `ws.py` disconnect 指标 dec 失败 | M 型 | 指标采集自身失败；主链路不受影响，连接上限拒绝对客户端可见（4009） |
| 2 | `rate_limit.py` `_patched_limit` 签名修补回退 | V 型 | 回退后 FastAPI 解析失败会以 500 暴露，非静默 |
| 3 | `rate_limit.py` `SafeRateLimitMiddleware` 捕获转 429 | 设计内 | RateLimitExceeded→统一 429 是既定行为，附告警日志 |
| 4 | `status.py` `_get_cached_model_status` cache_set 失败 | 无失真 | 返回实时计算的真数据，仅损失缓存收益 |
| 5 | `token_blocklist.py` `revoke_token` Redis 不可用 | V 型 | 三个调用方（logout / change_password / reset_password）均检查返回值并记 ERROR；检查侧 `is_token_revoked` fail-closed（CacheUnavailableError→503）已堵 |
| 6 | `tenant_guard.py` `scan_unscoped_protected_queries` 跳过不可解析文件 | 死代码 | 运行期不可达：全仓 `app/` 无调用方，仅 `test_p2_31_tenant_guard.py` / `test_isolation_wiring_gate.py` 两个测试门禁调用 |
| 7 | `checksum.py` `_read_recorded_hash` 解析失败 | fail-closed | 返回 None → 判 stale → strict 环境拒绝加载（安全方向）；启动审计报告 `audit_model_sidecars` 可见 |
| 8 | `checksum.py` `cleanup_stale_sidecars` 删除失败 | 低价值 | 仅 `scripts/generate_sidecars.py --cleanup` 与测试调用；失败仅残留磁盘文件 |
| 9 | `risk_service_warning.py` warning.created 发布失败 | 重复层 | 底层 `core.event_bus.publish` 队列满已接线且不向上抛；本层 except 只在 publish 意外抛错时触发，属防御性捕获 + exc_info 日志 |

### 1.58 闸门与读数

- 新增 `TestP235Round13Batch16Wiring`（5 条）：4 对 location 双向核对 + 一次
  运行时覆盖四条路径（假连接 `send_text` 必炸；pubsub 假客户端确投递过一条
  pmessage 且 `_handle_pubsub_message` 必炸；推理器 predict 必炸且失败后
  `_predictor_loaded` 仍为 False、统计不涨 —— 每条均带防假绿断言）+ 五条反向钉
  （8 个行为锚点不得出现接线；token_blocklist 的 `return False` V 型判据；
  tenant_guard 的 `continue` 形状 + 全仓 `app/` 无生产调用方；event_bus
  底层接线仍在）。
- 桶计数改钉：**W=89 / X=126**（4 处实记录 X→W，无桶间迁移；棘轮测试实跑
  通过 = 扫描器现场重算与改钉一致，不是改常数）。
- 六闸门本地单跑：**164 passed**（test_p2_09/10/11/12/31/32 六套件；
  不得并发双跑）。affected **139 passed**（ws 全家 / test_p4_shadow_mode /
  rate_limit ×2 / token_blocklist ×2 / risk_service_warning / fault_injection）。
- 全称注释棘轮：4 条新注释经检测器复核**零命中**（逐个词避开全称词表），
  维持 100，不做账不动闸门。
- 三次真实变异（删 ws 接线 / 改 shadow location 字面量 / 删 P2_11 附录登记行）
  均 RED-OK/GREEN-OK，日志 `mutate_p2_35_round13_batch16_result.log`。
- 未验证如实记账：后端全量本地未跑（约 37 分钟，禁止并发双跑），由 CI
  `backend-coverage` 兜底；前端未触及。

---

## 一之十八、#35 X 桶第十七批：3 处接线（X 126 → 123，跨三文件）+ 12 处不接线

1. **接线 3 处**（X 126→123，W 89→92，总数 334 不变）——共同形状是
   **失效发生后，主链路对外形态与正常态完全同形**：

   | location | 文件 | 降级形状 |
   |---|---|---|
   | `core.health.monitor_refresh_failed` | `core/health.py` | `_health_monitor_loop` 快照刷新失败 → 缓存留旧值，`/health/ready` 仍以 200 + 陈旧快照应答；K8s 探针与调用方无从得知健康数据已停止更新（守护对象实际可能已故障） |
   | `core.middlewares.http_metrics_record_failed` | `core/middlewares.py` | `metrics_middleware` finally 里 `http_requests_total.inc` 失败 → 请求本身照常返回，但 HTTP 请求量/时延数据出现缺口，SLO 可用性统计静默偏乐观 |
   | `services.registry_auto_rollback.check_failed` | `services/registry_auto_rollback.py` | `_rollback_loop` 里 `check_auto_rollback` 失败 → 循环静默续跑，自动回退监控形同停摆；回退率超阈值的高风险训练产物继续滞留 PRODUCTION 服务推理，而任何调用方都看到系统「正常运行」 |

   `core/health.py` 与 `services/registry_auto_rollback.py` 新增
   `from app.core.degradation import record_silent_degradation`（import 烟测
   验证名字绑定）；`core/middlewares.py` 复用既有 import（本文件 L281 已有
   `core.middlewares.error_sanitizer` 一处）。

2. **裁定不接线 12 处**（留 X 桶，逐一书面记账）：
   ① `hyperparameter_tuning._load_tuning_cache` / `_append_tuning_cache`
   缓存读/写失败——结果正确，仅断点续跑失效，属无失真的性能降级
   （同 `status.py` 缓存写口径）；② `pdf_report_service.generate_pdf` /
   `generate_pdf_stream` 异常分支——`success=False + error_message`
   显式失败（V 型，同 `excel_export_service` 第十五批口径）；
   ③ `instance.get_instance_id`——降级值 "unknown-<pid>" 形态可辨且已有
   warning；④ `tasks/observability._flush_lock_stats_impl`——返回 False
   交由上层 retry，MaxRetriesExceeded 时 raise 产生 FAILURE 事件（V 型）；
   ⑤ `ml/model_loader._resolve_artifacts_dir` / `ml/scaler.__getattr__`——
   F 型保守 fallback，回退路径不存在时后续加载可见地抛
   FileNotFoundError；⑥ `ml/model_validation._bootstrap_auc_ci_with_count`
   bootstrap 退化样本——`degenerate_samples` 随返回值暴露 + warning，
   信号可辨；⑦ `email_service._close_thread_smtp`——quit() 失败仅连接
   残留到超时，conn 已置空不重用，C 型清理低价值；
   ⑧ `text_tokenizer._get_jieba`——旧版 jieba 无 setLogLevel，仅日志级别
   差异，无功能失真；⑨ `review_service.create_review_task` 事件发布
   防御层——底层 `core.event_bus.publish` 已接线且队列满不向上抛，
   本层为重复层（第十六批同口径）。

3. **闸门**：新增 `TestP235Round13Batch17Wiring`（3 条）——3 对 location
   源码 + 文档双向断言；一次运行时覆盖三条路径（health 循环驱动、
   middlewares 假 Request + 假计数器、rar 循环驱动，各带防假绿断言：
   probe 确被调用 / inc 确被调用且响应仍以 200 交还 / check 确被调用）；
   一条反向钉 `test_declined_no_distortion_batch17` 对 12 处不接线裁定
   逐一「函数体未接线 + 行为锚点仍在」双断言。
4. **桶计数改钉**：**W=92 / X=123**（3 处实记录 X→W，无桶间迁移；棘轮
   测试实跑通过 = 扫描器现场重算与改钉一致）。
5. **实测读数**：六闸门本地单跑 **166 passed**（唯一失败为文档登记，
   本文档落盘后转绿；不得并发双跑）。affected 两组共 **1071 passed /
   10 skipped**（ml 全家 / pdf_report / observability / auto_rollback /
   celery×2 / health×3 / middlewares×2 / email / fault_injection /
   instance / review / security 等 47 文件）；其中
   `test_importlinter_config.py::test_lint_imports_passes` 1 条失败为
   **本机环境缺失**（venv 未装 import-linter，`lint-imports` 命令不存在），
   与本批无关——契约方向已手工核对：唯一 forbidden 契约为
   `app.core → app.ml/services`，本批两处新 import（health→core.degradation、
   services.registry_auto_rollback→core.degradation）均不违约，且
   services→core.degradation 同模式已在 `shadow_mode_service` 等多处存在。
6. **全称注释棘轮**：新增注释经检测器复核零命中，维持 100，不动闸门。
7. **变异三条**（删 health 接线 / 改 middlewares location 字面量 / 删 P2_11
   附录登记行）见 `mutate_p2_35_round13_batch17_result.log`。
8. **未验证如实记账**：后端全量本地未跑（约 37 分钟，禁止并发双跑），
   由 CI `backend-coverage` 兜底；前端未触及。

---

## 一之十九、#35 X 桶第十八批：3 处接线（X 123 → 120，跨两文件）+ 13 处不接线

1. **接线 3 处**（X 123→120，W 92→95，总数 334 不变）——共同形状是
   **失败把「未检查 / 不完整 / 只写一半」洗成了正常形态**：

   | location | 文件 | 降级形状 |
   |---|---|---|
   | `services.auto_rollback_service.check_failed` | `services/auto_rollback_service.py` | `check_all_canaries` 单 canary 检查/回滚整体失败 → `check_result` 洗成 `should_rollback=False + reason="check_error"`；两个调用方（scheduler beat / fallback monitor）都只按 `should_rollback` 分支走 **debug 级**日志——「无需回滚」假象下这次检查根本没跑成，超阈值金丝雀静默无人回滚（与已接线的 `rollback_savepoint_failed` 同族：那个是「结果说回滚了但其实没有」，这个是「结果说不用回滚但其实没检查」） |
   | `services.model_predict.training_jobs.redis_list_fallback` | `services/model_predict/training_jobs.py` | `list_training_jobs` 读 Redis 失败 → 回退进程内内存表，残缺子集经 `status.py` 的 `ok({"jobs": ...})` 直接包进成功响应返给前端——Redis 里可能仍在运行的任务整体消失，调用方拿到的就是「完整列表」形态 |
   | `services.model_predict.training_jobs.redis_update_failed` | `services/model_predict/training_jobs.py` | `update_job` 内存表已改而 Redis 持久化失败 → 双写不一致；函数无返回值，调用方（`model_predict_service._update_job` 乃至训练任务本身）无从得知这次状态变更只落了一半，Redis 恢复后读到旧状态 |

   两个文件的 degradation import 均已在（本批无新增 import）。

2. **裁定不接线 13 处**（留 X 桶，逐一书面记账）：
   ① `auto_rollback_service._redis_client_or_none`——Redis 客户端获取
   失败返回 None，三个调用方全部处理 None 且 `_bump_lock_counter("unavailable")`
   专用计数器（M 型）；② `try_acquire_check_lock` 锁获取异常——M 型计数器
   + 注释明示的「降级执行检查」语义；③ `publish_check_heartbeat` 写心跳
   失败——M 型计数器 + return False；④ `get_check_heartbeat_age` 读/解析
   失败（2 处）——M 型计数器 + return None，且调用方
   `canary_fallback_monitor` 对 None 有专门接管分支（heartbeat_missing）；
   ⑤ `notifier._dispatch` 单通道未捕获异常——success=False + error_msg
   随 results 字典返回，db 传入时写 `alert_channel_failed` OperationLog
   （V 型）；⑥ `notifier._write_channel_log` 通道审计写失败——C 型，
   通知结果已由 results 承载；⑦ `am_sync._write_sync_log`——C 型同上；
   ⑧ `am_sync.pull_silences`——返回 None 显式失败 + `am_sync_failed`
   审计（V 型）；⑨ `silences.create_silence` 的 AM sync 异常——第四批
   注释明示「am_sync 内部已写 am_sync_failed OperationLog，此处不重复
   计数（避免计数器长期为 0 误导运维）」；⑩ `training_jobs.get_training_job`
   Redis 读失败——not_found 带 `storage_degraded=True` + message 变更的
   显式降级标记（V 型，AUDIT-P0-8 修复）；⑪ `event_bus._consume_loop`
   handler 失败——`handler_errors` 专用计数器 + stop 时日志汇总（M 型）；
   ⑫ 同函数 loop 级未预期异常——`queue.get()` 异常的防御性路径，生产中
   不可达（与 tenant_guard 扫描器同理）。
3. **闸门**：新增 `TestP235Round13Batch18Wiring`（4 条）——3 对 location
   源码 + 文档双向断言；一次运行时覆盖三路径（auto_rollback 假 db/假
   savepoint + check 必炸、training_jobs 假 Redis 必炸 + 内存表有种，
   各带防假绿断言：check 确被调用且结果确被洗成 should_rollback=False /
   reason=check_error、内存任务确出现在返回里、内存写确已生效）；
   两条反向钉——10 个行为锚点逐一「函数体未接线 + 锚点仍在」+
   `test_declined_silences_am_sync_exception_not_wired` 对同函数双
   except 反向裁决的精细钉（AM sync 分支不得接线、补偿分支
   am_rollback_failed 必须仍在且全函数接线数恰为 1）。
4. **桶计数改钉**：**W=95 / X=120**（3 处实记录 X→W，无桶间迁移；棘轮
   测试实跑通过 = 扫描器现场重算与改钉一致）。
5. **实测读数**：六闸门本地单跑 **170 passed**（唯一失败为文档登记，
   本文档落盘后转绿）。affected 23 文件分三组：组 1（auto_rollback /
   canary_fallback / event_bus / notifier / am_sync / silence）
   **162 passed**；组 2（model_predict_service / model_training /
   scheduler / iss02×2 / training schema）**172 passed**；组 3
   （dedup / ml_breaker / perf×2 / resource_cleanup / security_p1 /
   services_init / api_contract）**406 passed**（20 分钟，含 schemathesis
   属性测试；三组合计 **740 passed**）。
   **环境性备注**：`tests/contract/test_api_contract.py`（schemathesis +
   hypothesis 属性测试）单跑或组合跑会随机超过工具默认 120s 时限被
   SIGTERM——已做还原对照实验（`git show HEAD:` 还原两个源文件后复跑）
   **两侧同为 58 passed / 100s 内完成**，确认与本批改动无关，纯属
   hypothesis 生成量的耗时波动；后续该文件一律后台跑或加 shell timeout。
6. **全称注释棘轮**：新增注释经检测器复核零命中，维持 100，不动闸门。
7. **变异三条**（删 auto_rollback 接线 / 改 training_jobs location
   字面量 / 删 P2_11 附录登记行）见 `mutate_p2_35_round13_batch18_result.log`。
8. **未验证如实记账**：后端全量本地未跑（约 37 分钟，禁止并发双跑），
   由 CI `backend-coverage` 兜底；前端未触及。

---

## 一之二十、#35 X 桶第十九批：纯裁定批（0 接线，W=95 / X=120 不变，13 条不接线）

本批对 scheduler(7) + `core/model_engine/loading`(4) + `core/config`(2)
共 13 条 X 候选逐条代码实证后**全部裁定不接线**，无一处实记录 X→W，
桶计数不变。判据分四类：

1. **S 型（自报失败通道自身失败）3 条**——`tasks/scheduler.py`：
   ① `_daily_risk_scan_impl` L401（滞留汇总的 Sentry `capture_message`
   失败只记 debug）——主通道已在：同分支上游 L383-390 已按 AUDIT-P0-2
   记 **error 级**汇总日志（含未送达条数与 warning_ids），Sentry 只是
   叠加的第二上报通道；② `_stale_warning_reminder_impl` L510 同型
   （滞留已逐条写 OperationLog + error 日志，P0-FIX-2026-10-11）；
   ③ `_cleanup_experiment_artifacts_impl` L1102（保护集解析失败的
   Sentry `capture_exception` 失败）——主通道更强：同分支 L1084 记
   error 后 L1104 `raise RuntimeError` **显式中止清理**（celery 任务
   失败可见，AUDIT-P0-3）。
2. **C 型（清理路径跳过/失败）4 条**——`tasks/scheduler.py`：
   ④ `_cleanup_uploads_dir_impl` L994（单文件 unlink OSError → debug
   「skip file」）；⑤ 同函数 L1001（空目录 rmdir OSError → 裸 pass）；
   ⑥ `_cleanup_experiment_artifacts_impl` L1054（`entry.stat()` 失败
   → continue，该产物目录漏删）；⑦ 同函数 L1170（rmtree OSError →
   warning，该目录清理失败）。失败形状均为「少删一些」——磁盘缓慢
   增长而非数据/安全失真，warning/debug 级日志已在；且这些任务跑在
   celery worker（跨进程，无 `PROMETHEUS_MULTIPROC_DIR`，按第十五批
   口径计数不可达，接线无意义）。
3. **V 型（显式失败信号）1 条**——`core/model_engine/loading.py`
   `_get_expected_hash` L82：侧车存在但不可解析时返回
   `(None, "unreadable_sidecar:<name>")`，与「侧车不存在」
   （`"absent"`）、「内容畸形」（`"malformed_sidecar:<name>"`）分成
   三种可区分来源（AUDIT-2026-10-08 P0-6 专门修复），调用方
   `_verify_file_hash` 按 source 分级告警/拒绝，形态可辨。
4. **设计内 / 低价值 / dev-only 5 条**：
   ⑧ `loading._load_adapter` L429：适配器整体加载失败 →
   `_incr_model_fallback("v1.24_adapter", "load_failed")` 专用计数器
   + return None（M 型；同函数内层 pkl→config.json 回退已接
   `adapter.pkl_fallback`，本 except 是外层兜底）；
   ⑨ `loading._load_model` L596：BERT 无本地缓存回退 Hub 下载是注释
   明示的正常双路径（`local_files_only` 优先、无缓存触网），两侧都
   成功加载、无失真；同函数 keras 二次加载失败已接
   `keras_compat_load_failed`；
   ⑩ `loading._patch_simple_imputer` L712：sklearn 兼容性补丁失败
   只记 debug，但旧模型 pickle 缺 `_fill_dtype` 会在后续 transform 时
   **可见地**抛 AttributeError，不属静默；
   ⑪ `core/config.py` `apply_env_defaults` L359（PII key 文件读失败
   → warning + 生成新密钥）；⑫ 同函数 L372（写失败 → warning）：
   均为 dev-only 路径（生产缺失密钥由模块级检查拦截），且都伴随
   `warnings.warn` 显式提示，重启后历史 PII 不可解密的风险有 UserWarning
   兜底告知。

**闸门**：新增 `TestP235Round13Batch19Declined`（3 条）——函数级反向钉
7 个（函数体未接线 + 行为锚点仍在）；except 块级精细钉 2 个
（`_load_adapter` / `_load_model` 同函数内存在其他已接线路径，函数级
断言会假红，故 AST 定位目标 handler，并同时钉住见证接线
`adapter.pkl_fallback` / `keras_compat_load_failed` 仍在）；文档登记
1 条（「一之二十」节 + 13 条裁定关键标识 + 纯裁定批账实一致）。
**桶计数**：不改钉，维持 **W=95 / X=120**（纯裁定批，无桶间迁移；
棘轮测试实跑通过）。
**未验证如实记账**：后端全量本地未跑（约 37 分钟，禁止并发双跑），
由 CI `backend-coverage` 兜底；前端未触及。

---

## 一之二十一、#35 X 桶第二十批：1 处接线（X 120 → 119）+ 14 处不接线

**接线 1 处**：`api.alerts.history_detail_parse_failed`
（`api/v1/alerts/__init__.py` `list_alert_history` L349）：detail JSON
解析失败 → warning + `detail = {}` → rule/severity/message 全为空的
**空壳 item 仍照常 append 进列表**（无 severity 过滤时；有过滤时该条被
`continue` 跳过，但 total 仍计它）。前端告警历史页因此看到一条字段全空
的告警记录——与正常记录同形（列表项存在、只是内容空），告警内容静默
丢失，从响应形态无法分辨。接线置于 `logger.warning` 前，注释写明判据。

**不接线 14 处**（逐条代码实证，仍留 X 桶，机器不裁、文档裁）：

1. **alerts 4 条（V 型显式失败上报）**——`api/v1/alerts/__init__.py`：
   ① `_handle_silenced_alert` L152：静默告警持久化失败 → error 日志 +
   `return False`，调用方（webhook 主流程）累计 failed（H-API-11 修复）；
   ② `_handle_active_alert` L173：去重检查失败 → `send = True`
   （defaulting to send），error 日志 + 注释明示的 fail-open 设计——
   失败方向是「多通知」而非「漏预警」，按本仓口径危害低；
   ③ 同函数 L190：持久化失败 → `return (0, 1, 0)`，failed 计数显式；
   ④ 同函数 L205：通知失败 → `return (1, 0, 1)`，notify_failed 显式。
2. **pii_crypto 2 条（V 型）**——`core/pii_crypto.py`
   `_get_previous_fernets` L133 / `_get_previous_aes_gcms` L191：旧密钥
   派生失败 → warning + 跳过该旧密钥。其后果（用该旧密钥加密的数据无法
   解密）在 `decrypt_field` 是**显式**的：当前 + 全部旧密钥耗尽后
   L336/L367 `raise ValueError("PII 解密失败（密钥错误或数据损坏）")`，
   且先记 error 日志（exhausted current + N previous keys），调用方
   可见，不属静默。
3. **escalation 2 条（M 型已有专用计数器）**——
   `monitoring/escalation.py` `compute_escalation` L102：detail 解析
   失败 → `alert_detail_parse_failed_total.inc(1, stage="escalation")`
   专用计数器 + 结构化 warning（AUDIT-2026-10-06 P1-6 专门修复，注释
   说明 acknowledged 丢失 / 重复升级两个后果）；L111：该计数器的上传
   失败（观察者的观察者）只记 debug，主信号已在。
4. **drift 2 条**——`services/drift_monitoring_service.py`：
   ① `check_all_modalities` L104：单模态检测失败 →
   `DriftCheckResult(failed=True)` 显式入结果列表 + rollback +
   exception 日志（V 型）；② `_push_to_gauge` L464：PSI/KL 推送 Gauge
   失败 → debug（S 型指标自身通道，且注释明示 failed 模态跳过推送的
   安全语义）。
5. **model_registry_v2 2 条**——`core/model_registry_v2.py`：
   ① `_quarantine_corrupt_file` L224：旁路 `os.replace` 失败 → error
   日志。「注册表已降级」的事实由上游 L190/L208 两条接线
   （registry_file_unparsable / registry_records_dropped）计数，旁路
   失败只是恢复现场的最佳努力，其后果是现场丢失而非新的降级；
   ② `_promote_model_locked` L462：磁盘写失败 → 内存状态回滚 + error
   + `return None`，调用方显式得知失败（V 型）。
6. **fusion 1 条（M 型变体）**——`services/model_predict/fusion.py`
   `predict_fusion` L164：canary 指标自增失败 → debug（注释明示 P1
   问题 5 的取舍）。推理主流程不受影响、响应无失真，灰度指标只缺一个
   样本，且紧随其后的 `_log_canary_event` 仍会写事件。
7. **main 1 条（V 型）**——`main.py` `_preload_models_background` L222：
   后台预加载失败 → `startup_status.record("model_preload", "failed", ...)`
   + error 日志。startup_status 是显式状态记录（运维可从
   /startup_status 看到 failed），不属于静默。

**闸门**：新增 `TestP235Round13Batch20Wiring`（6 条）——location 双向
核对 1 条；运行时驱动 1 条（正常行 + 损坏行各一条，两条都入列表、
损坏行 rule/severity/message 全空实证「同形失真」，计数器 +1）；
函数级反向钉 9 个（_handle_silenced_alert / _get_previous_fernets /
_get_previous_aes_gcms / compute_escalation / check_all_modalities /
_push_to_gauge / _quarantine_corrupt_file / _promote_model_locked /
_preload_models_background）；except 块级精细钉 5 个
（_handle_active_alert 三个 except 分别钉 defaulting-to-send /
`return (0, 1, 0)` / `return (1, 0, 1)`；escalation 内层计数上传失败；
predict_fusion 同函数已有 canary_routing_failed 接线，钉见证 +
handler 级未接线）；裁定前提见证钉 1 条（decrypt_field 的 raise 与
上游两条接线仍在）；文档登记 1 条（本节 + P2_11 附录 + 桶计数改钉）。
**桶计数**：改钉 **W=96 / X=119**（1 处实记录 X→W，总数 334 不变；
棘轮测试实跑通过）。
**未验证如实记账**：后端全量本地未跑（约 37 分钟，禁止并发双跑），
由 CI `backend-coverage` 兜底；前端未触及。

---

## 一之二十二、#35 X 桶第二十一批：纯裁定批（0 接线，W=96 / X=119 不变，predict.py 6 条）

### 1.60 本批结论一句话

`core/model_engine/predict.py` 剩余 6 条未接线候选逐条存在性实测后
**全部裁定不接线**，无实记录 X→W，桶计数维持 **W=96 / X=119**。
连带修复该文件一处注释漂移（v1.20「默认」标注与 config 实际默认 v1.23 矛盾，
正是初裁被引向误判的根源）。

### 1.61 逐条裁定明细

1. **scaler 加载失败 handler（L178，本批新裁：双重外部阻断不可达）**——
   `structured_scaler_v1.20` 加载失败（FileNotFoundError/ValueError）→
   warning「proceeding without scaling」→ `structured_scaler=None` →
   L192-198 `feature_scaled = feature_df` **未缩放特征直接送入
   `model.predict`**，概率/分数在错误特征尺度上算出，而响应
   `fallback_used=False`、无 `fallback_reason`、`model_used` 与正常态
   完全同形——单看代码形状与第二批 `experimental_v121_scaler_fallback`
   （scaler.transform 失败→未缩放算分）同型，初判为真降级候选。
   **存在性实测推翻初判**，发现双重外部阻断：
   ① `structured_default_model` 当前默认 `"v1.23"`
   （config.py L483；v1.23 是 Pipeline 自带 preprocessor，
   `primary_needs_scaler=False`，L175 的 `if model is not None and
   primary_needs_scaler` guard 直接为假，根本进不了该分支）；
   ② `models/*.pkl` 按 `.gitignore` L303-307 **有意不入库**（全仓
   tracked pkl 实测 0 个，Dockerfile COPY models/ 交付的是不含 pkl 的
   上下文），v1.20 主模型在官方交付形态下恒 `FileNotFoundError` →
   L167 except → `model is None` → 同上 guard 为假。
   与第十二批 `_run_experimental_v121` 外层（注册表移除 v1.21，代码级
   guard 保证不可达）同族，也与 keras 三条目「生产/CI 恒 MISSING」
   注释先例同口径 —— 接线即计数器恒 0 的死代码。
   **解锁条件（任一满足须重审本裁定）**：默认配置切回 v1.20 且 pkl
   纳入交付；或部署侧手工放置 v1.20 产物且 scaler 缺失/损坏。
   闸门 `test_delivery_form_premise` 把两个前提（默认配置 v1.23 +
   pkl 不入库）钉住，前提变化即红。
2. **模型加载失败 handler（L167，V 型）**——
   `fallback_reason = f"model_load_failed: {exc}"` 显式赋值，下游
   `model_used="structured_heuristic_fallback"` + `fallback_used=True`，
   响应可见。这正是当前交付形态下**真实可达**的降级点，且显式。
3. **`predict_lite` 两个 handler（L887/L897，V 型）**——非有限概率 /
   通用异常均 `logger.error/warning` + `_incr_fallback()` +
   `fallback_reason` 显式写入响应（`lite_model_non_finite_output:` /
   `lite_model_unavailable:`），AUDIT-2026-10-08 (P0-5) 修复后的成熟
   显式降级范式。
4. **`_run_experimental_v121` 外层（L421，第十二批已裁：死代码，
   本批实测复核维持）**——`get_model_info(
   "structured_v1.21_binary_lr")` 实测仍返回 None（S-03 已从注册表
   移除 v1.21 四条目，model_registry.py L132-137 注释明示 deprecated），
   try 块运行时不可达。
5. **`_run_adapter`（L538，第十二批已裁：M 型，本批实测复核维持）**——
   `adapter_hit` / `adapter_miss` 专用计数器成对覆盖适配器不可用，
   按 M 桶口径不重复接通用计数器。
6. （第 6 条即第 1 条的姊妹路径 `experimental_v121_scaler_fallback`
   L395，第二批已接线，本批不重复裁定。）

### 1.62 连带修复：注释漂移

`predict.py` L146-149 原文案：

```
# S-02: 根据 structured_default_model 配置选择默认结构化模型
# v1.20 (默认): structured_logistic_regression_quick + structured_scaler_v1.20
# v1.23: structured_v1.23_external_lr (Pipeline, 自带 preprocessor, 无需单独 scaler)
```

「v1.20 (默认)」与 `config.py` L483 `structured_default_model: str = "v1.23"`
矛盾（S-02 时代默认是 v1.20，后来切 v1.23 时注释没跟上）。该漂移直接
导致本批初裁把 L178 当成「默认路径上的真降级」。已更正为事实陈述 +
可达性结论 + 裁定出处（零行为变更，AST 解析通过）。

### 1.63 闸门、变异与读数

- 新增 `TestP235Round13Batch21Declined`（6 条）：scaler handler
  except 块级反向钉（锚点 "proceeding without scaling"，未接线且
  锚点在）；模型加载 handler 反向钉（未接线 + `fallback_reason =`
  显式赋值在）；lite 两个 handler 反向钉（未接线 + fallback_reason
  与 `_incr_fallback` 在）；已裁维持 1 条（`get_model_info` 实测
  None + adapter 计数器在）；交付形态前提钉 1 条（默认 v1.23 +
  `.gitignore` 排除 + `git ls-files *.pkl` 实测 0）；文档登记 1 条。
- **桶计数**：不改钉，维持 **W=96 / X=119**（纯裁定批，无桶间迁移；
  棘轮测试实跑通过）。
- 变异验证：4 条（M1 给 scaler handler 补接线 → 反向钉红；
  M2 删模型加载 handler 的 fallback_reason 赋值 → V 型前提钉红；
  M3 删本节标题 → 文档结构钉红； M4 删 P2_11 条目头行），
  全部 RED-OK/GREEN-OK，日志
  `mutate_p2_35_round13_batch21_result.log`。
- **未验证如实记账**：后端全量本地未跑（约 37 分钟，禁止并发双跑），
  由 CI `backend-coverage` 兜底；前端未触及。

---

## 一之二十三、#35 X 桶第二十二批：纯裁定批（0 接线，W=96 / X=119 不变）+ 连带修复「自出生即死」的专用计数器

### 1.63 本批结论一句话

`core/health.py` 1 条 + `services/auto_rollback_service.py` 5 条 +
`core/pii_crypto.py` 4 条共 10 条 X 桶候选逐条存在性实测后**全部裁定
不接线**，无实记录 X→W，桶计数维持 **W=96 / X=119**。另同文件 8 条
已被分类器定型（health 6×H / auto_rollback 2×S）复核维持。
**本批核心发现（连带修复）**：auto_rollback 锁/心跳家族的 M 型裁定
（第二批 1.7 表 / 第十八批）理由是「已有专用计数器
`canary_rollback_check_lock_total{outcome}`」——实测该计数器
**自引入（e120ce3）起从未递增**，两处调用点一直在用不存在的 API。

### 1.64 核心发现：专用计数器「自出生即死」

**事实链**（全部实测）：

1. 本仓 `app/core/metrics.py` 的 `Counter` 是**自研实现**（初始提交
   341f22c 即在）：API 为 `inc(amount=1.0, **labels)`，**没有
   `.labels()` 方法**（`Counter` 类只定义 `inc` / `collect`）。
2. `auto_rollback_service._bump_lock_counter` 原调用
   `canary_rollback_check_lock_total.labels(outcome=outcome).inc()`
   （prometheus_client 形态），`canary_fallback_monitor.
   _bump_takeover_counter` 同型——全仓仅此 2 处 `.labels(` 调用。
3. 每次调用都 `AttributeError`，被各自 `except Exception` 吞掉只留
   debug 日志（「…计数更新失败」）⇒ **两个计数器恒 0**。
4. `git log -S` 证实：`.labels(outcome=outcome)` 随 e120ce3
   （「修复金丝雀自动回滚三条不可达链路」）引入，自研 Counter 类自
   初版即在 ⇒ 不是回归，是**从未工作过**。
5. 运行时实证（修复前）：驱动 `try_acquire_check_lock` 的
   Redis 不可用路径，warning 日志正常打出，但
   `canary_rollback_check_lock_total{outcome="unavailable"}` 读数
   0.0（探针当场复现）。

**影响面**：第二批 1.7 表把这 5 条（57/90/123/152/161）裁为 M 型的
唯一理由「全部已有专用计数器」**从未成立**；第十八批
`test_declined_no_distortion_batch18` 与 P2_11 L448 同引该理由。
往批闸门只钉「调用点在源码里」的**字面量**（`_bump_lock_counter(
"unavailable")` in seg），从无**运行时计数断言**——死计数器因此
活过全部往批。「失败路径不允许静默」的设计被计数器自身击穿，
这正是 #35 要防的形态：可观测性设施自身静默失效。

**修复**：两处调用点改自研 API（`inc(outcome=...)` /
`inc(reason=...)`），docstring 记账缘由；新增运行时回归测试
`test_dedicated_counters_actually_increment`（直接调 helper 读
计数器值，`.labels()` 形态复潮即红）+ AST 级 `.labels(` 调用禁现
防回退钉（注释/docstring 字样不算，走 `ast.Call` 判定）。

### 1.65 不接线 10 条（X 桶候选，书面记账，仍留 X 桶）

| # | 位置 | 类型 | 理由 |
|---|---|---|---|
| 1 | `health.py` L375 `stop_health_monitor` CancelledError→pass | K 型 | lifespan 关闭阶段主动 `cancel()`，pass 是标准清理；取消是设计行为 |
| 2 | `auto_rollback` L58 `_redis_client_or_none` →None+error | V 型 | helper；三个调用方的 `if client is None:` 分支各自计数+warning（7 处 unavailable 计数点全覆盖） |
| 3 | `auto_rollback` L91 `try_acquire_check_lock` →True+计数+error | M/V 型 | 设计内 fail-open 降级执行（docstring 明示「beat/fallback 可能重复触发」），专用计数器经本批修复后真正生效 |
| 4 | `auto_rollback` L124 `publish_check_heartbeat` →False+计数+error | V 型 | 返回值显式；失败方向是兜底 monitor 接管（fail-safe 多查而非漏查） |
| 5 | `auto_rollback` L153 `get_check_heartbeat_age` →None+计数+error | V 型 | docstring 契约「不得静默跳过检查」由调用方遵守：fallback monitor 对 None 走接管 + `heartbeat_missing` 计数（实测见证） |
| 6 | `auto_rollback` L162 心跳内容解析失败 →None+计数+error | V 型 | 注释明示「显式记录, 不静默」；同上 |
| 7 | `pii_crypto` L228 `_decrypt_aes_gcm` InvalidTag→pass | V 型链 | 旧密钥回退尝试的中间步；末端 L244 `raise InvalidTag("…exhausted…")` |
| 8 | `pii_crypto` L242 同上 continue | V 型链 | 同上 |
| 9 | `pii_crypto` L344 `decrypt_field` InvalidToken→pass | V 型链 | Fernet 回退链中间步；末端 L367 `raise ValueError("PII 解密失败…")` + exhausted error 日志 |
| 10 | `pii_crypto` L358 同上 continue | V 型链 | 同上 |

### 1.66 已定型项复核维持（8 条，分类器现场重算确认）

- health 6×H（`check_database` L57 / `check_redis` L85、L89 /
  `check_celery_worker` L130、L136 / `check_models` L173）：
  `return False` + warning，经 `HealthSnapshot` 四字段进 `/health`
  对负载均衡显式暴露；celery 检查另置
  `celery_worker_heartbeat` gauge=0（S 型元素）。
- auto_rollback 2×S（L69/L174）：指标/gauge 自身失败只记 debug，
  主链路无失真。

### 1.67 闸门与读数

- 新增 `TestP235Round13Batch22Declined`（10 条）：health H 型家族
  反向钉 + stop_health_monitor K 型钉 + auto_rollback 家族反向钉
  （7 处计数点 + API 形态防回退）+ pii_crypto 回退链钉（handler 数
  + 末端 raise 计数 + exhausted 日志）+ 轮换探测见证 + **计数器
  真涨回归** + 运行时三条（锁 fail-open 可观测 / 心跳 None 可观测 /
  decrypt 耗尽显式 raise / 健康检查 return False）+ 文档登记。
- 桶计数棘轮实跑通过：**W=96 / X=119** 不变（纯裁定批 + 计数器修复
  不新增 `record_silent_degradation` 调用点）。
- 变异四条（删接线无对象——本批 0 接线，改以「修复回退」为变异
  对象）：M1 把锁计数器调用改回 `.labels().inc()` 形态（计数器回归
  测试红 + 运行时红）、M2 删 decrypt_field Fernet 末端 raise（链
  witness 红）、M3 删「一之二十三」节标题、M4 删 P2_11 条目头行。

---

## 一之二十四、#35 X 桶第二十三批：纯裁定批（0 接线，W=96 / X=119 不变，validation_engine 5 条）

### 1.68 本批结论一句话

`services/validation_engine.py` 5 条未接线 handler 逐条存在性实测后
**全部裁定不接线/复核维持**，无实记录 X→W，桶计数维持
**W=96 / X=119**。其中 L422/L512 为第十三批已裁 V 型（本批复核
维持），L147/L207/L271 为分类器定型 D（脏数据探测）的首次书面
裁定。提示词建议清单中的 `validation_engine` 簇至此收口。

### 1.69 存在性核查与分类器现场重算

（`tests/tools/verify_p2_35_batch23_candidates.py`：先重跑 scan 再
逐条 classify，口径与 `test_batch6_bucket_counts_pinned` 一致）

| 位置 | 函数 | 分类器桶 | 本批裁定 |
|---|---|---|---|
| L422 | `_run_model_inference` | X | V 型，第十三批已裁，复核维持 |
| L512 | `_compute_baseline_metrics` | X | V 型，第十三批已裁，复核维持 |
| L147 | `_load_csv_dataset` | D | D 型定型维持 + 首次书面裁定 |
| L207 | `calculate_metrics`（内层 auc） | D | 同上 |
| L271 | `_calculate_small_classification_metrics` | D | 同上 |

**挑簇教训记账（与第十六/十七批实锤同族）**：挑簇器按「审计文档
未提及」把 5 条全列为「未裁定」，但分类器现场重算显示
L147/L207/L271 早已被 D 规则（`types <= DIRTY_TYPES`，单条解析
跳过、数据本来就是坏的）定型——「文档未提及」≠「未裁定」，
文档提及计数只是粗排信号，裁定状态必须以分类器 + 审计文档逐条
核对为准。

### 1.70 不接线裁定 5 条（书面记账，X 二条仍留 X 桶，D 三条留 D 桶）

| # | 位置 | 类型 | 理由 |
|---|---|---|---|
| 1 | L422 `_run_model_inference` | V 型（维持） | 失败 `return None` + error 日志；调用方 `validate_model` 显式写 `result.errors`（"Model inference unavailable …"） |
| 2 | L512 `_compute_baseline_metrics` | V 型（维持） | 同上（"Baseline metrics unavailable …"），与第十一批 EXIF 剥离失败同口径 |
| 3 | L147 `_load_csv_dataset` 数值转换跳过 | D 型 + V 型链 | 非数值**原样保留字符串**（`test_load_dataset_csv_numeric_conversion` 钉住 `features[0]["b"] == "x"`），数据不丢失也不造假；字符串特征若令下游推理失败，走 L422 handler → `result.errors` 显式链 |
| 4 | L207 `calculate_metrics` 内层 auc | D 型 + V 型 | `roc_auc_score` 仅对单类标签抛 ValueError，此时 AUC 本就无定义，`metrics.auc = None` 是诚实取值且在返回值中显式（与 probabilities=None 同形态，均表示「未算」）。块级互锁：内层（L207，`pass`）不得接线 / 外层（L237，已接线 `calculate_metrics_failed`）必须仍在 |
| 5 | L271 `_calculate_small_classification_metrics` 标签跳过 | D 型 + V 型 | H-Svc-16 设计行为（`test_calculate_metrics_skips_non_numeric_labels` 钉住 `sample_count == 2`）；循环后 `metrics.sample_count = total` 更新为**有效样本数**，调用方核对返回值即可发现样本缩减，不存在「残缺但看起来合法」的失真 |

### 1.71 闸门、变异与读数

- 新增 `TestP235Round13Batch23Declined`（5 条）：D 型三兄弟块级
  反向钉（handler 未接线 + `pass` / `total -= 1` / auc 赋值见证 +
  外层互锁）+ X 二兄弟复核维持（error 锚点 + `return None` +
  调用方 `result.errors` 链）+ 运行时四条（CSV 非数值原样保留 /
  有效样本数如实 / 单类 AUC=None 且内层零接线调用 / 推理不可用写
  errors + 空指标无假数据）+ 文档登记。
- 桶计数棘轮实跑通过：**W=96 / X=119** 不变（纯裁定批，无新增
  `record_silent_degradation` 调用点）。
- 三次真实变异：M1 给 L207 内层 auc handler 接线（块级反向钉红）/
  M2 删 L271 的 `total -= 1` 设计行为（D 型见证红）/ M3 删「一之
  二十四」节标题（文档登记红），均 RED-OK/GREEN-OK，日志
  `mutate_p2_35_round13_batch23_result.log`。

---

## 一之二十五、#35 X 桶第二十四批：接线 1 处（W 96→97 / R 4→3 / X 119 不变，ws.py 13 条候选）

### 1.72 本批结论一句话

挑簇器输出的最大未裁定簇 `app/core/ws.py`（13 条）逐条存在性实测 +
分类器现场重算后：**1 处接线**（`core.ws.pubsub_loop_crashed`，
订阅循环崩溃重启窗口丢消息，原分类 R 本批改判接线）+ **12 处不接线**
（S/M/K/C/D/V 六型，含 1 条第十六批已裁项复核维持）。桶计数
**W=97 / X=119 / P=15**（总数 334 不变；R 4→3）。

### 1.73 存在性核查与分类器现场重算

（`tests/tools/verify_p2_35_batch24_candidates.py`：先重跑 scan 再
逐条 classify，口径与 `test_batch6_bucket_counts_pinned` 一致）

| 位置 | 函数 | 分类器桶 | 本批裁定 |
|---|---|---|---|
| L300 | `_pubsub_loop`（外层，扫描快照 L293） | R | **改判接线** `core.ws.pubsub_loop_crashed` |
| L32 | `_inc_ws_auth_failure` | S | S 型，不接 |
| L84 | `connect` | S | S 型，不接 |
| L130 | `disconnect` | X（机器）/ M（文档） | 第十六批已裁 M 型，复核维持 |
| L247 | `stop_pubsub_subscriber` | K | K 型，不接 |
| L249 | `stop_pubsub_subscriber` | C | C 型，不接 |
| L290 | `_pubsub_loop` | K | K 型，不接 |
| L306 | `_pubsub_loop`（finally） | C | C 型，不接 |
| L322 | `_handle_pubsub_message` | D | D 型，不接 |
| L344 | `_handle_pubsub_message` | D | D 型，不接 |
| L436 | `websocket_endpoint` | G（机器）/ V（裁定） | V 型，不接 |
| L461 | `websocket_endpoint` | G（机器）/ V（裁定） | V 型，不接 |
| L515 | `websocket_endpoint` | G（机器）/ V（裁定） | V 型，不接 |

（行号为接线后现状；扫描快照行号 L293/L316/L338/L430/L455/L509 因
本批插入 6 行注释整体 +6 平移，已逐条核对。）

**部署形态核查**：Redis 是生产依赖（`docker-compose.yml` 9 服务含
`redis:7.4-alpine`，backend/celery 均配 `REDIS_URL`），pubsub 跨进程
投递是生产真实路径；`_pubsub_loop` 经 `main.py:279` lifespan 启动
（`fatal=False`），运行期可达，非死代码。

**挑簇教训记账（第三例）**：挑簇器把 L130 列为「未裁定」，实则
第十六批「一之十七」不接线表第 1 条已裁 M 型（ws disconnect 指标
dec 失败）——「文档未提及」≠「未裁定」，本批复核维持并第三次
记账该信号缺陷（工具匹配未修，继续以分类器 + 审计文档逐条核对
为准）。

### 1.74 接线 1 处

| location | 文件 | 降级形状 |
|---|---|---|
| `core.ws.pubsub_loop_crashed` | `core/ws.py` `_pubsub_loop` | 订阅循环崩溃后 sleep 1s 重启，≥1s 内无订阅者（Redis 持续故障时每秒崩溃一次、窗口长期存在）；期间其它 worker 发布到本节点用户 channel 的消息被 Redis 直接丢弃（pubsub 无订阅者即丢），而发布方 `publish` 早已返回成功——消息永久丢失，投递方与接收方都毫无察觉 |

**R 型改判接线的关键论证**：分类器 R 规则（`sleep+continue/restart`
= 瞬时降级会自愈）在本处**不成立**。对照第六批先例：inference
`_persist_loop` 失败判 R 不接，因其下轮从进程内内存状态重新生成
快照、无外部输入丢失；而 pubsub 循环崩溃丢失的是**外部输入**
（其它 worker 已发布成功的消息），自愈只恢复订阅、不恢复消息。
与第十六批已接线的 `core.ws.pubsub_message_handling_failed` 位置
不同、形状不同：前者丢「一条消息」，此处丢「整个窗口的全部消息」。

### 1.75 不接线 12 处（书面记账，仍留原桶）

| # | 位置 | 类型 | 理由 |
|---|---|---|---|
| 1 | L32 `_inc_ws_auth_failure` 指标 inc 失败 | S 型 | 指标采集自身失败（warning 自报）；认证失败本身已由 close 4001 + 该函数计数上抛，客户端可见 |
| 2 | L84 `connect` 指标 inc 失败 | S 型 | 同族：连接照常建立并返回 True，仅 gauge 漂移；与 #3 互为镜像 |
| 3 | L130 `disconnect` 指标 dec 失败 | M 型（第十六批已裁） | 同 #2；连接上限拒绝对客户端可见（4009），主链路不受影响 |
| 4 | L247 `stop_pubsub_subscriber` CancelledError | K 型 | 取消是正常关停控制流（仅 main.py 关停时调用） |
| 5 | L249 `stop_pubsub_subscriber` stop 异常 | C 型 | 关停清理路径；任务已结束，warning + exc_info 留痕 |
| 6 | L290 `_pubsub_loop` CancelledError | K 型 | 循环取消即退出，break + info 日志 |
| 7 | L306 finally aclose 失败 | C 型 | 资源清理失败，debug 日志留痕（AUDIT-2026-10-06/P1-9 已定性为泄漏定位）；不影响业务语义 |
| 8 | L322 `_handle_pubsub_message` 畸形 payload | D 型 | 其它 worker 发来的数据本来就是坏的，warning + return 丢弃 |
| 9 | L344 `_handle_pubsub_message` 非法 channel | D 型 | 同上，user_id 无从提取，warning + return |
| 10 | L436 `websocket_endpoint` unexpected_error | V 型 | close 4001 + 专用计数器 + exception 日志，失败对客户端显式 |
| 11 | L461 `websocket_endpoint` db_error | V 型 | close 4503 + 计数器 + 日志；DB 故障显式呈现 |
| 12 | L515 `websocket_endpoint` runtime.error | V 型 | exception 日志 + `disconnect` 收尾，客户端连接显式终止 |

### 1.76 闸门、变异与读数

- 新增 `TestP235Round13Batch24Wiring`（6 条）：接线 location 双向
  核对 + 运行时一条（假 pubsub `psubscribe` 必炸 → 计数**恰好**
  +1，带防假绿：psubscribe 调用计数 ≥1；取消时机压在 sleep 内防
  双计数）+ 反向钉 10 条文本锚点 + K 型函数级锚点 1 条
  （`stop_pubsub_subscriber` 裸 `pass`，按 enclosing function
  定位）+ V 型见证 3 条（close 原因码 / disconnect 仍在）+
  文档登记。桶计数棘轮实跑改钉 **W=97 / R=3 / X=119**。
- 变异三条见 `mutate_p2_35_round13_batch24_result.log`。
- 未验证如实记账：后端全量本地未跑（约 37 分钟，禁止并发双跑），
  由 CI `backend-coverage` 兜底。

---

## 一之二十六、#35 X 桶第二十五批：纯裁定批（0 接线，W=97 / X=119 不变，scheduler.py 5 条新候选）

挑簇器本轮列出 `app/tasks/scheduler.py` 9 条未裁定项（ws.py 12 条系
第二十四批已裁，格式匹配缺陷误列）。手工核对：第十九批已裁 7 条
（`_send_push_notification` L401 / `_nightly_maintenance_impl` L510 /
`_cleanup_experiment_artifacts_impl` L994·L1001·L1054·L1102·L1170），
本批 5 条为剩余真新候选——`_notify_warning` 3 条（L81/L108/L129）+
`_cleanup_experiment_artifacts_impl` 2 条（L1134/L1150）。

**存在性核查**（`tests/tools/verify_p2_35_batch25_candidates.py`：先重跑
scan 再逐条 classify）：L81→M、L108→S、L129→M、L1134→F、L1150→F。
其中 L129 机器判 M 系**函数级归类的误并**（同一函数先命中 M 规则）；
按第十九批③ 同型裁定，Sentry 是叠加的第二上报通道，实为 **S 型**。
五条**均不在 X=119 内**，故本批**纯裁定、桶计数不变**。

### 1. 裁定逐条（全部不接线）

| # | 位置 | 类型 | 理由（可客观断言） |
|---|---|---|---|
| 1 | L81 `_notify_warning` 重试 except | M 型 | 失败先就地重试（`_NOTIFY_MAX_ATTEMPTS=2`），耗尽后 error 级完整上下文日志 + `warning_notify_failed_total` 专用计数器（**运行时实测真涨 +1**）+ Sentry + `return False`；调用方 `_daily_risk_scan_impl` 检查 `ok` 并汇总 error 上报 |
| 2 | L108 指标 inc 失败 | S 型 | 失败的是**指标采集通道自身**（只记 debug）；主通道日志/返回值不受影响（第五批 S 型同族） |
| 3 | L129 Sentry capture_exception 失败 | S 型 | 自报通道自身失败；主通道（L93 error 日志 + L107 专用计数器）已先触发（第十九批①②③ 同型） |
| 4 | L1134 产物目录 resolve 失败 | F 型 | AUDIT-P0-3 明示「宁可整个清理中止，也不能带残缺保护集继续删」：warning + `is_active = True` **保守跳过删除**，安全方向 fail-safe |
| 5 | L1150 产物文件 resolve 失败 | F 型 | 同族保守跳过（「无法判定真实位置 → 保守视为 active」+ `break` 停止遍历该目录） |

### 2. M 型前提的运行时实证（第二十二批纪律）

第二十二批实锤过「源码字面量在 ≠ 运行时活着」的死计数器。**本批在裁定
前实测 `warning_notify_failed_total` 存活**：注入双探针均抛 → `_notify_warning`
返回 `False`、探针确被调用 **2 次**（重试发生）、专用计数器 **+1**、
通用计数器 `silent_degradation_total.inc` **零调用**。⇒ M 型前提成立，
不重复接通用计数器；同一形态锁定为回归断言。

### 3. 闸门

- 新增 `TestP235Round13Batch25Declined`（6 条）：`_notify_warning` 三
  handler **块级反向钉**（按注释标记分辨 retry/metric/sentry）+ 终端
  见证（`return False` + error 级汇总日志 + 专用计数器 + Sentry）+
  调用方汇总见证（`ok` 检查 → `failed_notifications.append` → 汇总
  error）+ 清理两条 **F 型块级反向钉** + `is_active = True` 见证 +
  `rmtree` 仍在证明正常删除路径未被裁掉 + 运行时两条 + 文档登记。
- **运行时两条**：① 推送双探针均炸 → `return False` + 专用计数器 +1
  + 探针调用 2 次（防假绿）+ 通用计数器零调用；② **差分实验**——
  对照组（11 目录 keep_recent=10）删最老 1 个，实验组给最老目录注入
  `Path.resolve` 抛 `OSError` → `removed == 0` 且目录保留。
- 桶计数维持 **W=97 / X=119 / R=3**（纯裁定批，实跑棘轮验证）。

### 4. 记账

- 变异三条见 `mutate_p2_35_round13_batch25_result.log`。
- 未验证如实记账：后端全量本地未跑（约 37 分钟，禁止并发双跑），
  由 CI `backend-coverage` 兜底。
- 挑簇器「文档未提及 = 未裁定」信号缺陷**第四次**实锤（本批 5 条里
  第十九批已裁残留 / 格式匹配失配）。工具未修，后续挑簇继续以
  **分类器现场重算 + 审计文档逐条核对**为准。

---

## 一之二十七、#35 X 桶第二十六批：纯裁定批（0 接线，W=97 / X=119 不变，loading.py 收口）

挑簇器列 `app/core/model_engine/loading.py` 7 条。第七批已裁 8 条（当时的
行号）、第十九批又对其中 4 条做了精细钉复核。本批把**此前从未书面裁定过的
3 条**补齐，并对往批 4 条做记账一致性复核。

**存在性核查**（`tests/tools/verify_p2_35_batch26_candidates.py`）：机器口径
L82/L288/L294/L429/L596/L712 六条仍在 X（第七批「跳过 6 条、机器不裁文档裁」
的历史写法所致），L244 判 S。**五类并存不冲突**——X 是「机器未消化的留档」，
文档裁定不改变机器分类，故本批仍为纯裁定、桶计数不变。

### 1. 本批首次书面裁定（3 条，全部不接线）

| # | 位置 | 类型 | 理由（可客观断言） |
|---|---|---|---|
| 1 | L244 `_incr_model_fallback` 指标 inc 失败 | S 型 | 失败的是**指标采集通道自身**；P0 (2026-09-24) 注释已定性「指标递增失败时 Grafana 降级率曲线会**变平**（运维看到降级率 0%），若日志同时静默则『模型正在静默降级』与『指标链路已断』两种情况都不可见」——**日志侧盲区已由 AUDIT-2026-10-05 的 debug→warning 升级补齐**（带 `exc_info=True`）。注意此函数是第二批 L82（侧车）/L429（adapter）两次接线的 **M 型理由来源**；它自身失败只改变曲线形状，不改变任何调用方返回值（L108 scheduler 指标 inc 失败同族） |
| 2 | L288 `preload` PermissionError | V/M 混合（**消费点已接线**） | 详见 §2 |
| 3 | L294 `preload` OSError | V/M 混合（**消费点已接线**） | 详见 §2 |

### 2. L288/L294 的裁定依据：真降级那一刻已被计数

第七批只写了「critical 日志（loud）」这一条理由。本批把它换成**可客观断言的
调用链证据**，结论一致、依据更硬：

1. **异常在请求路径不被吞**：`PredictMixin.predict_structured` 的模型加载
   try **只捕获 `(FileNotFoundError, ValueError)`**（AST 实测该函数全部
   handler 就这两条，见闸门 `test_consumer_already_wired_and_oserror_
   propagates`），PermissionError / 一般 OSError **不被捕获 → 向调用方传播**
   （运行时实证：`pytest.raises(PermissionError)`）。
2. **主消费方已接线**：`services/risk_service_assessment.py` 对该调用包了
   `except Exception`，已接第二批的
   `services.risk_service_assessment.structured_predict_fallback`，且返回
   dict 自带 `"error": str(exc)` 与 `"model_used": "heuristic_fallback"`
   ——真正导致用户可见结果降级的那一刻**已被计数并显式标注**。
3. ⇒ 预热期再接一次会与消费点**重复计数**；诊断信息侧由 critical
   「NON-RECOVERABLE」日志文明（运维可查），metrics 侧由消费点覆盖。

互锁见证：同函数的 FileNotFoundError / 兜底 Exception 两条
（`preload.missing_file` / `preload.failed`）**仍在接线**，不得因本裁定被误删。

### 3. 往批 4 条记账一致性复核（不重复钉）

`_get_expected_hash` L82（V 型，P0-6 三态可区分）、`_load_adapter` L429
（M 型，见证 `adapter.pkl_fallback`）、`_load_model` L596（设计内 Hub 回退，
见证 `keras_compat_load_failed`）、`_patch_simple_imputer` L712（补丁失败
后续 transform 可见 AttributeError）——第十九批
`TestP235Round13Batch19Declined` 已钉，本批只做 4 个行为锚点 + 2 个见证
location 的跨批口径复核。

### 4. 闸门

- 新增 `TestP235Round13Batch26Declined`（7 条）：L244 块级反向钉 + warning/
  `exc_info`/`model_fallback_total.inc` 三见证；L288/L294 块级反向钉 +
  `logger.critical` + `NON-RECOVERABLE` 见证 + 两条既有接线互锁；
  **消费点见证钉**（`predict_structured` 捕获类型集合恰为
  `{FileNotFoundError, ValueError}`；`risk_service_assessment` 的 try→handler
  定位 + 专用 location + `"model_used": "heuristic_fallback"` + `"error"`）；
  运行时三条 + 往批复核 + 文档登记。
- **运行时三条**：① preload 内 `_load_model` 依次抛 PermissionError/OSError
  → 循环继续、**零接线调用**（防重复计数）+ critical 日志文明；② `predict_
  structured` 对该异常**真的向上抛**（用完整 14 特征，否则 routing 会在
  「信息不足」处提前 return——漏特征会让这条断言假绿）；③ 见①的日志侧断言。
- 桶计数维持 **W=97 / X=119 / R=3**（纯裁定批，实跑棘轮验证）。

### 5. 记账

- 变异四条见 `mutate_p2_35_round13_batch26_result.log`。
- 未验证如实记账：后端全量本地未跑（约 37 分钟，禁止并发双跑），
  由 CI `backend-coverage` 兜底。
- 挑簇器「文档未提及 = 未裁定」信号缺陷**第五次**实锤（loading 7 条里
  6 条系第七/十九批已裁或行号平移）。工具未修，继续以**分类器现场重算 +
  审计文档逐条核对**为准。

---

## 一之二十八、#35 X 桶第二十七批：纯裁定批（0 接线，W=97 / X=119 不变，sentry.py + api/v1/metrics.py 收口）

挑簇器前列的 `ws.py` 12 条 / `scheduler.py` 9 条 / `loading.py` 7 条
**全部系已裁残留**（第二十四/二十五/二十六批），挑簇器「文档未提及 = 未裁定」
信号缺陷**第六次**实锤。手工逐簇核对后改取**真正无任何裁定记载**的两簇：
`app/core/sentry.py`（6 条）与 `app/api/v1/metrics.py`（5 条）——检索
`P2_11_ROUND11_AUDIT.md` / `P2_13_ROUND13_AUDIT.md` 全文，
sentry 此前只在「scheduler 里的 Sentry 调用点」语境被裁过（第十九批②③、
第二十五批③），sentry.py 本体从未逐条裁；metrics.py 的 5 个 `_set_*`
采集器同样从未裁过。

**存在性核查**（`tests/tools/verify_p2_35_batch27_candidates.py`，MISSING=0）：
11 条机器口径**全判 S**（两文件均在分类器 `SELF_REPORT_FILES` 白名单里，
该名单把 metrics/sentry/otel/degradation 等可观测性自报文件整体归 S）。
按纪律分类器只作粗排，以下逐条独立复核。

### 1. app/core/sentry.py（6 条，全部不接线）

| # | 位置 | 类型 | 理由（可客观断言） |
|---|---|---|---|
| 1 | L103 `init_sentry` SDK import 失败 → warning + `return` | S 型 | 失败的是**可观测性设施自身启动**。部署形态核查：`sentry-sdk[fastapi]>=2.0.0` 是 `requirements.txt:50` 顶层依赖，`requirements.lock:323` 硬锁 `sentry-sdk==2.71.0`，`Dockerfile:100` 的 pin 清单显式含 `sentry-sdk:[fastapi]` ⇒ 生产镜像构建期必装，运行期 import 失败不可达。既有测试 `test_sdk_import_failure_does_not_raise` 已钉「不抛」语义 |
| 2 | L148 `capture_exception` SDK 调用失败 → warning | S 型 | 自报通道自身失败。调用方 `scheduler.py:117-130` 自己还包了一层 try/except 记 `debug(exc_info=True)`（双层保险），主通道不受影响 |
| 3 | L163 `capture_message` SDK 调用失败 → warning | S 型 | 同 #2（第十九批②③、第二十五批③同型） |
| 4 | L27 `_extract_status_code` 路径 1 `int()` 失败 → `pass` | D 型 | 上游 SDK 给的 status code 本来就非数值（脏数据探测），`pass` 后继续试路径 2/3 是**穷举降级**而非放弃 |
| 5 | L36 同上（路径 2） | D 型 | 同 #4 |
| 6 | L47 同上（路径 3） | D 型 | 同 #4；三条全失败才 `return None` |

**#1 的关键运行时发现（值得单列）**：`init_sentry` 的两个 handler 都是
`return` 而不抛，调用方 `main.py:249` 的 `record_step_sync("init_sentry",
_init_sentry, fatal=False)` 因此把状态记为 **`ok`**。运行时实测（阻断
`sentry_sdk` 导入后驱动 `record_step_sync`）：

```
WARNING:app.core.sentry:sentry_sdk not available, skipping Sentry initialization
init_sentry record -> {"status": "ok", "error_type": "", "error_message": "", "duration_ms": 0.0}
```

即 `/health/startup`（`main.py:543`，直接 `**startup_status.to_dict()`）
**无法区分「Sentry 已初始化」与「SDK 根本导不进来」**——运维读启动状态
会以为监控已就绪。`startup_status` 其实有 `skipped` 状态可用
（`test_iss02_startup_status.py:59` 已有用例），本批**不接线但如实记账**：
修它需要改 `init_sentry` 的返回契约或让 main.py 显式记 `skipped`，
属**行为变更而非接线**，超出 #35「静默降级接线」范围；
且 R-006 设计注释明示「sentry 初始化失败不影响启动（仅监控降级）」，
配合部署形态硬锁（见上）判 S 型。**该记账已转为独立待办信号。**

### 2. app/api/v1/metrics.py（5 条，全部不接线）

`/metrics` 端点（`main.py:390` 已注册）的自采集快照器，5 条形如
`logger.warning("<name> metric collection failed: %s", exc)`。

| # | 位置 | 类型 | 理由（可客观断言） |
|---|---|---|---|
| 7 | L84 `_set_breaker_metrics` | S 型 | 采集失败只影响该 gauge 本次是否刷新；端点其余指标照常返回，**HTTP 状态码不变**（200）。与第二十二批 `health` 家族、第十九批 metrics 同型 |
| 8 | L96 `_set_db_pool_metrics` | S 型 | 同 #7（连接池指标采不到，`db_pool_size` 保持上次值而非归零——**保持上次值比归零更保守**，不会误导成「池空」） |
| 9 | L117 `_set_model_fallback_metric` | S 型 | 同 #7。这里有一处往批先例可援引：第二十六批 L244 `loading._incr_model_fallback` 判 S 型的理由正是「降级率曲线变平不改变任何调用方返回值」 |
| 10 | L136 `_set_mttr_metrics` | S 型 | 同 #7（MTTR 统计来自 `mttr_service.compute_mttr`，失败时旧 gauge 留存） |
| 11 | L152 `_set_slo_metrics` | S 型 | 同 #7 |

**文件内正确范式对照（本批新增互锁）**：同一文件的 `_set_redis_metrics`
（L100-108）失败时执行 `redis_circuit_state.set(2)`——把「Redis 不可达」
**编码进指标值本身**，是全文件唯一「失败被显式编码」的采集器。
它与五处「只 warning」的采集器形成对照，构成本批的**范式互锁钉**：
若有人把 `set(2)` 改成纯 warning，闸门会红（Redis 不可达将从可观测
退化为静默）。同时 `_require_metrics_token`（L47-68，AUDIT-2026-10-06
P1-3）是 fail-closed 白名单，鉴权失败会显式 401/403/503——端点自身的
访问控制链无静默口子。

### 3. 闸门与读数

- 新增 `TestP235Round13Batch27Declined`（9 条）：11 处 handler 存在性 +
  块级反向钉（含直调式 `silent_degradation_total` 禁现）+ sentry 三条
  warning 文案见证 + `_extract_status_code` 三路径结构钉（handler 数=3 /
  捕获类型 / `pass` 形态 / 三个取值键按 AST 字符串实参断言）+ metrics 五条
  warning 文案见证 + **`_set_redis_metrics` 范式互锁** + 运行时两条
  （启动状态记 `ok` 实证 / 非数值 status code 三路径皆 `None` 且合法值
  仍能提取）+ 既有测试与 R-006 注释互锁 + 文档登记。
- 分类器现场重算：11 条全判 S（非 X）⇒ 纯裁定、桶计数不变。

### 4. 记账

- 变异四条见 `mutate_p2_35_round13_batch27_result.log`。
- 未验证如实记账：后端全量本地未跑（约 37 分钟，禁止并发双跑），
  由 CI `backend-coverage` 兜底。
- 挑簇器「文档未提及 = 未裁定」信号缺陷**第六次**实锤。工具未修，
  继续以**分类器现场重算 + 审计文档逐条核对**为准。
- **独立待办信号**：`init_sentry` 失败时 `/health/startup` 记 `ok`
  （见 §1），建议后续单独立项改 `skipped`；不属本轮接线范围。

---

## 一之二十九、#35 X 桶第二十八批：纯裁定批（0 接线，W=97 / X=119 不变，fallback.py + observability_exporter.py + notifier.py复核）

### 1. 存在性核查与分类器现场重算

14 条候选，14 条**全部不在 X 桶内**（D 1 + S 5 + K 1 + R 2 + 分类器粗排 X 5※），
故为纯裁定批，桶计数不变。

| 簇 | 条数 | 审计文档历史记载 | 本批性质 |
|---|---|---|---|
| `app/core/model_engine/fallback.py` | 5 | **零记载**（`_incr_model_fallback` 的 M 型先例只裁过 `model_engine/loading.py` L244 与 `predict.py` 侧调用点，从未裁过 fallback.py 自身的 4 个 inc 失败点） | 新库存 |
| `app/services/observability_exporter.py` | 4 | **零记载** | 新库存 |
| `app/monitoring/notifier.py` | 5 | P2_13 §1.25 + §一之十一⑤⑥ 已逐条裁过 | 复核 |

※ notifier 5 条的分类器粗排为 X，但文档已裁V/V/V/V/C——**分类器只是粗排**
（第五次印证），逐条以文档核对 + 本批运行时实证为准。

### 2. 核心发现：`fallback.py` 四处 except 的运行期**不可达**（E1）

分类器把 `fallback.py` L171/L199/L233/L297 判为 **S 型（metrics 自报失败）**，
本批运行时实测证明该判据**需修正为 P 型（特性探测）/ 运行期不可达**：

- **E1a**：`model_fallback_total` 专用计数器真的增长（`0.0 → 1.0`）
  —— 顺带补上第二十二批纪律「M 型裁定前必须实测专用计数器真涨」在本簇的执行。
- **E1b**：把 `model_fallback_total.inc` 打成必抛，`_incr_model_fallback`
  **仍未向外抛**——它自身内层已有 `except Exception` 全捕获并warning。
  ⇒ 外层 except 唯一可达路径是 `from app.core.model_engine.loading import
  _incr_model_fallback` 这一行失败（ImportError）。
- **E1c**：屏蔽该 import 后调用 `_text_heuristic_fallback`，返回结构与降级标记
  与正常态**完全同形**（`model_used="text_heuristic_fallback"` 保留）。

**判据意义**：这4 条 handler 保护的只是一次 import 语句，不是运行期降级。
给不可达路径接线等于制造「看起来有降级观测、实际永远不触发」的假设施——
正是第二十二批「自出生即死的专用计数器」同族陷阱的**镜像**形态
（那次是计数器活着但恒 0，这次是 except 存在但不可达）。两者的共同教训：
**源码字面量在 ≠ 运行时活着**。

对应闸门：`test_fallback_import_line_present_in_four_sites`（四处 try 首行必须是
那条 import）、`test_incr_model_fallback_inner_handler_keeps_full_capture`
（锁住「内层全捕获」这一前提——若有人把内层改成 `raise`，P 型判据失效）。

### 3. `observability_exporter.py` 四条裁定

| location | 裁定 | 依据 |
|---|---|---|
| L136 `stop` 的 `CancelledError` | **K 型**（取消） | `self._task.cancel()` 的正常配对，任务取消不是降级 |
| L150 `_wait_for_db_ready` 的 `SELECT 1` 失败 | **R 型**（自恢复） | 3 次重试后返回 False，但 `start()` 不阻断启动（warning 后继续），`_collect_all` 每轮内部继续重试 |
| L168 `_loop` 的 `_collect_all` 失败 | **R 型**（自恢复），**有硬证据** | 见下E2 |
| L206 `_record_export_failure` 的计数器 inc 失败 | **S 型**（自报失败） | 失败的是 `observability_export_errors_total` 自身；且注释明示「避免递归失败」——递归防护是设计决策 |

**E2（R 型的硬证据，对应第二十四批 R 型判据「自愈是否丢失外部输入」）**：

`_safe_set_alert_total` 失败时**不推进** `_prev_total_fired`，故下轮
`delta = total_fired - prev` 会把退避期间新增的告警**一并计入**。实测：
基线 100 → 失败轮（`_compute_trend` 必抛）→ 基线仍 100、Counter 无增量；
恢复轮 `total_fired=130` → delta **= 30**（含退避期间新增的 30）。
⇒ 自愈不丢外部输入，R 型判定成立。结构钉锁住「`_compute_trend` 调用行号 <
`_prev_total_fired` 赋值行号」，顺序颠倒会让退避期间的增量永久丢失。

### 4. `notifier.py` 五条复核（维持V/V/V/V/C）

- L198/L287/L342 三个通道 `send` 的 `except Exception` → **V 型**：
  E3 实测——通道失败既进 `results{"probe": False}`（调用方可察觉），又落
  `alert_channel_failed` 审计（detail 带 error 原文），**失败被如实呈现**。
- L413 `_dispatch` 的未捕获异常 → **V 型**（同上，`success=False` + `error_msg`
  随 results 返回）。
- L455 `_write_channel_log` 的审计写失败 → **C 型**（通知结果已由 results 承载）。

复核钉同时确认 `monitoring.escalation.notify_failed`（第二十四批已接）与
`alerts._handle_active_alert` 的 `return 1, 0, 1` 失败形态仍在。

### 5. 闸门与读数

- 新增 `TestP235Round13Batch28Declined`（10 条）：14 处 handler 存在性 + 块级反向钉
  （含直调式 `silent_degradation_total` 禁现）+ 四处 import 首行结构钉 +
  `_incr_model_fallback` 内层全捕获结构钉 + `_safe_set_alert_total` 基线推进顺序钉 +
  `observability_export_errors_total` 调用见证 + notifier 复核钉 + 运行时三条
  （E1a/E1b/E1c/E2/E3）+ 文档登记。
- **测试污染事故（已修）**：E3 首版用 `notifier.record_audit = _fake` 直接赋值替换
  模块属性且未还原，污染同进程后续测试 —— 合并跑时 `tests/test_notifier.py` 四条
  通道审计用例（`test_channel_sent_logged_on_success` /
  `test_channel_failed_logged_on_failure` /
  `test_channel_log_includes_duration_ms` /
  `test_channel_log_detail_includes_error`）红，而单跑 `test_notifier.py` 55 passed
  全绿。**「单跑绿、合并跑红」正是测试间污染的可客signature**；已改`monkeypatch.setattr`
  并复跑确认 **405 passed**（7 个受影响测试文件合并跑）。
- 分类器现场重算：14 条**无一条在 X 桶内** ⇒ 纯裁定、桶计数不变。
- CI（HEAD `24c7aea`，第二十七批）：**10/10 success**（含 `backend-coverage`），
  第二十七批收口。

### 6. 记账

- 变异四条见 `mutate_p2_35_round13_batch28_result.log`。
- 未验证如实记账：后端全量本地未跑（约 37 分钟，禁止并发双跑），由 CI
  `backend-coverage`兜底。
- 挑簇器「文档未提及 = 未裁定」信号缺陷**第七次**实锤（它把本批两簇新库存
  也报为「未裁定」，但同时也把已裁的 notifier 报进来）。工具未修。

---

## 一之三十、#35 X 桶第二十九批：纯裁定批（0 接线，W=97 / X=119 不变，otel.py + model_predict/_common.py）

### 1. 存在性核查口径修正（挑簇器与 basename 双双失效后）

第二十九批起，**裁定记载的检索单位从「文件名」改为「函数名」**。原因：
本批先试basename 口径（去掉 `.py` 的短名在四份文档中检索），结果「零提及簇」
只剩 4 个、其中 >=3 条的**0 个**——短名（`_common` / `training_jobs`）被别的
句子误命中，把已裁的也算成了零提及。而挑簇器「文档未提及 = 未裁定」已连续
七次误报。函数名才是P2_13 各节真实的登记单位（「文件 L号（函数名）」格式），
比文件名更细、也不受短名污染。工具 `tests/tools/probe_p2_35_batch29_unjudged.py`。

按函数名口径，全仓共 **99 条**真新库存候选，其中整簇零记载（该簇函数名一次都
未被登记）的有 6 个：`otel.py`(7)、`model_predict/_common.py`(6)、
`metrics_helpers.py`(4)、`user_data_service.py`(4)、`celery_breaker.py`(4)、
`idempotency.py`(3)。本批取前两簇（13 条）。两簇的完整路径为 `app/core/otel.py` 与
`app/api/v1/model_predict/_common.py`（下表为简写）。

### 2. 裁定明细（13 条，全部不接线）

| location | 桶 | 依据 |
|---|---|---|
| `otel.py:133` `init_otel` 初始化异常 | **S 型**（第三十批改判 **V 型**） | 自报设施自身失败；且 E2 证明该 handler **不可达**（见下） |
| `otel.py:151/166/180` `_instrument_*` 的 ImportError | **P 型** | instrumentation 是可选增强，缺失只少一段 trace；handler 只 `logger.debug`，无 metrics |
| `otel.py:203` `instrument_app` 的 ImportError | **P 型** | 同上（`pass` 形态） |
| `otel.py:205` `instrument_app` 的 Exception | **S 型**（第三十批确认 **P 型不可达**） | 自报设施自身失败，warning 带 `exc_info` |
| `otel.py:228` `shutdown_otel` 失败 | **S 型**（第三十批确认 **P 型不可达**） | 关停期清理失败，不影响业务语义 |
| `_common.py:184` `_save_assessment_sync` 调度失败 | **W（复核）** | 第六批已接 `api.model_predict._common.assessment_save_schedule_failed`，本批钉住完整 location 字面量防`_typo` 型变异 |
| `_common.py:261` `_generate_structured_factors` 的 `float()` 失败 | **D 型** | 脏数据探测，`continue` 跳过该特征 |
| `_common.py:317/333/349/365` `_generate_physio_factors` 四处 | **D 型** | 同上（四个生理字段各一处） |

### 3. 核心发现一：`otel_enabled` 是**死配置**（E1）

`config.py:427` 声明了 `otel_enabled: bool = False`，但**全仓 AST 零消费点**——
唯一命中是 `otel.py` 模块 docstring 里的说明文字，不是代码读取。`main.py:253`
的 `_init_otel` 只透传 `settings.otlp_endpoint`（默认 `""`），**从不读
`otel_enabled`**。运维改 `OTEL_ENABLED=true` 不会有任何效果，而配置项存在
本身会让人以为「关着是配置问题」。

### 4. 核心发现二：otel 依赖**双重不可达**（E2），方向与往批相反

> ⚠️ **本节的推理链已被第三十批推翻并重写**，结论由「7 条全部不可达」修正为
> 「**L133 可达（V 型）+ 其余 6 条不可达（P 型）**」。保留原文以存历史快照，
> 正确表述见下方「🔺 第三十批更正」。

- `requirements.txt` **零** opentelemetry 条目；
- `requirements.lock` 只有间接依赖 `opentelemetry-api==1.45.0`
  （来自 prometheus/fastapi 链路），**无 sdk / exporter / instrumentation / distro**；
- 实测 `_check_otel_available()` → `False`，`init_otel(endpoint="")` → `False`
  （走L71 的提前 return）。

> 🔺 **第三十批更正**：`opentelemetry-api` 的来源是 **fastapi**（lock 中该条目的
> `# via` 为 `fastapi`），因此**任何装了 fastapi 的环境（含 CI）顶层包都能导入**，
> `_check_otel_available()` 在交付形态下返回 **True**——本节「实测 → False」测的是
> **本机 venv 的环境状态**（恰好没装 api），不是交付形态。真正的默认阻断是
> `otlp_endpoint` 默认空串。且一旦运维显式配置 endpoint，`otel.py:133` 的外层
> `except Exception` **真实可达**（sdk/exporter 缺失 ⇒ ImportError 被捕获 ⇒
> `return False` + warning）。

⇒ `otel.py` 的 7 条 handler 在**交付形态下全部不可达**。这与第二十一/二十二批
的「双重外部阻断」同型但**方向相反**：那批是「接线即恒 0」（计数器活着但永不涨），
这批是「handler 永不触发，接线即假设施」。两者共同指向第二十二批那条纪律：
**源码字面量在 ≠ 运行时活着**。

**判据修订**：给不可达路径接线不只是「无价值」，而是**制造「看起来有降级观测、
实际永不触发」的假设施**——比不接线更危险，因为它会让后续维护者误以为该路径
已被覆盖。

### 5. 核心发现三：`/health/startup` 把 OTel 失败记为 `ok`（E3）

`main.py:253-262` 的 `_init_otel` 调用 `init_otel(...)` 但**不return**，
而 `init_otel` 自身所有失败路径都是 `return False` 不抛⇒
`record_step_sync("init_otel", _init_otel, fatal=False)` 把状态记为 **`ok`**。

实测输出：`init_otel 启动状态 -> status='ok' error_type=''`。
即 `/health/startup` **无法区分「追踪已启用」与「依赖根本没装」**。

这是第二十七批 `init_sentry` 同型信号的**第二次出现**（两次都是
「调用方不检查返回 bool + 被调用方只 return不抛」的组合）。两次都属**行为变更
而非接线**（`startup_status` 有 `skipped` 状态可用），超出 #35 范围，已并入
独立待办信号。

### 6. D 型的运行时见证（E4）

`_common.py` 五处脏数据 handler：结构化路径投`"abc"`/`None` ⇒ 返回 `[]`；
生理四个字段各投`"坏值"` ⇒ 全部跳过、返回 `[]`；`data_quality=="poor"` 时
兜底因子「数据质量」仍在。对照组：正常数据产出真实因子（证明不是「一律返回空」
的退化实现）。

### 7. 闸门与读数

- **M3 假绿事故（已修，方法论级）**：M3 把结构化因子的 `continue` 改成 `break`
  后闸门**竟全绿** —— 原E4 只投单个脏值，`continue` 与 `break` 行为完全相同，
  断言根本没覆盖「脏特征之后的正常特征是否仍被产出」这一真正的风险面。
  **根因**：变异只翻转了实现，没翻转断言的**真值空间**。已补①混合输入用例
  （脏 `stress_level` + 正常 `anxiety`，后者必须仍产出因子）②结构钉
  `test_structured_dirty_data_must_continue_not_break`（按 AST 断言 handler
  里有 `continue` 且无 `break`/`return`）③变异脚本 `mutate()` 加 `try/finally`
  —— **无论 RED 还是假绿都必须还原**，否则残留变异污染工作树
  （M3 中断时确实在 `_common.py` 留下了 `break`，靠 `git checkout --` 挽回）。
- 新增 `TestP235Round13Batch29Declined`（13 条）：13 处 handler 存在性 +
  12 处块级反向钉（`_common.py:184` 已接线故排除）+ **完整 location 字面量
  互锁**（防 `_typo` 型变异）+ `otel_enabled` **死配置 AST 钉** + 依赖未交付
  源码钉 + 三处 warning 文案见证 + 三处 debug-only 钉 + **`continue` 结构钉**
  （见上 M3 事故）+ 运行时四条（E1/E2/E3/E4）+ 文档登记。
- 分类器现场重算 13 条：S3 + P4 + D5 + W1（已接线）⇒ **无一条在 X 桶内**
  ⇒ 纯裁定、桶计数不变。
- CI（HEAD `8cac938`，第二十八批）：**10/10 success**。

### 8. 记账

- 变异四条见 `mutate_p2_35_round13_batch29_result.log`。
- 未验证如实记账：后端全量本地未跑（约 37 分钟，禁止并发双跑），由 CI
  `backend-coverage` 兜底。
- **检索口径修正**：裁定记载的检索单位由「文件名」改为「函数名」（见 §1）。
  挑簇器与 basename 口径**双双失效**（前者七次误报，后者被短名污染压到 0 个
  >=3 条簇）。工具 `probe_p2_35_batch29_unjudged.py` 已入库，输出 JSON 落盘
  `probe_p2_35_batch29_unjudged.json`（99 条真新库存候选清单，供后续批次取用）。
- **独立待办信号（第二次出现）**：`/health/startup` 把 `init_otel` 记为 `ok`，
  与第二十七批 `init_sentry` 同型；建议合并立项把两者改为 `skipped`。
- **CI 实锤本批 §4 判据错误**：HEAD `7bd9bcc` 的 `backend-coverage`
  **1 failed / 6901 passed**，红的正是 E2（详见下节）。

---

## 一之三十一、#35 第三十批：第二十九批 CI 红事故复盘（裁定修正，W=97 / X=119 不变）

### 1. 事故

HEAD `7bd9bcc` 第二十九批的 CI：`backend-coverage` **failure**
（**1 failed, 6901 passed, 68 skipped**, 576s），唯一红项：

```
TestP235Round13Batch29Declined::test_runtime_e2_otel_unavailable_and_returns_false
AssertionError: opentelemetry 在本机可导入 —— 与交付物（requirements.lock 无 sdk）
不一致，可达性判据需重估
```

### 2. 根因：我把**环境状态**当成了**交付形态**

第二十九批 E2 断言 `_check_otel_available() is False`，依据是本机 venv 实测。
但：

| 环境 | `opentelemetry-api` | `_check_otel_available()` |
|---|---|---|
| 本机 venv（fastapi 0.135.3） | **未安装** | `False` |
| CI（`pip install -r requirements.txt`） | **已安装**（lock 里经 fastapi 传递引入） | **`True`** |

`requirements.lock:229` 的 `opentelemetry-api==1.45.0` 的 `# via` 是 **`fastapi`**
（不是第二十九批文档里写的 prometheus 链路）⇒ **任何装了 fastapi 的机器**顶层
包都可导入。`_check_otel_available()` 只做 `import opentelemetry`，因此这道门
在交付形态下是**开着的**。

**这条是继「源码字面量在 ≠ 运行时活着」「变异只翻转实现 ≠ 翻转真值空间」之后，
第三条同族纪律：断言钉的必须是「交付形态下不变的事实」，不是「我这台机器上
碰巧成立的状态」。**

### 3. 裁定修正：7 条不是「全部不可达」

在 tempdir 里造出 **CI 等价环境**（顶层 `opentelemetry` 可导入、
sdk/exporter/instrumentation 全缺 = lock 的真实形态）逐条重算
（证据脚本 `tests/tools/probe_p2_35_batch30_runtime.py`，五项全部成立）：

| 编号 | 实测 | 修正后桶 |
|---|---|---|
| E1 | `_check_otel_available()` → **`True`** | 依赖门是开的 |
| E2 | `init_otel(otlp_endpoint="")` → `False`，且 `_otel_initialized` 不置位 | 真正的默认阻断在 **L77**（endpoint 空串），非依赖门 |
| E3 | 配 endpoint 后 `init_otel` → `False`，命中 `L133` 外层 except，记`initialization failed` warning | **L133 可达 = V 型**（`return False` + warning，失败如实上报，无需接线） |
| E4 | 三处 `_instrument_*()` 调用行号（2885等）**全部大于** `_otel_initialized = True` 行号（2615） | L151/L166/L180 **P 型不可达** |
| E5 | `_otel_initialized=False` 时 `instrument_app`+`shutdown_otel` 零日志；置 `True` 后产生 1 条日志（反证闸门生效） | L203/L205/L228 **P 型不可达** |

⇒ **净结果仍是 0 接线、桶计数 W=97 / X=119 不变**，但**理由换了**：不再是
「依赖未交付 ⇒ handler 不可达」，而是「成功路径需要 lock 里没有的 sdk/exporter
⇒ `_otel_initialized` 永不为 True ⇒ 六条 P 型不可达；L133 本身是 V 型可达」。

**判据修订（取代第二十九批那条）**：不可达性**不能**由「依赖没装」推出——
必须**逐条问它的进入路径被什么挡住**。这里挡住六条的是**上游成功路径的
依赖缺口**（`_otel_initialized` 闸门），不是它自己的 `except`。

### 4. 闸门修正（`TestP235Round13Batch29Declined` 13 → 16 条）

- **E2 重写**：不再断言 `_check_otel_available()` 的真实返回值（环境依赖），
  改为在 tempdir 里自造 CI 等价环境，断言①该环境下依赖门为 `True`
  ②空 endpoint 时`init_otel` 返回 `False`——两条与运行环境无关。
- **E2b 新增（反向钉）**：配了 endpoint 时`init_otel` 必须命中 `L133` 外层
  except 并 `return False` + warning。若哪天 sdk 补齐，此断言会红 ⇒ 那正是
  「该 handler 不再可达」的信号，应据实重估裁定。
- **`test_instrument_calls_only_on_success_path` 新增（结构钉）**：三处
  `_instrument_*()` 的调用位置必须**晚于** `_otel_initialized = True`。
- **`test_instrument_app_and_shutdown_gated_by_initialized_flag` 新增**：两函数
  必须有 `if not _otel_initialized: return` 闸门 + 运行时反证（零日志 / 有日志）。
- **`test_otel_dependency_not_delivered` 重写**：结论（「sdk/exporter 未交付」）
  不变，**推理链换掉**——并新增钉「`opentelemetry-api` 的 `# via` 是 `fastapi`」
  与「依赖门只 `import` 顶层包」两条，把「依赖门是开的」这个前提本身钉住。

### 5. 变异四条（全 RED-OK / GREEN-OK）

| 变异 | 改什么 | 红几条 |
|---|---|---|
| M1 | `_instrument_fastapi()` 提到 `_otel_initialized = True` **之前** | **1**（正是新加的顺序钉） |
| M2 | 删 `instrument_app` 的 `_otel_initialized` 闸门 | 3 |
| M3 | 依赖门收紧为同时 import `opentelemetry.sdk.trace` | 5 |
| M4 | 绕过空 endpoint 的提前 return（`or "http://mutated.invalid:4317"`） | 3 |

M1 只打 1 红这一点很有说服力：新加的顺序钉**精确命中**且不牵连其他断言
（旧断言对这次变异完全无感，说明「结构顺序」这条新判据是原测试集里缺的维度）。
变异后blob 哈希核对 `otel.py` / `_common.py` 与 HEAD 一致（无残留）。

### 6. 记账

- 变异日志 `tests/tools/mutate_p2_35_round13_batch30_result.log`。
- 后端全量本地仍未跑（约 37 分钟，禁止并发双跑），由 CI `backend-coverage` 兜底。
- **历史快照不改**：第二十九批节保留原文并加更正标记，符合「历史快照只追加、
  不篡改」纪律。
- **未验证**：本批 CI 结果待轮询确认，不预先宣称全绿。
- 纯裁定批，`app/` 生产代码**零改动**。

---

> 🔺 **本节的 E3 结论在第三十二批被加上条件前提**（L133 的可达性依赖交付形态
> 下顶层包可导入，非无条件成立），修正见「一之三十二」。

---

## 一之三十二、#35 第三十一批：第三十批 CI 红事故复盘（同一纪律在同一批里被违反两次，W=97 / X=119 不变）

### 1. 事故：修完 E2 的当批，E5 又红了

HEAD `b1d4493` 的 CI：`backend-coverage` **failure**（**1 failed / 6904 passed /
68 skipped**，848s），唯一红项是**本批新增**的
`test_instrument_app_and_shutdown_gated_by_initialized_flag`：

```
AssertionError: _otel_initialized=True 时仍无日志 ⇒ 闸门反证不成立，
L203/L205/L228 的可达性判据需重估
```

### 2. 根因：同一条纪律在同一批测试里被违反两次

我上一节刚把 E2 从「断言本机环境」改成「在 tempdir 造交付形态」，紧接着在 E5
里又写回了「环境状态」——用「`_otel_initialized=True` 时日志数 > 0」反证闸门生效：

| 环境 | `from opentelemetry import trace` | 走哪个分支 | 日志数 |
|---|---|---|---|
| 本机 venv（未装 otel） | **失败**（ImportError） | `except Exception` → warning | **1** |
| CI（api 经 fastapi 已装） | **成功** | `hasattr(provider,"shutdown")`；`ProxyTracerProvider` 无 `shutdown` ⇒ 整个 `if` 跳过 | **0** |

⇒ 本机绿、CI 红。**「我刚立完的纪律，在下一条测试里就违反」本身就是一个信号**：
说明这条纪律没有被**机制**兜住，只停留在文字层面。

### 3. 修法一：反证改用**探针调用计数**（与包是否安装无关）

不再数日志，改为自造 `opentelemetry` 包并让 `trace.get_tracer_provider()` 记录
被调用次数：
- 闸门生效 ⇒ `_otel_initialized=False` 时 provider **一次都不该被取**；
- 反证 ⇒ 置 `True` 后 **必须被取**（证明上面不是假通过）。

两条在「装了 otel」和「没装 otel」的机器上都成立。

### 4. 修法二：把「CI 装了 otel」变成本机可复现（防再犯的机制）

新增 `tests/tools/probe_p2_35_batch31_ci_env.py`：把 fake `opentelemetry`
装进 `PYTHONPATH`，让 pytest **进程启动起**就认为 otel 可导入，跑整批闸门四轮：

| 轮 | 环境 | 结果 |
|---|---|---|
| A | 本机默认（未装 otel） | **17 passed** |
| B | CI 等价（注入命名空间包形态的 otel） | **17 passed** |
| C | B + **故意注入一条环境依赖断言** | **1 failed** ← 证明该环境**真能识别**环境依赖断言 |
| D | 还原后 | **17 passed** |

C 轮是关键：没有它，「B 全绿」可能只是探针失真。**反向验证让结论可信。**

### 5. 附带发现（裁定层面）：「L133 可达」是**条件结论**，不是无条件结论

双形态实测（新测试 `test_reachability_conclusions_hold_in_both_env_shapes` 自身
输出即证据）：

| 形态 | 依赖门 | 空 endpoint | 配 endpoint 后命中 L133？ |
|---|---|---|---|
| A：opentelemetry 完全不可导入 | `False` | `False` | **否**（走 L71 提前 return，进不去 L133） |
| B：顶层包可导入、sdk/exporter 全缺（**交付形态**） | `True` | `False` | **是** |

⇒ 第三十批那句「L133 可达（V 型）」**以交付形态为前提**。前提已由
`test_otel_dependency_not_delivered` 钉住（lock 里 `opentelemetry-api==1.45.0`
的 `# via` 是 `fastapi` ⇒ 顶层包必然可导入）。若后续 fastapi 版本变更把 api
移出依赖闭包，L133 将退化为不可达 ⇒ 该测试形态 B 段会红，裁定需据实重估。

**由此新增一条纪律**：可达性结论若依赖依赖形态，**必须把那个形态钉成断言的
前提**，并在文档里写明它是条件结论。

### 6. 修法三：形态 A 的构造也不能用 `sys.path` 过滤

初版形态 A 用「从 `sys.path` 里过滤掉 `site-packages`」来屏蔽 otel，自验证时
**B 轮立刻红**——那样只能屏蔽装在 site-packages 的包，屏蔽不了 `PYTHONPATH`
注入的（CI 仿真正是这么注入的）。改用 `sys.meta_path` 拦截器抛 `ImportError`，
与安装位置无关。

### 7. 闸门与读数

- 闸门 `TestP235Round13Batch29Declined` 16 → **17 条**（新增
  `test_reachability_conclusions_hold_in_both_env_shapes`）。
- 变异四条重跑全RED-OK/GREEN-OK：M1 → 1 红 / M2 删闸门 → **3 红**（探针法生效）
  / M3 依赖门收紧 → **6 红**（比上轮多 1，正是新形态测试）/ M4 绕过提前
  return → 3 红。变异后 blob 哈希核对 `otel.py` / `_common.py` 与 HEAD 一致。
- 受影响测试合并跑（6 文件）**253 passed**。
- 纯裁定批，`app/` 生产代码**零改动**，桶计数 W=97 / X=119 不变。

### 8. 记账

- 证据 `probe_p2_35_batch31_ci_env_result.log`（四轮读数全落盘）。
- 后端全量本地未跑（约 37 分钟，禁止并发双跑），由 CI `backend-coverage` 兜底。
- **未验证**：本批 CI 待轮询，不预先宣称全绿。
- **纪律落地缺口已补**：第三十批立的纪律只写在文档里，没有机制兜 ⇒ 本批把
  「双环境跑闸门 + 反向验证探针有效性」做成可复现脚本，作为后续批次的固定动作。

---

## 一之三十三、#35 X 桶第三十二批：1 接线（`metrics_helpers._load_json`），W=97→98 / X=119 不变

### 1. 本批范围（15 条：1 接线 + 14 不接）

簇来源仍是 `tests/tools/probe_p2_35_batch29_unjudged.py` 的**函数名级**零记载
候选清单（第二十九批确立的口径）。四簇的函数名在 P2_10/P2_11/P2_13 三份文档中
均零出现：

| 簇 | 条数 | 裁定 |
|---|---|---|
| `app/api/v1/metrics_helpers.py` | 4 | **W 1（本批接线）+ W 3（已接线复核）** |
| `app/core/celery_breaker.py` | 4 | **P 4**（ImportError 在交付形态下不可达） |
| `app/services/user_data_service.py` | 4 | **D 4**（脏数据跳过） |
| `app/core/idempotency.py` | 3 | **W 3**（已接线复核） |

桶计数 **W 97→98、S 36→35，总数 334 不变**；累计状态 **W=98 / X=119**。

### 2. 接线项：`metrics_helpers.py:116` `_load_json`（S → W）

**判据不是「日志不够响」** —— 那类软理由一律不采（见 §2 判据纪律）。依据是可客
断言的**同形性**（runtime 实测，见 `probe_p2_35_batch32_runtime.py` E3）：

| 情形 | `_load_json` 返回 | 下游 `_extract_*` | Prometheus |
|---|---|---|---|
| 产物正常 | `dict` | 有指标 | 序列存在 |
| **产物损坏**（截断/权限/训练并发写半截） | **`None`** | `{}` | **序列消失** |
| **产物未部署** | **`None`** | `{}` | **序列消失** |

后两行**对调用方完全同形**：Grafana 上「模型没训过」与「产物坏了」长得一模一样，
调用方从返回值看不出 ⇒ 满足接线判据。

**同族一致性（范式互锁）**：同文件 `collect_ml_quality` / `collect_drift` /
`collect_canary` 三处**已经接线**（L231/L257/L283），失败语义同样是「真实产物
读不到 ⇒ 指标序列消失」。本处不接就与同文件已接线路径自相矛盾。

**可达性已按第三十批纪律核实**（不靠「依赖没装」推断）：`docker-compose.yml:155`
把 `./backend/models` 只读挂载进容器，实测该目录下真实存在 3 个 `metrics.json`
（`artifacts/physiological/`、`artifacts/physiological_optimized/`、
`v1.23_external_lr/`）⇒ 文件确实存在 ⇒ `OSError`/`JSONDecodeError` 可达。
这与第二十一批 scaler 的情形**相反**（那批默认配置 + 模型文件不入库 ⇒ 不可达）。

接线 location：`"api.metrics_helpers.load_json"`。

### 3. 不接项判据

**`celery_breaker.py` 4 条 —— P 型不可达（接线即假设施）**

- `requirements.txt` 有 `celery>=5.4.0` / `redis>=5.0.4`；
  `requirements.lock` 有 `celery==5.6.3` / `kombu==5.6.2` / `redis==8.1.0`。
- 实测 `_INFRA_EXCEPTIONS` 已含 `OperationalError` / `TimeoutError` /
  `ConnectionError` / `BusyLoadingError` ⇒ 四条 `except ImportError` 在交付
  形态下**永不触发**。
- 这是第二十九批 otel 同族，但**方向相反**：otel 那里我错把「本机没装」当成
  交付形态（实际 `# via` 是 fastapi，门是开的）；这里恰恰是「依赖**已交付**」
  ⇒ ImportError 真的不会触发。两次都要求查 `requirements.lock` 的真实来源，
  不凭印象。

**`user_data_service.py` 4 条 —— D 型脏数据**

- 混合输入实测（脏 `sleep_hours` + 正常 `heart_rate`/`steps`/`exercise_minutes`）：
  脏字段只跳过自己，其余三项**全部仍产出**（`['步数','运动时长','心率']`）。
- 这是第二十九批 M3 假绿事故教训的直接应用：只投**单个**脏值无法区分
  `continue` 与 `break`，必须投「脏 + 正常」混合输入。
- 全脏 + `data_quality=poor` 时兜底因子「数据质量」仍在 ⇒ 不是静默降级。

**`idempotency.py` 3 条 —— W 复核**：`begin_failed_fail_open` /
`settle_failed` / `dismiss_failed` 三个 location 字面量齐全。

### 4. 闸门与变异

- 新增 `TestP235Round13Batch32Wiring`（9 条）：15 处 handler 存在性 + 所属函数
  未漂移 + **块级反向钉**（8 条不得接线路径内禁现 `record_silent_degradation`）
  + location 完整字面量 + 交付物依赖钉 + 运行时 E1/E2/E3 + 文档登记。
- 变异四条见 `mutate_p2_35_round13_batch32_result.log`。

### 5. 附带记账：CI 出现一条与本轮无关的计时 flake

HEAD `48c6410`（第三十一批）的 `backend-coverage` **failure**，
**1 failed / 6905 passed / 68 skipped**（609s），唯一红项是
`tests/performance/test_observability_perf.py::test_response_time_7d_under_300ms`
—— `assert 421.86 < 300`。判定为**与本轮无关的计时型 flake**，依据三条：

1. 失败项与前两批完全不同（前两批分别是 otel 的两个新断言），说明第三十一批
   的修复**已生效**；
2. 该文件自仓库初始化（`341f22c`）以来未被本轮任何批次改动过，且断言的是
   5000 行聚合查询的**墙钟耗时**（`<300ms`），本质受机器负载影响；
3. 本机单独复跑该用例 **1 passed**（8.08s）。

本轮不改它（超出 #35 范围），转**独立待办**：该性能断言缺少容差/重试机制。
下一次 CI 运行同时充当这条 flake 的 A/B 复测。

- **未验证**：本批 CI 待轮询，不预先宣称全绿。

---

## 一之三十四、#35 X 桶第三十三批：1 接线（`user_upload._validate_mime_type`），W=98→99 / G=8→7 / X=119 不变

### 1. 本批范围与挑簇信号（15 条：1 接线 + 14 不接）

**挑簇信号本批换了一个**。第二十九批确立的「函数名级零记载」被证明只是粗排：
第三十二批的四簇里，`tasks/pdf_report.py` 的三个函数（`_notify_progress` /
`save_pdf_bytes_to_redis` / `get_pdf_bytes_from_redis`）至今仍报函数名零记载，
但该文件早在 §1.9 就被**整簇裁定**过（5 条接线）。也就是说裁定文档的登记单位
在文件级与函数级之间并不一致，光看函数名会把已裁残留重新挑一遍。

本批改用更硬的信号：候选文件名的 **basename 在 P2_10/P2_11/P2_13 全文出现
0 次** ⇒ 该文件从未被点名裁定过。命中该口径的正好是 12 个文件 15 条：

| 簇 | 条数 | 裁定 |
|---|---|---|
| `app/api/v1/user_upload.py` | 1 | **W 1（本批唯一接线）** |
| `app/core/fire_forget_metrics.py` | 2 | S 2 |
| `app/core/db_breaker.py` | 2 | P 2 |
| `app/core/smtp_breaker.py` / `ml_breaker.py` | 2 | P 2 |
| `app/ml/drift_detector.py` | 1 | P 1 |
| `app/services/email_service.py` | 1 | R（人工裁定 **V**，见 §3） |
| `app/core/logging_config.py` | 1 | S 1 |
| `app/api/v1/alerts/_schemas.py` | 2 | G 2 |
| `app/core/deps.py` | 1 | G 1 |
| `excel_job_store.py` / `pdf_job_store.py` | 2 | D 2 |

存在性核查 `verify_p2_35_batch33_candidates.py`：**MISSING=0，无 FUNC-DRIFT**。
桶计数 **W 98→99、G 8→7，总数 334 不变**；累计状态 **W=99 / X=119**。

### 2. 接线项：`user_upload.py:162` `_validate_mime_type`（G → W）

**判据是同形性实测**（`probe_p2_35_batch33_runtime.py` E1），不是软理由：

| 情形 | `_validate_mime_type` | `_process_batch_file` 返回 | 上传方可见？ |
|---|---|---|---|
| libmagic 正常、MIME 匹配 | 通过 | `{"url": "/uploads/1/xxx.png", ...}` | — |
| **libmagic 抛 MagicException/OSError** | **静默 return（跳过校验）** | **`{"url": "/uploads/1/yyy.png", ...}`** | **完全看不出** |
| 对照组：MIME 与扩展名不匹配 | 抛 400 | `{"error": "文件内容类型(text/plain)与扩展名不匹配"}` | 被拒 |

前两行**响应键集合完全相同（都带 `url`）**——内容类型其实没被验证，只剩扩展名
白名单在兜底，而上传方拿到的是"上传成功"。第三行是对照组：它证明这条同形性
断言**有区分力**，不是恒真（第二十九批 M3 假绿的教训：断言必须能分辨实现差异）。

**同族互锁（决定性）**：第十一批已为
`services.file_security.clamav_dependency_missing_fail_open` 接线，当时的裁定
理由原话是「依赖缺失时的 fail-open 跳过同样是『未扫描按已扫描处理』，必须计数」。
本条的语义**完全相同**：安全校验被 fail-open 跳过 = 未校验按已校验处理。同一条
上传安全链路（SEC-P2-003）上 ClamAV 侧已计数、MIME 侧不计数，即自相矛盾。

**分类器误判值得单列**：它把本条粗判为 **G（fail-closed）**，因为 handler 返回
`None`。但这里的 `None` 是**放行**（函数提前 return，调用方继续走保存+返回 url），
与 `_schemas.py:68` 那种「解析失败 ⇒ 置 None 中性化」的 fail-closed 截然相反。
⇒ **分类器按「返回值形态」粗排会把 fail-open 与 fail-closed 混为一谈**，
这是继第二十九批「函数级归类误并」之后的又一类粗排缺陷，最终裁定仍以逐条
文档核对 + 运行时实测为准。

接线 location：`"api.user_upload.validate_mime_type"`。接线后 E6 实测
`silent_degradation_total{location=...}` **0 → 1**（不是「源码字面量在」就算数）。
> 附带：实测时发现本仓 `app.core.metrics.Counter` 是**自研**实现（无 `.labels()`、
> 读值走 `collect()`）。第二十二批正是把 prometheus 形态的 `.labels(x).inc()`
> 用在它上面导致恒 0；本批探针按自研形态读数，避免重演。

### 3. 不接项判据

**`fire_forget_metrics.py` 2 条 —— S 型（可观测设施自身故障 + 同源失效）**

两条保护的都是 `app.core.metrics` 的 Counter 自增。不接的理由有两条，第二条是
硬判据：

1. 模块 docstring 明示设计原则「优雅降级：指标采集失败仅 debug 日志，不影响主
   流程」；任务失败另有 `failed` 状态计数与各模块 `_log_*_exception` 覆盖。
2. **同源失效**：`record_silent_degradation`（`degradation.py:30-32`）内部同样
   是 `from app.core.metrics import silent_degradation_total` + `.inc()`。
   实测（E2）阻断 `app.core.metrics` 后，`record_scheduled` 静默返回，
   `record_silent_degradation` 也静默返回，探针 location 计数 **0 → 0**。
   ⇒ 用它去观测「metrics 采集失败」等于用一个会在同一故障下一起失效的设施去
   观测该故障，正是第二十九批禁止的「看起来有降级观测、实际永不触发」。

> 探针写法教训：阻断依赖时必须**同时清 `sys.modules` 缓存** —— 只插
> `sys.meta_path` 拦截器挡不住已在缓存里的 `app.core.metrics`，那样跑出来的是
> 假证据（第三十一批 meta_path 屏蔽法的补充）。

**`db_breaker` 2 / `smtp_breaker` 1 / `ml_breaker` 1 / `drift_detector` 1 —— P 型不可达**

- `sqlalchemy[asyncio]`（txt:16 / lock:343）、`asyncpg`（txt:17 / lock:57）、
  `fastapi`、`scipy`（txt:35 / lock:316）在交付形态下齐备；`docker-compose.yml`
  的 `DATABASE_URL` 用的是 `postgresql+asyncpg://`。
- 与第三十二批 celery_breaker 同族、方向一致：被「依赖已交付」挡住。
- `drift_detector.py:128` 的降级分支是 `self._approximate_ks_test(...)`（近似
  KS 检验），若可达则**同形性成立**（都返回 statistic/p_value/is_drift，但算法
  不同）会是本批第二个接线候选；但 scipy 已交付 ⇒ 不可达 ⇒ 判 P。

**`email_service.py:164` `_send_smtp` —— 分类器判 R，人工裁定 V**

分类器按「sleep + retry」把它粗判为 R（自恢复）。但函数末尾有
`raise last_exc`（L182-183）：重试耗尽后异常**向上传播**，
`send_password_reset_email` 的 `except Exception`（L132）再 `logger.exception`
+ `raise ValueError("重置邮件发送失败，请稍后重试")`。实测（E5）注入
`SMTPServerDisconnected` 后 `_send_smtp` **抛出** `SMTPException`。
⇒ 失败态（抛异常）与正常态（静默返回）**不同形**，不满足接线判据。
桶计数仍按分类器口径（R 不变），本条分歧在此登记。

**`logging_config.py:235` —— S 型**：日志设施**自身**启动失败（第二十七批
sentry.py #1 同型），且 warning 文案已显式自报「降级为仅控制台输出」，
`enable_file=False` 之后链路继续。**边界如实记账**：若同时 `LOG_CONSOLE=false`，
则该降级彻底无痕；修它属行为变更（不在 #35 接线范围）。

**`_schemas.py` 2 条 / `deps.py:184` —— G 型 fail-closed**：`_schemas.py:68`
解析异常 ⇒ 置 `None` 中性化（AUDIT-2026-10-06 P1-9 由裸 `pass` 改来的
fail-closed）；`deps.py:184` token 解码失败 ⇒ `return None` ⇒ 上层拒绝。
另：`_schemas.py:63` 的 `except ValueError: pass` 是**正常控制流**（域名不是
IP 格式 ⇒ 走后续域名分支），根本不是降级路径。

**两个 job_store 的 `_cleanup_expired` —— D 型**：混合输入实测（1 条脏
`created_at` + 2 条过期 + 1 条未过期）⇒ 脏条目只跳过自己，两条过期条目照常
清理、未过期条目保留（第二十九批混合输入纪律）。

### 4. 闸门与变异

- 新增 `TestP235Round13Batch33Wiring`（**11 条**）：15 处 handler 存在性 + 所属
  函数未漂移 + **块级反向钉**（14 条不得接线路径内禁现
  `record_silent_degradation`）+ location 完整字面量 + **ClamAV 同族互锁**
  （第十一批接线仍在）+ 同源结构钉（degradation 与 fire_forget 同走
  `app.core.metrics`）+ 运行时 E1/E2/E3/E4/E5 + 文档登记。
- 变异 **7 条**全部 RED-OK / 还原后 GREEN-OK（见
  `mutate_p2_35_round13_batch33_result.log`）：M1 删接线（2 红）/ M2 给同源
  失效路径接线（2 红）/ M3 location typo（1 红）/ M4 降级态改 `raise`
  —— 破坏同形性、反证接线判据（1 红）/ M5 `continue`→`break`（1 红）/
  M6 删 `raise last_exc`（1 红）/ M7 删节标题（1 红）。
- 变异见 `mutate_p2_35_round13_batch33_result.log`。
- **CI 10/10 success（含 backend-coverage）** ⇒ 第三十三批完整收口。

---

## 一之三十五、#35 X 桶第三十四批：1 接线（`observability._parse_detail_json`），W=99→100 / X=119→118

### 1. 挑簇口径（本批**再换信号**）

第三十三批用的「候选文件 basename 在裁定文档 0 次」口径**已耗尽**（剔除当批
12 个文件后剩余 0 条）。而且它这次是**反向失效**：

- `cache.py` / `reports.py` / `inference.py` 这类短名会被文档里**别处的同名串**
  命中（如 `api/v1/reports.py` 命中 `v1/reports.py`、`model_predict/inference.py`
  命中 `model_engine/inference.py`）⇒ 产生**假负**。

本批改用：**函数名级零记载 − 第二十至三十三批已处理簇**，并逐簇人工核对。
人工核对剔除掉两个大簇（它们函数名级都零记载，但早已整簇裁过）：

| 剔除的簇 | 条数 | 裁定出处 |
|---|---|---|
| `core/model_engine/predict.py` | 9 | 第十二批接线 3（§1.12）+ 第二十一批剩余 6 条全部裁定不接（§1.21） |
| `services/canary_fallback_monitor.py` | 5 | 第九批整簇裁过（§1.9） |

同向验证：`tasks/pdf_report.py` 的三个函数在文档中**确有记载**，故它不应进候选
（印证第三十三批「函数名级零记载只是粗排」的判断）。

### 2. 接线清单（1 处）

| location | 文件:行 | 降级语义 |
|---|---|---|
| `services.observability.aggregate.detail_json_parse_failed` | `app/services/observability/aggregate.py:38`（`_parse_detail_json`） | 审计详情 JSON 损坏 ⇒ 回退 `{}`，两个消费点都把它渲染成一条**真实记录**：flush 统计里是一条 `acquired=0` 的 0 值假记录（且 `totals` 被静默低估），AM 同步里是一条 `operation=unknown` / `duration_ms=0` 的假行 |

判据全部是可客断言的（无一条依赖「日志不够响」这类软理由）：

1. **同形性（源码明文）**：L37 就是
   `return _json_loads(detail_json) if detail_json else {}` ⇒
   **损坏**与「**本来就没有 detail**」返回完全相同的 `{}`，
   下游（`_fetch_recent_flushes` L509、`_fetch_am_sync_failures` L346）
   无从分辨。运行时实测：损坏行 `[0, 0, 0, 0, None]` == 无 detail 行
   `[0, 0, 0, 0, None]`（逐字段）。
2. **假数据（不是被跳过）**：脏条目**进入输出**，不是被 `continue` 跳过 ——
   这是与 D 型的分水岭（第三十二批 `user_data_service` 是「脏字段只跳过自己」）。
   实测混合输入 1 坏 + 2 好 + 1 空 ⇒ 输出 4 条，`totals.acquired` 只统计到 10
   （损坏条目的贡献被静默吞掉）。
3. **可达性（正向实测 + 对称于第二十一批）**：`OperationLog.detail` 是
   `Text, nullable=True`，且同表四列（`operator_role`/`action_type`/
   `target_type`/`ip_address`）都有长度 CHECK，**唯独 detail 没有任何 JSON
   合法性约束** ⇒ 非 JSON 文本可入库。运行时：`json.loads("{broken json")`
   抛 `JSONDecodeError`。**与第二十一批 scaler 相反**（那次是模型文件有意不入库
   ⇒ 不可达）。
4. **同族互锁**：同文件 `_fetch_lock_memory_stats`（L484）已于**第六批**接线
   （`services.observability.aggregate.lock_stats_unavailable`），语义完全相同
   ——「读失败 ⇒ 下面回填的 0 会被观测页当作真实数据展示」。本处不接即自相矛盾。

### 3. 不接线清单（11 条）

| 文件:行（函数） | 裁定 | 硬判据 |
|---|---|---|
| `app/services/observability/aggregate.py:484`（`_fetch_lock_memory_stats`） | **W 复核** | 第六批接线，location 字面量齐全 |
| `app/monitoring/dedup.py:95`（`should_send`） | **M** | 已有专用计数器 `alert_detail_parse_failed_total.inc(1, stage="dedup")`，**实测真涨** 0→1（第二十五批纪律：M 型裁定前必须实测计数器活着） |
| `app/monitoring/dedup.py:103`（`should_send`） | **S** | 它保护的是那个专用计数器本身，且该计数器走 `app.core.metrics`，与 `record_silent_degradation` **同源** ⇒ 接线即恒 0 假设施 |
| `app/core/model_engine/inference.py:348`（`_publish_to_prometheus`） | **P** | 九个 Gauge 全部定义在 `metrics.py`（L538-567）⇒ 交付形态齐备；唯一残留触发路径是「Gauge 被改名/删除」这类代码缺陷。附加同源理由（内部 `from app.core import metrics`） |
| `app/core/model_engine/inference.py:362`（`stop_persist`） | **K** | `CancelledError` 是预期控制流 |
| `app/core/kill_switch.py:109`（`_record_degraded`） | **S** | 可观测设施自身（`kill_switch_degraded_total`），与主判定路径同源 |
| `app/services/registry_auto_rollback.py:136` | **K** | `CancelledError` 预期 |
| `app/services/registry_auto_rollback.py:138` | **C** | 停止监控的清理路径，已有 `logger.warning(..., exc_info=True)` 自报 |
| `app/api/v1/admin.py:619`（`_stream_csv`） | **S** | 审计日志回填失败有 `logger.exception` + `log_id=` 定位键 ⇒ 服务端有可追溯痕迹 |
| `app/core/rate_limit.py:142`（`decorator`） | **F** | 回退到原始签名是**保守**行为（不是「未校验按已校验」的放行），且有 debug 自报 |
| `app/core/rate_limit.py:198`（`__call__`） | 正常控制流 | 限流正常生效 → 统一 429 响应，不是降级 |

### 4. 闸门与变异

- 新增 `TestP235Round13Batch34Wiring`（**13 条**）：12 处 handler 存在性 +
  所属函数未漂移 + **块级反向钉**（10 条不得接线路径内禁现
  `record_silent_degradation`）+ location 完整字面量 + **同族互锁**
  （第六批 `_fetch_lock_memory_stats` 仍在）+ 结构钉 E3（detail 列无 JSON
  约束）/ P 型前提钉（九个 Gauge 齐备）/ M 型形态钉（自研 Counter 的
  `inc(1, stage=...)`）+ 运行时 E1/E2/E3/E4/E5 + 文档登记。
- 变异 **7 条**全部 RED-OK / 还原后 GREEN-OK（见
  `mutate_p2_35_round13_batch34_result.log`）：M1 删接线（**4 红** ——
  location 钉 + 块级钉 + E5 计数）/ M2 location typo（2 红）/ M3 给同源失效
  路径接线（1 红）/ M4 降级态改 `raise` —— 破坏同形性、反证接线判据
  （3 红：E1/E2/E5）/ M5 给 detail 列加 JSON 约束 —— 移除可达性前提
  （1 红）/ M6 删节标题（1 红）/ M7 删同族互锁锚点（2 红）。
- 变异见 `mutate_p2_35_round13_batch34_result.log`。
- 受影响 19 个测试文件 504 passed。
- **CI 10/10 success**（含 backend-coverage）⇒ 第三十四批完整收口。

### 5. 本批结论一句话

10 个文件 12 条候选逐条实测后**接线 1 条**（`_parse_detail_json`），
桶计数 **W=100 / X=118**（总数 334 不变）。

---

## 一之三十六、#35 X 桶第三十五批：**0 接线**（8 文件 8 条全部不接），W=100 / X=118 不变

### 1. 挑簇：信号第三次更换（前两个口径相继退化）

| 口径 | 出处 | 失效方式 |
|---|---|---|
| basename 在文档 0 次 | 第三十三批 | **反向失效**：`cache.py`/`reports.py`/`inference.py` 等短名被文档别处同名串命中 ⇒ **假负**（第三十四批初耗尽） |
| 函数名级零记载 | 第三十四批 | **彻底退化**：本批实测 25 个候选函数名在三份审计文档全文命中数**全为 0** —— 文档只按 location 登记、从不按函数名登记 ⇒ 该信号已无区分力 |
| **location 登记表零收录** | **本批** | 候选文件是否从未出现在任何 `\| \`a.b.c\` \| \`path/x.py\` \|` 登记表行里（登记表共收录 22 个文件），再减去第二十至三十四批已处理簇 + 逐簇人工核对 |

本批命中 8 个文件 8 条。

### 2. 裁定表（全部不接）

| 候选 | 分类器 | 人工裁定 | 硬判据 |
|---|---|---|---|
| `api/v1/observability/__init__.py:228`（`cached_or_compute`） | S | **同形性不成立** | 降级态 `data` 是 **0 键 `{}`**；任何正常态（含真实空数据）都是固定 **6 键**结构化字典（`total_fired`/`total_acked`/`total_pending`/`response_time`/`by_severity`/`ack_rate`）⇒ **键集合可分辨** |
| `core/metrics.py:868`（`track_model_inference`） | S | **S + V** | 被保护的 `model_inference_total` / `model_inference_duration_seconds` 就定义在 `metrics.py` 本模块内（同源）；且业务异常在 `except` 里被 `raise` **照常外抛**（实测 `ValueError` 传播）⇒ 失败态对调用方可见 |
| `ml/canary_controller.py:235`（`_log_comparison`） | X | **死代码** | `CanaryController(` 在生产代码中**零实例化**；`_log_comparison` 唯一调用点只在本文件 L172 |
| `monitoring/escalation.py:59`（`_observe_escalation_latency`） | S | **S（同源）** | 可观测设施自身；`record_silent_degradation` 同走 `app.core.metrics` ⇒ 实测阻断后计数 **0→0** |
| `services/observability_service.py:135`（`_flush_loop`） | X | **死代码产物** | 唯一产物 `_flushed_buffer` 的消费者 `consume_flushed_logs` 生产中**零调用点**，已按 **RES-P1-004** 登记为有意保留的死缓冲区（`flush_to_db` 直接取 `_pending_logs` 绕过它）⇒ 循环故障不影响任何生产可见行为 |
| `services/risk_service.py:138`（`_schedule_warning_and_intervention`） | X | **P（内层全捕获）** | ① 唯一调用方 `assess_structured` 是 `async def` 且含 await ⇒ `ensure_future` 不抛；② `fire_forget_metrics` 模块级**无 app 依赖** ⇒ import 不抛；③ `register_task` → `record_scheduled` 自身内层 `except Exception` 全捕获。实测阻断 metrics 后仍不抛 |
| `services/risk_service_warning.py:136`（`_check_warning_trigger`） | X | **P（内层全捕获）** | `event_bus.publish` 自身内层 `except asyncio.QueueFull` 全捕获，且**已在第一批接线** `core.event_bus.publish` ⇒ 唯一真实失败路径既不外抛、也已被观测 |
| `tasks/anomaly_detection.py:140`（`_detect_impl`） | X | **P（跨进程）** | 跑在 `celery_worker` **独立容器**（`docker-compose.yml:175`，命令 `celery -A app.core.celery_app worker`）；`/metrics` 由 backend 容器暴露；全仓无 `PROMETHEUS_MULTIPROC_DIR` / `MultiProcessCollector` ⇒ 接线计数恒 0（第十五批 `celery_app` 同族） |

### 3. 一条方法论收获：同形性判据的**反面**用法

第三十四批 `_parse_detail_json` 是 `{}` == `{}`（逐字段同形）⇒ **接**；
本批 `cached_or_compute` 是 `{}` vs 6 键 ⇒ **不接**。
同一条判据在本项目里第一次以「反面对照」的方式被使用：
**判据的价值不只在于选出该接的，也在于排除不该接的** —— 只要键集合可分辨，
调用方就有机会察觉，就不满足 #35 的「静默」定义。

### 4. 第二十八批不可达形态的第二次实锤

第二十八批在 `fallback.py` 首次裁定「外层 `except` 存在但运行期不可达 ——
被调函数自身内层已 `except Exception` 全捕获、永不外抛」。
本批 `risk_service.py:138` 是**第二次**：挡住它的是
`fire_forget_metrics.record_scheduled` 的内层全捕获。
（§0 已立：给不可达路径接线＝制造「看起来有降级观测、实际永不触发」的假设施。）

### 5. 闸门与读数

- 新增 `TestP235Round13Batch35Declined`（**12 条**）：8 处存在性 + 所属函数
  未漂移 + **全量反向钉**（8 条 handler 内一律禁现 `record_silent_degradation`）
  + 桶计数不变钉 + 运行时 E1~E8 + 文档登记。
- 变异见 `mutate_p2_35_round13_batch35_result.log`。

### 6. 本批结论一句话

8 个文件 8 条候选逐条实测后**全部不接**，**本批 0 接线**；
桶计数 **W=100 / X=118**（总数 334 不变）。

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

0. **本轮累计状态**（二十七批）：当前棘轮
   **W=97 / X=119 / P=15**（总数 334 不变；R 4→3）。
   第二十七批增量：**W +0 / X -0**（纯裁定批：sentry.py 6 条 +
   api/v1/metrics.py 5 条，两簇均**首次逐条书面裁定**——sentry 此前
   只在「scheduler 里的 Sentry 调用点」语境被裁过、本体从未裁过，
   metrics.py 的 5 个 `_set_*` 采集器同样从未裁过。L103
   `init_sentry` SDK import 失败为 S 型（可观测性设施自身启动失败，
   且 `sentry-sdk[fastapi]` 是 requirements.txt:50 顶层依赖 +
   requirements.lock:323 硬锁 2.71.0 + Dockerfile:100 pin 清单显式
   含，生产镜像构建期必装、运行期不可达）；L148/L163 S 型（自报通道
   自身失败，调用方 scheduler 还有第二层 try/except）；L27/L36/L47
   `_extract_status_code` 三条为 D 型（上游脏数据，`pass` 后穷举下一
   路径）。metrics.py 五条 `_set_*` 全为 S 型（采集失败不改 HTTP 状态码、
   旧 gauge 留存比归零更保守；文件内 `_set_redis_metrics` 的
   `redis_circuit_state.set(2)` 是唯一「失败编码进指标值」的正确范式，
   已加互锁钉）。**运行时实证附带发现**：`init_sentry` 的 handler
   `return` 不抛 ⇒ `record_step_sync(fatal=False)` 记 `ok` ⇒
   `/health/startup` 无法区分「已初始化」与「SDK 导不进来」，已转独立
   待办信号。分类器现场重算 11 条全判 S（非 X），桶计数不变）；
   第二十六批增量：**W +0 / X -0**（纯裁定批：loading.py 7 条候选里
   3 条为首次书面裁定——L244 `_incr_model_fallback` 指标 inc 失败 S 型
   （指标采集通道自身失败，日志侧盲区已由 debug→warning 升级补齐；该
   函数是第二批两次接线的 M 型理由来源，其自身失败只改变曲线形状不改
   返回值）；L288/L294 `preload` PermissionError/OSError 为 **V/M 混合
   （消费点已接线）**——`predict_structured` 只捕获 (FileNotFoundError,
   ValueError)，该异常向上传播，主消费方 `risk_service_assessment` 已接
   `structured_predict_fallback` 且返回 dict 显式带 `error` 与
   `heuristic_fallback`，预热期再接会重复计数。另 4 条系第七/十九批已裁，
   本批只做跨批记账一致性复核。机器分类维持六条 X + 一条 S，桶计数不变）；
   第二十五批增量：**W +0 / X -0**（纯裁定批：scheduler.py 5 条新候选
   ——L81 `_notify_warning` 重试 except 为 M 型（失败重试 2 次后 error
   日志 + 专用计数器 `warning_notify_failed_total` **运行时实测真涨
   +1** + Sentry + `return False`，调用方检查 `ok` 汇总上报）；
   L108 指标 inc 失败、L129 Sentry capture_exception 失败为 S 型
   （自报通道自身失败，主通道已先触发）；L1134/L1150 产物目录/文件
   resolve 失败为 F 型（AUDIT-P0-3：宁可整个清理中止也不带残缺保护集
   继续删，`is_active = True` 保守跳过删除）。分类器现场重算确认
   五条均不在 X=119 内，故桶计数不变）；
   第二十四批增量：**W +1 / X -0 / R -1**（ws.py 13 条候选：1 处
   接线 `core.ws.pubsub_loop_crashed`——订阅循环崩溃重启窗口内
   （≥1s，Redis 持续故障时长期存在）其它 worker 发布的消息被
   Redis 丢弃而发布方已返回成功，消息永久丢失；原分类器判 R
   （sleep+restart 自愈）本批改判：自愈只恢复订阅不恢复消息，
   丢失的是外部输入，与第六批 inference persist R 型先例（下轮
   从进程内状态重生、无外部输入丢失）本质不同。12 处不接线：
   S 2 + M 1（第十六批已裁复核）+ K 2 + C 2 + D 2 + V 3）；
   第二十三批增量：**W +0 / X -0**（纯裁定批：validation_engine 5 条
   逐条实测后全部裁定不接线/复核维持——L422/L512 为第十三批已裁 V 型
   维持，L147/L207/L271 为分类器 D 定型（脏数据探测）的首次书面裁定；
   无实记录 X→W，桶计数不变）；
   第二十二批增量：**W +0 / X -0**（纯裁定批：health 1 +
   auto_rollback 5 + pii_crypto 4 共 10 条 X 桶候选逐条实测后全部
   裁定不接线，8 条已定型项复核维持；**连带修复一对自出生即死的
   专用计数器**——`_bump_lock_counter` / `_bump_takeover_counter`
   原用 prometheus_client 的 `.labels().inc()`，而本仓 Counter 是
   自研类（`inc(**labels)`），每次 AttributeError 被 except 吞掉，
   计数器自 e120ce3 引入起恒 0，第二批起两条 M 型裁定的「已有专用
   计数器」前提从未成立；已改自研 API 并补运行时回归测试）；
   第二十一批增量：**W +0 / X -0**（纯裁定批：predict.py 剩余 6 条
   逐条存在性实测后全部裁定不接线——scaler 路径双重外部阻断不可达
   （默认配置 v1.23 + pkl 有意不入库）、模型加载/lite 4 条 V 型显式、
   2 条第十二批已裁项实测复核维持；连带修复 L147 注释漂移）；
   第二十批增量：**W +1 / X -1**（1 处实记录 X→W：告警历史 detail
   JSON 解析失败 → 空壳 item 照常入列表，告警内容静默丢失；另裁定
   不接线 14 处，留 X 桶）；
   第十九批增量：**W +0 / X -0**（纯裁定批：scheduler 7 +
   model_engine/loading 4 + config 2 共 13 条逐条实证后全部裁定不接线，
   无实记录 X→W，桶计数不变）；
   第十八批增量：W +3 / X -3（3 处实记录 X→W：金丝雀检查失败洗白 /
   训练任务 Redis 列表回退 / 训练任务 Redis 更新失败；另裁定不接线
   13 处，留 X 桶）；
   第十七批增量：W +3 / X -3（3 处实记录 X→W：健康监控快照刷新失败 /
   HTTP 指标记录失败 / 自动回退检查失败；另裁定不接线 12 处，留 X 桶）；
   第十六批增量：W +4 / X -4（4 处实记录 X→W：ws 本进程投递失败 /
   ws 订阅消息处理失败 / 影子推理器不可用 / 影子对拍异常；
   另裁定不接线 9 处，留 X 桶）；
   第十五批增量：W +3 / X -3（3 处实记录 X→W；另裁定不接线 12 处，留 X 桶）；
   第十四批增量：W +4 / X -4（4 处实记录 X→W，无桶间迁移）；
   第十三批增量：W +5 / X -5（5 处实记录 X→W，无桶间迁移）；
   第十二批增量：W +3 / X -3（3 处实记录 X→W，无桶间迁移）；
   第十一批增量：W +3（2 处实记录 X→W + 1 处探针记录 P→W，首见探针接线）、X -2、P -1。
   已裁定跳过 35（第一批 2 + 第二批 11 + 第三批 1 + 第四批 13 + 第六批 8）之外，
   第七/八/九/十/十一批另有 M/S/critical/设计内/调用方可见/既存落点，均在各
   「一之X」节记账，不进 35。逐批明细见各节；本节为结账口径，历史快照不回改。
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
