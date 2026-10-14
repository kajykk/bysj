# P2 第十二轮审计清单（#34 全量收敛 + #33 余量分批 + #35 余量 + #36 余量 + #32 收尾）

- 生成时间：2026-10-14（HEAD 以 `a0b68f1` 为基线；扫描在**无变异窗口**内生成）
- 扫描器：`backend/scripts/scan_p2_11_audit.py`（#33/#35 口径沿用）+ #34 精确判据脚本
- 闸门：`backend/tests/test_p2_12_round12.py`
- 回退实验：`backend/scripts/rollback_p2_12.py` → `backend/scripts/rollback_p2_12_result.log`

---

## 〇、开工前置：两个必须先结的账（均已完成）

### 1. 1291 / 1292 差 1 条 —— **已结清**

| 取证 | 结果 |
|---|---|
| `git show 0e7eb4f:frontend/src/utils/p2CsvSsot.test.ts` 的 `it(` 数 | **2** |
| `git show ac58f97:frontend/src/utils/p2CsvSsot.test.ts` 的 `it(` 数 | **3** |
| 差异内容 | `it('accepts numbers (MisclassifiedTable score column)')` |
| 引入提交 | `28d531b`（第十轮补，02:12），提交信息自述"前端 67+1=68 passed（3 文件）" |

**结论**：第十轮全量读数 1291 测于 `0e7eb4f`（该提交**之前**），第十一轮基线
`ac58f97`（03:12）已包含 `28d531b` ⇒ 1292。**两轮数字都对，差别是测量时点**，
不是丢失用例、不是动态生成、不是抖动。以 1292 为起点正确。

### 2. 偶发失败红线 —— 基线已立

本轮开工跑的前端全量（JSON reporter 落盘 `backend/scripts/vitest_round12_baseline.json`）：

    numTotalTests: 1306  passed: 1302  failed: 0  pending: 4  files: 103

**`UserReportsPage.nullable` 本轮未复现**。按纪律：本轮后续任何一次全量若再红同一位置，
按真问题查，不判抖动；单文件隔离重跑 → 全量重跑 → 两次结果都落盘 → 记账写明以哪次为准。

---

## 一、#34 全量：统一错误方言（本轮主菜）

### 1.1 先修正第十一轮的分类口径（重要）

第十一轮审计用启发式（`detail=` 源码含 `str(e)`/`sql`/`token` 等特征词）扫出
**28 处"疑似 detail 泄漏"**。本轮改用**精确判据**（AST：`HTTPException` 的 `detail`
实参里出现异常对象被格式化）重扫，实测：

| 判据 | 数量 | 说明 |
|---|---|---|
| 精确判据：异常文本出网（`str(exc)` / f-string 插值 exc） | **33** | 真泄漏类 |
| 第十一轮启发式报的 28 处 | 28 | **既漏报又过报**：漏掉 auth/canary/experiment 等 27 处真泄漏；把 `deps.py` 的"未提供认证Token"等正当用户可读文案算成泄漏 |

⇒ **口径差异如实记账**：28（启发式）与 33（精确）不是矛盾，是判据精度不同。
本节所有收敛动作以精确判据的 33 处为准。

### 1.2 基础设施

**`ServiceError(client_message, internal_detail)`**（`app/core/exceptions.py`）：

- `to_dict()` **只出 `client_message`**，绝不含 `internal_detail` —— 硬约束 1；
- `internal_detail` 只进日志，由 `_service_error_handler` 以 `logger.error` 落盘，
  **格式与 `record_audit` 对齐**：`detail={"tenant_id": …, "no_request": …}`
  （`log_payload()` 方法，见 `app/core/audit.py`），**不自创字段**；
- `tenant_id` 为**必填关键字参数**（sentinel 模式，与 `record_audit` 同口径），
  漏传 `TypeError`（带 `match="tenant_id"` 的断言把守）。

**末道脱敏中间件**（`app/core/middlewares.py::error_sanitizer_middleware`）：

- 只处理 4xx/5xx 的 JSON 响应（2xx 零开销），流式响应不缓冲；
- 判据是**确定性特征清单**（13 条正则：Traceback / Python 源码行 / SQL 语句 /
  psycopg·sqlalchemy·asyncpg / Errno / 连接类异常 / 绝对路径 / 约束违反文案），
  **不用"看起来像内部信息"的启发式**（会把正当文案误伤）；
- 命中即替换为通用文案，并 `logger.warning` + `error_sanitized_total` 计数留痕；
- 解析失败（非 JSON / 流式）**原样放行**，不猜不抛；
- 挂载位置：request_id **之内**（脱敏日志带 request_id）、路由/异常处理器**之外**
  （覆盖未捕获异常与限流 429 的响应体）。

### 1.3 收敛结果（按族，不按文件顺序）

| 族 | 处数 | 改法 |
|---|---|---|
| A：服务层主动抛的 `ValueError`（业务消息即客户端文案） | 26 | `ServiceError(str(exc), tenant_id=…)` —— 保持既有契约（测试与前端依赖这些文案） |
| B：`FileNotFoundError` 等非业务异常 | 5 | 同上（消息本身已是用户可读的 404 语义） |
| C：`f"…: {exc}"` 拼异常原文 | 2 | `ServiceError("固定文案", internal_detail=str(exc), code=…)` —— **真正堵住泄漏** |

合计 **33 处全部收敛**，精确判据复扫 **0 处**。

**样板间**：`review.py` 6 处（`handle/escalate/close crisis_event` ×3 + assign/review ×3），
先改透一处 → 写脱敏前后对照测试 → 回退变异，形成范式后再批量。

### 1.4 正当明文登记（`RETENTION_REGISTRY.md`）

- **`RES-P2-034-01`**：服务层业务校验消息明文豁免。**边界写死**：只覆盖服务层主动抛的
  `ValueError`；`except Exception` / `FileNotFoundError` 路径禁止套用，必须走
  `internal_detail` 形态。边界由闸门 `test_no_exception_text_in_http_exception_detail`
  把守。
- **`RES-P2-034-02`**：末道脱敏的确定性特征清单登记，含"补特征必须同时加
  '正当文案不被误伤'反向用例"的复核条件。

### 1.5 连带发现（两个，都已固化）

1. **批量脚本不能统一写 `tenant_id=current_user.tenant_id`**：`auth.py` 的
   register/refresh/change_password/request_password_reset/reset_password、
   `canary.py` 的 4 个平台管理员端点、`experiment.py` 的 import/evaluate/compare
   **都没有 `current_user`**（用 `_` 占位或无登录态）。批量写统一串 → 11 处
   `NameError`。**是作用域闸门逐个抓出来的**（本轮它扩容到覆盖 13 个文件后，
   每跑一次就报出下一批）。修法：AST 按"所在函数是否有 current_user 参数"分流，
   无则写 `tenant_id=None` + 注释说明平台级操作。
2. **`import` 插入必须用 AST 定位**：我第一版用"最后一个顶层 import 行"启发式，
   **三次误插进函数内延迟 import 之后**（`admin.py` / `canary.py` / `registry.py`），
   其中 `admin.py` 直接 `IndentationError`。改用 AST（`tree.body` 里的
   `Import`/`ImportFrom` 节点，函数内 import 天然不在 `tree.body`）后一次做对。
   这与第十一轮"import 掉进多行括号块"是同族的第四/五次事故。

### 1.6 实测读数

- 精确判据复扫：**0 处**异常文本出网（起点 33）。
- 新增闸门 `tests/test_p2_12_round12.py`：**16 passed**
  （ServiceError 契约 4 + 末道脱敏 6 + 泄漏收敛 4 + 作用域 1 + 扫描器自证 2）。
- 受影响既有测试：**139 passed**（crisis_event_state_machine / review_api /
  auth_flow / auth_p0p1 / auth_response_contract / review_service / canary_api /
  crisis_audit / review_assign_auth / uploads_auth）。
- 回退对照实验：**9 项全 RED-OK / GREEN-OK**，日志 `rollback_p2_12_result.log`，
  每条含**变异强度自评**。

## 二、第二批补遗（独立复核接手后，2026-10-14）

### 2.1 #34 漏网 3 处（精确判据扫描器范围缺口）

- 现象：test_no_exception_text_in_http_exception_detail 红，报 admin.py:404 + counselor.py:262/341。
  审计 1.3 节写的 33 处全部收敛失实：精确判据扫描时没扫这两个文件（扫描器文件集与闸门文件集不一致）。
- 形态：全是 A 族，按范式转 ServiceError(str(exc), status_code=409/422, tenant_id=current_user.tenant_id)。
  首次出现非默认 status 的 ServiceError；handler 按 exc.status_code 原样出码，契约不变。
- 实际总量修正：33 + 3 = 36 处，现复扫 0。1.3 节数字不改（历史快照），以本节为准。

### 2.2 #33 第二批：counselor.py 3 处

- list_users / get_user_detail / list_consultation_records 改调 record_audit：
  tenant 与邻近服务调用同口径取 get_request_tenant_id(request)；dict detail 直接传；ip 改由 helper 取。
- 构造点 54 到 51。棘轮同步：AFTER_BATCH2 = 51，counselor.py 进入已迁移文件表 + ip 硬约束表。
- 连带修：TestSourceStructure 3 处断言放宽为（OperationLog 或 record_audit 在源码中）；
  TestP234RaiseClassificationSynced 的 P2_11 文档 token 已过期，在 P2_11 文档末尾追加同步块。
- 服务层剩余 51 处多无 request/tenant 上下文，需逐点穿参或记账，留第三批。

### 2.3 本节实测读数

- test_p2_12_round12.py：16 passed（修前 15+1 红）。
- upload_counselor_audit_log + p2_11 + p2_12 同跑：55 passed。
- import app.api.v1.admin/counselor 烟测通过。

### 2.4 第三批（#33：gdpr/auth/uploads/user_upload/user_risk，共 7 处；#34：gdpr 4 处）

- #34：判据补强覆盖同函数变量中转（`msg = str(exc)` 再 `detail=msg`），先红后绿：gdpr.py 223/224（自删路径 401/404）+ 339/340（管理删除 404/400）改 ServiceError，总量 36→38，复扫 0。P2_11 同步块追加 211/335/37。
- #33：gdpr 2（export/admin 删除；后者 anonymized_at 显式 str，helper 内 dumps 无 default=str）、auth 助手 1（改 async，3 调用点加 await；reset 未登录态 tenant 显式 None）、uploads 1、user_upload 2、user_risk 1。构造点 51→44，AFTER_BATCH3=44 同步。
- 删 import 清理：5 文件去 OperationLog/json/get_real_client_ip 不用导入（均逐个计数确认零残留引用）。auth.py 的 get_real_client_ip 保留（168/197 另有调用）。

### 2.5 第四批（#33：+7 处→44；#35：loading 3 处；#36：2 页；判据补强）

- #33：gdpr 2（export/admin 删除；anonymized_at 显式 str）、auth 助手 1（改 async，3 调用点加 await）、uploads 1、user_upload 2、user_risk 1。构造点 51→44，AFTER_BATCH3=44；8 文件进入已迁移表 + ip 硬约束表。
- #34 判据补强：同函数变量中转（msg = str(exc) 再 detail=msg）纳入，结果先红（gdpr 4 处：自删 401/404 + 管理删除 404/400）后绿。总量 36→38，复扫 0；P2_11 同步块追加 211/335/37。
- #35：core/model_engine/loading.py 3 处真降级接线（preload.missing_file / preload.failed / adapter.pkl_fallback）；ImportError 探测点（preload:275）按规则跳过。棘轮为 >= 式，保持 8 不动，新位置登记于此。
- #36：useTemplatesData + useInterventionData-history 改由 useListQuery；对外名零改动（loadData/pageError/handlePageChange；historyRows/historyError/loadHistory 等）；lazy 语义保持（immediate:false + 原 once 门闩/onMounted）。迁移钉 2 文件 5 用例全绿，其中竞态用例做过真实变异（绕过 run 裸调 → 红 [20] 覆盖 [30] → 恢复绿）。
- 实测：后端三套件 55 passed（第一批）/ 本批 affected+gates 94 passed；前端迁移钉 5 passed + useListQuery 15（含）；vue-tsc 0 错；BASELINE 0 保持。

### 2.6 终轮读数与偶发红线复查

- 前端全量第一次：105 files / 1306 passed / 1 failed / 4 skipped，红仍是 UserReportsPage.nullable 同一位置（collect 期 STACK_TRACE_ERROR，无应用栈）。按红线当真问题查：该文件 94 行自述 element-plus 首挂编译慢近 30s 超时阈值；隔离重跑 8/8；与本批 2 个新文件无共享导入。结论：worker 负载下收集期资源耗尽，非产品回归（与第十一轮同签名事件为同一机制）。
- 前端全量第二次：105 files / 1307 passed / 0 failed / 4 skipped。两次 JSON 均落盘（vitest12b2.json），以第二次为准，第一次如实保留在此。
- 后端：affected+gates 94 passed；test_p2_12 19 passed；回退驱动重跑 9/9；vue-tsc 0 错，BASELINE 0 保持。

### 2.7 第五批（#33：+7 处→37；SSOT 根因修复：tenant 落列）

- #33：admin 2（update_model 平台 None / crisis 导出透传 tenant 范围）、alerts 2（ack 平台 None / silenced 系统三 None）、helpers 1（系统三 None，message 截断保留）、analytics 1、reports 1。构造点 44→37，AFTER_BATCH4=37。
- **SSOT 根因修复（本批最重要）**：record_audit 文档声称“该表无租户列”，但 Phase 5 已加 tenant_id 非空列。修前所有已迁移行列恒为默认租户 1，detail 与列各说各话（tenant_admin 的 SEC-FIX 归属要求被静默丢弃）。修复：tenant 落列，None→DEFAULT_TENANT_ID（与列默认值同值，None 调用方零行为变化）。变异验证：stash 修复后新闸门红（assert 1 == 7，正是 bug 本体）→ 恢复绿。
- 门禁配套：正文 ip 表改 AST 提取（正则嵌套括号截断曾致 admin 导出漏检假红）；新增 test_system_paths_use_explicit_none（webhook 三 None 锁死）；helpers 的 role 以签名默认 system 为准（调用处透传形参，不锁字面量）。另修测试内 docstring 转义 SyntaxWarning。
- 实测：10 文件 affected+gates 195 passed；4 迁移钉 11 passed；vue-tsc 0 错。
- 注：useSilencesData / useCrisisEventsData 的 #36 迁移及配套钉由并行工作完成，本节仅记录与其合并验证的结果，归属以各自提交为准。

### 2.8 第六批（#33：+3 处→34，服务层穿参打样；#35：+4；#36：+2→9/12；#32 确认）

- #33：warning_service 3 处（mark_read/mark_all_read/update_setting）改 record_audit，服务方法新增 `request/tenant_id` 可选关键字（API 端点传入 request + current_user.tenant_id；任务与旧测试不传则记 None/平台默认，28 个既有单测零改动全绿）。user_warning.py 3 端点加 Request 穿入。构造点 37→34，AFTER_BATCH5=34。
- #35：reports 2（pdf-job redis→local 显式回退 / job 合并失败少数据）+ predict 2（复核任务调度丢失 / 危机事件落库失败，最高危静默丢失）。棘轮为 >= 式，新位置登记于此。
- #36：useCounselorWarningsData（副作用搬迁：取前清留包裹层，取后清走 onSuccess）+ UserWarningsPage（无权限短路留包裹层）。迁移钉 2 文件 4 用例全绿，counselor 钉做过真实变异（绕过 run 裸调 → 双红 → 恢复绿）。剩余 3 页（AdminAlerts/CounselorReviewList/UserAssessments，均已有 STATE 做 URL 持久化，只差竞态守卫）记账留后续。
- #32：事实锁（4 定义处 + 双标签）本批 affected 全绿，无变化；维持只裁定不合并。
- 教训：同套件并发双跑会卡死（sqlite 争用，~5 分钟无输出；kill 后单跑 8s 过）。以后本地只单跑，落盘看结果。

### 2.9 本批（#33 服务层穿参 34→24；#35 +4；#36 最后 3 页 → 12/12）

> 批次编号说明：本节接续 2.8（提示词口径称其为第四批），提交后由 CI `total_count` 实数佐证。

- **#33 第六批（服务层穿参）10 处，构造点 34 → 24**，棘轮 `AFTER_BATCH6 = 24` 同步，
  4 个文件进入已迁移表：
  - `review_service` 2：`escalate_review`（tenant 已有，新增 `request` 可选关键字）、
    `_write_crisis_audit_log`（新增 `request`/`tenant_id`，三个危机处置方法透传）；
    `review.py` 4 个端点加 `request=request`。
  - `intervention_service` 2：`complete_task` / `feedback_task`。
    ⚠️ **detail 口径变化（记账）**：原为裸字符串（`task_id=1, scheduled_date=...`），
    改走 `record_audit` 后统一为 JSON 对象（新增 `feedback_score` 字段）。
  - `counselor_service_binding` 6：`get_or_create_bind_code` / `refresh_bind_code` /
    `bind_by_code` / `unbind`（后者在 `counselor.py` 2 端点 + `user_data.py` 2 端点穿参，
    `unbind_counselor` 端点新增 `Request` 形参）。detail 同样由裸字符串转 JSON 对象，
    枚举状态走新增的 `_status_value()` 静态助手（避免 `str(枚举)` 出 `BindingStatus.ACTIVE`）。
  - `tenant_admin` 4 处**不动**（目标租户归属语义，record_audit 落列后需逐点确认归属再迁），
    本批只记账，与 2.8 节口径一致。
- **#35：4 处真降级接线**（跳过 ImportError 探测 / `Sentry capture_*` 自身失败 / 指标上报失败）：
  `risk_service_assessment`（模型失败→启发式打分，**风险分是干预触发依据**）、
  `drift_monitoring_service`（版本解析失败→告警退出自动回滚闭环）、
  `shadow_comparison_service`（对拍统计落盘失败→激活校验缺依据）、
  `validation.py` 任务存储**写路径**降级内存（多实例下轮询打到别的实例查不到）。
  实测 `record_silent_degradation(` 调用点 16 → **20**；棘轮为 `>=` 式（`BASELINE=8`）未改数，
  新位置登记进 `P2_11_ROUND11_AUDIT.md` 四·节追加表，并新增
  `test_batch6_locations_wired_in_code_and_doc` 做**源码 + 文档双向**核对
  （只查文档会漏"登记了没接线"，只查源码会漏"接了没登记"）。
- **#36：最后 3 页完成（12/12）**：`AdminAlertsPage`（tab 双数据源 history/archive，
  fetcher 内分支选端点）、`UserAssessmentsPage`（`rawItems` + sessionStorage 快照改由
  `onSuccess` 写，过期响应不再污染详情页）、`CounselorReviewListPage`（本地 page ref，
  `setPage` 写本地状态；`loadReviews` 保留为 `run` 别名）。三页均 `immediate:false`
  + 原 `onMounted` 保留，对外名零改动；筛选/重置/切 tab 改走 `search()`
  （先作废在途请求再回第 1 页），翻页路径按 M2 同型修法补 `await`。

#### 2.9.1 实测读数

| 项 | 读数 |
|---|---|
| 前端全量 | **112 files / 1326 passed / 4 skipped / 0 failed** |
| vue-tsc（`typecheck:baseline` stdin 模式） | **0 错**（基线 0） |
| 迁移钉（本批 3 文件） | **9 passed** |
| #33 受影响既有 9 文件（api/test_review_assign_auth 等 + services + unit） | **241 passed** |
| #35 受影响（risk/shadow/validation/drift 等 9 文件） | **35 + 18 + 106 passed** |
| `test_p2_11_round11.py` | **23 passed**（含新增双向断言） |
| `test_p2_12_round12.py` | 含在上述 35 内，全绿 |

#### 2.9.2 本批三次真实变异（均红 → 恢复绿）

1. `useListQuery.ts` 摘掉竞态守卫（`if false return`）→ AdminAlerts + UserWarnings 两个
   竞态用例红（旧页 `[20]` 覆盖新页 `[30]`）→ 恢复绿。
2. `UserAssessmentsPage.vue` 把 `writeAssessmentDetailCache` 搬回 fetcher 内 → 第三个用例红
   （过期响应把旧页写进 sessionStorage，`CACHE_KEY` 命中旧 id）→ 恢复绿。
3. `CounselorReviewListPage.vue` 摘掉 `setPage` 里的 `page.value = value` → 重置筛选后
   请求仍带 `page=3`（应为 1）→ 恢复绿。
4. 后端两处：`counselor_service_binding` 回退为手写 `OperationLog` 构造 → 棘轮红
   （24 → 实际 25，且"已迁移文件不得再手写"断言同红）；`drift_monitoring_service` 的
   location 字面量改掉 → 双向核对断言红。

#### 2.9.3 未验证 / 待办（如实记账）

- 后端**全量本地未跑**（约 37 分钟，历轮同例），由 CI 兜底；本地只跑 affected + 闸门。
- #33 余 **24** 处：服务层剩余簇（`counselor_service_group/consultation/warning` 各 2）+
  任务层（`tasks/scheduler.py`、`anomaly_detection.py`）+ `monitoring/*`
  （notifier/dedup_lock/escalation/am_sync）+ `admin_service_*` 3 + `tenant_admin` 4
  （目标租户归属语义，需逐点确认）+ `gdpr_service_anonymize` 1 + `user_intervention.py` 1。
- #35 余量未重扫（本批只做 4 处真降级）；`api/v1/validation.py` 的读路径降级（get/update）
  同型但未接线，留后续（写路径丢失后果最重，先做写）。
- #34 / #32 本批未动（#32 维持只裁定不合并）。
- `tests/test_iss02_validation_engine.py` 在本机沙箱下需 `--basetemp` 才能跑：
  默认 tmpdir 的 GC（`pytest.pathlib.rm_rf`）会触发环境侧的 bulk-delete guard 直接
  `SystemExit`，与产品代码无关；CI 环境无此 guard。

### 2.10 CI 红后修复（跨文件闸门 pin 了旧形参名）

- 现象：push `1c21a99` 后 CI `total_count=10`，其中 **backend-coverage 失败 1 条** ——
  `tests/test_p2_10_round10.py::TestP232BERoles::test_constants_actually_used`，
  断言 `operator_role=USER_ROLE_COUNSELOR` 存在于 `counselor_service_binding.py`
  与 `operator_role=USER_ROLE_ADMIN if is_admin else USER_ROLE_COUNSELOR` 存在于
  `review_service.py`。
- 根因（正是提示词铁律预告的那一类）：本批把这两处审计改为调 `record_audit`，
  helper 的形参名是 `actor_role`，**旧断言 pin 的是实现形参名而非行为**，
  迁移后恒假。其他 6756 条全绿，说明不是产品回归。
- 修法：断言改为 pin「角色取自 `USER_ROLE_*` 常量」这一行为，
  用正则同时兼容 `actor_role=` / `operator_role=` 两种形态，并保留失败时的
  可定位文案。
- 变异验证：把 binding 的 `actor_role=USER_ROLE_COUNSELOR` 临时改回裸字面量
  `"counselor"` → 该闸门与 `test_no_bare_role_literals_in_scope` 同时红
  → 恢复后 10 passed，证明放宽后仍敏感。
- 教训（记账）：**affected 集合不能只按调用图取**——本项目里闸门是
  **跨文件源码文本断言**，凡改动被闸门点名的文件（即使只是审计调用换 helper），
  都要把 `tests/test_p2_0*.py` / `test_p2_1*.py` 全列入 affected。
  本批漏了 `test_p2_10_round10.py`，以后默认全跑 `tests/test_p2_*.py`。
- 复跑读数：全部 P2 闸门 `test_p2_09`~`test_p2_12` + `test_p2_31`/`test_p2_32`
  **126 passed**；`tests/api`+`tests/services`+`tests/unit` **1795 passed /
  10 skipped / 0 failed**。

---

## 六、第六批（提示词 `docs/ROUND_12_BATCH6_PROMPT.md`）

> 三项任务：① detail-JSON 下游重验（最高优先级）；② #33 余 24 收敛；
> ③ #35 收尾（候选清单逐条裁定归零）。

### 6.1 detail-JSON 下游重验（第五批口径变化的影响面）

第五批把 intervention / binding 的审计 detail 由裸字符串改为 JSON 对象。
本批用 AST 枚举 `app/` 下**全部** `OperationLog.detail` 消费点（14 个模块），
逐点确认按 JSON 对象重验通过：

| 模块 | 读取数 | 消费形态 | 重验结论 |
|---|---|---|---|
| `api/v1/alerts/__init__.py` | 6 | parse（含 SQL contains 兜底） | ✅ JSON 对象；裸串历史行走 contains 分支 |
| `monitoring/dedup.py` | 1 | parse | ✅ |
| `monitoring/escalation.py` | 10 | parse（alert_fired 行） | ✅ 迁移后写入侧即 JSON 对象 |
| `services/mttr_service.py` | 2 | parse | ✅ |
| `services/observability/aggregate.py` | 8 | parse（`_parse_detail_json`） | ✅ 带 except 兜底 |
| `services/observability/query.py` | 8 | sql | ✅ 只进 SQL 表达式 |
| `tasks/alerts.py` | 1 | parse | ✅ |
| `tasks/scheduler.py` | 2 | parse（`user_file_upload` 的 url） | ✅ 早就是 JSON 串 |
| `api/v1/tenant_audit.py` / `content_governance.py` / `ops_dashboard.py` / `admin_service_log.py` | 2/1/2/1 | passthrough / slice 预览 | ✅ 原样透出，无解析假设 |
| `tasks/anomaly_detection.py` | 3 | 写入侧（`AnomalyFinding.detail` JSON 串→dict） | ✅ 非 OperationLog 消费点（见 6.5.2 记账） |

新增闸门 `TestAuditDetailJsonDownstream`（5 条断言，含 2 个运行时用例）：
1. **写入侧**：`record_audit` 的 detail 实参禁止字符串/f-string（扫描器自检 ≥30 个点）；
2. **消费侧清单**：14 模块读取数钉死，变化即红 → 强制重新核对；
3. **解析侧兜底**：7 个 parse 模块的 `json.loads` 必须在 try 内（历史裸串行不会炸链路）；
4. **运行时**：真跑 `complete_task` / 绑定码 / 解绑，按 JSON 对象读回。

**发现并修复的问题**：`record_audit` 原实现 `json.dumps(payload)` 无 `default=str`，
而 scheduler 滞留提醒迁移前显式依赖该容忍（注释：「序列化失败会让本条以外的
滞留预警全部丢失」）。不加回则测试用 MagicMock 值触发 TypeError（`tests/tasks/
test_scheduler.py` 3 failed 实锤）。已在 helper 内补 `default=str` 并在文档字符串
说明理由（审计写永不因序列化失败拖垮业务流）。

### 6.2 #33 余 24 收敛：`OperationLog(` 手写构造点 **24 → 0**

| 簇 | 处数 | 文件 | 备注 |
|---|---|---|---|
| counselor 服务 | 6 | `counselor_service_warning` 2 / `_consultation` 2 / `_group` 2 | 方法加 `request`/`tenant_id` 可选关键字；`counselor.py` 6 端点穿参 |
| admin_service | 4 | `admin_service_config` / `_threshold` / `_template`（4 处） | `admin.py` 4 端点穿参；⚠️ 两处签名原有 `*,` 与新加 `*,` 相邻 → 合并（见 6.5.3） |
| monitoring | 4 | `am_sync` / `dedup_lock` / `notifier` / `escalation` | 系统内部写，`request=None` + 注释 |
| 任务层 | 2 | `scheduler` / `anomaly_detection` | `request=None`；anomaly 的 detail 先 `json.loads` 还原 dict（失败退 `{"raw": …}`） |
| gdpr | 1 | `gdpr_service_anonymize` | 归属语义：审计行主体是**被匿名化用户** → tenant 默认取 `user.tenant_id`（不随发起删除的管理员） |
| user_intervention | 1 | `_log_intervention_op` helper | 改 async；5 个调用点补 `await` + 穿 request；3 个端点新增 `Request` 形参 |
| **目标租户簇** | 6 | `tenant_admin` 4 + `tenant_branding` 1 + `tenant_export` 1 | 见 6.3 |

棘轮 `AFTER_BATCH6 = 0`（`test_p2_11_round11.py`），17 个文件进入「已迁移不得再手写」清单。
`record_audit` 调用点总数 **63**（AST 实测，不含 helper 本体）。

**⚠️ 本批两次踩到「import 烟测不查名字绑定」**（记忆中已记账的坑，仍复发）：
`tenant_admin.py` 与 `scheduler.py`/`pdf_report.py`/`_common.py` 加了调用但漏加导入，
`import app.xxx` 全绿而运行时报 `NameError`。已在收工前用 AST 全仓复查
（`record_audit` / `record_silent_degradation` 两个 helper 的调用点 vs 导入绑定），
全部 OK。**教训**：改完必须跑「调用点⊆导入绑定」的 AST 核查，不能只做 import 烟测。

### 6.3 目标租户归属语义（SEC-FIX 回归闸门）

`tenant_admin` 4 处 + `tenant_branding` / `tenant_export` 共 6 处的归属对应关系
（提示词要求「迁之前先写清归属从列 X 搬到列 Y」）：

- **列 tenant_id**：迁移前手写 `tenant_id=<目标租户 id>`（create 用 `tenant.id`，
  其余用路径参数 `tenant_id`）；迁移后同样显式传目标租户 id。helper 仅在 None 时
  落 `DEFAULT_TENANT_ID`，而目标租户主键恒非 None → **落列值与迁移前完全一致**。
- **绝不许改传 `current_user.tenant_id`**：这些端点的操作者是平台管理员（自己的
  租户是平台默认租户 1），传操作者租户会把归属从目标租户搬回操作者租户，
  目标租户管理员的 tenant-audit 可见性直接断裂，且**没有任何既有测试会红**
（它们只断言 200/结构）。
- `tenant_branding` 迁移前传 `current_user.tenant_id`，但该端点经
  `require_role_tenant_scoped("admin") + _assert_tenant_owned_by` 双重校验，
  操作者租户恒等于目标租户，两者同值；迁移后统一传目标租户，语义不变且不再依赖
  「操作者恰好拥有该租户」这一前提。
- **detail 口径变化**：6 处均由裸字符串改 JSON 对象
  （`f"name=x; code=y"` → `{"name": …, "code": …}`）。前端审计页
  （`AdminOperationLogsPage` / `AdminAuditLogsPage`）用 `JSON.stringify(row)` 整体
  渲染 detail 字符串，展示形态从分号串变为 JSON 串——与第五批以来所有已迁 action
  一致，非新问题。全仓检索无测试断言这些 action 的 detail 字面量。

新增闸门 `TestTargetTenantAttribution`（源码侧 + 运行时侧双钉）：
- 源码侧：6 文件的 record_audit 调用的 `tenant_id` 实参必须是目标租户表达式
  （`tenant.id` / `tenant_id`），不得是 `current_user.tenant_id`；
- 运行时侧：平台管理员创建租户后，落库行 `tenant_id == 新租户 id` 且 `!= 1`，
  `operator_id == 1`（操作者信息保留），detail 可按 JSON 对象读回。
  测试先种平台租户 id=1 占位（不种则新租户直接拿 id=1，目标与操作者数值相同，
  断言失效——这个坑在首跑时实锤）。

### 6.4 #35 收尾：候选清单逐条裁定（清单归零）

口径与第十一轮 `scan_silent_except` 一致（except 无 raise 且体内有
logger.*/pass/continue；本批扫描器把日志级从 debug/warning 扩到全级，
故总数 318 > 第十一轮 243，差异已记账）。新增两个工具
（`tests/tools/scan_p2_35_batch6.py` + `classify_p2_35_batch6.py`，
产物 JSON 落盘同目录）：

- **扣除已接线改为认 `record_silent_degradation(`**：第十一轮的 `has_metric`
  只认 `inc/labels` 直调，看不到本仓 SSOT helper 的间接接线，导致「已接线 3」
  严重低报（实际 25+2 直调）。
- **ImportError 特性探测 16 处分桶**（沿用第十一轮裁定：不计降级债）。

**逐条裁定桶计数（334 = 318 真降级候选 + 16 探测）**：

| 桶 | 计数 | 裁定理由 |
|---|---|---|
| W 已接线 | 27 | handler 内有 record_silent_degradation（25）或直调 inc（2，第十一轮 cache.py 风格） |
| P 特性探测 | 16 | ImportError/ModuleNotFoundError，不计降级债 |
| S 自报失败 | 36 | metrics/sentry/otel/gauge 上报自身失败（第五批裁定的推广：`inc failed`/`指标不可用` 等文本特征） |
| D 脏数据探测 | 22 | JSONDecodeError/InvalidTag/ValueError/TypeError 单条解析跳过，数据本来就是坏的 |
| C 清理路径 | 7 | aclose/close/stop 失败，不影响业务语义 |
| H 检查型 | 6 | health check 返回 False——不健康**就是**返回值，信号即数据 |
| K 任务取消 | 11 | CancelledError，预期控制流 |
| R 自恢复 | 4 | handler 内 sleep+continue/restart，瞬时降级会自愈 |
| M 已有专用计数器 | 6 | 同函数已有 `warning_notify_failed_total` / `model_fallback_count` gauge，不重复接通用计数器 |
| G fail-closed 安全 | 8 | token 解码/URL 安全/MIME 校验失败→拒绝，安全方向不是降级 |
| V 显式失败上报 | 2 | handler 把状态写成 `status="failed"`，调用方可见，非静默 |
| F 保守 fail-safe | 2 | 宁可少清理/不发（AUDIT-P0-3 同型） |
| **X 真降级留档** | **187** | 确属真降级但本批未接，全量清单见 JSON 产物，后续批待接 |

**本批新接线 6 处**（都挑「漏预警/误删/用户不可见」方向，且**原本无任何计数**）：

| location | 文件 | 降级语义 |
|---|---|---|
| `core.model_engine.predict.text_ml_all_unavailable` | `core/model_engine/predict.py` | 文本 ML 全挂→启发式分（**无 `_incr_fallback` 计数**，与 structured/lite 不同） |
| `core.model_engine.predict.physiological_model_not_found` | 同上 | 生理模型缺失→启发式分（无计数） |
| `core.model_engine.predict.physiological_prediction_failed` | 同上 | 生理推理失败→启发式分（无计数） |
| `tasks.scheduler.upload_reference_query_failed` | `tasks/scheduler.py` | 引用查询失败→仅按过期时间清理，**仍被引用的文件可能被误删** |
| `tasks.pdf_report.save_pdf_bytes_failed` | `tasks/pdf_report.py` | PDF 字节存 Redis 失败=用户拿不到报告（`reports.py` 同型点的任务侧孪生） |
| `api.model_predict._common.assessment_save_schedule_failed` | `api/v1/model_predict/_common.py` | fire-and-forget 调度失败=评估结果永久丢失（第三批已接两处的同型） |

`record_silent_degradation(` 调用点 **16 → 26**（18 个文件）；棘轮为 `>=` 式（BASELINE=8）未改数。
新增闸门 `test_batch6_bucket_counts_pinned` 把上表 13 个桶计数钉死——
清单再变化（新增/接线/误分类）即红，强制重跑工具并更新本文档。
X 桶 187 条不是「没处置」：它是显式的「真降级，留待后续批」记账，
全量清单（file:line:function:handled）在 `classify_p2_35_batch6_result.json`。

#### 6.4.1 本批四次真实变异（均红 → 恢复绿）

1. `tenant_admin.py` 的 `tenant_id=tenant.id` 临时改 `current_user.tenant_id`
   → 归属闸门源码侧 + 运行时侧**同时红** → 恢复绿。
2. `intervention_service.py` 的 detail 临时改回裸字符串 f-string
   → 写入侧断言 + 运行时应同时红 → 恢复绿。
3. `admin_service_log.py` 临时新增一个 `row.detail` 读取点
   → 消费侧清单闸门红（1 → 2）→ 恢复绿。
4. `observability/aggregate.py` 临时摘掉 `_parse_detail_json` 的 try 兜底
   → 解析侧兜底断言红 → 恢复绿。

### 6.5 未验证 / 待办（如实记账）

1. **后端全量本地未跑**（约 37 分钟，历轮同例）：本地跑了 `tests/api` +
   `tests/services` + `tests/unit` **1795 passed / 10 skipped / 0 failed**、
   全部 P2 闸门、affected 既有测试（#33 九文件 241 + admin/counselor/gdpr/
   monitoring/scheduler/pdf 等约 900 条）；根目录其余文件由 CI 兜底。
2. **#33 已归零**（构造点 0），但 `record_audit` 调用点 62 处中，
   「服务层方法加 request/tenant_id 可选关键字」的打样只覆盖到本批 17 文件；
   后续如新增审计写点，按同打样接入。
3. **#35 X 桶 187 条待接**（真降级留档），Top 簇：`model_engine/loading.py` 9、
   `auto_rollback_service.py` 9、`api/v1/validation.py` 读路径 7、
   `api/v1/silences.py` AM 同步 6、`api/v1/alerts/__init__.py` 6、
   `monitoring/dedup_lock.py` Redis→SQL 降级 4、`core/cache.py` 4。
4. **`anomaly_detection.py` 清单数 1 → 3 的口径说明**：迁移后该函数内
   `finding.detail`（AnomalyFinding dataclass 字段）读取从 1 处变 3 处
   （try/except/回退各一），函数 docstring 含 "OperationLog" 字样故被扫描器计入；
   已复核确认这三处**不是** OperationLog.detail 消费点，清单注释写明。
5. **`default=str` 加进 `record_audit`**：这让所有审计写获得序列化容忍，
   与 scheduler 原注释的意图一致；副作用是异常值会静默退化成字符串
   （如 `"<MagicMock ...>"`）——可接受（审计详情本就允许降级可读性），已记账。
6. `tests/test_iss02_validation_engine.py` 本机仍需 `--basetemp`
   （pytest tmpdir GC 触发环境 bulk-delete guard，与产品代码无关）。
7. #34 / #32 本批未动（#32 维持只裁定不合并）。
