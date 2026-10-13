# 第九轮整改提示词（P2 剩余项 #32 余量 + #33–#40）

> 用法：新开一轮对话，把下面「提示词正文」整段粘贴进去即可。
> 本文件只是存档，正文以「提示词正文」小节为准。

---

## 提示词正文

接手 `E:\code\bysj` 的代码审查整改第九轮。全程用简体中文。

### 零、先读这些（按顺序，不要跳）

1. `.workbuddy/memory/MEMORY.md` —— 项目长期纪律（测试判据、Git 纪律、验证工具失效清单、前端基线读数）。
2. `.workbuddy/memory/2026-10-13.md` —— 本轮上下文。
3. `docs/CODE_REVIEW_2026-10-11.md`：
   - 「P2（后续优化，消除系统性根因）」表格（第 714–727 行）= 本轮全部待办原文；
   - 「系统性代码根因」六条；
   - 「第七轮：P2-31」「第八轮：P2-32」两节（1216 行起 / 1339 行起）= 前两轮的做法范式与已踩过的坑。
4. `docs/P2_31_TENANT_QUERY_AUDIT.md`、`docs/P2_32_SSOT_DEDUP_AUDIT.md` —— 已建立的审计清单范式。

**先复述一遍你读完的理解与本轮计划，再动手。** 计划里必须写明：本轮打算做哪几项、明确不做什么、每项的客观断言是什么。

### 一、本轮范围（已确认的剩余待办）

前八轮已闭环：P0 全部 10 项；P1 全部 #11–#30；P2 #31；P2 #32 第一类（Blob 下载链路 + 危机词表死副本，提交 `61b01f9` + `a58f95c`）。

剩余：

| # | 事项 | 本轮建议 |
|---|---|---|
| 32 余量 | SSOT 其余 5 类：风险等级标签、文件名清洗、CSV 转义、角色定义、模型元数据 | 必做 |
| 33 | 统一审计 helper `_audit(db, request, actor, action, target, detail)`；写操作同步落、读操作异步队列；`ip_address` 与 `tenant_id` 归属规则统一 | 建议做 |
| 34 | 统一错误方言 `ServiceError(client_message, internal_detail)` + 中间件末道脱敏 | 可延后 |
| 35 | 静默降级治理：所有 `except → logger.debug/continue/return` 必须留 metric；Celery 任务失败必须 `raise` | 建议做 |
| 36 | 前端抽 `useListQuery()` composable（竞态守卫 + 页码重置 + 三态），覆盖 12 个列表页，约消除 700 行重复 | 独立一轮更稳 |
| 37 | 前端抽 `isAdminRole()`/`isStaffRole()`；路由 `permissions` 补齐 + 静态检查 | 建议做 |
| 38 | 注释与实现一致性核查：把「注释所述行为必须有测试或调用点」固化为检查项 | 建议做 |
| 39 | 删除死代码：`ExperimentTab` 的 `bertDisabled` 分支、`exportUtils` 之外的重复实现、`observability_service._flushed_buffer` | 建议做 |
| 40 | 契约测试：`render_prometheus_rules()` 用 `promtool check rules`；`render_exposition()` 用 `prometheus_client.parser` | 建议做 |

**推荐本轮做 32 余量 + 33 + 35 + 39 + 40**，34/36/37/38 排到第十轮（34 改动面大需要分批；36 是 12 个页面的前端重构，与第八轮的前端基线冲突风险高，单独一轮更干净）。

如果你判断组合不合适，可以调整，但必须在回复里说清理由，且**不得静默缩减范围**。

### 二、本轮必须遵守的纪律（前八轮用血换来的，逐条照做）

**验证纪律**

- 先实测再写断言。无真实来源的指标不上报，**绝不上报 0**。
- 整改前先做**机制扫描**（AST / 正则判据脚本），产出审计清单文档，再决定改什么。**审计与整改分开**，不要"扫一遍就顺手改"。
- 每项整改做**回退对照实验**：临时变异源码 → 闸门必须变红 → 恢复 → 必须变绿。日志落盘。
- 闸门必须**反向也验**：绕过机制 → 红；机制本身能测到（造临时违规文件证明扫描器能检出），否则是假闸门。
- 判据的**语法形态覆盖要全**：`ast.Assign` / `AnnAssign`、`dict[int,str]` 键为 int、模块级常量、`if TYPE_CHECKING` 块 —— 上一轮四个假阴性全出在这上面。
- 静态审计产物**必须在无源码变异窗口内生成**，否则产出同源伪影。
- Windows 下跑前端测试：`node_modules/.bin/vitest.cmd` 绝对路径（`npx` 会 `FileNotFoundError`），前端路径先 `.resolve()`，subprocess 加 `encoding="utf-8"`。
- vitest 失败名三种格式都认：`FAILED <path>` / ` FAIL  <file> > suite > name`（捕获整行）/ `× name`（行尾带 `12ms`）。驱动必须做 **anchor 校验**，`old` 不在文件里当场抛错，不记成 INVALID。
- 写临时脚本用 Write 工具，**不要 bash heredoc**（会展开 `$var`）；改源文件前 `try/finally` 恢复保护。

**跑测试固定姿势**

```
cd backend && .venv/Scripts/python.exe -m pytest -o "addopts=--strict-markers --import-mode=importlib --cov=app --cov-report=xml:coverage.xml --ignore=functional_test.py --ignore-glob=test_result*.txt --ignore=test_final.txt" -p no:cacheprovider -q
```

- ❌ 不要覆盖 `addopts=`（丢 importlib → import file mismatch）；❌ 不要加 `--timeout`（缺插件）。
- **不在本机跑后端全量**（约 37 分钟/轮），且**禁止并发跑其它 backend 测试**（共用 `test_app.db`）。以受影响文件集读数 + CI 全量兜底为准。
- 前端基线逐位比对，防"单跑绿"冒充"无回归"：当前基线 **100 test files / 1285 passed / 4 skipped**，`vue-tsc --noEmit` **0 error**。

**Git 纪律**

- 沙箱红线：❌ stash / rebase / branch / filter-repo 等一切 ref 重写；✅ fetch / push / status / log / add / commit / diff / grep。
- 判 git 成功必须匹配输出特征串（如 `main -> main`），交叉核对 `gh api repos/…/commits/main`。
- **显式逐文件 `git add <path>`**，不用 `-A .`。
- 一轮整改（源码 + 测试 + 实验脚本 + 文档）= **一次提交**；提交信息四段式：改了什么 / 连带修复 / 验证实测读数 / 未验证如实记账，**末段不得省略**。
- 推完用 `gh api repos/…/commits/<sha>/check-runs` 确认 CI（`actions/runs?sha=` 的 sha 会被忽略；job 名 ≠ 工作流名）。CI 10 个 job，逐个报 success/failure，不靠印象。

### 三、本轮几个具体任务的坑（来自前两轮实测，先给你省时间）

**#32 余量**

- 判定「真重复」的标准是**内容集合完全相同**（可 re-export），**仅"有重叠词"不算重复**。审计文档已明确：风险等级 `none/low/medium/high/critical`（契约输出标签）vs `mild/moderate/high/critical`（分档阈值键）是**不同语义体系**，机械合并会改行为 —— 属业务决策，不要动。
- 文件名清洗 12 处：先判 3 个清洗实现（`admin.py:42`、`reports.py:141`、`user_risk.py:24` 的 `_sanitize_filename`/`_safe_export_filename`/`_SAFE_FILENAME_RE`）是否语义等价。`gdpr.py:182/295` 两处**无清洗痕迹**，是文件名注入面 —— 这可能是真缺陷而非去重项，优先取证。
- CSV 转义：4 处内联重复转义链（`PhysioTab.vue:314`、`useTextPredictionHistory.ts:130`、`MisclassifiedTable.vue:157`、`usePredictionHistory.ts:74`）。`MisclassifiedTable.vue:157` 的 `csvEscape` **连 `sanitizeCellForExcel` 都没调**，只做了引号转义 → 公式注入面实锤，优先改。
- 角色定义 57 处：`contracts.py` 的 `USER_ROLE_*` 是唯一 SSOT。注意 `require_role("counselor")` 里**路由 prefix/tag 名也是字面量**，与角色语义不同 —— 不要一起收编。#37 与此项重叠，若本轮做 37 就一起收口。
- 模型元数据 145 处引用：绝大多数是 `model_version` 字段**传递**，不是重复定义。别被数量吓退，先按"定义处 vs 引用处"分类再判断。

**#33**

- `counselor_service_user.py:70` 那条注释已自承「无任何租户条件」，属于上一轮闸门可能漏到的洞，先确认是否被 `tenant_guard` 覆盖。
- `ip_address` 取值要从 request 拿，**测试里要真造 client host**，不能写死。

**#35**

- 反向参考：`alerts.py:59-69` 是仓库里已有的"失败必须 raise"正面样板，对齐它。
- metric 要有真实埋点，不能只加一行计数器了事而没人消费 —— 至少保证能被 `/metrics` 端点暴露出来。

**#40**

- `promtool` 可能不在本机 PATH。若不可达，**如实记账**并改用可离线验证的等效断言（规则表达式语法子集 + exposition 用 `prometheus_client.parser` 真实解析），不要伪造"已用 promtool 校验"。

### 四、交付要求

1. 审计清单文档（沿用 `docs/P2_XX_*.md` 命名与结构范式）。
2. 回退实验日志（沿用 `backend/scripts/rollback_p2_XX_result.log`）。
3. 新增闸门测试，命名沿用 `backend/tests/test_p2_XX_*.py` / `frontend/src/utils/*.test.ts`。
4. `docs/CODE_REVIEW_2026-10-11.md` 追加「第九轮」小节：改了什么 / 连带发现 / **实测读数** / 踩到的新坑 / **未验证如实记账**。不得修改上文任何历史快照。
5. 一轮一次提交 + 文档追记一次提交，推送后报 CI 结果。
6. 收尾回复里给我一份可点开的交付物清单。

### 五、验收判据（我用什么判断你真做了）

- 每条整改都有**可复现的失败案例**（回退实验日志能对上）。
- 每条断言都能回答"它凭什么这么判"，而不是断言源码字面。
- 报告里的每个数字都有来源，**没有 0、没有"应该没问题"**。
- 未完成的、没验证的、被否决的方案，都写在"未验证/记账"里，不许消失。

现在开始。先读文档，然后复述理解与计划。
