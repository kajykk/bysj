# 第十轮整改提示词（P2 收尾：#37 + #32 角色余量 + CSV 三处 + #38）

> 用法：新开一轮对话，把下面「提示词正文」整段粘贴进去即可。
> 本文件只是存档，正文以「提示词正文」小节为准。

---

## 提示词正文

接手 `E:\code\bysj` 的代码审查整改第十轮。全程用简体中文。

### 零、先读这些（按顺序，不要跳）

1. `.workbuddy/memory/MEMORY.md` —— 项目长期纪律（测试判据、Git 纪律、验证工具失效清单、前端基线读数）。**第一条「判据必须可客观断言」和「断言异常类型 ≠ 断言异常来源」必须逐字读完。**
2. `.workbuddy/memory/2026-10-13.md` —— 第七/八/九轮完整上下文，含所有已踩过的坑。
3. `docs/CODE_REVIEW_2026-10-11.md`：
   - 「P2（后续优化，消除系统性根因）」表格（714–727 行）= 全部待办原文；
   - 「系统性代码根因」六条；
   - 第七轮（1216 行起）/ 第八轮（1339 行起）/ **第九轮（1458 行起，含末尾两节「第九轮补」）**。
4. `docs/P2_09_ROUND9_AUDIT.md` —— 第九轮审计清单（本轮待办的来源）。
5. **特别注意**：第九轮末尾「第九轮补：E33 假闸门加固」那一节，是本轮方法上的硬约束，不是历史流水账。

**先复述一遍你读完的理解与本轮计划，再动手。** 计划里必须写明：本轮做哪几项、明确不做什么、每项的客观断言是什么、每个闸门打算怎么证明"它不是假闸门"。

### 一、本轮范围（已确认的剩余待办）

已闭环：P0 全部 10 项；P1 全部 #11–#30；P2 #31、#32（第一类 + 余量）、#33、#35、#39、#40（提交至 `721def3`，CI 10/10）。

剩余：

| # | 事项 | 规模（第九轮机制扫描实锤） | 本轮建议 |
|---|---|---|---|
| 37 | 前端抽 `isAdminRole()`/`isStaffRole()`；路由 `permissions` 补齐 + 静态检查 | 前端裸角色判定 **13 处 / 11 文件** | **必做** |
| 32 余量 | 后端角色字面量收编（`seed.py` + 服务层 `operator_role="..."`） | **25 处**（第九轮只改了 `review.py` 5 处） | **必做** |
| 32 余量 | CSV 三处内联链收敛到 `csvEscape` SSOT | 3 处（见下） | **必做** |
| 38 | 注释与实现一致性核查，固化为检查项 | 待扫描 | **必做** |
| 34 | 统一错误方言 `ServiceError(client_message, internal_detail)` + 中间件末道脱敏 | 待扫描（异常路径规模未知） | 第十一轮 |
| 36 | 前端抽 `useListQuery()` composable，覆盖 12 个列表页，约 700 行重复 | 12 页 | 第十一轮 |
| 33 余量 | 其余 63 处手写 `OperationLog(` 迁移到 `record_audit` | 64 处 / 已迁移 1 | 第十一轮 |
| 35 余量 | 其余 100+ 静默降级候选点接 `silent_degradation_total` | 119 候选 | 第十一轮 |
| 40 补 | `promtool check rules` 真校验（第九轮降级为 YAML 形状断言） | 若环境可得 | 顺带 |
| — | 仓库 Prettier 格式整理（CI 不检查） | 全仓 | 第十一轮 |

**推荐本轮做：#37 + #32 角色余量（后端 25 处 + 前端 13 处）+ CSV 三处 + #38。**

理由：这四项同属一个主题——**「字面量与注释跟实现的一致性」**，可以共用一套 AST/正则扫描器与同一份审计清单，一次收干净。而 #34 需要先对全仓异常路径做分类（规模未知、改动面大），#36 是 12 个页面的前端重构，两者单独一轮，避免与本轮前端改动叠加、污染前端基线（101 files / 1287 passed）。

组合不合适可以调整，但必须说明理由，**不得静默缩减范围**。

### 二、本轮必须遵守的纪律（前九轮用血换来的）

**验证纪律（最高优先）**

- 先实测再写断言。无真实来源的指标不上报，**绝不上报 0**。
- 整改前先做**机制扫描**（AST / 正则脚本），产出审计清单文档，再决定改什么。**审计与整改分开**，不要"扫一遍就顺手改"。
- 静态审计产物**必须在无源码变异窗口内生成**，否则产出同源伪影。
- **每个闸门都要做变异验证**：绕过/退化机制 → 必须变红 → 恢复 → 必须变绿。第九轮 4 个变异里 1 个暴露出假闸门（命中率 25%），只复跑测试会得到 100% 的绿、什么都发现不了。这是本轮的硬动作，不是可选项。
- **两条假闸门高发形态，写断言时主动避开**：
  - 断言"字符串存在"≠ 断言"被使用"（第八轮 E35：删掉行为、只留 import 行，测试恒绿）；
  - **断言异常类型 ≠ 断言异常来源**（第九轮 E33：只写 `pytest.raises(TypeError)`，把显式 `raise` 改成 `if False` 后仍绿，因为 `json.dumps(object())` 抛的也是 TypeError）→ **必须 `match=` 消息特征**。
- 判据的**语法形态覆盖要全**：`ast.Assign` / `AnnAssign` / `ast.Dict`（无 `targets` 属性，写了会 `AttributeError`）、`dict[int,str]` 键为 int、模块级常量、`if TYPE_CHECKING` 块、`@overload`。前两轮的假阴性全出在这上面。
- 扫描器报 0 时必须**造临时违规文件证明它能检出**，否则是假闸门。
- 写临时脚本用 Write 工具，**不要 bash heredoc**（会展开 `$var`）；改源文件前 `try/finally` 恢复保护。

**跑测试固定姿势**

```
cd backend && .venv/Scripts/python.exe -m pytest -o "addopts=--strict-markers --import-mode=importlib --cov=app --cov-report=xml:coverage.xml --ignore=functional_test.py --ignore-glob=test_result*.txt --ignore=test_final.txt" -p no:cacheprovider -q
```

- ❌ 不要覆盖 `addopts=`（丢 importlib → import file mismatch）；❌ 不要加 `--timeout`（缺插件）。
- **不在本机跑后端全量**（约 37 分钟/轮），**禁止并发跑其它 backend 测试**（共用 `test_app.db`）。以受影响文件集读数 + CI 全量兜底。
- 前端基线逐位比对：**101 files / 1287 passed / 4 skipped**，`vue-tsc --noEmit` **0 error**。改一个文件就多一个文件、加两条测试就多两条，数字对不上要解释。

**前端专项坑**

- Windows 下：`node_modules/.bin/vitest.cmd` 绝对路径（`npx` 在 subprocess 里 `FileNotFoundError`），前端路径先 `.resolve()`，subprocess 加 `encoding="utf-8"`。
- vitest 失败名三种格式都认：`FAILED <path>` / ` FAIL  <file> > suite > name`（捕获**整行**）/ `× name`（行尾带 `12ms`）。只认 `^FAILED` 会把红了的闸门判成"实验无效"。
- 驱动必须做 **anchor 校验**：变异 `old` 不在文件里当场抛错，不记成 INVALID。
- **改 `.vue` 的 import 前，必须先查文件内既有 import**。第九轮 `37b6e0f` 就是这个事故：在 157 行新增 import 而 130 行已有同名 import → rollup 报 Identifier already declared → lighthouse + frontend-coverage 两个 CI job 红。

**Git 纪律**

- 沙箱红线：❌ stash / rebase / branch / filter-repo 等一切 ref 重写；✅ fetch / push / status / log / add / commit / diff / grep。
- **显式逐文件 `git add <path>`**，不用 `-A .`。
- 一轮整改（源码 + 测试 + 实验脚本 + 文档）= **一次提交**；提交信息四段式：改了什么 / 连带修复 / 验证实测读数 / 未验证如实记账，**末段不得省略**。
- 判 push 成功必须匹配 `main -> main`，交叉核对 `gh api repos/…/commits/main`。
- 推完用 `gh api repos/…/commits/<sha>/check-runs` 确认 CI。**逐提交查**，不要只看最终 HEAD —— 第九轮就是在这里把两轮的因果串成了一轮（7bc85e8 是 lighthouse+frontend-coverage 红，backend-coverage 的 prometheus_client 红在 37b6e0f）。CI 10 个 job，逐个报 success/failure。

### 三、本轮任务的坑与已知线索（省时间，但都要自己复核）

**#37 前端角色 helper**

- ⚠️ **前端已有权限基础设施，先读再动手，别重复造轮子**：`frontend/src/config/permissions.ts`（72 行，含 `PAGE_PERMISSIONS` / `OPERATION_PERMISSIONS` / `ROLE_PERMISSIONS` / `hasPermission`）、`routeAccess.ts`（21 行）、`permissions.alignment.test.ts`（35 行，已做对齐检查）。本轮是**扩展既有设施**还是**补齐缺失**，先给结论。
- 裸判定散落在 11 个文件（实测）：`BottomNav.vue`、`HelpCenter.vue`、`useLayoutMenu.ts`、`MainLayout.vue`、`router/guard.ts`、`ForbiddenPage.vue`、`CounselorReviewListPage.vue`（第 285 行 `auth.role === 'admin' || auth.role === 'super_admin'`）、`LoginPage.vue`、`EvalResultCard.vue`、`useModelTrainingData.ts`、`ProfileCard.vue`。
- 判据要小心：`require_role("counselor")` 里的**路由 prefix / tag 字面量与角色语义不同**，不要一起收编（第九轮已确认）。前端同理，`path: '/admin'` 不是角色。
- 权限模型收益 < 成本是项目既有结论之一（见 MEMORY.md 六条根因第 6 条），所以#37 的价值在**消除散落判定**，不在重构权限体系 —— 别做超范围设计。

**#32 后端角色余量（25 处）**

- `operator_role="counselor"` / `"admin"` 集中在 `counselor_service_*.py`（binding/consultation/group/user/warning）、`admin_service_log.py`、`admin_service_stats.py`、`anomaly_detection_service.py`、`review_service.py:320`、`seed.py`。
- 注意 `admin_service_log.py:137-150` 那批是**SQL 过滤条件 + label 名**，两个用途混在一起，收编时要分清。
- `seed.py:605/808` 是造数脚本，改不改要说明。
- 唯一 SSOT 是 `app/core/contracts.py` 的 `USER_ROLE_*` 模块常量（101–104 行）。

**#32 CSV 三处收敛**

- 具体位置：`PhysioTab.vue:314`、`useTextPredictionHistory.ts:130`、`usePredictionHistory.ts:74`。
- 这三处**语义已等价、无注入面**（已调 `sanitizeCellForExcel` + 引号转义），本轮是纯去重，不是修缺陷 —— 别在报告里写成"修复注入"。
- SSOT 是 `exportUtils.ts` 第 48 行的 `export const csvEscape = toCsvCell`（第九轮新增别名）。

**#38 注释与实现一致性**

- 判据建议：**注释所述行为必须有测试或调用点支撑**。先把"注释"限定为可机械判定的子集（如 `# XXX 修复：` / `ISS-xxx` / `P0-x` / 断言性描述），不要贪多，否则噪声淹没信号。
- 仓库已有 `RES-P1-004` 这类书面保留依据的写法，遇到"有注释但看起来是死代码"的点，先查是否有登记依据，别当死代码删。

**#40 补（顺带）**

- `promtool` 大概率仍不在 PATH。**若不可达就如实记账**，不要伪造"已用 promtool 校验"。九轮已用 YAML 形状断言兜底。

### 四、交付要求

1. 审计清单文档（沿用 `docs/P2_XX_*.md` 命名与结构范式）。
2. 回退实验日志（沿用 `backend/scripts/rollback_p2_XX_result.log`），**每个闸门一条变异记录**。
3. 新增闸门测试，命名沿用 `backend/tests/test_p2_XX_*.py` / `frontend/src/**/*.test.ts`。
4. `docs/CODE_REVIEW_2026-10-11.md` 追加「第十轮」小节：改了什么 / 连带发现 / **实测读数** / 踩到的新坑 / **未验证如实记账**。**不得删改上文任何历史快照**；发现上文有误时，用**追加更正**的方式（第九轮就是这么处理的）。
5. 一轮一次提交 + 文档追记一次提交，推送后逐提交报 CI 结果。
6. 收尾回复里给我一份可点开的交付物清单。

### 五、验收判据（我用什么判断你真做了）

- 每条整改都有**可复现的失败案例**（回退实验日志能对上），且**每条闸门都做过变异验证**。
- 每条断言都能回答"它凭什么这么判"，而不是断言源码字面；异常断言都带了 `match=`。
- 报告里的每个数字都有来源，**没有 0、没有"应该没问题"**。
- 前端测试数与文件数能与基线逐位对上（101 / 1287 / 4）。
- 未完成的、没验证的、被否决的方案，都写在"未验证/记账"里，不许消失。

现在开始。先读文档，然后复述理解与计划。
