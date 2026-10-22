# P2_52 · ROUND_25 审计：兑现「不可验证的修复」——L13 脚本处置 + 排序判据扩展

> 状态：HEAD 起点 `7cc22e7`（ROUND_24，CI 10/10）。本轮两个独立提交：
> **commit 1 = A 摊**（L13 脚本处置 + 记账闸门），**commit 2 = B 摊**（排序判据扩展防回归）。
> 全部读数为 2026-10-22 实测。

## 〇、要兑现的「不可验证修复」是什么

ROUND_23b 的 L13 把 7 个本地登录辅助脚本的口令改成了环境变量读取——但：

1. 这些脚本被 `.gitignore` 通配规则排除（理由原文：「含**明文口令**的本地登录辅助脚本」）；
2. 口令改环境变量后，**排除的理由已消失**，但文件仍在 CI 视野外；
3. 闸门 `test_p2_49` 的 `test_whitelist_entries_are_real` 对不在工作区的文件
   **`pytest.skip`** ⇒ 这 7 个脚本在 CI 上「无人看管」；
4. 即：**修复做了，但没有任何机制能在修复退化（口令被写回字面量）时发现**。

ROUND_25 就是给这个缺口补上 CI 背书，并按同一纪律把分页排序判据从
「只有 created_at」扩展到「一切非唯一排序列」。

---

## 一、A 摊：L13 脚本处置

### A1 · 逐读后的裁定（7/7 全部实读，不凭文件名）

| 脚本 | 裁定 | 依据（读后） |
|---|---|---|
| `scripts/login_admin.py` | **入库** | docstring 自述 canary 发布运维辅助（发版后健康检查/指标核对）；71 行，读环境变量 `BYSJ_ADMIN_PASSWORD` |
| `scripts/login_admin.ps1` | **入库** | 与 `.py` 同口令同用途的 PowerShell 版。**P1-30 事故的教训正是这两个必须同进同出**（当初按文件名枚举漏了 ps1，该文件曾误入库 3a1740e）⇒ 47 行，同环境变量形态 |
| `scripts/check_metrics_v2.py` | **入库** | `_v2` 命名 = 被迭代替换的运维工具（拉全量指标 JSON 做对账），非一次性；59 行，`BYSJ_ADMIN_PASSWORD` + `BYSJ_BASE_URL` |
| `scripts/trigger_fusion_inference_v2.py` | **入库** | 同上，触发融合推理并校验响应结构；85 行，同环境变量形态 |
| `scripts/dump_errors.py` | **删除** | 一次性调试脚本：连本地 sqlite 打印最近异常行，无运维复用价值 |
| `scripts/test_gdpr_fix.py` | **删除** | ROUND_19 M15（GDPR 统计排除匿名化）的当时验证脚手架，缺陷已修且有正式闸门覆盖 |
| `scripts/revise_download_thesis.py` | **删除** | 论文下载/修订辅助，与系统运行无关；含 `secret/api_key` 字样经逐读确认为**误报**（是学术论文 API 的参数名注释，非真凭证） |

入库前复核：4 个文件均无明文口令字面量（23b 环境变量化保留）；
删除的 3 个均**从未入库**（未跟踪文件，物理删除不影响 tracked 集合）。

### A2 · `.gitignore`：定向否定，不删通配

```
/scripts/login_admin.*          ← 通配规则**保留**
!/scripts/login_admin.py        ← 定向否定放行 4 个逐读确认过的文件
!/scripts/login_admin.ps1
!/scripts/check_metrics_v2.py
!/scripts/trigger_fusion_inference_v2.py
```

- **为什么不删通配只留单文件**：P1-30 事故的根因就是「枚举会漏」——通配挡住
  未来新出现的登录辅助脚本，定向否定只放行已逐个读过的具体文件。
  既恢复 CI 保护，又不退回「枚举式」脆弱形态。
- 剩余同通配文件处置：当前 `scripts/` 下无其他匹配 `login_admin.*` 的文件
  （实测）；`.admin_token.txt`/`*.token` 的令牌产物规则**原样保留**
  （那是运行期产物，与登录脚本是两回事）。

### A3 · 闸门增强（A4，本轮最有价值的一条）

`test_p2_49_round23b_secret_scan.py` 10 → **14 passed**：

1. **`KNOWN_UNTRACKED_CREDENTIAL_SCRIPTS` 记账闸门**：实测「本地存在、未入库、
   且消费凭证字段」的脚本集合必须与登记簿**双向相等**——
   实际 ⊋ 清单 ⇒ 红（新的没人看管的含凭证脚本）；
   清单 ⊋ 实际 ⇒ 红（已入库/已删除忘同步，防腐烂）。
   当前登记 2 条：`check_tabular_v2.py`（一次性探针，读 `.admin_token.txt`）、
   `gen_canary_traffic_v2.py`（金丝雀 5% 流量生成器，阶段产物）——
   均**非 L13 七脚本之列**（消费令牌文件而非登录口令），登记备查、本轮不处置。
2. **移除静默 skip**：白名单条目指向的文件不在工作区时，必须在记账清单里
   找得到登记理由，否则红——`skip` 不得代替记账。

凭证消费判据（注释行除外）：`os.environ[...]` / `os.environ.get(...)` /
`os.getenv(...)` / `getenv(...)` / `$env:XXX`（ps1）/ 读 `.admin_token.txt`。
**自证当场抓到一个真缺口**：初版判据漏了 `os.getenv(...)` 形态，
自证用例（合成样本必须被识别）直接红 ⇒ 修正后才上场。

### A 摊变异（`mutate_p2_52_round25.py` + `_result.log`，已入库）

| 组 | 变异 | 结果 |
|---|---|---|
| M1 | 口令字面量塞回**已入库**的 `login_admin.py` | RED-OK |
| M2 | 登记簿伪造一条指向不存在文件的条目 | RED-OK（防腐烂臂） |
| M3·本机 / M3·CI | **反向臂**：把已登记的未入库脚本强推进库（模拟 A2 完成忘同步清单） | RED-OK ×2（两种形态） |
| M4 | 新建一个未入库却消费凭证的脚本 | RED-OK |

`5/5 RED-OK；residual_clean=True; final_green=True`。

---

## 二、B 摊：排序判据扩展（防回归，非修 bug 叙事）

### B1 · 判据怎么扩的

`pagination_order_lint.py`：

- `NON_UNIQUE_TIME_COLUMNS`（只有 `created_at`）→
  **`NON_UNIQUE_SORT_COLUMNS`** = 时间戳族（`created_at`/`updated_at`/`bound_at`/
  `started_at`/`completed_at`/`recorded_at`/`latest_viewed_at`… 显式枚举）
  **+ 结构判据**：任何 `_at` 结尾列 **+** 低基数业务列
  （`status`/`role`/`level`/`category`）。
- **排除**（判据注释写明，防后人凭感觉加列）：`id`/`pk`/`config_key` 等
  近似唯一列不得纳入——否则白名单会腐烂。
- 顺手补上 **ROUND_24 的形态覆盖缺口**：`desc(Model.col)` 函数形态
  （`from sqlalchemy import desc` 后 `order_by(desc(X.created_at))`）
  原先完全不在 AST 判据内——全仓 14 处这种写法，ROUND_24 一个都没看见。

### B2 · 扩展后实测：**前置盘点确实漏了**

提示词的前置实测预估「扩展后 0 违规」。实际（诚实记账）：

| 读数 | ROUND_24（仅 created_at） | ROUND_25（扩展后） |
|---|---|---|
| 扫描文件 | 268 | 268 |
| order_by 站点（判据内） | 32 | **58** |
| 违规（分页/截断且无 tie-break） | 0（白名单外） | **29** |

新增 26 站点 / 29 违规中，**14 处是真修复**（前置盘点漏因：只看方法形态
`Model.col.desc()`，漏了函数形态 `desc(Model.col)`；且只看了提示词点名的
4 个站点，没扫全量）。逐站读查询链后的裁定：

**7 处 offset 真分页（用户可见列表）——补次级键：**

| 站点 | 列 |
|---|---|
| `api/v1/alerts/__init__.py` `list_operation_logs` | `OperationLog.created_at` |
| `api/v1/alerts/__init__.py` `list_alert_archives` | `AlertArchive.original_created_at` |
| `api/v1/silences.py` `list_silences` | `AlertSilence.starts_at` |
| `services/content_service.py` `list_recent_viewed` | `latest_viewed_at` |
| `services/review_service.py` `get_reviews` | `ReviewTask.created_at` |
| `services/review_service.py` `get_crisis_events` | `CrisisEvent.created_at` |
| `services/user_data_service.py` `get_history`(physio) | `PhysiologicalRecord.recorded_at` |

**7 处 limit(1)/limit(N) 业务可见——补次级键：**

| 站点 | 理由 |
|---|---|
| `services/counselor_service_binding.py` ×3（`get_user_binding`/`get_counselor_binding`/`unbind`） | 取「当前绑定」：同秒绑多条时取错行 = 解绑错对象 |
| `services/risk_service_warning.py` ×2 | 取当前生效预警/计划，同秒并列取错 |
| `api/v1/metrics_helpers.py` `collect_drift_metrics` | gauge 读数不确定 |
| `monitoring/dedup.py` `should_send` | 窗口边界并列时「最近 50 条」集合不确定，可能漏检边界重复告警 |

**5 处聚合/扫描窗口——进白名单**（`observability/aggregate.py` ×2、
`observability/query.py`、`monitoring/escalation.py`、
`api/v1/ops_dashboard.py`）：窗口聚合无跨页语义，理由逐条写入白名单。

修复后读数：**58 站点 / 15 违规，且 15 违规全部是 limit-only 白名单站点**
（10 个 ROUND_24 存量 + 5 个本轮新登记），白名单外违规 = 0。

### B3 · 阈值/哨兵同步

`test_p2_51_round24_pagination_order_gate.py`：文件数哨兵 268、站点数哨兵
**30 → 50**（防函数形态/新列名重新不可见时静默降级）；新增 3 条自证：
函数形态可判 / 业务列可判 / `_at` 结构判据可判；`_UNIQUE_COLUMN` 排除自证
（id + 分页不判违规，防判据过严）。

### B 摊变异（`mutate_p2_52_round25_pagination.py` + `_result.log`，已入库）

| 组 | 变异 | 结果 |
|---|---|---|
| BM1 | 去掉 `review_service.get_reviews` 新补的 id 次级键（分页仍在） | RED-OK |
| BM2 | 从判据常量删掉 `status` | RED-OK |
| BM3 | 阉割 `_at` 结构判据 | RED-OK（指名用例 + 哨兵 14 failed） |
| BM4 | 让函数形态 `desc(Model.col)` 重新不可见（ROUND_24 缺口复发模拟） | RED-OK |
| BM5 | **放行臂**：同时去掉次级键与 offset/limit | **GREEN-OK**（无分页 ⇒ 不判违规） |

`4 RED-OK + 1 GREEN-OK；residual_clean=True; final_green=True`。

---

## 三、连带修复（回归连抓，全部留痕）

### 3.1 p2_11 硬编码行号漂移（本轮修复引入，4 处）

B 摊在生产站点前插入 tie-break 注释行 ⇒ `test_p2_11` 里以行号定位 except
handler 的登记漂移：`metrics_helpers.py` collect_drift 257→**258**、
collect_canary 283→**284**；`dedup.py` should_send 95→**97**、103→**105**。
已更新 CANDIDATES 与文档字符串。**教训**：行号见证对「在文件中段插注释」
零容忍——后续批次优先用 AST 锚点而非行号。

### 3.2 p2_10 全称注释棘轮 113→116

3 条新注释含「保证」（alerts/content_service/review_service 的 tie-break
说明），按机制同步 P2_10 附录附四；另 8 条存量注释行号漂移记录在案。

### 3.3 变异脚本自身的环境抖动（本次最难缠的一个）

B 摊变异前两次运行出现「15 个自证用例集体 teardown ERROR、与变异内容无关」
的非确定性红。控制变量实验（同序列手动复刻不出现、固定 basetemp 单跑不出现）
定位到：**pytest 的 `tmp_path` 在 Windows 无 symlink 权限时为每个用例维护
`<name>current` 目录（退化为 copytree），与复用 basetemp 下累积的目录竞争**。
处置（两层）：

1. **变异脚本**：每次 pytest run 用全新 basetemp（`r25_mut_bt_N`）；
   判定逻辑区分 FAILED 与 ERROR——指名用例必须真的 FAILED 才算 RED，
   出现 ERROR 先原样重跑一次再判（环境抖动不得伪装成闸门红绿）；
2. **闸门自身**：自证用例不再落盘——lint 工具新增 `scan_source(source)`
   内存态入口，15 个自证用例改为直接传源码字符串，**从设计上消除**
   tmp_path 依赖。这不削弱断言强度（同样的 AST 判定、同样的样本）。

---

## 四、读数汇总（全部实测）

| 项 | 读数 |
|---|---|
| scripts/ 入库脚本 | 111 `.py` + 2 `.ps1`（原 108 + 1；本轮 +3 py +1 ps1 入库，删 3 个未跟踪文件） |
| 未入库含凭证脚本 | 2（全部登记于 `KNOWN_UNTRACKED_CREDENTIAL_SCRIPTS`） |
| `test_p2_49` | **14 passed**（原 10） |
| `test_p2_51` gate + behavior | **27 passed**（原 23） |
| 收工标准组合（p2_49+p2_10+p2_11+p2_50+p2_51×2） | **289 passed**（基线 281） |
| tests/services / tests/api 全目录 | 830 passed / 549 passed, 10 skipped |
| lint 工具 | 268 文件 / 58 站点 / 15 违规（全 limit-only 白名单内，白名单外 0） |
| 变异 | A 摊 5/5 RED-OK；B 摊 4 RED-OK + 1 GREEN-OK |

**纪律备注（不隐瞒）**：

- tests/api 与 tests/services 曾并发双跑，出现 449 errors 的假失败；
  单独重跑均全绿（830/549）。铁律「同套件禁并发双跑」再次实证。
- B 摊 14 处修复中，与 ROUND_24 一样只做了结构见证（AST 判据 + 单元级
  行为测试 p2_51 behavior 6 条覆盖其中 4 处的同秒语义）；其余靠「同型已接线」
  论证，未见逐条行为断言——记账为已知缺口。
- 判据目前只覆盖 `order_by` 的显式列名；`text()` 原样排序、混合大小写列名
  不在覆盖内（全仓实测 0 处，防回归用）。
- 工作区遗留本轮变异 basetemp 目录 `r25_mut_bt_1..7`（环境防护按 turn 累计
  拦截 >50 文件删除，未强行绕过），已在 `.gitignore` 之外作为临时产物记账，
  提交时不 `add`。
