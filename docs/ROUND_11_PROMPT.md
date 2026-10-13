# 第十一轮整改提示词（P2 收尾：#34 + #36 + #33/#35 余量 + 类型存量）

> 用法：新开一轮对话，把下面「提示词正文」整段粘贴进去即可。
> 本文件只是存档，正文以「提示词正文」小节为准。

---

## 提示词正文

接手 `E:\code\bysj` 的代码审查整改第十一轮。全程用简体中文。

### 零、先读这些（按顺序，不要跳）

1. `.workbuddy/memory/MEMORY.md` —— 项目长期纪律。**本次新增两条必须逐字读完**：(a) 每采用一个质量指标，先造一个已知错误证明它能检出（`vue-tsc --noEmit` 根配置只查 `env.d.ts` 的教训）；(b) 解析文本计数的门禁要用目标编码的真实输出验一遍（UTF-16 落盘按 utf8 读会解析出 0 错误而假绿）。
2. `.workbuddy/memory/2026-10-13.md` —— 第七至十轮完整上下文。
3. `docs/CODE_REVIEW_2026-10-11.md`：
   - 「P2（后续优化，消除系统性根因）」表格（714–727 行）= 全部待办原文；
   - 「系统性代码根因」六条；
   - 第十轮小节 + 「第十轮补」两节 = 上轮做法、已踩的坑、独立复核翻出的 `BottomNav` 与 `vue-tsc` 两件事。
4. `docs/P2_10_ROUND10_AUDIT.md` —— 第十轮审计清单（含豁免表：`require_role` 参数 / `target_type` / dict 键 / 类型声明 / 路由 path，**本轮不得推翻这些豁免**，有异议用追加更正）。
5. `frontend/scripts/vue-tsc-baseline.mjs` —— 头部注释（决策四：45 存量增量门禁的由来与棘轮规则）+ `BASELINE = 45` 当前值。

**先复述一遍你读完的理解与本轮计划，再动手。** 计划里必须写明：本轮做哪几项、明确不做什么、每项的客观断言是什么、每个闸门打算怎么证明"它不是假闸门"、本地验证命令与 CI 的对应关系（裸命令一律禁用，写出每条本地命令对应的 CI job）。

### 一、本轮范围（已确认的剩余待办）

已闭环：P0 全部；P1 全部；P2 #31、#32（见下方措辞警告）、#33（helper 本体）、#35（metric 本体）、#37、#38、#40（YAML 断言层）。提交至 `3b1260a`，CI 10/10。

> ⚠️ **本清单已被独立复核抓出两处失实（第 39 项与 #32 措辞），开工前必须自己再抽验一遍**（判据见第五节第 6 条）。不要默认清单为真——清单写错会直接导致整项漏做。

**已复核属实的读数（可直接引用）**：CI 10 个 job（coverage-summary / frontend-coverage / backend-coverage / contract-test / lighthouse / Check Deployment Window / harness / Gitleaks Secret Scan / E2E Full Stack / Gitleaks Full History Scan）；前端基线 102 files / 1291 passed / 4 skipped；类型 42/45（`npm run typecheck`）；`OperationLog(` 命中 64 处 = 63 构造点 + 1 模型定义（`models/admin.py:47`）；#35 候选 119（`P2_09_ROUND9_AUDIT.md:51` 口径，我的更宽口径 222/含 ImportError 21，两者判据不同、不矛盾）；prettier 有 `.prettierrc`/`.prettierignore`/`format:check` 但 **workflow 未调用**，CI 确不检查。

剩余：

| # | 事项 | 规模（已知信息） | 本轮建议 |
|---|---|---|---|
| 34 | 统一错误方言 `ServiceError(client_message, internal_detail)` + 中间件末道脱敏 | 全仓异常路径，规模未知，**先分类审计再分批** | **必做（审计 + 第一批）** |
| 36 | 前端抽 `useListQuery()` composable（竞态守卫 + 页码重置 + 三态），覆盖 12 个列表页 | 12 页，约 700 行重复 | **必做** |
| 33 余量 | 其余 **62** 处手写 `OperationLog(` 迁移到 `record_audit` | 64 命中 = 63 构造点 + 1 模型定义（`models/admin.py:47`）；已迁移 1（`gdpr.py:271`）⇒ 余量 62，不是 63 | **必做（分批，未必全迁完，迁不完记账）** |
| 39 | **删除死代码**：`ExperimentTab.vue` 的 `bertDisabled` 分支、`observability_service._flushed_buffer`、以及仍无引用方的死组件 | 实测**完全未做**：`bertDisabled` 11 处（含 `ExperimentTab.vue:339 const bertDisabled = true` + 2 个死分支 + 4 处模板绑定 + 2 语种 i18n）；`_flushed_buffer` 11 处（7 处代码，注释自承"在生产中属于死缓冲区"） | **必做**（本轮最高性价比，且是根因④"注释与实现不符"的活标本） |
| 35 余量 | 其余 100+ 静默降级候选点接 `silent_degradation_total` | 119 候选（含 `ImportError` 特性探测噪声） | **必做（分批，先真降级点）** |
| 类型存量 | `DefaultRow` 家族 42 错（基线 45，余量 3），`npm run typecheck` 实测 | 15 个未动文件；`UserRiskPage` 另 1 族 | **顺带收敛 + 按棘轮调低 BASELINE** |
| 40 补 | `promtool check rules` 真校验 | 若环境可得；不可达如实记账 | 顺带 |
| — | 仓库 Prettier 格式整理（CI 不检查） | 全仓；第九轮已定性为存量问题 | 做（独立提交，与整改提交分开） |

**推荐本轮做：#39（先做，小且干净）+ #36 + #33 余量第一批 + #35 余量第一批 + #32 矛盾裁定 + 类型存量收敛 + prettier；#34 只做分类审计 + 第一批（如登录/鉴权等高危路径），剩余改动面留第十二轮。**

理由：#39 是被清单遗漏、实测完全未做的一项，改动面小（`bertDisabled` 分支 + i18n 词条 + `_flushed_buffer`）且是根因④的活标本，性价比最高，应最先收掉；#36 是 12 页前端重构，与 #34 后端异常体系无文件重叠，可并行；#33/#35 第一批与 #34 审计共用"异常/降级路径"扫描器，一次扫全、改两批；#32 矛盾裁定是纯取证、几乎零改动，但能防止下一轮继续基于错误结论跳过；类型存量 42 错是独立文件集（紧跟 #36 的前端改动一起验，防 #36 新增类型错）；prettier 单独提交、不污染整改 diff。#34 全量改动面大（异常抛出点 + 中间件 + 前端错误映射），必须分两轮，这是第九轮就定下的分批原则。

若 #36 与其余项叠加后单轮过大，**优先砍 #36 的页数（12 页 → 收 6 页），不要砍 #39**。

组合不合适可以调整，但必须说明理由，**不得静默缩减范围**。

### 二、本轮必须遵守的纪律（前十轮用血换来的，逐条照做）

**验证纪律（最高优先）**

- 先实测再写断言。无真实来源的指标不上报，**绝不上报 0**。
- 整改前先做**机制扫描**（AST / 正则判据脚本），产出审计清单文档，再决定改什么。**审计与整改分开**，不要"扫一遍就顺手改"。
- 每项整改做**回退对照实验**：临时变异源码 → 闸门必须变红 → 恢复 → 必须变绿。日志落盘 `backend/scripts/rollback_p2_11_result.log`，**每个闸门一条变异记录**。
- 闸门必须**反向也验**：绕过机制 → 红；机制本身能测到（造临时违规文件证明扫描器非"报 0"型假闸门）。
- 异常断言一律带 `match=` 消息特征（E33：断言类型 ≠ 断言来源）；存在性断言必须同时断言被使用（E35：`test_constants_actually_used` 范式）；计数棘轮的增减必须同步审计文档（#38 范式）。
- **本地命令必须与 CI 同构**：前端类型检查只用 `npm run typecheck`（`-p tsconfig.app.json`）或基线脚本 spawn 模式；**禁用裸 `vue-tsc --noEmit`**（根配置只查 `env.d.ts`）。核验失败清单**不得 `grep|head` 截断**，完整落盘再计数。
- 新质量指标先证伪：先造已知错误证明它能红，再用它判通过。
- pytest 固定姿势：`cd backend && .venv/Scripts/python.exe -m pytest -o "addopts=--strict-markers --import-mode=importlib --cov=app --cov-report=xml:coverage.xml --ignore=functional_test.py --ignore-glob=test_result*.txt --ignore=test_final.txt" -p no:cacheprovider -q`。全量约 37 分钟，不并发跑其它 backend 测试。
- 前端基线逐位比对：**102 files / 1291 passed / 4 skipped**（第十轮实测），`vue-tsc -p tsconfig.app.json` 错误数基线 **42/45**。

**Git 纪律**

- 沙箱红线：只做 `fetch/push/status/log/add/commit/diff/grep`，不碰 stash/rebase/branch/filter-repo 与 git config。
- 一轮整改（源码+测试）= 一次提交；prettier 独立一次提交；文档追记一次提交；**显式逐文件 `git add`**，提交信息固定四段（改了什么/连带修复/验证实测读数/未验证如实记账）。
- 推送后用 `gh api repos/kajykk/bysj/commits/<sha>/check-runs` 逐个报 10 个 job（`gh run list --commit` 与 job 名 ≠ 工作流名均不可靠；允许 `gh run rerun --failed` 处理性能抖动类红，但必须先取证红因与本轮无关）。

### 三、本轮几个具体任务的坑（实测沉淀，先给你省时间）

**#39 死代码（清单遗漏项，实测未做）**

- `ExperimentTab.vue`: `const bertDisabled = true`（:339）+ `:342`/`:363` 两个死分支 + `:83/:84/:92/:93` 四处模板绑定 + `i18n/locales/{zh-CN,en-US}/user.ts:988` 两处词条 → 一并删除。**只删常量会留下死分支**，这是"删了一半"的典型形态，按整条链路删。
- `observability_service.py`: `_flushed_buffer`（:99 初始化、:143-147 写入、:167-170 读取）+ 相关注释。该注释**自承"在生产中属于死缓冲区"**——正是根因④"注释与实现不符比缺注释更危险"的活标本，删完顺手在追记里记一笔这类自承型注释。
- `BottomNav.vue`：语法已于 `28d531b` 修好，但**仍是死组件**（无 import 方，不在构建图内）。**本轮必须给出处置结论**（删除，或补引用 + 保留 `test_no_import_inside_import_block` 回归闸），不能继续让它游离在所有检查之外。
- 判"死组件/死分支"**必须全仓 import 扫描 + 模板引用扫描**，`components.d.ts` 只是自动生成声明，不能证明被使用。

**#32 两处需先裁定（措辞与矛盾）**

- **文件名清洗不是"已闭环"，是"审计豁免"**：第九轮定性为 3 实现语义不等价、机械合并会改端点行为（`admin.py:42` / `reports.py:141 _safe_export_filename` / `user_risk.py:24`，白名单与回退名不同），`gdpr.py:183/295` 文件名由 int id + uuid 切片构成、无注入面。⇒ **这是"不合并"的业务决策 + 记账，不是去重完成**。若本轮要收，路径是先统一清洗策略（业务决策），不是改代码；维持豁免则必须在审计文档里写清依据（与 #31 豁免登记同纪律）。
- **模型元数据存在审计结论与审查原文的硬矛盾**：`P2_09_ROUND9_AUDIT.md:15/39` 称"145 处几乎全是 `model_version` 字段传递，无第二定义处，不建 SSOT"；但 `CODE_REVIEW_2026-10-11.md:195/651` 原文说"模型元数据 3 份：`MODEL_PATHS` / `MODEL_COMPATIBILITY_REGISTRY` / registry_v2 JSON"。实测三者**都还在**（`model_engine/loading.py:40` 引 `MODEL_PATHS`、`model_compatibility.py:42` 定义 `MODEL_COMPATIBILITY_REGISTRY`、`model_registry_v2` 被 `model_predict/registry.py` 4 处引用）。⇒ 审计那条结论很可能只扫了 `model_version` 单一关键词。**本轮先裁定这一矛盾**（用追加更正，不得删改原文），再决定要不要建 SSOT。
- 同类参考：风险等级两套标签混用实测仍在（`model_engine/risk.py:97` 返回 `"medium"`，而 `core/risk_thresholds.py:9-17` 用 `mild`/`moderate`），与原文"low/medium vs mild/moderate"吻合，可一并裁定。

**#36 `useListQuery`**

- 12 个列表页先扫出"竞态守卫/页码重置/三态"三要素缺失矩阵再动手；一次只收 2–3 页、每批独立验证，不要 12 页一个提交。
- `BottomNav.vue` 是**死组件**（无 import 方，不在构建图内）——动它之前先确认它是否仍是死的；任何改动必须配文本级回归闸（如 `test_no_import_inside_import_block` 范式），因为构建/测试/CI 全碰不到它。
- 改 `.vue`/`.ts` 的 import 时，**先读全文件既有 import 块**：applier 三次把 import 插进多行括号块内部（`37b6e0f`、`7c7756f`、BottomNav）。多行 `import {` 块必须用 AST 或手改，禁用"末行启发式"。

**#34 错误方言**

- 先分类：用户可读错误 vs 内部错误 vs 透传第三方错误；`ServiceError` 只管前两者的边界，**不要把所有 `raise HTTPException` 一次全改**。
- 中间件末道脱敏必须有"脱敏前后对照测试"（原始内部信息进、通用文案出），而不是断言中间件存在。

**#33 余量**

- `record_audit` 的 `tenant_id` 必填、`ip` 取自 request 是硬约束；迁移时遇到"无 request 上下文"的调用点（如 Celery 任务内），按 helper 文档走 `request=None` + `no_request` 标记，不要手填 ip。
- `admin_service_log.py` 的 SQL 统计行与 `target_type="user"` 豁免仍在，不要顺手"统一"掉。

**类型存量 42 错**

- 全是 `DefaultRow` 泛型家族 + `UserRiskPage`，与第十轮文件集零重叠。修一个文件验一个文件；错误数每降一档就把 `BASELINE = 45` 同步调低（棘轮，脚本头部有规则）。
- `components.d.ts` 只是自动生成的类型声明，不能证明组件被使用；判"死组件"必须用全仓 import 扫描。

**prettier**

- 独立提交、`--write` 后必须重跑前后端全量（格式提交也可能打碎模板表达式），CI 不检查不等于不验证。

### 四、交付要求

1. 审计清单文档（`docs/P2_11_*.md` 命名与结构范式，含 **"已闭环"清单抽验表** + #34 分类表 + #36 缺失矩阵 + **#39 死代码全链路清单** + **#32 矛盾裁定结论** + 豁免表）。
2. 回退实验日志（`backend/scripts/rollback_p2_11_result.log`），每个闸门一条。
3. 新增闸门测试（`backend/tests/test_p2_11_*.py` / `frontend/src/**/*.test.ts`），异常断言带 `match=`。
4. `docs/CODE_REVIEW_2026-10-11.md` 追加「第十一轮」小节（改了什么 / 连带发现 / **实测读数** / 新坑 / **未验证如实记账**），不得改历史快照；**本地验证命令与 CI job 的对应表**必须写进小节。
5. 一轮一次整改提交 + prettier 独立提交 + 文档追记一次提交，推送后逐提交报 CI 结果。
6. 收尾回复里给我一份可点开的交付物清单。

### 五、验收判据（我用什么判断你真做了）

- 每条整改都有**可复现的失败案例**（回退日志能对上），每条闸门都做过变异验证。
- 每条断言都能回答"它凭什么这么判"；异常有 `match=`；存在性断言同时断言被使用。
- 报告里的每个数字都有来源（全量落盘计数），**没有 0、没有"应该没问题"**。
- 前端测试数/文件数与基线逐位对上（102 / 1291 / 4 为起点）；类型错误数只降不升且 BASELINE 同步收紧。
- 未完成的、没验证的、被否决的方案，都写在"未验证/记账"里，不许消失。
- **开工前先抽验"已闭环"清单**（本轮复盘中该清单被抓出 2 处失实，其中 #39 整项漏做）。做法：对清单里每一项跑一条独立判据（grep 计数 / 文件存在性 / 调用点扫描），把实测数写进审计文档；**与清单不符的按"追加更正"处理，不得删改清单原文**。这一步不做完不许动手整改。

现在开始。先读文档，然后复述理解与计划。
