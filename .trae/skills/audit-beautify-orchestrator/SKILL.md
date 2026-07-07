---
name: audit-beautify-orchestrator
description: 审查与美化协调器。负责驱动前后端代码审查 + 前端美化全生命周期：6 阶段流转 (准备 → 静态审查 → 功能走查 → 专项审查 → 修复回归 → 验收交付)。Invoke when user asks to "start audit"、"启动审查"、"继续审查"、"查看审查进度"、"开始美化"。
---

# Skill: audit-beautify-orchestrator

## 📋 技能描述 (Description)
这是 **审查与美化工作流的最高指挥官与全生命周期状态管理员**。
你的职责是管理 `AUDIT_STATE.md`，并调度 6 个阶段的流转，同时维护 `audit-issues.md` / `regression-tests.md` / `visual-beautification.md` 三大事实清单。

工作流基于 `e:\code\bysj\uploads\计划.md` 制定，覆盖前后端代码审查与前端美化两大主线。

## 使用场景 (Usage)
- 用户指令: "启动审查"、"开始审查"、"start audit"、"继续审查"、"查看审查进度"、"开始美化"、"完成审查阶段"。
- 系统指令: 当 `RALPH_STATE.md` 显示项目进入交付前审查阶段时自动调用。
- **状态更新**: 每次需要切换阶段或同步问题时，**必须**调用此 Skill，而非手动编辑文件。

## 📂 文件结构 (File Layout)

所有审查产物存放在 `docs/planning/v1.40-audit-beautify/` 目录下：

```
docs/planning/v1.40-audit-beautify/
├── AUDIT_STATE.md              # 聚合状态投影（由本 Skill 维护）
├── 01-preparation-baseline.md  # Phase 1 基线命令执行结果
├── 02-static-review.md         # Phase 2 静态审查发现
├── 03-functional-walkthrough.md # Phase 3 功能走查发现
├── 04-special-reviews.md       # Phase 4 专项审查发现（权限/安全/性能/响应式等）
├── 05-audit-issues.md          # 主问题清单（事实来源 #1，类似 04-tasks）
├── 06-regression-tests.md      # 回归测试计划与结果（事实来源 #2，类似 05-tests）
├── 07-visual-beautification.md # 前端美化问题清单（事实来源 #3）
└── 08-delivery-report.md       # Phase 6 最终交付报告
```

## 指令 (Instructions)

### Phase 0: 引导协议 (Bootstrap Protocol)
**在开始任何工作之前，必须优先执行以下协议：**
1. **资源定位**:
   - 本 Skill 的标准模板位于 `./assets/` 目录中。
   - 创建任何文档之前，**必须**优先读取对应模板文件。
2. **上下文对齐**:
   - 加载规则后的第一步，**立即**读取 `docs/planning/v1.40-audit-beautify/AUDIT_STATE.md`。
   - 如果内部状态与 `AUDIT_STATE.md` 不一致，**必须**废弃内部状态，按文件重建。
3. **事实清单加载**: 同步读取 `05-audit-issues.md`、`06-regression-tests.md`、`07-visual-beautification.md`，统计实际进度。

### Phase 1: 状态检查与初始化
1. **读取状态文件**：调用 `Read` 读取 `AUDIT_STATE.md`。
2. **状态判断**：
   - **如果文件不存在**：执行 **[初始化协议]** 创建文件，初始化为 `Phase 1 / Step 1`。
   - **如果文件存在**：找到当前标记为 `🔄 进行中` 的阶段，根据该阶段定义执行对应操作。

### Phase 2: 阶段流转控制 (State Flow Control)

#### 阶段 1: 准备阶段 (Preparation)
- **目标**: 冻结范围、准备账号与数据、跑出基线。
- **子步骤**:
  1. 冻结本轮审查范围（功能清单来自 `uploads/计划.md` 第二节）。
  2. 确认测试账号：普通用户 / 咨询师 / 管理员 / 无权限账号。
  3. 准备测试数据：正常风险记录 / 高风险记录 / 空数据 / 大数据量列表 / 过期 Token。
  4. 运行基线命令并归档到 `01-preparation-baseline.md`。
     - 前端：`cd frontend && npm run typecheck && npm run lint && npm run test && npm run build`
     - 后端：`cd backend && pytest && ruff check app tests && black --check app tests && bandit -r app`
- **流转条件**: 基线报告已生成且可读 → 进入 Phase 2。
- **触发**: 输出 "📦 Phase 1 Baseline Captured. Initiating Static Review..."

#### 阶段 2: 静态审查 (Static Review)
- **目标**: 通过代码静态分析发现问题，无需运行时。
- **前端重点**: 组件结构、类型定义、API 封装、路由守卫、Store、主题变量、重复代码、错误处理。
- **后端重点**: 路由层职责、service 层边界、schema 完整性、权限校验、事务与异常、安全配置、数据库迁移。
- **输出**: 发现的问题追加到 `05-audit-issues.md`，详细记录写入 `02-static-review.md`。
- **流转条件**: 前后端静态审查清单全部走查完毕 → 进入 Phase 3。
- **触发**: 输出 "🔍 Phase 2 Static Review Completed. Initiating Functional Walkthrough..."

#### 阶段 3: 功能走查 (Functional Walkthrough)
- **目标**: 按角色执行端到端功能验证。
- **角色顺序**: 未登录 → 普通用户 → 咨询师 → 管理员 → Token 过期用户 → 被禁用/权限不足用户。
- **每个角色覆盖**: 登录、首页、主要列表页、详情页、新增/编辑/删除/确认/导出、异常输入、无数据、网络错误。
- **覆盖检查表**: 通用功能检查表（计划二.1）、用户端（二.2）、咨询师端（二.3）、管理端（二.4）、后端 API（二.5）。
- **输出**: 问题追加到 `05-audit-issues.md`，详细记录写入 `03-functional-walkthrough.md`。
- **流转条件**: 6 个角色 × 8 类操作全部覆盖 → 进入 Phase 4。
- **触发**: 输出 "🚶 Phase 3 Functional Walkthrough Completed. Initiating Special Reviews..."

#### 阶段 4: 专项审查 (Special Reviews)
- **目标**: 针对专项维度深度审查（计划三、六、七、八）。
- **必跑专项**:
  1. **权限专项**（计划三.1.4 / 三.2.4）
  2. **安全专项**（Bandit、PII、CORS、CSRF、路径穿越、SQL 注入）
  3. **性能专项**（前端 Lighthouse、后端 P95 延迟、N+1、连接池）
  4. **响应式专项**（计划六.2，断点 375/390/768/1024/1366/1920）
  5. **视觉一致性专项**（计划六.1，色/字/距/角/影/图标/表格/表单/图表/弹窗/空状态/加载态）
  6. **错误处理专项**（计划三.1.5 / 三.2.5）
  7. **可观测性专项**（日志、指标、Tracing、Sentry、request_id 透传）
  8. **前端美化专项**（计划六.1.3 页面级优化：登录页 / 用户 Dashboard / 管理 Dashboard / 列表页 / 详情页）
  9. **UX 提升专项**（计划七：交互一致性、可用性、可访问性）
  10. **性能优化专项**（计划八：构建与资源、运行时、网络请求、后端配合）
- **输出**: 问题追加到 `05-audit-issues.md`；UI 美化类问题追加到 `07-visual-beautification.md`；详细记录写入 `04-special-reviews.md`。
- **流转条件**: 10 个专项全部完成 → 进入 Phase 5。
- **触发**: 输出 "🎯 Phase 4 Special Reviews Completed. Initiating Fix & Regression..."

#### 阶段 5: 修复与回归 (Fix & Regression)
- **目标**: 按严重级别修复问题并验证。
- **问题级别**（计划五.1）: P0 阻塞 / P1 高 / P2 中 / P3 低 / P4 建议。
- **修复优先级**: P0 → P1 → P2 → P3 → P4，**严禁** 在 P0 未清空时修复 P2 及以下。
- **每个修复必须记录**:
  1. 问题原因
  2. 修复方案
  3. 影响范围
  4. 回归测试结果（写入 `06-regression-tests.md`）
  5. 关联提交哈希
- **横向排查**: 同类问题必须全代码库扫描，不能只修单点。
- **复核规则**: 涉及权限、安全、数据一致性的修复必须由第二人复核。
- **流转条件**:
  - 所有 P0/P1 已关闭
  - P2 已关闭或有明确延期说明
  - 前端 `typecheck/lint/test/build` 通过
  - 后端 `pytest/ruff/black --check/bandit` 无阻塞
  - 核心功能链路通过手工回归
- **触发**: 输出 "🔧 Phase 5 Fix & Regression Completed. Initiating Final Acceptance..."

#### 阶段 6: 最终验收与交付 (Final Acceptance & Delivery)
- **目标**: 完成验收清单并归档交付物。
- **验收标准**（计划十二）:
  1. 所有 P0/P1 问题已关闭
  2. P2 问题已关闭或有明确延期说明
  3. 前端 `typecheck/lint/test/build` 通过
  4. 后端 `pytest/ruff/black --check/bandit` 无阻塞问题
  5. 核心功能链路通过手工回归
  6. 角色权限与越权测试通过
  7. 移动端、平板、桌面主要页面可用
  8. Lighthouse Performance ≥ 80 且 Accessibility ≥ 90
  9. UI 截图对比显示视觉一致性已改善
  10. 问题跟踪表中所有已修复问题均经过复核关闭
- **交付物**（计划十）: 12 项交付物清单写入 `08-delivery-report.md`。
- **完成动作**: 标记 `AUDIT_STATE.md` 为 `Project Audited & Delivered`，输出 "🎉🎉🎉 AUDIT & BEAUTIFICATION COMPLETED SUCCESSFULLY! 🎉🎉🎉"。

### 初始化协议 (Initialization Protocol)
如果需要初始化 `AUDIT_STATE.md`：
1. **加载模板**：读取 `./assets/AUDIT_STATE_TEMPLATE.md`。
2. **生成文件**：基于模板生成 `AUDIT_STATE.md`，替换 `[Iteration]` 为 `v1.40-audit-beautify`。
3. **同时创建事实清单**:
   - `05-audit-issues.md` ← `./assets/AUDIT_ISSUES_TEMPLATE.md`
   - `06-regression-tests.md` ← `./assets/AUDIT_REGRESSION_TEMPLATE.md`
   - `07-visual-beautification.md` ← `./assets/AUDIT_VISUAL_TEMPLATE.md`
4. **状态设定**: 仅 Phase 1 / Step 1 标记为 `🔄 进行中`，其余均为 `⏳ 待定`。

## 问题操作 (Issue Operations)

针对 `05-audit-issues.md` 中的问题：

- **Log Issue (`log-issue <module> <severity> <title>`)**:
  1. 在 `05-audit-issues.md` 追加一行，分配唯一编号 `ISS-NNN`。
  2. 填入：模块 / 级别 / 标题 / 发现日期 / 状态=`新建`。
  3. 同步 `AUDIT_STATE.md` 的问题统计。

- **Confirm Issue (`confirm-issue <id>`)**: 状态 `新建` → `已确认`。

- **Start Fix (`start-fix <id>`)**: 状态 `已确认` → `修复中`，记录责任人与计划修复日期。

- **Submit Fix (`submit-fix <id> <commit>`)**: 状态 `修复中` → `待复核`，记录修复方案、影响范围、关联提交。

- **Close Issue (`close-issue <id>`)**: 状态 `待复核` → `已关闭`，记录复核人与关闭日期。**必须**先确认 `06-regression-tests.md` 中关联回归用例已通过。

- **Defer Issue (`defer-issue <id> <reason>`)**: 状态任意 → `暂缓`，需写明理由与延期到何时。

- **Reject Issue (`reject-issue <id> <reason>`)**: 状态 `新建` → `拒绝`，需写明非问题理由。

## 🛡️ 铁律与约束 (Iron Rules & Constraints)

1. **单步流转**: 仅允许将 **当前** `🔄 进行中` 的阶段改为 `✅ 完成`。
2. **禁止跳变**: **绝对禁止** `⏳ 待定` → `✅ 完成`；**绝对禁止** 跳过 P0/P1 直接修复 P2 及以下。
3. **阶段闭环**: Phase N 未完成严禁进入 Phase N+1；Phase 4 专项审查未全完成严禁进入 Phase 5。
4. **单一事实来源**: `05-audit-issues.md`、`06-regression-tests.md`、`07-visual-beautification.md` 是绝对真理。`AUDIT_STATE.md` 是基于真理计算出的投影。
5. **禁止手动同步**: 严禁 Agent 手动分别编辑四个文件来同步状态，必须遵循本 Skill 的原子更新逻辑。
6. **严禁伪造**: 只有当问题真正修复（代码已提交 + 回归通过）时，才允许 `close-issue`。
7. **量化进度铁律**: `AUDIT_STATE.md` 中的进度必须严格符合 `X/Y Issues` 格式，**严禁** 使用"基本通过"、"大部分完成"等模糊描述。
8. **数据隔离**: `AUDIT_STATE.md` 仅存储 **聚合状态**，**严禁** 在其中复制具体问题列表。
9. **同类横向排查**: 修复一个权限/安全/数据一致性问题时，必须全代码库扫描同类问题。
10. **第二人复核**: 涉及权限、安全、数据一致性的修复必须由第二人复核才能关闭。
11. **修复必带回归**: 任何 `submit-fix` 都必须同步在 `06-regression-tests.md` 创建或更新对应回归用例。
12. **计划对齐**: 所有审查范围、检查表、验收标准必须与 `uploads/计划.md` 对齐，不得擅自增删。

## 📂 关联资产 (Related Assets)
- `./assets/AUDIT_STATE_TEMPLATE.md` (State Template)
- `./assets/AUDIT_ISSUES_TEMPLATE.md` (Issue Tracker Template)
- `./assets/AUDIT_REGRESSION_TEMPLATE.md` (Regression Test Template)
- `./assets/AUDIT_VISUAL_TEMPLATE.md` (Visual Beautification Template)
- `e:\code\bysj\uploads\计划.md` (Source Plan, Read-Only Reference)
- `e:\code\bysj\.trae\rules\Ralph.md` (Project Rules)

## 示例 (Examples)

### 示例 1：启动审查
**Input**:
> 用户：启动审查

**Output**:
> 🚀 **Audit Orchestrator Initialized**
> - **Phase**: Phase 1 / Preparation / Step 1
> - **Action**: Creating `AUDIT_STATE.md` and three fact lists under `docs/planning/v1.40-audit-beautify/`.
> - **Next**: Freeze audit scope and run baseline commands.

### 示例 2：查看进度
**Input**:
> 用户：审查进度如何？

**Output**:
> 📊 **Current Audit Status**:
> - **Phase**: Phase 4 / Special Reviews (3/10 completed)
> - **Issues**: 27 total / 5 P0 / 9 P1 / 10 P2 / 3 P3
> - **Fixed**: 8 closed / 12 in fix / 7 pending
> - **Regression**: 6/8 passed
> - **Next Action**: Continue with Performance Special Review (Plan §8)

### 示例 3：记录问题
**Input**:
> 用户：发现咨询师列表 API 越权问题，P1

**Output**:
> ⚠️ **Issue Logged: ISS-014**
> - Module: counselor API
> - Severity: P1
> - Title: Counselor list API leaks users outside authorization scope
> - Status: 新建
> - Synced `AUDIT_STATE.md` (Issues: 14 total, P1: 5)
> - **Reminder**: Same-class horizontal scan required (Iron Rule #9)
