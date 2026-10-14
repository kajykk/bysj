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
- **X 桶余 173 条**（180 - 本批记账跳过的 2 - 已接 7 = 173 待接；跳过 2 条仍留
  X 桶）。下一批候选（按审计 6.5 Top 簇续）：`core/model_engine/predict.py` 10、
  `core/model_engine/loading.py` 8、`services/auto_rollback_service.py` 7、
  `tasks/scheduler.py` 7、`api/v1/silences.py` 6、`api/v1/alerts/__init__.py` 6、
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

1. **桶计数改钉（W 27→34 / X 187→180）**：只影响 `test_batch6_bucket_counts_pinned`
   的 expected 与 P2_11 附录；总数 334 不变证明无候选丢失/新增。X 桶下降 7 的
   去向全部可逐条指认（1.1 表），无静默蒸发。
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
