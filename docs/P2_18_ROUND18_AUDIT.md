# ROUND_18 审计：审查报告 M 批 1（认证会话 + 复核状态机）

> 上游：`outputs/CODE_REVIEW_2026-10-20.md` §2.1 / §2.2。
> 范围：M1 / M2 / M6 / M7 / M8 / M9 六条，逐条**先实测再动手**。

## 〇、开工前置与逐条裁定

- 基线：`HEAD == origin/main == 5c60b05`（提示词写的 `9b8fb25` 是 ROUND_17 之前的基线，
  5c60b05 已把 ROUND_17 合并进来），`git diff` = **0 字节**。
  `git status` 报 75 行 M，逐文件 `git hash-object` vs `git rev-parse HEAD:<path>` 比对后，
  真实差异只有 7 个运行时产物（`leak_delta_*.json` / `pool*.json` /
  `verify_p2_35_batch34_result.json`），按仓库惯例不入库。
- 裁定表（**不允许默认按报告开工**）：

| 编号 | 审查报告结论 | 本轮实测（改前） | 裁定 |
|---|---|---|---|
| M1 | `/auth/refresh` 响应体回传 refresh_token | `api/v1/auth.py:243` 仍是 `return ok(tokens)`；`TokenResponse` 仍声明该字段 | **仍存在** |
| M2 | WS 建连不校验 jti 撤销 | `core/ws.py:418-440` 只有 decode + type + sub；全文件 `is_token_revoked` **0 命中** | **仍存在** |
| M6 | `created_by` 类型漂移 | `api/v1/validation.py:289-293` 转 `int`；写入 `:413` 是 `str()`；消费 `:501 / :533 / :557` 比 `str()` | **仍存在** |
| M7 | `resolve` 无行锁、无审计 | `services/review_service.py:293-322`（改前）普通 SELECT、无 `record_audit`、直接 commit | **仍存在** |
| M8 | 分配复核不校验受派人 | `services/review_service.py:257-291`（改前）直接 `task.assigned_to = counselor_id`；API `review.py:398-411` 无校验 | **仍存在** |
| M9 | 预警升级无幂等/状态前置 | `services/counselor_service_warning.py:225-262`（改前）无 `is_handled` 分支，每次调用一条审计 | **仍存在** |
| M5 | admin 下载无租户校验 | `uploads.py` admin 分支已有 `tenant_id` 比对（S3 落地） | 已修复，本轮不做 |
| M3 | 租户封禁失效 | 已升为 S7 并修复（ROUND_17 又补了入口闸门） | 已修复，本轮不做 |
| M4 | 请求头决定租户归属 | 已降级为 L21（原结论不成立） | 转出，本轮不做 |

- **需修正描述一条**：M8 原文建议"角色不满足返回 400，非咨询师即拒"。实际实现把
  `admin / super_admin` 列入允许集合 —— 分配端点自己的文档写明"管理员不传
  `assignee_id` 则接管给自己"，只认 `counselor` 会把这条既有行为改成 400。
  本轮判据改为"**无处置权限的角色（`role=user`）被拒**"，并把该取舍写进服务层 docstring。

## 一、逐条修复与判据

### T1（M1）refresh 响应体剥离 refresh_token

- 做法：`TokenResponse` 删除 `refresh_token` 字段（**强制点在这里**，FastAPI 按
  response_model 过滤多余键）；处理函数同时只返回 `access_token` / `token_type`。
  Cookie 仍是唯一载体（`_set_refresh_cookie` 不变）。
- 兼容实测：`grep -rn refresh_token frontend/src` 命中 18 处，全部是"Cookie 管理 /
  logout 载荷 / 测试断言"，**无一处读取 refresh 响应体的该字段**；
  `frontend/src/api/auth.ts:21` 的响应类型只有 `access_token`。
- 判据（`tests/test_p2_42_round18_refresh_body.py`）：
  1. 真实 register → login → refresh，`set(data) == {"access_token", "token_type"}`；
  2. OpenAPI 中 `TokenResponse.properties` 不再含该键（防有人把字段加回模型，
     以 `null` 形式重新暴露键名）；
  3. 反向对照：同一用例断言 Cookie 仍被轮换成新值。

### T2（M2）WS 握手校验 jti 撤销

- 做法：`core/ws.py` 在 decode 之后、查库之前加 jti 撤销检查；
  `CacheUnavailableError` ⇒ 关闭码 **4503**（与 HTTP 侧 503 同语义，fail-closed）；
  无 `jti` 的 token 跳过（与 `deps.py` 的 `if jti:` 同构）。
- 判据（`tests/unit/test_websocket_auth.py` 追加 3 条）：
  1. `create_access_token` 签发 → `revoke_token`（登出端点调用的同一原语）→
     真实 `websocket_endpoint` ⇒ `(4001, "Token已被撤销")`；
  2. 反向对照：同路径未撤销的 jti ⇒ 连接放行；
  3. 基础设施不可用 ⇒ `(4503, "认证服务暂时不可用，请稍后重试")`。
  第 1 条只把缓存后端切到内存（`_get_redis_url → None`，单进程部署形态），
  **不替换** `is_token_revoked` —— 缺陷就在"少调一次撤销检查"，替身会抹掉它。

### T3（M6）created_by 统一字符串口径

- 做法：`_deserialize_dict` 对 `created_by` 不再转 `int`，按字符串保留
  （bytes 走 `decode()`），与写入侧 `str(current_user.id)` 对齐。
- 判据（`tests/test_p2_43_round18_validation_created_by.py`）：
  1. `_serialize → _deserialize_dict` 往返后是 `"5"`，且端点判据
     `!= str(5)` 为 False；
  2. 走**真实** `ValidationJobStore`（create / get / list_jobs），只把外部 Redis
     换成内存字典替身：刚创建的任务在详情与列表里对该用户可见；
  3. bytes 输入同样归一为字符串；反向对照：别的用户看这条任务仍是"不存在"。

### T4（M7）resolve 行锁 + 审计 + 409

- 做法：
  1. 新增 `_locked_review_stmt(review_id)`：主键 `SELECT ... FOR UPDATE`，
     租户归属由同事务 `_ensure_review_in_tenant` 先行校验（复用 `assign_review` 的
     豁免理由，避免 JOIN 连带锁 users 行）；
  2. 状态冲突抛 `ReviewStateConflict(ValueError)`，API 映射 **409**；
  3. `record_audit(action="review.resolved")`，detail 记 `resolved_by` /
     `previous_status` / `resolution_note_chars` —— **不落备注原文**（临床内容不进审计表）。
- 判据（`tests/test_p2_44_round18_review_state.py`）：
  1. 编译真实加锁语句（PostgreSQL 方言）断言含 `FOR UPDATE`；
  2. spy 断言 `resolve_review` 确实调用 `_locked_review_stmt`（防"helper 留在文件里不用"）；
  3. 审计行落库且不含备注原文；4. 二次 resolve 抛 `ReviewStateConflict`、审计仍只有 1 条、
     首次结论未被覆盖；5. 跨租户 resolve 仍按 `not found` 拒绝。
- **诚实边界**：测试库是 SQLite，`FOR UPDATE` 在 SQLite 上是 no-op，双会话无法复现
  "后写覆盖"。因此并发判据是"语句带锁 + 调用链走该语句"的结构闸门，
  **不声称**在单测里验证了 PostgreSQL 的锁语义。

### T5（M8）受派人校验

- 做法：新增 `_ensure_assignee`，四道判据：存在 / 同租户（None 视为默认租户）/
  角色 ∈ {counselor, admin, super_admin} / `status == active`；不满足抛 `ValueError`（400）。
- 判据：存在性、普通用户、跨租户、停用四种各一条用例；反向对照：同租户咨询师
  正常分配成功；失败后任务仍是 `pending`（没被锁成 `in_review`）。

### T6（M9）预警升级幂等与状态前置

- 做法：`escalate_warning` 改 `SELECT ... FOR UPDATE` 取行；`is_handled` 时：
  - `handle_action == escalated` ⇒ 幂等返回 True，**不写第二条审计、不覆盖首次原因**；
  - 其它动作（`ignored` / `handled`）⇒ 返回 False 并告警日志，原结论保持。
- 判据：首次升级落库 + 1 条审计；重复升级幂等（原因不被覆盖、审计仍 1 条）；
  `ignored → escalated` 被拒（审计 0 条 `warning_escalate`）；反向对照：
  非本人预警、 不存在的预警仍返回 False。

## 二、变异读数

脚本：`backend/tests/tools/mutate_p2_42_round18.py`，
日志：`backend/tests/tools/mutate_p2_42_round18_result.log`（已 `git add -f`）。

| 变异 | 翻转的实现 | 结果 | 打红的用例 |
|---|---|---|---|
| T1 | 把 `refresh_token` 加回 `TokenResponse` | RED-OK（2 项） | `exposes_only_access_token` / `schema_does_not_declare` |
| T2 | `if revoked:` → `if False:` | RED-OK（1 项） | `rejects_jti_revoked_after_logout` |
| T3 | `created_by` 转回 `int` | RED-OK（3 项） | `keeps_created_by_as_str` / `decodes_created_by_bytes` / `redis_mode_job_visible` |
| T4a | `_locked_review_stmt` 去掉 `with_for_update()` | RED-OK（1 项） | `locked_statement_compiles_with_for_update` |
| T4b | 整段删除 `record_audit(...)` | RED-OK（2 项） | `writes_audit_without_clinical_note_text` / `second_resolve...` |
| T5 | 删除 `_ensure_assignee` 调用 | RED-OK（4 项） | 四种非法受派人各一条 |
| T6 | 删除 `is_handled` 幂等/状态前置分支 | RED-OK（2 项） | `escalate_twice_is_idempotent` / `escalate_after_ignore` |

- 基线未变异：`27 passed`；收尾还原：`residual_clean=True`、`final_green=True`。
- 关于 T1 的变异点：强制点在响应模型而非处理函数 —— 处理函数回退到 `ok(tokens)`
  时闸门仍绿，属"模型兜底生效"，不是假绿（模型被改回才会红）。

## 三、连带修复与契约变更（有意为之，非"改历史读数"）

1. **三处既有断言按新契约反向重写**（原断言把缺陷写成了契约）：
   - `tests/api/test_auth_flow.py`（原 `assert "refresh_token" in body["data"]`）；
   - `tests/api/test_auth_p0p1.py`（原 `assert refresh_data["refresh_token"]`）；
   - `tests/api/test_p0_p1_regressions.py`（同上）。
   三处都改为"响应体不含该键 + Cookie 已轮换"，并注明 M1。
2. **既有 WS 用例改缓存后端**：`test_ws_accepts_access_token` 用真实 token（带 jti），
   在"Redis 配了但连不上"的环境下会被新的 fail-closed 判成 4503 —— 这不是缺陷，
   是该用例与本轮判据的环境条件冲突。用例改走内存后端（单进程形态），
   fail-closed 由新增用例单独把守。
3. `api/v1/auth.py` 的 `ServiceError` 导入位置越过 `app.services`，ruff I001；
   本轮顺手排序（纯 lint，无行为变化）。

## 四、棘轮同步（改了源码就必须同步读数）

- #35 桶计数：**G 7→8，总数 340→341**（`websocket_endpoint` 撤销检查不可用 ⇒ 4503
  属 fail-closed 拒绝，不是降级）；其余桶不变。重扫产物
  `tests/tools/scan_p2_35_batch6_result.json` / `classify_p2_35_batch6_result.json` 已更新。
- #34 raise 分类：`HTTPException=214` 不变；**`other_raise=354`**（350→354，
  `_ensure_assignee` 的 4 处 ValueError）；**`ServiceError=38`**（37→38，
  review 端点把状态冲突映射 409 的那一处）。
- #36 位置漂移：`api/v1/validation.py::_execute_validation` 的 handler **478→481**，
  `TestP235Round13Batch37Wiring.CANDIDATES` 同步。
- 全称注释棘轮：本轮新增注释最初有 3 行触发（"永远查不到" / "原实现只有"×2），
  已改写为等义表述，**净增 0**。

## 五、未验证与边界

- **PostgreSQL 行锁未在真实 PG 下压测**：单测只证明语句带 `FOR UPDATE` 且调用链走它。
- M7 审计**有意**不记处置备注原文，只记长度；若后续要求"审计可还原完整处置"，
  需另立字段并做加密/授权设计。
- M8 允许 admin / super_admin 受派（与分配端点"管理员自取"的既有行为一致）；
  报告原文"非咨询师一律拒"属**描述需修正**。
- WS 撤销检查对无 jti 的 token 跳过（与 HTTP 侧同构）；现网 token 由 `_build_token`
  自动带 `jti=uuid4().hex`，故实际不会跳过。
- M1 属**破坏性契约变更**：仓库内前端不消费该字段；若有外部第三方客户端依赖
  refresh 响应体里的 `refresh_token`，升级后会拿不到。
- 未跑 37 分钟全量套件，以 CI 为准。
