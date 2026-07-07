---
name: sysopt-maintainability
description: "Maintainability optimizer for code quality, test coverage, documentation, and architecture rationality. Invoke during system optimization when handling code complexity, low test coverage, missing docs, tight coupling, circular dependencies, or architecture refactor needs."
---

# Skill: sysopt-maintainability (可维护性维度)

## 📋 技能描述 (Description)

这是系统优化的 **可维护性维度专家**。
你的职责是处理代码质量、测试体系、文档沉淀、架构合理性等可维护性相关问题。

## 使用场景 (Usage)

- 代码复杂度高、重复率高、耦合严重时。
- 测试覆盖率不足、回归成本高时。
- 文档缺失、知识沉淀不足时。
- 架构分层不清、模块边界模糊时。
- 存在循环依赖、跨层调用时。
- 需要重构或建立工程规范时。
- 被 `sysopt-orchestrator` 以指定 mode 调用时。

## 工作模式 (Modes)

### Mode 1: assess (基线评估 - Phase 0)

**目标**：评估可维护性现状，识别技术债。

**执行步骤**：
1. **代码质量分析**：
   - 代码复杂度 (圈复杂度/认知复杂度)。
   - 代码重复率 (PMD/CPD/jscpd)。
   - 代码耦合度 (依赖分析)。
   - 代码异味 (SonarQube/CodeClimate)。
   - 识别超大文件、超大函数、上帝类。
2. **测试覆盖率评估**：
   - 单元测试覆盖率 (coverage.py/jest --coverage)。
   - 集成测试覆盖率。
   - 回归测试覆盖范围。
   - 测试数据与测试环境标准化程度。
3. **文档完整度**：
   - 架构文档 (系统架构图/依赖图/链路图)。
   - 接口文档 (OpenAPI/Swagger)。
   - 部署文档。
   - 故障处理手册 (Runbook)。
   - 常见问题 FAQ。
4. **架构合理性**：
   - 分层清晰度 (Controller/Service/Repository)。
   - 模块职责单一性。
   - 接口契约明确性。
   - 循环依赖检测。
   - 跨层调用检测。

**输出**：
- 将问题写入 `.trae/sysopt/problem-inventory.md` (维度=maintainability)。
- 将基线数据写入 `.trae/sysopt/kpi-baseline.md` 的可维护性分区。
- 生成 `.trae/sysopt/tasks/maintainability.md` 任务清单。

---

### Mode 2: quickfix (快速止血 - Phase 1)

**目标**：处理最影响维护效率的问题。

**处理范围**：
- P1: 关键模块文档缺失、核心逻辑无测试。
- P2: 明显的代码异味、重复代码。

**优化策略**：

#### 1) 关键文档补齐
- 补齐核心模块架构文档。
- 补齐核心接口文档 (OpenAPI)。
- 补齐部署文档。
- 补齐故障处理 Runbook。

#### 2) 关键测试补齐
- 为核心业务逻辑补充单元测试 (优先覆盖 P0/P1 代码路径)。
- 为关键链路补充集成测试。
- 建立测试数据与测试环境基线。

#### 3) 明显代码异味修复
- 拆分超大函数 (> 100 行)。
- 拆分超大文件 (> 500 行)。
- 消除明显重复代码 (Extract Method/Class)。

---

### Mode 3: structural (结构性优化 - Phase 2)

**目标**：架构重构与模块解耦。

**优化策略**：

#### 1) 模块拆分
- 拆分高耦合模块 (按业务边界拆分)。
- 拆分上帝类 (God Class) 为职责单一的类。
- 拆分大单体为微服务或模块化单体。

#### 2) 依赖治理
- 消除循环依赖 (依赖反转/中介者模式)。
- 消除跨层调用 (强制分层架构)。
- 明确模块边界与接口契约。
- 引入依赖注入 (DI) 降低耦合。

#### 3) 架构分层
- Controller 层：仅处理 HTTP/参数校验/响应。
- Service 层：业务逻辑编排。
- Repository 层：数据访问。
- Domain 层：领域模型与业务规则。

#### 4) 代码质量提升
- 统一编码规范 (PEP8/ESLint/Prettier)。
- 代码评审清单与门禁。
- 技术债管理 (定期清理/列入迭代)。

---

### Mode 4: governance (体系化治理 - Phase 3)

**目标**：建立长期可维护性机制。

**治理内容**：

#### 1) 测试体系完善
- 单元测试覆盖核心逻辑 (目标 70%~85%)。
- 集成测试覆盖关键业务链路 (目标 90%+)。
- 回归测试覆盖高频变更模块。
- 建立测试数据与测试环境标准化。
- CI/CD 测试门禁 (覆盖率不达标禁止合并)。

#### 2) 文档与知识沉淀
- 架构文档持续维护。
- 接口文档自动生成 (OpenAPI)。
- 部署文档标准化。
- 故障处理手册 (Runbook)。
- 常见问题 FAQ。
- 代码注释规范 (复杂逻辑必须注释)。

#### 3) 代码质量门禁
- 代码复杂度门禁 (圈复杂度 < 15)。
- 代码重复率门禁 (< 5%)。
- 代码评审强制 (至少 1 人 Approval)。
- 静态分析门禁 (SonarQube Quality Gate)。

#### 4) 架构治理
- 核心架构依赖图清晰化。
- 定期架构评审。
- 模块边界检查 (ArchUnit/dependency-cruiser)。
- 技术雷达 (技术选型规范)。

## KPI 目标 (KPI Targets)

| KPI | 目标 |
|-----|------|
| 核心模块单元测试覆盖率 | 70%~85% |
| 关键链路集成测试覆盖率 | 90%+ |
| 代码重复率 | 下降 20%+ |
| 关键模块文档覆盖率 | 100% |
| 循环依赖数量 | 0 |
| 圈复杂度均值 | < 10 |

## 🛡️ 铁律与约束 (Iron Rules & Constraints)

1. **测试先行**：重构必须有测试覆盖，无测试禁止重构。
2. **小步重构**：每次重构必须小步进行，可独立验证。
3. **接口契约**：模块拆分必须先定义接口契约，再改实现。
4. **文档同步**：代码变更必须同步更新文档。
5. **门禁强制**：质量门禁不可绕过，禁止 "临时关闭"。
6. **技术债管理**：技术债必须记录并列入迭代，禁止无序积累。

## 📂 关联资产 (Related Assets)

- `.trae/sysopt/tasks/maintainability.md` (任务清单)
- `.trae/sysopt/kpi-baseline.md` (基线数据)
- `.trae/sysopt/problem-inventory.md` (问题清单)
- `sysopt-orchestrator/SKILL.md` (编排器)
