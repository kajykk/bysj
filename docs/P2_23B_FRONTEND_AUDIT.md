# P2_23B · ROUND_23b 审计：前端越权与静默降级（M25 / M26 / M27 + L13）

> 轮次：ROUND_23（23b）。前置提交：23a `02e1ab1` + 补漏 `3acd5eb`（CI 10/10）。
> 本文档随 23b 提交入库。反向对照记录见 `frontend/tests/tools/mutate_round23b.md`
> （前端变异见证机制首次建立）。

## 一、M25 · 评估详情快照的跨用户泄漏

### 缺陷

`assessmentDetailCache.ts` 用固定键 `bysj:assessment-history-snapshot`（无用户后缀），
而另三个历史键（`text_prediction_history_v1_` / `physio_history_v1_` /
`prediction_history_v1_`）都走 `historyKeyWithUser` 的 `_u<id>` / `anon_` 后缀——
本键是异类。后果：同一标签页 A 登出、B 登录后，B 打开详情页读到 A 的评估快照
（心理健康数据，共享设备场景即 PII 泄漏）。且 `clearAssessmentDetailCache`
**生产调用点为 0**，其 docstring 里「退出登录时随之丢弃」是句空话。

### 修复：键后缀 + 归属校验（两者都做）

| 防线 | 实现 | 为什么需要它 |
|---|---|---|
| ① 键加用户后缀 | `historyKeyWithUser(CACHE_KEY, userId)` ⇒ `bysj:assessment-history-snapshot_u7` | 与另三个历史键**同构**（不造第四套命名）；也是登出清理按模式匹配的前提 |
| ② 读取归属校验 | 快照包裹 `{v:2, userId, items}`，读取时校验 `userId` 与版本 | 纵深：防「键后缀对但 userId 被改用过期值」等边缘路径 |
| ③ fail-closed | 取不到有效 userId ⇒ `assessmentDetailCacheKey` 返回 null ⇒ 不写、不读 | 评估详情只可能属于登录用户，绝不回落匿名键或他人数据 |
| ④ 登出清理 | 该键纳入 `SENSITIVE_KEY_PATTERNS`，由既有 `clearSensitiveLocalStorage` 在登出/登录时清两种 storage | 让 docstring 那句承诺真正成立；不依赖新增生产调用点 |

**取舍说明**：与 `historyKeyWithUser` 的**刻意差异**——后者对缺失 userId 回落
`anon_` 会话键（三个历史键的匿名隔离语义），本模块**不回落**（无 userId 即不落盘）。
理由：评估详情是登录后才拉得到的数据，回落到匿名键等于把「谁的数据」交给运气。

**格式升级**：v1（裸数组）无归属信息 ⇒ 读取时丢弃并顺手清键。sessionStorage
生命周期本就跟会话同长，一次性升级成本可忽略。

### 门槛与实测

`src/views/user/utils/assessmentDetailCache.test.ts`（16 用例）+
`src/stores/auth.test.ts`（+2）+ `UserAssessmentDetailPage.local.test.ts`（+1）：

- A（id=7）写入 ⇒ B（id=8）读不到；A 自己的读取不受影响
- 登出 ⇒ `sessionStorage` 中 `bysj:assessment-history-snapshot_u7` 不存在
- 登录 ⇒ 上一位用户残留快照被清
- 归属元数据被篡改 ⇒ 丢弃
- 旧格式（裸数组）⇒ 丢弃并清键
- userId 为 null/undefined/0/-1/1.5 ⇒ 不写入、读取返回 null

## 二、M26 · 前端路由权限取自可篡改 localStorage

### 缺陷

`authStorage.getStoredUser()` 是 `JSON.parse(userRaw) as UserInfo`——`as` 是类型
**断言**不是校验：DevTools 把 localStorage 的 user 改成 `{"role":"super_admin"}`
就能让前端按超管渲染。守卫的 role 直接取自这份占位值。

### 修复：schema 校验 + 已验证来源

1. **落地前 schema 校验**（`getStoredUser`）：字段白名单
   （`id/username/role/nickname`）+ 类型与取值检查 + `isKnownRole`
   （复用 `src/utils/roles.ts`，不另造角色字面量）。任一不过 ⇒ 返回 null，
   不抛异常。白名单顺带挡住被塞回的 `email` 等 PII。
2. **已验证来源 = JWT claims**：新增 `parseJwtRole(token)` 从 access_token 的
   `role` claim 取角色（后端 `auth_service.py` 的 claims 含 `role`，
   签名改动会被后端拒绝）。auth store 暴露
   `isRoleVerified = parseJwtRole(token) === role`。
3. **守卫 fail-closed**：`GuardAuthState` 新增 `roleVerified`（缺省 false）。
   - 未验证 ⇒ 不按 role 做跳转决策（`/login` 停在当前页）；
   - 未验证 ⇒ 不放行管理端（`isAdminArea`：路径前缀 `/admin` 或
     `meta.role` **全部**为 admin 类）；
   - `isAdminArea` 用 `every` 而非 `some`：`/user/model-training` 这类多角色路由
     （`['user','admin','super_admin']`）位于用户区，按 `some` 判定会误伤正常
     admin 用户——**那是误伤不是防护**（此点是跑既有测试时暴露并修正的）。

### ⚠️ 边界声明（不得夸大）

本项**只修 UI 层越权与后台结构暴露**：篡改 localStorage 不再能让前端按超管渲染、
不再能进 `/admin/*` 路由。**真实数据仍由后端 403 拦截**——后端鉴权逻辑本轮未动，
403 语义未变。不得表述为「已修复越权访问」。

### 门槛与实测

`src/utils/authStorage.test.ts`（+9）、`src/router/guard.test.ts`（+6）、
`src/router/index.test.ts`（集成 4 条按新契约同步）：

- 篡改 localStorage 为 `super_admin` 且无有效凭证 ⇒ 不放行 `/admin/*`
- 非法 role（未知字符串 / 数字 / null / 缺失 / 数组）⇒ 丢弃，不抛异常
- 不传 `roleVerified` ⇒ 按未验证处理（调用方漏传也不放行）
- 多角色用户区路由不按管理端口径约束

## 三、M27 · 待处理预警数失败时静默返回 0

### 缺陷

`getCounselorUnhandledWarningCount` 的 `catch { return 0 }`：接口 500/超时把
「加载失败」渲染成「确实没有待处理预警」——咨询师据此判断"没人需要干预"，
是漏报信号。且唯一生产调用点在 `Promise.all([...])` 内，抛错会把同批的
`getCounselorUserCount` 一起拖挂。

### 三态对照表

| 状态 | API 返回 | 仪表盘渲染 | 语义 |
|---|---|---|---|
| 加载中 | — | `SkeletonScreen`（`statsLoading` 分支） | 尚未拿到结果 |
| 成功且为 0 | `0` | `CountUp :end="0"` + `heroSub` | **确实没有**待处理预警 |
| 成功且 > 0 | `n` | `CountUp :end="n"` + `heroSub`（+「需处理」tag） | 真实待处理数 |
| **加载失败** | `null` | `—` + `heroLoadFailed`（警示色副文案） | **未能获取**，不得渲染成 0 |

API 层**禁止抛异常**（返回 `number | null`），保证 `Promise.all` 不被拖挂。

### 门槛与实测

`src/api/counselorApi.test.ts`（+3）：500 ⇒ `null`（`expect(count).not.toBe(0)`）、
超时 ⇒ resolves null、确实为 0 ⇒ `0`（与 null 区分）。
`src/views/counselor/CounselorDashboard.test.ts`（+5）：三态互斥的**源码结构见证**。

## 四、L13 · scripts/ 硬编码口令与令牌

### 修复

| 文件 | 修前 | 修后 |
|---|---|---|
| `scripts/login_admin.py` | 硬编码口令 + 令牌写绝对路径 `e:\code\bysj\scripts\.admin_token.txt` | 读 `BYSJ_ADMIN_USERNAME` / `BYSJ_ADMIN_PASSWORD`，缺失 ⇒ 打印指引 **exit 2**；令牌路径按**仓库根相对**解析，可由 `BYSJ_ADMIN_TOKEN_PATH` 覆盖 |
| `scripts/login_admin.ps1` | 同款硬编码 + 绝对路径 | 同上（PowerShell 版） |
| `scripts/check_metrics_v2.py` | 硬编码 `dev-only-metrics-token` | 优先级 环境变量 `BYSJ_METRICS_TOKEN` > `settings.metrics_access_token` > 占位符 |
| `scripts/trigger_fusion_inference_v2.py` | 模块级 `PASSWORD = "Admin@Canary2026"` | 环境变量 + 缺失报错（**闸门扫出来的，提示词未列出**） |
| `scripts/dump_errors.py` / `scripts/test_gdpr_fix.py` | 硬编码 E2E 账号口令 | 环境变量 + 缺失报错（**同为闸门扫出**） |

**不得在注释里重复口令字面量**：`login_admin.py` / `.ps1` 的 docstring 只说
「修前硬编码了管理员口令」，不写具体值（写进版本库即失去意义）。

**⚠️ 记账：上述 6 个脚本全部不在版本库**。实测 `.gitignore` 刻意排除了它们
（`:182 /scripts/login_admin.*`、`:169 /scripts/*_v2.py` 等）——前人的防泄漏
手段正是「不入库」。因此：
- 这 6 个文件的修复**只在本机工作区生效，不由 CI 背书**；
- 闸门在 CI checkout 中扫的是**已入库的 118 个 scripts 脚本**（仍有效：正是
  它扫出了本机未入库之外的同类问题形态），并对「文件不存在」的用例 skip；
- 防闸门空转：新增 `test_scan_covers_a_meaningful_number_of_files`（断言扫到
  ≥50 个文件），目录结构退化会红。
- 本轮**不改** .gitignore 惯例、不 `add -f` 强行入库（改变仓库惯例需单独决策）。

### 闸门：`backend/tests/test_p2_49_round23b_secret_scan.py`（9 passed，进 CI）

- 扫 `scripts/**/*.py` 与 `**/*.ps1`，命中模式：`(password|passwd|pwd|token|secret|
  api_key|apikey|access_key)` + 可选闭合引号 + `[:=]` + **引号字面量（≥6 字符）**；
- 环境变量读取（`os.environ[...]` / `getenv` / `$env:X`）天然不命中，并有专门
  用例锁住「不得误判正确改法」；
- **闸门自检**：断言模式能命中已知硬编码样例（防止正则写错导致空转）；
- 白名单**显式 + 逐条理由**（`dev-only-metrics-token`），并断言白名单条目
  在文件中真实存在（防腐烂成死条目）；
- 附带钉住 `.admin_token.txt` 已被 `.gitignore` 排除（产物不落版本库）；
- 两个 login 脚本的契约用例：必须读环境变量、缺变量明确退出、**不得**再含原口令、
  **不得**含绝对路径。

不改 gitleaks 配置、不加 allowlist（那是反向操作）——本闸门与之互补：
gitleaks 扫已入库历史且未配 allowlist，本闸门断言源码结构。

## 五、反向对照（变异见证，前端首次建立）

`frontend/tests/tools/mutate_round23b.md`：

| 组 | 变异点 | 红数 | 还原后 |
|---|---|---|---|
| B1-v1 | 缓存键去掉用户后缀 | 7 | 69 passed |
| B1-v2 | 去掉归属校验 | 1 | 69 passed |
| B2-v1 | schema 校验旁路 | 5 | 101 passed |
| B2-v2 | 未验证角色当已验证 | 3 | 101 passed |
| B3 | 失败伪装成 0 | 2 | 59 passed |
| B4 | 塞回口令字面量 | 闸门 fail | 9 passed |

**B1 的归因记账（重要）**：「A 写 ⇒ B 读不到」在 B1-v1 下红，直接原因是
「B 的读取被归属校验挡住后顺手删了 A 的快照，导致后续 A 自己的读取落空」，
不是「B 读到了 A 的数据」。跨用户读取由**两道防线共同保证**，任一单独失效
都不会造成泄漏——这是纵深设计的预期表现，因此不能用该用例的「红」作为
单一防线变异的判据（否则会得出错误结论）。同理 B1-v2 下「换用户读不到」不红。

## 六、读数（实数）

- `npm run test`：**112 文件 / 1358 passed | 4 skipped（1362）**，0 失败
  （改前基线 112 文件；本轮净增用例：assessmentDetailCache +7、authStorage +9、
  guard +6、counselorApi +2、CounselorDashboard +5、auth +2、local +1）
- `npm run typecheck`：通过（vue-tsc + baseline 棘轮，BASELINE 未抬升，仍为 0）
- `npm run lint`：存量 4 errors / 135 warnings（**均在未改动文件**，
  如 `PhysioTab.vue`）；对本轮真实改动的 12 个源码文件单独跑 eslint ⇒ **0 error**
- 后端：`tests/test_p2_49_round23b_secret_scan.py` **10 passed**（本机；CI 上
  4 条 login_admin 契约用例与 1 条白名单校验会因文件未入库而 skip）；
  `p2_10 + p2_11 + p2_49` **252 passed**（frontend/src 侧棘轮含
  `ORPHAN_BASELINE = 9` **未变**——本轮未新增 `components/` 下组件、未动
  `components.d.ts`）
- 数字自检（check_portfolio_numbers）：**21/21**

## 七、CI 抓到的补漏：预警列表分页确定性排序（commit `2d2eb38`）

23b 提交后 CI `backend-coverage` 红了
`tests/services/test_counselor_service.py::TestListWarningsExtended::test_with_warnings`
（`assert 'low' == 'high'`）。根因**不在本轮改动**，而是存量生产缺陷：

`list_warnings` 只按 `created_at.desc()` 单键排序，而 `created_at`
**不是唯一键**——同一秒内产生的多条告警值相同，此时顺序由 DB 决定
（SQLite/PG 都不保证），配 `LIMIT/OFFSET` 会让同一条告警在相邻两页
**重复出现或被整页跳过**。

修复：咨询师端（`counselor_service_warning`）与用户端（`warning_service`）
两处同型实现加 `id.desc()` 作确定性 tie-break；测试侧给两条告警显式不同的
`created_at`，消除「同秒谁在前」的歧义（修前该用例依赖 SQLite 恰好按插入序
返回，CI 上偶发翻面）。新增闸门 `test_p2_50_round23b_warning_order_stability.py`
（5 用例）钉住二级排序键的存在——**结构性见证**，因为本机 SQLite 恰好按插入序
返回，去掉二级排序时行为断言不会红（无效变异）。连跑 3 次均稳定通过。

同型风险记账：全仓另有 10+ 处 `order_by(<created_at>.desc())` 的单键分页
（`admin_service_config` / `content_service` / `counselor_service_consultation` /
`counselor_service_user` ×3 / `crisis_export_service` 等）属同一风险，**本轮不动**。

> **ROUND_24 已兑现（2026-10-21，`docs/P2_51_ROUND24_PAGINATION_ORDER_AUDIT.md`）**：
> 上述「10+ 处」是当时的**估算**，实测口径为 AST（非字符串匹配）：
> 含非唯一时间列的 `order_by` 站点共 **32 处**，其中带 `.offset` 的真分页 **18 处**
> （本轮补次级键 15 处，另 3 处 ROUND_23 已修/原有）、只带 `.limit` 的单页截断
> **11 处**（10 处经裁定入白名单、1 处原有次级键）、无分页子句 3 处。
> 当前白名单外违规 = **0**，并由闸门 `test_p2_51_round24_pagination_order_gate.py`
> 持续看守。

## 八、未验证记账

- **M27 三态是源码结构见证，不是挂载级渲染验证**：`CounselorDashboard.vue` 依赖
  i18n / element-plus / 多个 api，挂载成本高，本轮未做 `mount()` 级断言。
  渲染层若后续改坏（如把 `v-else-if` 写成 `v-if`），结构见证仍会抓到，
  但「不出现 0」这条的**视觉**正确性未由测试背书。
- **M26 未做端到端验证**：未用真实篡改的 localStorage + 真实后端跑一遍
  「前端不放行 + 后端仍 403」；前后端各自的断言是分开验证的。
- **L13 脚本未实跑**：改后的脚本需要可用的本地服务与真实口令，本轮只验证
  「缺变量即 exit 2」的代码路径（静态断言），未做真实登录跑通。
- 前端**无覆盖率门禁变化**（`vitest.config.ts` thresholds 未动，加测试只升不降）。
- 工作区约 52 个未跟踪临时产物（`backend/r17_bt4/`、`r18_reg*`、`r22_bt*`、
  `pool_leakage*.json`、`p2_47_diag*` 等）**本轮不清理**（避免误删他人证据），
  仅此处记账。
