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
