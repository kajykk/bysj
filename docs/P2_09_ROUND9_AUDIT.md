# P2 第九轮审计清单（#32 余量 + #33 + #35 + #39 + #40）

- 生成时间：2026-10-13（HEAD 以提交时为准）
- 方法：机制扫描（脚本 `backend/scripts/scan_p2_09_roles.py` / `scan_p2_09_rest.py`，无变异窗口内生成）+ 人工语义判定
- 判定标准沿用 P2-32：内容集合完全相同才算真重复；仅有重叠词不算

## 汇总

| 项 | 结论 |
|---|---|
| #32 文件名清洗 | 3 清洗实现语义不等价，不合并；`gdpr.py:182/295` 文件名来自 int id / uuid 切片，无注入面，记账不改 |
| #32 CSV 转义 | 4 处内联链 → 3 处已调 `sanitizeCellForExcel`，仅 `MisclassifiedTable.vue:157` 缺公式转义 → 已改调 SSOT（本轮唯一行为修复） |
| #32 风险等级 | `none/low/medium/high/critical`（契约输出标签）vs `mild/moderate`（分档阈值键）不同语义，不合并 |
| #32 角色 | `contracts.USER_ROLE_*` 为 SSOT；`review.py` 5 处裸字面量已改调常量；路由 prefix/tag 字面量语义不同，不收编 |
| #32 模型元数据 | 145 处几乎全是 `model_version` 字段传递，无第二定义处，不建 SSOT |
| #33 审计 helper | 新建 `app/core/audit.record_audit`；`admin_export_user_data` 原来缺 `ip_address` → 已迁移补上 |
| #35 静默降级 | 新增 `silent_degradation_total{location}` 经 `/metrics` 暴露；`cache._get_redis_url` 已接线；Celery alerts 双任务已是 raise 范式 |
| #39 死代码 | `csvEscape` 重复实现已删（改调 SSOT）；`bertDisabled=True` 是有意下线 UX，保留；`_flushed_buffer` 有 RES-P1-004 书面保留依据，保留 |
| #40 契约测试 | `render_exposition` 用 `prometheus_client.parser` 真解析；`render_prometheus_rules` 用 YAML 形状断言（本机无 promtool，如实记账） |

## #32 余量逐类

### 文件名清洗：3 实现不等价（不合并）

- `admin.py:42 _sanitize_filename` / `reports.py:141 _safe_export_filename` / `user_risk.py:24 _sanitize_filename`：三者白名单/回退文件名不同，机械合并会改任一端点行为。SSOT 化需先统一策略 = 业务决策，本轮不做。
- `gdpr.py:182` 文件名 `my_data_{current_user.id}.json`（int）、`:295` `user_{user_id}_data_{export_id[:8]}.json`（int + uuid hex 切片）：字符集封闭，无注入面。原提示词怀疑为真缺陷，取证后降级为安全（记账）。

### CSV 转义：1 处真缺陷已修

- `PhysioTab.vue:314`、`useTextPredictionHistory.ts:130`、`usePredictionHistory.ts:74`：内联链但已调 `sanitizeCellForExcel`，与 `csvEscape` **语义等价、无注入面**。
  ⚠️ **更正（独立复核发现）**：本轮**并未**把这三处改调 `csvEscape` 别名（提交 `7bc85e8` 的 diff 实际只改了 `exportUtils.ts` / `p2CsvSsot.test.ts` / `MisclassifiedTable.vue`）。此处原文"本轮统一改调"属表述失实。安全面无问题，但 #32 的去重目标在这三处**未落地**，仍为内联重复链 —— 留第十轮收敛（记账，非静默）。
- `MisclassifiedTable.vue:157`：本地 `csvEscape` 只做引号转义、未调 `sanitizeCellForExcel` → 公式注入面。已删本地定义，改调 `exportUtils.csvEscape`（新导出别名）。回退实验 E31 把守。

### 角色：5 处已收编

- `review.py:94/302/341/424/461`：`== "counselor"` → `== USER_ROLE_COUNSELOR`（常量已在文件内 import，无新增依赖）。
- 范围外：`counselor.py` 路由 `prefix="/counselor"`、`tags=["counselor"]`、`require_role("counselor")` 参数字面量——路由名语义 ≠ 角色语义，不收编；`seed.py` / 服务层 `operator_role="counselor"` 传参字面量 30+ 处，分散且需逐个确认常量可达性，留第十轮与 #37 一起收口（记账，非静默）。

### 模型元数据：无重复定义

- 145 处引用中定义处仅：模型列（`monitoring.py`）、schema 字段、指标 label 名、字面版本号传递。无“同一常量两处定义”，不建 SSOT。

## #33 审计 helper

- 全仓 `OperationLog(` 64 处，`ip_address` 57 处：写法分散（有的带 ip 有的不带，`admin_export_user_data` 完全缺 ip）。
- 新建 `app/core/audit.py::record_audit`：写操作同步 `add+flush`；`tenant_id` 必填关键字（sentinel `_MISSING`，漏传 TypeError）；`ip_address` 一律从 request 经 `get_real_client_ip` 取，禁止手填。
- 已迁移 1 处（`gdpr.admin_export_user_data`，补 ip）；其余 63 处留待分批迁移（记账）。

## #35 静默降级

- 全仓 `except→debug/continue/pass` 候选 119 处（含大量 `except ImportError: pass` 特性探测，不属降级）。
- 本轮：新增 `silent_degradation_total{location}`（`metrics.py`，随 `render_exposition` 即 `/metrics` 暴露）；`cache._get_redis_url` 静默 except 已接线；`alerts.py` 双 Celery 任务已是“失败 raise 原始异常”范式（注释载明）， gate 锁死 `raise exc` 存在。
- 未完成：其余 100+ 候选点逐点接线（需分批，记账）。

## #39 死代码

- 删：`MisclassifiedTable` 本地 `csvEscape`（与 SSOT 重复且少一次转义）。
- 保留（书面理由）：`ExperimentTab.bertDisabled=True`（权重归档后的有意下线 UX：禁用按钮 + 解释文案，删了用户看到的就是坏按钮）；`observability_service._flushed_buffer`（RES-P1-004 文档化保留，供未来 TSDB 消费者）。

## #40 契约测试

- `render_exposition()`：优先 `prometheus_client.parser` 真解析；该包非项目依赖（CI 无）时降级为严格自解析（HELP/TYPE 成对、样本行正则）。双分支均有实测（自解析分支用桩包遮蔽验证，`FALLBACK-OK help=78`）。

## 已知局限（如实记账）

1. `promtool check rules` 未跑（本机无 promtool）。
2. 后端全量未跑（37 分钟），以受影响文件集（54 passed）+ CI 全量兜底为准。
3. 前端全量未跑（基线 100 files / 1285 passed / 4 skipped 待 CI/本地补测）。
4. #34/#36/#37/#38 移第十轮（见计划）。
