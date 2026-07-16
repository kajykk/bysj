---
name: sys-code-quality
description: >-
  This skill should be used when improving code quality and maintainability —
  "降低耦合", "清理重复代码", "拆分大模块", "补文档", "代码质量门禁",
  "提升测试覆盖率". It implements §4.5 of the optimization plan.
agent_created: true
---

# sys-code-quality

## 用途
治理代码复杂度/重复率/耦合，完善测试与文档，建立可演进的架构与质量门禁。

## 何时使用
- WF-0 评估、WF-2 重构、WF-3 质量/测试门禁。
- 用户要求「降耦合」「清重复」「补文档」「加测试门禁」。

## 执行流程
1. **度量现状**：复杂度（radon）、重复率、耦合度、循环依赖、测试覆盖率。
2. **清理重复**：提取公共函数/模块；删除死代码（vulture）。
3. **降耦拆分**：拆分大模块；统一编码规范（ruff）；降低跨层调用与循环依赖。
4. **架构契约**：用 `import-linter`/`grimp` 固化分层（本工程已有 Core 不依赖 ml/services 的契约）。
5. **测试体系**：
   - 单测覆盖核心逻辑（pytest，目标 70–85%）。
   - 集成测试覆盖关键链路（目标 90%+）。
   - 回归测试覆盖高频变更模块。
6. **文档沉淀**：架构文档、接口文档、部署文档、故障手册、FAQ。
7. **质量门禁**：CI 中配置 ruff + import-linter + coverage 阈值，未达不合并。

## 工具与脚本
- Lint/格式：`ruff`（backend/pyproject.toml 已配置）。
- 架构：`import-linter` + `grimp`（已配置 forbidden contract）。
- 复杂度/死码：`radon`、`vulture`。
- 测试：`pytest` + `coverage`（后端）、`vitest` + `playwright`（前端）。
- 门禁：CI 步骤（GitHub Actions，origin 在 GitHub）。

## 验收与 KPI（§3 / §9）
- 核心单测覆盖率 70–85%、关键链路集成 90%+。
- 代码重复率 ↓20%+，关键模块文档 100%。
- 核心架构依赖图清晰，循环依赖与跨层调用减少。

## 与本工程栈的对应
- 后端 `backend/app`：core/ml/services 分层；已知 model_engine 6 处延迟导入技术债（已在 import-linter 豁免）。
- 前端 `frontend/`：361 处 `any` 类型，纳入类型治理。
- 既有 `.grimp_cache`/`.import_linter_cache` 可直接复用。

## 注意事项
- 重构须伴随测试，避免功能回退。
- 架构契约变更需评审；豁免项（ignore_imports）须定期复核清理。
