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

0. **本轮累计状态**（十二批，结账时点 `478d1cc` + 第十二批）：当前棘轮
   **W=73 / X=142 / P=15**（总数 334 不变）。
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
