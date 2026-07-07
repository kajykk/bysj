---
name: remediation-orchestrator
description: 整改协调器。基于《整改清单_修复优先级_验证用例表》驱动 10 项问题 (R-001~R-010) 按 P0→P1→P2 优先级修复与验证全生命周期。Invoke when user asks to "启动整改"、"开始修复"、"继续整改"、"查看整改进度"、"执行验证用例"、"整改交付"。
---

# Skill: remediation-orchestrator

## 📋 技能描述 (Description)

这是 **整改工作流的最高指挥官与全生命周期状态管理员**。
你的职责是管理 `REMEDIATION_STATE.md`，并调度 6 个阶段的流转，同时维护 `01-remediation-checklist.md` / `02-fix-tracker.md` / `03-verification-cases.md` 三大事实清单。

工作流基于 `e:\code\bysj\docs\整改清单_修复优先级_验证用例表.md` 制定，覆盖 10 项整改问题（R-001~R-010）的修复优先级管理与验证用例执行。

## 使用场景 (Usage)

- 用户指令: "启动整改"、"开始修复"、"start remediation"、"继续整改"、"查看整改进度"、"执行验证用例"、"整改交付"、"完成修复阶段"。
- 系统指令: 当审核阶段进入修复与回归阶段时自动调用。
- **状态更新**: 每次需要切换阶段或同步问题时，**必须**调用此 Skill，而非手动编辑文件。

## 📂 文件结构 (File Layout)

所有整改产物存放在 `docs/planning/v1.40-audit-beautify/remediation/` 目录下：

```
docs/planning/v1.40-audit-beautify/remediation/
├── REMEDIATION_STATE.md              # 聚合状态投影（由本 Skill 维护）
├── 01-remediation-checklist.md       # 整改清单（10 项问题 R-001~R-010，事实来源 #1）
├── 02-fix-tracker.md                 # 修复跟踪表（生命周期跟踪，事实来源 #2）
├── 03-verification-cases.md          # 验证用例执行记录（5 类共 19 条用例，事实来源 #3）
└── 04-delivery-report.md             # 最终交付报告
```

## 指令 (Instructions)

### Phase 0: 引导协议 (Bootstrap Protocol)

**在开始任何工作之前，必须优先执行以下协议：**

1. **资源定位**:
   - 本 Skill 的标准模板位于 `./assets/` 目录中。
   - 创建任何文档之前，**必须**优先读取对应模板文件。
2. **上下文对齐**:
   - 加载规则后的第一步，**立即**读取 `docs/planning/v1.40-audit-beautify/remediation/REMEDIATION_STATE.md`。
   - 如果内部状态与 `REMEDIATION_STATE.md` 不一致，**必须**废弃内部状态，按文件重建。
3. **事实清单加载**: 同步读取 `01-remediation-checklist.md`、`02-fix-tracker.md`、`03-verification-cases.md`，统计实际进度。
4. **源计划对齐**: 读取 `e:\code\bysj\docs\整改清单_修复优先级_验证用例表.md`，确认整改范围与验证用例与源计划一致。

### Phase 1: 状态检查与初始化

1. **读取状态文件**：调用 `Read` 读取 `REMEDIATION_STATE.md`。
2. **状态判断**：
   - **如果文件不存在**：执行 **[初始化协议]** 创建文件，初始化为 `Phase 1 / Initialization`。
   - **如果文件存在**：找到当前标记为 `🔄 进行中` 的阶段，根据该阶段定义执行对应操作。

### Phase 2: 阶段流转控制 (State Flow Control)

#### 阶段 1: 初始化 (Initialization)

- **目标**: 冻结整改范围、拆分源文件、初始化跟踪文件。
- **子步骤**:
  1. 读取源计划 `docs/整改清单_修复优先级_验证用例表.md`，确认 10 项问题（R-001~R-010）与 19 条验证用例（V-Auth/Predict/Upload/Health/Perf）完整无缺。
  2. 基于模板创建三大事实清单：
     - `01-remediation-checklist.md` ← `./assets/REMEDIATION_CHECKLIST_TEMPLATE.md`
     - `02-fix-tracker.md` ← `./assets/FIX_TRACKER_TEMPLATE.md`
     - `03-verification-cases.md` ← `./assets/VERIFICATION_CASES_TEMPLATE.md`
  3. 初始化所有问题状态为 `新建`，所有验证用例状态为 `未执行`。
  4. 运行基线命令归档当前状态：
     - 前端：`cd frontend && npm run typecheck && npm run lint && npm run test && npm run build`
     - 后端：`cd backend && pytest && ruff check app tests && black --check app tests && bandit -r app`
- **流转条件**: 三大事实清单已创建且与源计划对齐 → 进入 Phase 2。
- **触发**: 输出 "📦 Phase 1 Initialization Completed. Initiating P0 Remediation..."

#### 阶段 2: P0 必须优先修复 (P0 Remediation)

- **目标**: 修复 3 项 P0 问题，必须优先完成。
- **P0 问题清单**:
  | 编号 | 项目 | 原因 | 目标完成标准 |
  |---|---|---|---|
  | P0-1 | R-008 `element-plus` 按需引入审计 | 直接影响首屏体积和整体包大小，收益高 | 确认无全量引入；构建产物中 `element-plus` chunk 体积显著下降 |
  | P0-2 | R-010 关键链路 E2E 实测 | 当前"功能可用"主要来自静态审查，需运行验证闭环 | 至少覆盖登录、刷新、权限、预测、复核 5 条主链路 |
  | P0-3 | R-001 chunk 失败误判修正 | 可能掩盖真实运行时错误，影响排障 | 仅在明确 chunk 失效时自动刷新，真实语法错误不被吞掉 |
- **执行顺序**: P0-1 → P0-2 → P0-3（按编号顺序，但可根据依赖关系调整）
- **每个修复必须记录**:
  1. 问题原因（写入 `02-fix-tracker.md`）
  2. 修复方案
  3. 影响范围
  4. 回归测试结果（同步更新 `03-verification-cases.md`）
  5. 关联提交哈希
- **流转条件**:
  - 3 项 P0 问题全部状态为 `已关闭`
  - 每项修复均有关联回归用例通过
  - 前端 `typecheck/lint/test/build` 通过
  - 后端 `pytest/ruff/black --check/bandit` 无阻塞
  → 进入 Phase 3。
- **触发**: 输出 "🔧 Phase 2 P0 Remediation Completed. Initiating P1 Remediation..."

#### 阶段 3: P1 高优先级修复 (P1 Remediation)

- **目标**: 修复 4 项 P1 问题。
- **P1 问题清单**:
  | 编号 | 项目 | 原因 | 目标完成标准 |
  |---|---|---|---|
  | P1-1 | R-007 图表页与 ECharts 懒加载 | 对首屏和交互性能有直接收益 | 图表类页面进入后再加载 ECharts 相关模块 |
  | P1-2 | R-002 登录跳转保留完整 URL | 影响复杂页面恢复体验 | 登录后可恢复 query/hash 状态 |
  | P1-3 | R-005 fire-and-forget 任务可观测性 | 影响后台任务可靠性定位 | 可以统计调度成功率、失败率、超时率 |
  | P1-4 | R-006 启动失败结构化状态 | 影响健康检查与运维排障 | health 或日志中能明确定位失败组件 |
- **执行顺序**: P1-1 → P1-2 → P1-3 → P1-4
- **横向排查**: 同类问题必须全代码库扫描，不能只修单点。
- **复核规则**: 涉及权限、安全、数据一致性的修复必须由第二人复核。
- **流转条件**:
  - 4 项 P1 问题完成度不低于 100%（或已关闭 + 有明确延期说明）
  - 每项修复均有关联回归用例通过
  - 前后端基线命令无阻塞
  → 进入 Phase 4。
- **触发**: 输出 "🔧 Phase 3 P1 Remediation Completed. Initiating P2 Remediation..."

#### 阶段 4: P2 中优先级修复 (P2 Remediation)

- **目标**: 修复 3 项 P2 问题。
- **P2 问题清单**:
  | 编号 | 项目 | 原因 | 目标完成标准 |
  |---|---|---|---|
  | P2-1 | R-003 显式导入或强化自动导入验证 | 提升基础层稳定性和可移植性 | 关键基础文件不依赖隐式注入或已补齐验证 |
  | P2-2 | R-004 稳定序列化 GET 去重 key | 目前风险较低，但复杂参数场景存在扩展隐患 | 支持复杂参数的稳定 key 生成 |
  | P2-3 | R-009 页面重计算与 resize 节流优化 | 改善中低端设备交互体验 | 大列表、大图表页面滚动和缩放更平滑 |
- **执行顺序**: P2-1 → P2-2 → P2-3
- **流转条件**:
  - 3 项 P2 问题全部状态为 `已关闭` 或 `暂缓`（需写明理由）
  - 前后端基线命令无阻塞
  → 进入 Phase 5。
- **触发**: 输出 "🔧 Phase 4 P2 Remediation Completed. Initiating Verification..."

#### 阶段 5: 验证用例执行 (Verification)

- **目标**: 执行 5 类共 23 条验证用例，确保整改效果。
- **验证用例分类**:
  1. **登录与鉴权** (V-Auth-01 ~ V-Auth-04，共 4 条)
  2. **预测与复核** (V-Predict-01 ~ V-Predict-05，共 5 条)
  3. **上传与文件访问** (V-Upload-01 ~ V-Upload-04，共 4 条)
  4. **监控、健康与告警** (V-Health-01 ~ V-Health-03 + V-Alert-01 ~ V-Alert-02，共 5 条)
  5. **前端性能** (V-Perf-01 ~ V-Perf-05，共 5 条)
- **执行规则**:
  - 每个修复项完成后，至少执行对应验证用例中的 1~2 个核心场景
  - 所有 P0/P1 用例完成后，再做一次完整回归
  - 验证结果实时记录到 `03-verification-cases.md`
- **用例状态**: `未执行` → `执行中` → `通过` / `失败` / `阻塞`
- **流转条件**:
  - 23 条验证用例全部执行完毕
  - P0/P1 对应验证用例通过率 100%
  - P2 对应验证用例通过率不低于 80%
  - 失败用例已有复现步骤与原因分析
  → 进入 Phase 6。
- **触发**: 输出 "✅ Phase 5 Verification Completed. Initiating Final Regression & Delivery..."

#### 阶段 6: 最终回归与交付 (Final Regression & Delivery)

- **目标**: 完成验收清单并归档交付物。
- **验收标准**（源计划第 5 节）:
  1. 所有 P0 项修复完成
  2. 所有 P0 对应验证用例通过
  3. P1 项修复完成度不低于 80%
  4. 关键业务链路 E2E 可重复执行并通过
  5. 前端性能指标有明确的基线与优化对比结果
- **最终回归命令**:
  - 前端：`cd frontend && npm run typecheck && npm run lint && npm run test && npm run build`
  - 后端：`cd backend && pytest && ruff check app tests && black --check app tests && bandit -r app`
- **交付物**（写入 `04-delivery-report.md`）:
  1. 整改清单完成情况汇总
  2. 修复跟踪表（含生命周期记录）
  3. 验证用例执行报告
  4. 前端性能基线与优化对比
  5. 关键链路 E2E 执行结论
  6. 遗留问题与延期说明
- **完成动作**: 标记 `REMEDIATION_STATE.md` 为 `Project Remediated & Delivered`，输出 "🎉🎉🎉 REMEDIATION COMPLETED SUCCESSFULLY! 🎉🎉🎉"。

### 初始化协议 (Initialization Protocol)

如果需要初始化 `REMEDIATION_STATE.md`：

1. **加载模板**：读取 `./assets/REMEDIATION_STATE_TEMPLATE.md`。
2. **生成文件**：基于模板生成 `REMEDIATION_STATE.md`，替换 `[Iteration]` 为 `v1.40-remediation`。
3. **同时创建事实清单**:
   - `01-remediation-checklist.md` ← `./assets/REMEDIATION_CHECKLIST_TEMPLATE.md`
   - `02-fix-tracker.md` ← `./assets/FIX_TRACKER_TEMPLATE.md`
   - `03-verification-cases.md` ← `./assets/VERIFICATION_CASES_TEMPLATE.md`
4. **状态设定**: 仅 Phase 1 / Initialization 标记为 `🔄 进行中`，其余均为 `⏳ 待定`。
5. **问题初始化**: 10 项问题（R-001~R-010）状态初始化为 `新建`；23 条验证用例状态初始化为 `未执行`。

## 问题操作 (Issue Operations)

针对 `02-fix-tracker.md` 中的问题：

- **Log Issue (`log-issue <id> <severity> <title>`)**:
  - 确认问题已在 `01-remediation-checklist.md` 中登记，分配唯一编号 `R-NNN`。
  - 填入：编号 / 优先级 / 标题 / 模块 / 发现日期 / 状态=`新建`。
  - 同步 `REMEDIATION_STATE.md` 的问题统计。

- **Confirm Issue (`confirm-issue <id>`)**: 状态 `新建` → `已确认`。

- **Start Fix (`start-fix <id>`)**: 状态 `已确认` → `修复中`，记录责任人与计划修复日期。

- **Submit Fix (`submit-fix <id> <commit>`)**: 状态 `修复中` → `待复核`，记录：
  1. 修复方案
  2. 影响范围
  3. 关联提交哈希
  4. 横向排查结论（同类问题全代码库扫描结果）

- **Close Issue (`close-issue <id>`)**: 状态 `待复核` → `已关闭`，记录复核人与关闭日期。
  - **必须**先确认 `03-verification-cases.md` 中关联回归用例已通过。
  - 涉及权限/安全/数据一致性的修复必须由第二人复核。

- **Defer Issue (`defer-issue <id> <reason>`)**: 状态任意 → `暂缓`，需写明理由与延期到何时。

- **Reject Issue (`reject-issue <id> <reason>`)**: 状态 `新建` → `拒绝`，需写明非问题理由。

## 验证用例操作 (Verification Operations)

针对 `03-verification-cases.md` 中的验证用例：

- **Run Case (`run-case <case-id>`)**: 状态 `未执行` → `执行中`，记录执行人与开始时间。

- **Pass Case (`pass-case <case-id> <evidence>`)**: 状态 `执行中` → `通过`，记录：
  1. 执行步骤
  2. 实际结果
  3. 证据（截图/日志/测试输出）
  4. 关联修复编号

- **Fail Case (`fail-case <case-id> <reason>`)**: 状态 `执行中` → `失败`，记录：
  1. 失败现象
  2. 复现步骤
  3. 原因分析
  4. 关联问题编号（如有新问题需 `log-issue`）

- **Block Case (`block-case <case-id> <reason>`)**: 状态 `未执行` → `阻塞`，需写明阻塞原因与依赖。

## 🛡️ 铁律与约束 (Iron Rules & Constraints)

1. **单步流转**: 仅允许将 **当前** `🔄 进行中` 的阶段改为 `✅ 完成`。
2. **禁止跳变**: **绝对禁止** `⏳ 待定` → `✅ 完成`；**绝对禁止** 跳过 P0 直接修复 P1/P2。
3. **阶段闭环**: Phase N 未完成严禁进入 Phase N+1；P0 未清空严禁进入 P1；P1 未达 80% 严禁进入 P2。
4. **单一事实来源**: `01-remediation-checklist.md`、`02-fix-tracker.md`、`03-verification-cases.md` 是绝对真理。`REMEDIATION_STATE.md` 是基于真理计算出的投影。
5. **禁止手动同步**: 严禁 Agent 手动分别编辑四个文件来同步状态，必须遵循本 Skill 的原子更新逻辑。
6. **严禁伪造**: 只有当问题真正修复（代码已提交 + 回归通过）时，才允许 `close-issue`。
7. **量化进度铁律**: `REMEDIATION_STATE.md` 中的进度必须严格符合 `X/Y Issues` 格式，**严禁** 使用"基本通过"、"大部分完成"等模糊描述。
8. **数据隔离**: `REMEDIATION_STATE.md` 仅存储 **聚合状态**，**严禁** 在其中复制具体问题列表。
9. **同类横向排查**: 修复一个权限/安全/数据一致性问题时，必须全代码库扫描同类问题。
10. **第二人复核**: 涉及权限、安全、数据一致性的修复必须由第二人复核才能关闭。
11. **修复必带回归**: 任何 `submit-fix` 都必须同步在 `03-verification-cases.md` 创建或更新对应回归用例。
12. **计划对齐**: 所有整改范围、优先级、验证用例必须与 `docs/整改清单_修复优先级_验证用例表.md` 对齐，不得擅自增删。
13. **排除状态文档**: 审核与整改过程中**必须**排除所有状态文档及 `ralph` 相关文档。
14. **优先级铁律**: 严格遵循 P0 → P1 → P2 的修复顺序，**严禁** 在 P0 未清空时修复 P2 及以下。

## 📂 关联资产 (Related Assets)

- `./assets/REMEDIATION_STATE_TEMPLATE.md` (State Template)
- `./assets/REMEDIATION_CHECKLIST_TEMPLATE.md` (Checklist Template)
- `./assets/FIX_TRACKER_TEMPLATE.md` (Fix Tracker Template)
- `./assets/VERIFICATION_CASES_TEMPLATE.md` (Verification Cases Template)
- `e:\code\bysj\docs\整改清单_修复优先级_验证用例表.md` (Source Plan, Read-Only Reference)
- `e:\code\bysj\.trae\rules\Ralph.md` (Project Rules)

## 示例 (Examples)

### 示例 1：启动整改

**Input**:
> 用户：启动整改

**Output**:
> 🚀 **Remediation Orchestrator Initialized**
> - **Phase**: Phase 1 / Initialization / Step 1
> - **Action**: Creating `REMEDIATION_STATE.md` and three fact lists under `docs/planning/v1.40-audit-beautify/remediation/`.
> - **Issues**: 10 total (R-001~R-010) / P0: 3 / P1: 4 / P2: 3
> - **Verification Cases**: 23 total (5 categories)
> - **Next**: Freeze remediation scope and run baseline commands.

### 示例 2：查看进度

**Input**:
> 用户：整改进度如何？

**Output**:
> 📊 **Current Remediation Status**:
> - **Phase**: Phase 3 / P1 Remediation (2/4 completed)
> - **Issues**: 10 total / 3 P0 (3 closed) / 4 P1 (2 closed, 1 fixing, 1 pending) / 3 P2 (pending)
> - **Fixed**: 5 closed / 1 in fix / 4 pending
> - **Verification**: 8/23 passed / 2 failed / 13 pending
> - **Next Action**: Continue with P1-3 (R-005 fire-and-forget observability)

### 示例 3：提交修复

**Input**:
> 用户：R-008 已修复，提交哈希 abc1234

**Output**:
> ✅ **Fix Submitted: R-008**
> - Severity: P0
> - Title: element-plus 按需引入审计
> - Commit: abc1234
> - Status: 修复中 → 待复核
> - **Reminder**: Must run V-Perf-01 (首屏加载) and V-Perf-02 (图表页加载) verification cases before close.
> - **Reminder**: Same-class horizontal scan required (Iron Rule #9)
> - Synced `REMEDIATION_STATE.md` (P0: 1/3 submitted for review)

### 示例 4：执行验证用例

**Input**:
> 用户：执行 V-Auth-01

**Output**:
> 🧪 **Verification Case Running: V-Auth-01**
> - Category: 登录与鉴权
> - Scenario: 未登录访问受限页面
> - Status: 未执行 → 执行中
> - **Next**: Execute test steps and record actual results.
