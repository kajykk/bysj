# ROUND_24 审计 · 分页排序确定性：从 2 处修复扩成全仓闸门

- 基线：HEAD `85a7850`（23b 收尾，CI 10/10）
- 上游记账：`docs/P2_23B_FRONTEND_AUDIT.md` §七「同型风险：全仓另有 10+ 处单键分页，本轮不动」
- 本轮产出：AST 闸门 + 白名单 + 15 处次级键 + 6 条行为回归 + 5 组变异见证

---

## 一、判据（为什么必须是 AST）

判据的本质是 `order_by(...)` 的 **args 结构**：有几个排序键、分别是什么列、
有没有唯一列做 tie-break，以及这个 statement 是否真的接了分页。

- 字符串匹配认不出 `stmt = stmt.offset(...)` 这种**拆分形态**
  （`user_data_service.get_history` 就是这种写法：`order_by` 与 `offset` 相隔数行）；
- 字符串匹配也认不出多行 `order_by(\n  A.created_at.desc(),\n)`；
- 字符串匹配会命中注释与 docstring 里的示例代码。

判定（`backend/tests/tools/pagination_order_lint.py`）：

```
违规 = order_by 的 args 含「非唯一时间列」(created_at)
     且 不含次级键 (id / pk)
     且 该 statement 接了 .offset（真分页）或 .limit（单页截断）
```

**为什么 limit 也纳入**：`limit(N)` 没有第二页，不存在"跨页重复/漏行"；
但"取到的是哪 N 条"在 `created_at` 并列时由 DB 决定（N 的边界可能落在并列组中间）。
因此它不自动放行，而是必须**逐条裁定**——要么补次级键，要么进白名单并写明
"单页 top-N、无跨页语义"。这正是提示词预判的「约 10 处取最新」。

**为什么无 offset/limit 的不判违规**：纯"取最新一条"没有跨页语义。
若把它算违规，白名单会腐烂成"到处豁免"，闸门就失去意义。

---

## 二、盘点实数（与提示词 22/9 的差异已逐项对齐）

| 口径 | 数值 |
|---|---|
| 被扫 `.py` 文件 | **268** |
| 含非唯一时间列的 `order_by` 站点 | **32** |
| 其中带 `.offset` 的真分页 | **18**（本轮修 15，原有次级键 3） |
| 其中只带 `.limit` 的单页截断 | **11**（10 处入白名单，1 处原有次级键：`core/seed.py:873`） |
| 无分页子句 | **3**（`crisis_export` / `risk_service_export` / `admin_service_log.export_operation_logs`） |
| 白名单外违规（修前，按本轮判据回算） | **25**（15 真分页 + 10 单页截断） |
| 白名单外违规（修后） | **0** |

### 与提示词盘点的对齐

- 提示词 **9 处强分页**：全部命中（`tenant_audit:68/140`、`monitoring:437/259`、
  `content_service:153`、`canary:95`、`admin_service_config:30`、
  `counselor_service_consultation:144`、`intervention_service:223`）。
- 提示词 **3 处中等**：`user_data_service:437/:476` 确认为真分页（拆分形态，见 §三）；
  `content_governance:377`、`ops_dashboard:284` 确认为**单页 limit**（无 offset）⇒ 白名单。
- 提示词 **22 处（字符串口径）** vs 本轮 **32 处（AST 口径）**：多出的 10 处来自
  ①多行 `order_by`（`content_service.get_recommendations` ×2、`user_data_service` ×2）；
  ②`asc` 方向（`content_governance.list_pending_content`）；
  ③`order_by` 作用于变量而非直接链（`admin_service_log._query_logs`）；
  ④提示词清单未列但同属分页的 `content_service.list_contents`、
  `counselor_service_warning.list_warnings`、`warning_service.list_warnings`。
  **字符串口径会漏掉这些形态**——这是本轮坚持 AST 的直接理由。

---

## 三、T2 裁定表（3 处中等风险逐读）

| 位置（修前行号） | 裁定 | 依据 |
|---|---|---|
| `services/user_data_service.py:437` | **是真分页** ⇒ 已补次级键 | `stmt = (...order_by(StructuredAssessment.created_at.desc()))` 与 `stmt.offset(offset).limit(page_size)` **分处两行**（拆分形态），`offset` 在 458 行；AST 变量流判定命中 |
| `services/user_data_service.py:476` | **是真分页** ⇒ 已补次级键 | 同上（`TextEntry` 分支） |
| `api/v1/content_governance.py:377` | 单页截断 ⇒ 白名单 | 链尾 `.limit(100)`，全函数无 `offset`；"该内容的最近 100 条审核日志"无下一页 |
| `api/v1/ops_dashboard.py:284` | 单页截断 ⇒ 白名单 | `.limit(limit)`（默认 10），无 `offset`；仪表盘"近期事件"卡片 |

---

## 四、T3 修复清单（15 处，均只加次级键，不动分页语义）

| # | 位置（修后） | 表 / 排序键 | 形态 |
|---|---|---|---|
| 1 | `api/v1/canary.py:95` | `CanaryRecord.created_at desc, id desc` | chain |
| 2 | `api/v1/content_governance.py:296` | `EducationContent.created_at **asc**, id **asc**` | variable |
| 3 | `api/v1/monitoring.py:259` | `DriftAlert.created_at desc, id desc` | chain |
| 4 | `api/v1/monitoring.py:439` | `MonitoringLog.created_at desc, id desc` | chain |
| 5 | `api/v1/tenant_audit.py:68` | `OperationLog.created_at desc, id desc` | chain |
| 6 | `api/v1/tenant_audit.py:140` | `OperationLog.created_at desc, id desc` | chain |
| 7 | `services/admin_service_config.py:29` | `ModelFeedback.created_at desc, id desc` | chain |
| 8 | `services/content_service.py:57` | `sort_order asc, created_at desc, id desc` | chain |
| 9 | `services/content_service.py:152` | `UserFavorite.created_at desc, id desc` | chain |
| 10 | `services/content_service.py:275` | `priority_case, view_count desc, created_at desc, id desc` | chain |
| 11 | `services/content_service.py:289` | `view_count desc, created_at desc, id desc` | chain |
| 12 | `services/counselor_service_consultation.py:139` | `ConsultationRecord.created_at desc, id desc` | chain |
| 13 | `services/intervention_service.py:221` | `InterventionPlan.created_at desc, id desc` | chain |
| 14 | `services/user_data_service.py:435` | `StructuredAssessment.created_at desc, id desc` | **variable**（拆分） |
| 15 | `services/user_data_service.py:477` | `TextEntry.created_at desc, id desc` | **variable**（拆分） |

### 同秒顺序是否被业务依赖（逐处判断）

**结论：14 处不依赖，1 处方向有语义但结论一致。**

- 列表/审计/告警/反馈/干预/咨询/用户数据历史 —— 都不存在"同秒内谁必须在前"的业务规则，
  原先是"DB 随机"，现在是"确定"。**变化是消除不确定性，不是改变语义。**
- 唯一需要说明的是 **#2 `list_pending_content`（审核队列）**：队列语义是 FIFO
  （`created_at asc`），同秒内"先提交先审"才是符合直觉的顺序。次级键选用
  `id.asc()`（**与主排序同向**）而非 `id.desc()`，因此同秒内按插入序排列，
  **比原先的随机顺序更贴合 FIFO**。这也是唯一一处 asc 站点——若照抄 `id.desc()`
  会变成"同秒内后提交先审"，反而破坏 FIFO。

> 统一提醒（提示词要求写明）：加次级键会把"同秒页边界归属"从 DB 随机变为确定但不同。
> 本轮 15 处均无跨页业务契约依赖该归属（不存在"第 2 页第一条必须是某条记录"的约定），
> 故不构成行为兼容性问题。

---

## 五、白名单（8 个 key / 11 个站点）

白名单**不是豁免通道**，而是"已裁定为单页、无跨页语义"的监控名单：

| 位置 | 站点数 | 理由 |
|---|---|---|
| `api/v1/content_governance.py:367` `get_content_history` | 1 | `.limit(100)` 单页，无 offset |
| `api/v1/ops_dashboard.py:284` `_get_recent_audit_events` | 1 | `.limit(10)` 单页 |
| `services/counselor_service_user.py:235/255/270` `get_user_detail` | 3 | 风险历史/评估/干预各 `.limit(100)`，一次返回时间线 |
| `services/drift_monitoring_service.py:292/304` `_create_drift_alert` | 2 | 去重存在性探测，`.limit(1)` |
| `services/intervention_service.py:96` `get_active` | 1 | `.limit(1)`；ROUND_23a 后每用户至多一条 active（部分唯一索引）⇒ 并列组大小恒为 1 |
| `services/risk_service_report.py:24` `get_risk_report` | 1 | `.limit(20)` 单页 |
| `services/risk_service_warning.py:38` `_check_warning_trigger` | 1 | 取上一条评估，`.limit(1)` |
| `services/crisis_export_service.py:95` `iter_export_crisis_csv` | 1 | **L20 已知项，按边界只登记不动**：全量流式导出，服务端游标 `yield_per=1000` 分块，同一次查询执行内不跨页 |

白名单的四条防腐烂规则（`test_whitelist_entries_are_real`）：

1. 条目必须仍在源码中存在（否则是"腐烂条目"）；
2. 条目页数必须对得上（防一个 key 掩盖多处）；
3. 条目**一旦接上 `.offset`** ⇒ 立即失效，必须补次级键（不得用白名单豁免真分页）；
4. 条目**一旦补了次级键** ⇒ 必须移出白名单（防囤积已修站点）。

---

## 六、T1 闸门设计（三档自检）

`backend/tests/test_p2_51_round24_pagination_order_gate.py`（17 用例）

| 档 | 用例 | 作用 |
|---|---|---|
| **生产闸门** | `test_no_unlisted_violations` | 读 `app/` 真实源码，白名单外违规必须为 0 |
| | `test_whitelist_entries_are_real` | 上述四条防腐烂 |
| | `test_every_whitelist_entry_has_reason` | 空理由 = 隐性豁免 |
| **自证（红臂）** | `test_detects_paginated_without_tiebreak` / `test_detects_limit_only` / `test_detects_variable_split_flow` / `test_detects_asc_order` | 四种形态都能被抓到 |
| **自证（放行臂）** | `test_allows_no_paging_clause` / `test_allows_tiebreak` / `test_ignores_non_time_column` | 无分页/有次级键/非时间列都不误报 |
| **自证（防腐烂）** | `test_whitelist_guard_catches_removed_entry` / `..._stale_entry` / `..._gained_offset` / `..._count_drift` | 防腐烂逻辑自身可证伪 |
| **防空转** | 文件数 ≥260（实际 268）/ 站点数 ≥30（实际 32）/ 哨兵站点字段逐项核对 | 扫描器退化不会静默变绿 |

**与 p2_50 的反面例子划清界限**：p2_50 的 `test_*_has_tie_break`（L40/L57）是
**测试自己重建 statement** 再断言——生产侧改坏了照样绿。本轮闸门全部读生产源码，
自证部分才用合成样本，且合成样本只用于证明"判据两臂都在工作"，不作为生产证据。

---

## 七、T4 变异见证（5 组）

`backend/tests/tools/mutate_p2_51_round24.py` + `mutate_p2_51_round24_result.log`

| 组 | 变异 | 期望 | 实测 |
|---|---|---|---|
| T1 | 去掉 `intervention.get_history` 的 `id.desc()`（分页仍在） | 闸门红 | **RED-OK** `test_no_unlisted_violations` |
| T2 | 白名单塞入指向不存在文件的伪造条目 | 防腐烂红 | **RED-OK** `test_whitelist_entries_are_real`（"腐烂条目"） |
| T3 | 同处**同时**去掉次级键与 `offset/limit`（退化为无分页） | 闸门**放行** | **GREEN-OK**（反向证明 T1 的红来自"分页+无次级键"，不是"改了文件就红"） |
| T4 | `user_data_service` 变量拆分形态去次级键 | 闸门红 | **RED-OK**（验证 variable 分支） |
| T5 | 白名单站点接上 `.offset(0)` | 防腐烂红 | **RED-OK**（"已接 offset"） |

附带读数 **T1-behavior**：同一变异下行为测试
`test_intervention_history_pages_are_disjoint` 也红（`target_hit=True`）。
这说明**本机 SQLite 上"并列组内 id 降序"这半边断言确有区分力**——
比 p2_50 当时"行为断言无区分力"的结论更强。但另一半（跨页不重复/不丢行）
仍不可区分（SQLite 恰好按插入序返回），所以**结构见证仍是主保障**。

收尾：`residual_clean=True`、还原后 `23 passed`（闸门 17 + 行为 6）、无 `MUTATION` 残留。

---

## 八、行为侧回归（6 条，并诚实标注效力）

`backend/tests/test_p2_51_round24_pagination_behavior.py`

| 用例 | 覆盖形态 |
|---|---|
| `test_intervention_history_pages_are_disjoint` | 链式 + offset/limit |
| `test_content_favorites_pages_are_disjoint` | JOIN + 链式 |
| `test_content_list_pages_are_disjoint` | 三键排序（sort_order/created_at/id） |
| `test_user_data_history_pages_are_disjoint` | **拆分**形态（order_by 与 offset 分行） |
| `test_consultation_records_pages_are_disjoint` | 链式 + 二次查询 |
| `test_model_feedback_pages_are_disjoint` | 管理端列表 |

每条的构造：6 行**共用同一 `created_at`**，页大小 3，取页 1 + 页 2；
断言 ①无重复 ②无遗漏（与预期 id 集合相等）③并列组内 id 降序（方向语义）。

> **效力声明（不得夸大）**：本机 SQLite 在并列时按 rowid 升序返回，
> "跨页不重复/不丢行"这半边**不具备区分力**；真正拦住回归的是 §六 的结构见证。
> 行为测试的价值在 ①offset 计算/过滤/count 口径写错会红 ②锁住 tie-break 方向语义
> （§七 T1-behavior 实测：去掉次级键即红）。

**覆盖缺口（记账）**：15 处修复中 **6 处有行为回归**，其余 9 处仅由结构见证覆盖：
`canary:95`、`content_governance:296`、`monitoring:259/439`、`tenant_audit:68/140`、
`content_service:275/289`（推荐列表）、`user_data:477`（TextEntry 分支）。
其中 API 层 5 处需管理员鉴权+路由级夹具，成本明显更高，本轮不做，如实记账。

---

## 九、回归读数与棘轮

| 项 | 读数 |
|---|---|
| 新闸门 | **17 passed** |
| 新行为回归 | **6 passed** |
| `p2_10 + p2_11 + p2_49 + p2_50 + p2_51×2` | **279 passed** |
| 受影响 service 四文件 | **221 passed** |
| 受影响 API 五文件（canary / content_governance / ops_dashboard / tenant_audit / monitoring） | **92 passed** |
| 全称注释棘轮 | **113 未变**（本轮新增注释不含全称词） |
| `#35` 桶计数 | **未变**（W=109 / X=116 / 总数 341）：纯 SQL 排序参数调整，未新增 except 降级点；p2_10/p2_11 闸门通过即证据 |
| `ORPHAN_BASELINE` | 未动（本轮不碰前端） |

---

## 十、边界与未验证记账

- **未改分页语义**：页大小、offset 计算、默认排序方向全部保持原样；只追加次级键。
- **`crisis_export_service.py:95` 未动**（L20 已知项，白名单登记）。
- **未做 D 批（M17–M24）/ E 批（L1–L21）**，未动前端，未改 `ORPHAN_BASELINE`。
- **全量后端套件未在本机跑完**（约 37 分钟），交 CI `backend-coverage` 实测。
- **同型风险仍有残留**：`order_by(<非 created_at 的非唯一列>)`（如 `risk_score`、
  `view_count` 单键）不在本轮判据内；若将来出现"按分数分页"同样会重复/漏行。
  本轮不扩判据（避免一次改太多），记账待议。
- **行为回归只覆盖 6/15**（见 §八），其余依赖结构见证。
- 白名单的 `crisis_export` 条目是**登记而非豁免违规**（该站点本就无 offset/limit 子句，
  按判据不判违规）；保留它是为了在"未来给它加 offset"时能被 T5 类变异立刻抓到。
