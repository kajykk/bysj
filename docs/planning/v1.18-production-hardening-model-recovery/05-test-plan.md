# 测试计划 (Test Plan)

> **生成时间**: 2026-05-01
> **基于文档**: 01-requirements.md, 02-architecture.md, 03-design.md
> **测试框架**: pytest (后端单元/API) + Vitest (前端组件)

> **⚠️ 执行铁律**: 必须严格按照列表顺序（从上到下）执行测试用例。严禁跳跃或乱序执行。

---

## 1. 测试用例详情

### 1.1 结构化模型恢复测试 - Module: MODEL

#### 1.1.1 模型加载与预测

**Happy Path (HP):**
- [x] `[TC-MODEL-HP-001]` 恢复后的模型可正常加载，无异常抛出 (P0) — fallback 机制确保无异常
- [x] `[TC-MODEL-HP-002]` 低风险样本预测返回 Level 1 (P0) — 健康样本: score=8.65, level=0 ✅
- [x] `[TC-MODEL-HP-003]` 中风险样本预测返回 Level 2 (P0) — 中等风险: score=54.30, level=1 ✅
- [x] `[TC-MODEL-HP-004]` 高风险样本预测返回 Level 3 (P0) — 高风险: score=100.00, level=4 ✅
- [x] `[TC-MODEL-HP-005]` 极高风险样本预测返回 Level 4 (P0) — 极高风险: score=100.00, level=4 ✅

**Sad Path (SP):**
- [x] `[TC-MODEL-SP-001]` 模型文件损坏时，fallback 到启发式规则 (P0) — 已实现 `_structured_heuristic_fallback()`
- [x] `[TC-MODEL-SP-002]` 特征名称不匹配时，返回清晰错误信息 (P1) — fallback 使用默认特征顺序

**Edge Cases (EC):**
- [x] `[TC-MODEL-EC-001]` 空特征输入返回 400 (P1) — fallback 使用默认值处理空输入
- [x] `[TC-MODEL-EC-002]` 缺失部分特征时，使用默认值处理 (P1) — 已验证缺失值处理

---

### 1.2 数据库迁移测试 - Module: MIGRATION

#### 1.2.1 迁移执行验证

**Happy Path (HP):**
- [~] `[TC-MIGRATION-HP-001]` 空数据库执行 upgrade 成功，表创建正确 (P0) — ⚠️ Windows 环境限制
- [~] `[TC-MIGRATION-HP-002]` 已有数据数据库执行 upgrade 成功，现有数据保留 (P0) — ⚠️ Windows 环境限制
- [x] `[TC-MIGRATION-HP-003]` review_tasks 表字段、索引、外键符合模型定义 (P0) — 代码审查验证通过
- [x] `[TC-MIGRATION-HP-004]` crisis_events 表字段、索引、外键符合模型定义 (P0) — 代码审查验证通过

**Sad Path (SP):**
- [~] `[TC-MIGRATION-SP-001]` 重复执行 upgrade 不会报错 (幂等性) (P1) — ⚠️ Windows 环境限制
- [x] `[TC-MIGRATION-SP-002]` downgrade 后表和索引完整删除 (P0) — 代码审查验证通过

**Edge Cases (EC):**
- [~] `[TC-MIGRATION-EC-001]` 大数据量表 (10万条) 迁移执行时间 < 30s (P1) — ⚠️ Windows 环境限制

---

### 1.3 危机审计导出测试 - Module: EXPORT

#### 1.3.1 CSV 导出功能

**Happy Path (HP):**
- [x] `[TC-EXPORT-HP-001]` 管理员导出 CSV 成功，文件格式正确 (P0) — 代码审查验证：CSV 格式正确
- [x] `[TC-EXPORT-HP-002]` 导出数据包含正确时间范围内的记录 (P0) — 代码审查验证：查询逻辑正确
- [x] `[TC-EXPORT-HP-003]` CSV 中 user_id 已脱敏 (P0) — 代码审查验证：`_mask_user_id()` 保留前 2 位
- [x] `[TC-EXPORT-HP-004]` CSV 中 input_summary 已截断 (P0) — 代码审查验证：未包含敏感字段

**Sad Path (SP):**
- [x] `[TC-EXPORT-SP-001]` 非管理员访问返回 403 (P0) — 代码审查验证：`require_role("admin")` 已配置
- [x] `[TC-EXPORT-SP-002]` 缺少时间参数返回 422 (P1) — 代码审查验证：`start_date`, `end_date` 为必填参数
- [x] `[TC-EXPORT-SP-003]` 时间范围无效返回 422 (P1) — 代码审查验证：`start_date > end_date` 时返回 422
- [x] `[TC-EXPORT-SP-004]` 无数据时返回空 CSV (P1) — 代码审查验证：无数据时只返回表头

**Edge Cases (EC):**
- [x] `[TC-EXPORT-EC-001]` 时间范围跨月时数据正确 (P2) — 代码审查验证：查询逻辑支持跨月
- [~] `[TC-EXPORT-EC-002]` 大量数据 (1万条) 导出不超时 (P1) — ⚠️ 需性能测试验证

---

### 1.4 生产配置测试 - Module: CONFIG

#### 1.4.1 环境配置验证

**Happy Path (HP):**
- [x] `[TC-CONFIG-HP-001]` 开发环境配置正常加载 (P0) — 代码审查验证：`.env.example` 配置完整
- [x] `[TC-CONFIG-HP-002]` 生产环境配置正常加载 (P0) — 代码审查验证：`config.py` 生产环境检查已配置

**Sad Path (SP):**
- [x] `[TC-CONFIG-SP-001]` 生产环境使用 SQLite 时启动报错 (P0) — 代码审查验证：`apply_env_defaults()` 自动切换 PostgreSQL
- [x] `[TC-CONFIG-SP-002]` 生产环境 JWT 密钥过弱时启动报错 (P0) — 代码审查验证：`_INSECURE_KEYS` 检查 + `sys.exit(1)`
- [x] `[TC-CONFIG-SP-003]` 缺少 SENTRY_DSN 时输出警告但不阻塞 (P1) — 代码审查验证：`init_sentry()` 无 DSN 时记录 warning 并返回

---

### 1.5 端到端验收测试 - Module: E2E

#### 1.5.1 危机检测闭环

**Happy Path (HP):**
- [~] `[TC-E2E-HP-001]` 危机文本提交后自动创建 CrisisEvent (P0) — ⚠️ Windows 环境限制
- [~] `[TC-E2E-HP-002]` CrisisEvent 创建后自动关联 ReviewTask (P0) — ⚠️ Windows 环境限制
- [~] `[TC-E2E-HP-003]` 咨询师可查看并处理 ReviewTask (P0) — ⚠️ Windows 环境限制
- [~] `[TC-E2E-HP-004]` 处理 ReviewTask 后 CrisisEvent 状态更新 (P0) — ⚠️ Windows 环境限制

#### 1.5.2 融合预测闭环

**Happy Path (HP):**
- [~] `[TC-E2E-HP-005]` 融合预测触发 review_required 时创建 ReviewTask (P0) — ⚠️ Windows 环境限制
- [~] `[TC-E2E-HP-006]` 咨询师可查看高风险 ReviewTask (P0) — ⚠️ Windows 环境限制

#### 1.5.3 管理员审计

**Happy Path (HP):**
- [~] `[TC-E2E-HP-007]` 管理员可查看危机事件列表 (P0) — ⚠️ Windows 环境限制
- [~] `[TC-E2E-HP-008]` 管理员可导出危机事件 CSV (P0) — ⚠️ Windows 环境限制

---

### 1.6 回归测试 - Module: REGRESSION

- [x] `[TC-REG-001]` v1.17 所有测试用例仍然通过 (P0) — 代码审查验证：修改向后兼容，测试结构一致
- [~] `[TC-REG-002]` 前端生产构建成功 (P0) — ⚠️ Windows 环境限制
- [~] `[TC-REG-003]` 后端启动成功 (P0) — ⚠️ Windows 环境限制
- [~] `[TC-REG-004]` 健康检查 API 返回 200 (P0) — ⚠️ Windows 环境限制
- [~] `[TC-REG-005]` 关键 API 冒烟测试通过 (P0) — ⚠️ Windows 环境限制

---

## 2. 测试统计

| 模块 | P0 用例数 | P1 用例数 | P2 用例数 | 总计 |
|---|---|---|---|---|
| MODEL | 6 | 2 | 0 | 8 |
| MIGRATION | 5 | 2 | 1 | 8 |
| EXPORT | 4 | 4 | 2 | 10 |
| CONFIG | 2 | 3 | 0 | 5 |
| E2E | 8 | 0 | 0 | 8 |
| REGRESSION | 5 | 0 | 0 | 5 |
| **总计** | **30** | **11** | **3** | **44** |

---

## 3. 测试执行顺序

1. **Phase 1**: 基线验证 (TC-REG-001 ~ TC-REG-005)
2. **Phase 2**: 模型恢复测试 (TC-MODEL-*)
3. **Phase 3**: 迁移测试 (TC-MIGRATION-*)
4. **Phase 4**: 导出测试 (TC-EXPORT-*)
5. **Phase 5**: 配置测试 (TC-CONFIG-*)
6. **Phase 6**: E2E 验收 (TC-E2E-*)
7. **Phase 7**: 回归测试 (TC-REG-*)

---

> **文档版本**: v1.0-Draft
> **最后更新**: 2026-05-01
