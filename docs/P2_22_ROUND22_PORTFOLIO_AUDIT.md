# P2-R22（ROUND_22）：作品集化——把工程资产变成可读的对外材料

> 日期：2026-10-20｜基准 HEAD：`ae998eb`（= origin/main，开工时 `git diff | wc -c` = 0）
> 边界：**只做呈现层**。不改任何模型 / 接口 / 配置行为；不改既有源文档的数字与结论，
> 只在其头部加一条指向对外材料的链接。
> 铁律：对外材料里的每个数字都要能复现；不得隐藏负面发现；文档改动也要有自检。

---

## 〇、开工前置（先实测）

1. **HEAD 与工作区**：`git rev-parse HEAD` = `ae998eb` = `origin/main`；`git diff` = **0 字节**。
   `git status` 有 75 行 `M`，按仓规用 `git hash-object` 逐文件比对，真实差异只有 7 个运行时
   产物（`pool*.json` / `leak_delta*.json` / `verify_p2_35_batch34_result.json`），按入库惯例不入库。
   > 提示词写的基线是 `9b8fb25`，实际已在 ROUND_17（`5c60b05`）与 ROUND_18（`ae998eb`）之后，
   > 本轮以实际 HEAD 为准。
2. **通读 5 份源文档**：`EVALUATION_INTEGRITY_REPORT.md`、`ML_LEAKAGE_AUDIT.md`、
   `ML_LEAKAGE_REMEDIATION.md`、`planning/P2_R15_EARLY_DETECTION_RESULT.md`、
   `planning/P2_R15_CLINICAL_READINESS.md`。
3. **README 既有数字逐项复测**（结果见 §五，发现 8 处不一致并修正）。

---

## 一、T1：一页式概览（README 顶部）

新增 `## 60 秒概览`，把原来「一眼看懂 + 项目亮点」两段合并重写，结构固定为四问：

| 段落 | 内容 | 目的 |
|---|---|---|
| **是什么** | 一句话定位 + 三角色工作台 + 闭环 | 60 秒内知道这是什么 |
| **难在哪** | 三个"不会报错"的坑：评估口径泄漏 / 静默降级 / 鉴权入口漏配 | 说明难点不在功能而在可信度 |
| **怎么证明** | 4 个技术亮点，各配 1 个可复现数字 + 一个命令 | 每个数字都能自己跑 |
| 流向图 | mermaid `flowchart LR`：信号 → 融合 → 分级 → 预警 → 复核 → 升级/复盘 + 三条虚线（治理/可观测/验证） | 一图看完整链路 |
| 最短跑起来 | 4 条命令（Redis → 后端 → 前端）+ 指向部署指南 | 降低上手门槛 |
| 文档索引 | 7 行"想了解什么 → 看哪份" | 让深读者按需深入 |

**4 个亮点与数字出处**（数字都不是新编的，全部来自仓库内产物）：

| # | 亮点 | 数字 | 出处（可执行） |
|---|---|---|---|
| 1 | 完整闭环 | 206 REST + 3 WebSocket、39 张表 | `app.routes` 运行时计数；`__tablename__` AST 计数 |
| 2 | 评估可信度 | 40 个交付脚本 / 88 处调用点；F1 0.5864 vs 0.9964 | `leakage_audit_scan.py`（git ls-files + AST）；`backend_text_bilingual_v2_metrics.json` |
| 3 | 静默降级 | 341 处 except 候选全裁定（109/116/8） | `classify_p2_35_batch6_result.json` + `test_p2_11` 棘轮 |
| 4 | 认证入口 | 8 个 token 入口（6 强制 + 2 豁免） | `test_p2_41_round17_auth_gate.py` 的 `REGISTRY`（AST 读取） |

> 亮点 2 特意写了两个数（0.5864 / 0.9964）而不是只写高的那个：
> **只报 0.9964 就是本项目花一整轮去治理的那种虚高**。

---

## 二、T2：评估可信度一页摘要

新增 `docs/EVALUATION_TRUST_SUMMARY.md`。结构：一句话（约 160 字）+ 一张五段主线表 + 三条"不好看但必须留"的记录。

主线表按「发现 → 量化 → 补救 → 上闸门 → 自查」五段，每段给"做了什么 + 硬读数"：

| 阶段 | 硬读数 |
|---|---|
| 发现 | 40 个交付脚本 / 88 处调用点；口径修正两次（28→118 漏扫、42→39 未入库）均记账 |
| 量化 | ΔF1 +0.3111 / ΔAUC +0.1573；L4 特征 corr=1.0、单特征 AUC 1.0000 |
| 补救 | 10 处更正；逐条核对后 **0 个 go/no-go 决策被推翻** |
| 上闸门 | 7 条断言 + 3 个真实变异（红 → 还原绿） |
| 自查 | 阴性：ERDE50 0.1958 vs 0.0052、F_latency 0.5820 vs 0.6721 ⇒ 不进主路径 |

**负面/反例全部保留**（这是本轮明确要求，也是摘要的价值所在）：

1. 自己项目踩过的坑：随机划分 0.9964 vs 按人分组 0.5864（差 0.41）；
2. 反例推翻直觉：mmpsy 55.9% 重复行，实测 **ΔAUC = 0.0000**（天花板效应，不是没泄漏）；
3. 阴性结论：学习式停止两向均不达标，**不做参数自救**，并标注基准过易、结论不可外推。

---

### 二·补、T5（可选）：作品集素材

README 新增「作品集素材（问题 → 动作 → 可验证结果）」四条，**只复用已钉数字、不引入新事实**：
其中三条分别复述审计面（40/88）、降级分桶（341）、鉴权入口（8），第四条报自己的检查条数
（21，由 `len(CHECKS)` 自指计算）。四条各配一条检查，写入 README 时若打错一个数字，
闸门同样会红。

## 三、T3：演示脚本（一条命令跑通最小闭环）

`backend/tests/tools/portfolio_demo.py`：

```
[1/3] 审计  git ls-files + AST → 40 个交付脚本 / 88 处调用点
[2/3] 闸门  泄漏守卫 + 鉴权入口闸门 + 文档数字自检 → 29 passed
[3/3] 变异  清空 LABEL_DERIVED_FEATURES → 2 failed（RED，符合预期）→ 还原 → 7 passed
DEMO OK
```

设计要点：

- **复用同一份口径**：第 1 步直接调 `check_portfolio_numbers.probe_scan()`，不重新实现扫描
  （否则演示脚本自己就成了"第二套真相"）。
- **变异必须指名**：不只判 returncode≠0，还要求失败信息里出现目标用例（此处是 G5 类）。
- **安全还原**：先留字节快照，`try/finally` 还原，收尾比对字节一致；Ctrl-C 也会走 finally。
- 实测耗时约 **85 秒**（2026-10-20 本机），不需要 Redis（这 3 个文件不碰 DB）。

---

## 四、T4：数字一致性自检（文档钉事实）

### 4.1 脚本与闸门

| 产物 | 作用 |
|---|---|
| `backend/tests/tools/check_portfolio_numbers.py` | 21 条检查；`--show` 可打印各探针算出的真值 |
| `backend/tests/test_p2_46_round22_portfolio_docs.py` | 把检查接进 CI（7 条：全量核对 / 反弱化 / 3 条自证 / 2 条测量纪律） |
| `backend/tests/tools/mutate_p2_46_round22.py` | 4 处真实变异 + 日志入库 |

**两类探针**（在文档里也写明了，避免"假装能复算"）：

- `probe`（**18 条**）：现场从代码 / 测试 / JSON 算出真值——路由数、文件数、表数、
  扫描入口数、桶计数、鉴权入口数、文本双口径 F1；
- `report`（**3 条**）：数字源头是需要数据集才能重跑的实验（ΔF1/ΔAUC、单特征 AUC、
  ERDE/F_latency），CI 无数据集，**判据改为"概览层 == 权威报告"的跨文档对齐**，
  不伪装成"我能重算"。

### 4.2 判据强度

每条检查钉的是**带单位的完整字面量**，例如
`40 个交付脚本 / 88 处划分与挑优调用点`、`341 处 except 候选全部裁定：已接线 109 / 真降级留档 116 / fail-closed 8`。

不钉"文档里出现过 88 这个数字"：后者会被页面别处的同值命中，改了真地方也不会红——
这是本仓"断言钉结构、不钉孤立字面量"纪律在文档侧的延伸。

### 4.3 21 条检查清单

| 文档 | 检查项 | 条数 | 类型 |
|---|---|---|---|
| README | 206 REST + 3 WS；39 张表；40/88 入口；F1 0.5864（随机 0.9964）；341 桶计数三拆；8 个 token 入口（6+2） | 6 | probe |
| README | 规模块：49 路由 / 66 服务 / 69 核心 / 29 ML / 39 表声明 / 运行时 206+3 / 9 Docker | 7 | probe |
| 摘要 | 40/88 入口（与 README 同一探针，措辞不同故单列） | 1 | probe |
| 摘要 | ΔF1 + ΔAUC / 单特征 AUC / ERDE 与 F_latency 四数 | 3 | report |
| README | 作品集素材 4 条（审计面 / 降级分桶 / 鉴权入口 / 自检条数） | 4 | probe |
| **合计** | | **21** | 18 probe + 3 report |

### 4.4 刻意不纳入闸门的数字

**测试用例数**（7,455 后端 / 1,327 前端）：每次提交都在变，钉死会把闸门变成噪声。
README 里以"带日期的快照 + 复现命令"呈现，并在同一行写明"不入数字闸门"。
这是**显式排除并给出理由**，不是"数字太少抓不到"。

### 4.5 自证（闸门有效性）

测试文件里带 3 条自证：把 README/摘要复制到临时目录、改坏一个数字，
再要求 `run_checks()` **指名**报出对应检查编号。这三条保证"闸门会红"不依赖外部变异脚本。

另有 2 条**测量纪律**用例（2026-10-20 CI 红项后补，见 §八）：路由计数不得读进程内
`app.routes`（污染注入后读数必须不变）、子进程失败必须抛错而不是报 0。

### 4.6 真实变异（4/4 RED-OK）

日志：`backend/tests/tools/mutate_p2_46_round22_result.log`

| 变异 | 内容 | 结果 |
|---|---|---|
| T1 | README `**341 处 except 候选**全部裁定` → `342`（锚点含强调符，故整句唯一） | 红，且指名 `[readme.buckets]` |
| T2 | 摘要 `ΔAUC +0.1573` → `+0.1574`（末位改一位） | 红，且指名 `[summary.delta_f1]` |
| T3 | README `88 处划分与挑优调用点` → `188 处` | 红，且指名 `[readme.scan]` |
| T4 | `probe_routes` 由「子进程数」翻回「进程内数」 | 红，且由隔离用例 `test_route_probe_isolated_from_in_process_app_state` 指名 |

`residual_clean=True`、`final_green=True`、`all_red_ok=True`（还原后 7 passed）。

---

## 五、README 既有数字核对与修正（发现 8 处不一致）

| 项 | 旧读数（2026-09-23） | 本轮实测（2026-10-20） | 口径 |
|---|---|---|---|
| REST 端点 | 191 | **206** | FastAPI 运行时 `APIRoute` 计数 |
| WebSocket | 3 | 3 | `starlette` `WebSocketRoute` 计数 |
| API 路由文件 | 50 | **49** | `backend/app/api/**/*.py` |
| 业务服务文件 | 62 | **66** | `backend/app/services/**/*.py` |
| 核心模块文件 | 61 | **69** | `backend/app/core/**/*.py` |
| ML 模块文件 | 27 | **29** | `backend/app/ml/**/*.py` |
| 数据表 | 40（代码 39 + 生产库 40） | **39** | AST `__tablename__` 声明数 |
| Docker 服务 | 9 | 9 | `docker-compose.yml` services 段 |
| 后端用例 | 6,160 | **7,455** | `pytest --collect-only -q` |
| 前端用例 | 1,119 | **1,327** | `npx vitest list \| wc -l` |

处理方式与边界：

- 全部替换为实测值，并把**复算口径写进括号**（旧读数没写口径，无法判断是"增长"还是"口径不同"）。
- 「生产库实测 40 张表」这一条**不再对外声称**：它需要跑起来的 PostgreSQL，本轮没复现，
  不能把无法复算的数字留在对外材料里。代码声明数 39 可离线复算，因此只报 39。
- 上一版读数与差异原因以引用块形式留在 README 里（不删历史，标明"本轮按实测更新"）。

---

## 六、未验证 / 边界（不乐观推断）

1. **渲染未在 GitHub 上验证**：mermaid 图与表格锚点（`#60-秒概览`、`#文档索引`）只在本地
   markdown 校验过，GitHub 的锚点规则（中文标题的 slug）未实测；若链接失效，属呈现缺陷。
2. **report 类 5 条检查只做跨文档对齐**，不重算实验：ΔF1/ΔAUC 与 ERDE 需要数据集/仿真器重跑，
   CI 无数据。若权威报告本身写错，闸门会一起错——这是该类的已知上限，已在脚本 docstring 写明。
3. **`40 个交付脚本 / 88 处调用点` 只统计 git 跟踪的 `.py`**：新增未入库脚本不计入；
   入库后扫描器会变，闸门会红并强制更新文档（与 `test_p2_38` 的 G4 棘轮同源）。
4. **数字闸门不覆盖源文档**（`EVALUATION_INTEGRITY_REPORT.md` 等）：它们是历史快照，
   按仓规只追加不改；本轮仅在头部加链接。注意其摘要写的是 `39 文件 / 87 入口`
   （ROUND_16 增补 `fusion_ablation.py` 前的基线），与当前 40/88 的差异已由
   `ML_LEAKAGE_AUDIT.md` §四补记解释，本轮**不改原文**。
5. **前端用例数取 `vitest list` 的行数**：按测试名计数，与 `--reporter=json` 的
   `numTotalTests` 可能有 ±1 的差别（末尾换行），量级无影响。
6. 未跑 37 分钟全量后端套件；受影响集与 CI 结果见提交说明。

---

## 七、产物清单

| 产物 | 说明 |
|---|---|
| `README.md`（改） | 新增 60 秒概览 / 流向图 / 最短跑起来 / demo / 文档索引；规模数字按实测更新 |
| `docs/EVALUATION_TRUST_SUMMARY.md`（新） | T2 一页摘要 |
| `backend/tests/tools/check_portfolio_numbers.py`（新） | T4 数字自检（21 条） |
| `backend/tests/test_p2_46_round22_portfolio_docs.py`（新） | T4 CI 闸门（7 条，含 3 条自证 + 2 条测量纪律） |
| `backend/tests/tools/portfolio_demo.py`（新） | T3 最小闭环演示 |
| `backend/tests/tools/mutate_p2_46_round22.py` + `_result.log`（新） | 4 处变异见证 |
| 5 份源文档（各 +1 行） | 只加指向概览/摘要的链接，数字与结论未动 |

### 附：本轮踩到的两个坑（写进来是因为它们都是"口径"问题）

1. **扫描探针少了一步过滤**：首版 `probe_scan` 忘了排除 `in_test`，算出 **43 文件 / 94 入口**，
   而权威口径是 40/88。差的 6 处全在测试文件里。教训：复用别人的扫描器时，
   要连"默认过滤"一起复用，不能只复用 AST 遍历。
2. **CRLF 锚点**：demo 首版用 `\n` 拼变异锚点，在本机（autocrlf）永远匹配不到，
   于是误报"锚点不存在"。教训：**改文件内容的脚本必须先读实际换行符**。
3. **锚点 vs 归一化的不对称**：检查器比对前会去掉 `*` 和反引号（`_normalize`），
   但变异脚本改的是**原始字节**，两者对"同一句话"的看法不同。
   T1 首版用 `341 处 except 候选`，先因为作品集素材复述了同一个数字而命中 2 次（锚点不唯一 ⇒
   脚本判 ANCHOR-BAD，拒绝执行 —— 这个自检救了它），改用整句后又因为原文是
   `**341 …**` 而 0 次命中。最终锚点取 `**341 处 except 候选**全部裁定：已接线 109`。
   教训：**变异锚点必须钉原文形态（含排版符），而判据可以归一化**——两者目的不同，
   不能共用一套字符串。

---

## 八、CI 红项复盘：`readme.routes` 在 CI 里数到 5 个 REST（2026-10-20）

**现象**：`2948428` 推送后 `backend-coverage` 唯一红项是
`test_p2_46_round22_portfolio_docs.py::test_portfolio_numbers_match_repo_artifacts`，
失败信息指名 `[readme.routes]` / `[readme.scale.routes]`：
README 期望 `206 个 REST 端点 + 3 个 WebSocket 长连接`，CI 里探针算出的是
`5 个 REST 端点 + 3 个 WebSocket`。

**定位（实测，不是推断）**：5 = `app/main.py` 里 `@app.get` 自注册条数（实测
`grep -c "^@app\\.\\(get\\|post\\|put\\|patch\\|delete\\)" app/main.py` → 5），
3 = `@app.websocket` 条数。也就是说 **CI 那一刻的 `app` 实例里，
`app.include_router(api_router)` 进来的 v1 路由一条都没有**。仓库对这类现象早有
记录：`tests/test_observability_api.py::test_observability_registered_in_api_router`
为避免它直接 `pytest.skip`，注释原文「全量套件下 api_router 因模块加载顺序为空导致的
CI flake」。

**根因**：`app.routes` 是**进程内可变全局**。首版探针在 pytest 进程里
`from app.main import app` 直接数 —— 7000+ 个用例跑完之后，模块表早已被搅成
某个顺序相关的状态，读数随之漂移。README 里「运行时端点」的本意是**交付形态**
（干净解释器 import 一次得到的东西），用会话内状态去代表它，必然顺序敏感。

**修复**：`probe_routes()` 改为 `sys.executable -c <脚本>` 起**独立解释器**，
在里面 import 一次、数一次、打印哨兵行 `__ROUTE_PROBE__{json}`，父进程按哨兵行取数。
失败一律 `RuntimeError`，**不返回 0**（数不出来就说数不出来）。

**复现与见证**：

- `test_route_probe_isolated_from_in_process_app_state`：把进程内
  `app.router.routes` 削成"5 条 REST + 3 条 WS"（**复刻 CI 形态**），
  要求探针读数不变。旧实现在此必红。
- `test_route_probe_fails_loudly_instead_of_reporting_zero`：`sys.executable`
  指向不存在的路径 ⇒ 必须抛错。
- 变异 T4（`mutate_p2_46_round22.py`）：把 `probe_routes` 由「子进程数」翻回
  「进程内数」⇒ 必须由隔离用例指名变红。实测 RED-OK。

**读数**（2026-10-20 本机）：`check_portfolio_numbers.py` 21/21；闸门 7 passed；
变异 4/4 RED-OK、`residual_clean=True`、`final_green=True`。

**未隔离项（记账）**：具体是哪个用例 / 哪次导入把 `app` 建成了空壳，
**没有定位出来**。本地 `pytest tests/test_p2_11_round11.py + 闸门` 238 passed
（无复现），全量 37 分钟套件本轮未跑。因此隔离用例采用**症状复刻**（把路由表削到
CI 形态）而非"注入真凶"；子进程方案对两类污染（任何形式的进程内改动）均免疫。
若未来再出现进程内读数漂移类问题，本条就是排查起点。

**教训（与 §4.2 是一体两面）**：§4.2 的"断言钉结构、不钉孤立字面量"防的是
**改错地方不红**；本条防的是**环境变了假红/假绿**。判据必须钉"交付形态"，
不能钉"当前进程状态"。
