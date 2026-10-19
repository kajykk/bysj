# P2 ROUND_17 审计：止血开关收口（租户封禁覆盖度的机器不变式）

- **基线**：HEAD `9b8fb25`（CI 7/7 全绿），工作区 `git diff` = 0 字节。
- **上游**：《CODE_REVIEW_FIX_2026-10-20》§五.1（WS 无自动化用例）、§五.2（缺租户行 fail-open 无计数）自记的两个缺口。
- **范围**：只做租户封禁这一条线；未改 M/L 清单、未改生产预测主路径、未改 fail-open 决策本身。

## 一、鉴权入口盘点（2026-10-20 实测，AST 口径）

「入口」定义：函数自身语句里直接调用以下任一 API ——
`decode_token` / `create_access_token` / `create_refresh_token` /
`create_password_reset_token`。这就是"正在发放凭证或兑换凭证"的机器可检特征。

| # | 入口 | 类型 | 封禁校验 | 覆盖证据 |
|---|---|---|---|---|
| 1 | `deps.get_current_user` | HTTP 依赖（所有已认证请求） | ✅ | `test_rev_s7_tenant_suspend.py` + 结构闸门 |
| 2 | `ws.websocket_endpoint` | WS handshake | ✅ | `tests/unit/test_websocket_auth.py::test_websocket_rejects_suspended_tenant` + 结构闸门 |
| 3 | `AuthService.login` | 签发 access/refresh | ✅ | `test_rev_s7` + 结构闸门 |
| 4 | `AuthService.refresh` | 续期 | ✅ | `test_rev_s7` + 结构闸门 |
| 5 | `AuthService.request_password_reset` | 签发重置令牌（邮件） | ✅（本轮新增） | `test_p2_41_round17_auth_gate.py` 行为用例 |
| 6 | `AuthService.reset_password` | 兑换重置令牌改密 | ✅（本轮新增） | 同上 |
| 7 | `AuthService.logout` | 撤销会话 | 豁免：封禁期间仍应允许主动退出 | 结构闸门（exempt + 理由） |
| 8 | `deps._role_for_request` | 角色声明助手 | 豁免：仅在 `get_current_user` 成功后调用，只取 role 不单独放行 | 结构闸门 |
| 9 | `deps._resolve_current_user` | 委托 `get_current_user` | 豁免（人工登记） | `test_manual_exempt_entries_have_reason_and_exist` |
| 10 | `uploads._optional_resolve_user` | 委托 `get_current_user` | 豁免（人工登记） | 同上 |
| 11 | `deps.require_sa_or_admin` | Grafana 平台 SA / 管理员 JWT | 豁免：SA 为平台凭据；JWT 路径委托 | 同上 |
| 12 | `AuthService.change_password` | 改密（已认证路由） | 豁免：路由挂 `Depends(get_current_user)`，封禁已在 HTTP 入口拒绝 | 同上 |
| — | `AuthService.register` | 注册（不签发会话） | 不适用：无 token 操作，注册后登录仍被封 | 本文档登记（不进发现集） |
| — | `tasks/scheduler.py` 周期任务 | 平台级后台任务 | 不适用：不代用户鉴权、无用户令牌 | 本文档登记 |

> 入口 1–8 由 AST 自动发现并强制登记；9–12 为"发现集之外但语义上是鉴权链一环"的人工登记，
> 同样要求写理由且函数必须存在。

## 二、T1：缺租户行的 fail-open 显式化

**决策未变**：`tenants` 缺行仍返回 `False`（未暂停），不因异常部署拒绝全站。

**新增可观测性**：
- 每次命中记
  `silent_degradation_total{location="core.tenant_status.missing_tenant",tenant_id="<id>"}`；
- 保留 warning 日志（含 tenant_id）。

**指标 schema 变更**：`silent_degradation_total` 的 labelnames 由
`("location",)` 扩为 `("location", "tenant_id")`；`record_silent_degradation`
新增可选关键字 `tenant_id`，非租户上下文落空串。这样做的原因是
`Counter.inc` 要求 label 集合精确匹配 —— 不给默认值会让全仓既有调用点
（100+ 处）同时失效。同步改了 2 个直调点（`core/cache.py`、`tests/test_p2_09_round9.py`）
与 1 条源码字面量断言。

**门槛用例**（`tests/test_p2_41_round17_tenant_status.py`）：
- 缺行 ⇒ `False` 且该 (location, tenant_id) 计数 +1；
- active / suspended 行 ⇒ 判定正确且**不**计入缺行降级；
- `tenant_id=None` ⇒ `False` 且不计降级（不是"缺行"）。

**变异**：删掉 `record_silent_degradation(...)` 调用 ⇒
`test_missing_tenant_counts_with_tenant_label` RED-OK。

## 三、T2：覆盖度自检闸门

`tests/test_p2_41_round17_auth_gate.py` 的四条不变式：

1. **发现 = 登记**：AST 扫描 `backend/app` 全部模块（跳过嵌套函数），
   发现集必须与 `REGISTRY` 键完全相等。新增 token 操作入口不登记 ⇒ 红。
2. **enforced 必须有校验**：函数自身语句中必须存在 `is_tenant_suspended` 调用
   （AST `Call` 节点，不查字符串）。
3. **先核验后兑现**：校验调用行号必须早于任何 `create_*` 签发或
   `password_hash` 写入；判据自带合成样本自证（早/晚两种都被测到）。
4. **豁免必须诚实**：exempt 条目必须有非空理由，且不得出现封禁调用。

**变异**：
- 移除 `AuthService.refresh` 的校验 ⇒ `test_enforced_entries_have_ban_check` RED-OK；
- 新增一个未登记的 `decode_token` 函数 ⇒
  `test_every_token_operation_function_is_registered` RED-OK。

## 四、读数（2026-10-20 实测）

- 新增门禁基线：`12 passed`（T1 4 条 + T2 结构 4 条 + 自证 2 条 + 行为 2 条）。
- 变异脚本：`tests/tools/mutate_p2_41_round17.py` →
  `RED-OK 3/3`、`final GREEN-OK=True`、`residual-clean=True`、`integrity-clean=True`；
  日志见 `backend/tests/tools/mutate_p2_41_round17_result.log`。
- 扩展回归集（新增门禁 + #35 棘轮 + 全称注释棘轮 + exposition + cache + degradation +
  WS 单测 + S7 用例）：`316 passed, 0 failed`（128s）。
- 连带棘轮：`other_raise 349→350`（`reset_password` 新增一条"租户已暂停" ValueError）；
  `metrics.py` 因加 3 行注释/标签，Batch34 的 `track_model_inference` 位置 868→871；
  `auth_service.logout` 位置 466→497。均已同步 `test_p2_11_round11.py` 与
  `P2_11_ROUND11_AUDIT.md`。桶计数（W/X/S/P/R）不变。

## 五、边界与未覆盖（显式记账）

1. **已建立的 WS 连接不会因封禁被主动断开**：校验发生在 handshake；
   停用只保证新连接/重连被拒，存量长连接要等自然断开。若要求"封禁即踢线"，
   需要在 suspend 端点回调 `ws_manager` 主动关闭，属独立改动。
2. **`register` 未加封禁**：它不签发会话，注册后登录仍被拒；是否禁止向暂停租户
   写入新用户属产品决策，本轮不改。
3. **后台周期任务照常运行**：`daily_risk_scan`、`stale_warning_reminder` 等是平台级
   任务，不代用户鉴权；"暂停租户是否还应收提醒"是另一个需求。
4. **发现集只覆盖"凭证签发/兑换"族**：若未来引入 API Key、OAuth 等不走这四个
   token API 的入口，闸门抓不到，需要扩展 `TOKEN_OPS` 或增加发现规则。
5. **缺租户行仍 fail-open**：本轮只加可观测性与用例，未改决策（任务边界要求）。
