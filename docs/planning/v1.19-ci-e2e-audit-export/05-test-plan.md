# 测试计划 — v1.19-ci-e2e-audit-export

> **生成时间**: 2026-05-01  
> **基于文档**: 01-requirements.md, 02-architecture.md, 03-design.md  
> **测试框架**: pytest (后端) + Vitest (前端) + 手动 E2E

> **⚠️ 执行铁律**: 必须严格按照列表顺序（从上到下）执行测试用例。严禁跳跃或乱序执行。

---

## 1. 测试用例详情

### 1.1 CI/Docker 后端验证 - Module: CI-BACKEND

**Happy Path (HP):**
- [ ] `[TC-CI-HP-001]` 后端依赖安装成功, exit code 0 (P0)
- [ ] `[TC-CI-HP-002]` `pytest` 全量运行通过 (P0)
- [ ] `[TC-CI-HP-003]` `alembic upgrade head` 成功执行 (P0)
- [ ] `[TC-CI-HP-004]` `alembic downgrade -1` 成功回滚 (P0)
- [ ] `[TC-CI-HP-005]` `/health` 返回 200 + status ok (P0)
- [ ] `[TC-CI-HP-006]` `/health/ready` 返回 200 (P0)
- [ ] `[TC-CI-HP-007]` 结构化预测 API (fallback) 返回 200 (P0)
- [ ] `[TC-CI-HP-008]` 文本预测 API 返回 200 (P0)

---

### 1.2 前端构建验证 - Module: CI-FRONTEND

**Happy Path (HP):**
- [ ] `[TC-FE-HP-001]` `npm ci` 成功 (P0)
- [ ] `[TC-FE-HP-002]` `npm run build` exit code 0 (P0)
- [ ] `[TC-FE-HP-003]` 构建产物 `dist/` 存在 (P0)
- [ ] `[TC-FE-HP-004]` 无阻塞型 build error (P0)

**Edge Cases (EC):**
- [ ] `[TC-FE-EC-001]` chunk size warning 记录但不阻塞 (P2)

---

### 1.3 数据库迁移实测 - Module: MIGRATION

**Happy Path (HP):**
- [ ] `[TC-MIG-HP-001]` 空库 `alembic upgrade head` 成功创建 review_tasks 表 (P0)
- [ ] `[TC-MIG-HP-002]` 空库 `alembic upgrade head` 成功创建 crisis_events 表 (P0)
- [ ] `[TC-MIG-HP-003]` review_tasks 表字段与模型定义一致 (P0)
- [ ] `[TC-MIG-HP-004]` crisis_events 表字段与模型定义一致 (P0)
- [ ] `[TC-MIG-HP-005]` 索引 `ix_crisis_events_status_created_at` 存在 (P0)
- [ ] `[TC-MIG-HP-006]` 索引 `ix_crisis_events_trigger_source_created_at` 存在 (P0)
- [ ] `[TC-MIG-HP-007]` 已有数据库迁移后已有数据不丢失 (P0)

**Sad Path (SP):**
- [ ] `[TC-MIG-SP-001]` `alembic downgrade -1` 成功删除新表和索引 (P0)
- [ ] `[TC-MIG-SP-002]` 重复执行 upgrade 不报错 (幂等性) (P1)
- [ ] `[TC-MIG-SP-003]` 迁移失败时数据库回滚到迁移前状态 (P1)

---

### 1.4 危机事件 CSV 导出 - Module: EXPORT

**Happy Path (HP):**
- [ ] `[TC-EXP-HP-001]` 管理员导出 CSV，文件格式正确 (P0)
- [ ] `[TC-EXP-HP-002]` CSV 中 user_id 已脱敏（保留前 2 位）(P0)
- [ ] `[TC-EXP-HP-003]` CSV 中 handled_by 已脱敏 (P0)
- [ ] `[TC-EXP-HP-004]` 导出数据在正确时间范围内 (P0)
- [ ] `[TC-EXP-HP-005]` 文件名格式正确: `crisis_events_YYYYMMDD_YYYYMMDD.csv` (P1)

**Sad Path (SP):**
- [ ] `[TC-EXP-SP-001]` 非管理员访问返回 403 (P0)
- [ ] `[TC-EXP-SP-002]` 缺少 start_date 参数返回 422 (P1)
- [ ] `[TC-EXP-SP-003]` start_date > end_date 返回 422 (P1)
- [ ] `[TC-EXP-SP-004]` 无数据时返回空 CSV（仅表头）(P1)

**Edge Cases (EC):**
- [ ] `[TC-EXP-EC-001]` 跨月导出数据正确 (P2)
- [ ] `[TC-EXP-EC-002]` 大量数据 (1万条) 导出不超时 (P2)

---

### 1.5 危机文本闭环 E2E - Module: E2E-CRISIS

**Happy Path (HP):**
- [ ] `[TC-E2E-HP-001]` 用户提交危机文本 → CrisisEvent 创建成功 (P0)
- [ ] `[TC-E2E-HP-002]` CrisisEvent 创建后自动关联 ReviewTask (P0)
- [ ] `[TC-E2E-HP-003]` 咨询师可查看待处理 ReviewTask 列表 (P0)
- [ ] `[TC-E2E-HP-004]` 咨询师处理 ReviewTask (resolve) 成功 (P0)
- [ ] `[TC-E2E-HP-005]` ReviewTask 处理后 CrisisEvent 状态更新 (P0)

---

### 1.6 融合预测闭环 E2E - Module: E2E-FUSION

**Happy Path (HP):**
- [ ] `[TC-E2E-HP-006]` 高风险融合预测触发 review_required=true (P0)
- [ ] `[TC-E2E-HP-007]` review_required 时自动创建 ReviewTask (P0)
- [ ] `[TC-E2E-HP-008]` 咨询师可查看和处理 ReviewTask (P0)

---

### 1.7 前端导出 UI - Module: UI-EXPORT

**Happy Path (HP):**
- [ ] `[TC-UI-HP-001]` 日期选择器正常渲染 (P0)
- [ ] `[TC-UI-HP-002]` 导出按钮默认状态正常 (P0)
- [ ] `[TC-UI-HP-003]` 点击导出触发 API 调用 (P0)
- [ ] `[TC-UI-HP-004]` 导出中显示 Loading 状态 (P1)
- [ ] `[TC-UI-HP-005]` 导出成功触发 CSV 下载 (P0)

**Sad Path (SP):**
- [ ] `[TC-UI-SP-001]` 网络错误显示 Error Toast (P1)
- [ ] `[TC-UI-SP-002]` 空数据显示"无数据"提示 (P1)
- [ ] `[TC-UI-SP-003]` 无权限时显示提示 (P1)

---

### 1.8 结构化模型重训预研 - Module: MODEL-PRE

- [ ] `[TC-MP-001]` `train_baseline.py` 脚本存在且可解析 (P1)
- [ ] `[TC-MP-002]` 训练数据文件存在且格式正确 (P1)
- [ ] `[TC-MP-003]` sklearn 版本与模型兼容 (P1)

---

### 1.9 v1.18 功能回归测试 - Module: REGRESSION

- [ ] `[TC-REG-001]` 结构化模型 fallback 可用，4 个风险等级输出正确 (P0)
- [ ] `[TC-REG-002]` `GET /api/v1/admin/crisis-events/export` 管理员可用 (P0)
- [ ] `[TC-REG-003]` `GET /api/v1/admin/crisis-events/export` 非管理员 403 (P0)
- [ ] `[TC-REG-004]` CSV 导出 user_id 脱敏正确 (P0)
- [ ] `[TC-REG-005]` Sentry 配置正常加载 (P1)
- [ ] `[TC-REG-006]` `.env.example` 配置项完整 (P1)

---

## 2. 测试统计

| 模块 | P0 | P1 | P2 | 总计 |
|---|---|---|---|---|
| CI-BACKEND | 8 | 0 | 0 | 8 |
| CI-FRONTEND | 4 | 0 | 1 | 5 |
| MIGRATION | 7 | 2 | 0 | 9 |
| EXPORT | 4 | 4 | 2 | 10 |
| E2E-CRISIS | 5 | 0 | 0 | 5 |
| E2E-FUSION | 3 | 0 | 0 | 3 |
| UI-EXPORT | 4 | 3 | 0 | 7 |
| MODEL-PRE | 0 | 3 | 0 | 3 |
| REGRESSION | 4 | 2 | 0 | 6 |
| **总计** | **39** | **14** | **3** | **56** |

---

## 3. 测试执行顺序

1. **Phase 1**: CI-FRONTEND (前端构建)
2. **Phase 2**: CI-BACKEND (后端启动与 pytest)
3. **Phase 3**: MIGRATION (数据库迁移)
4. **Phase 4**: EXPORT (CSV 导出 API)
5. **Phase 5**: UI-EXPORT (前端导出 UI)
6. **Phase 6**: E2E-CRISIS (危机文本闭环)
7. **Phase 7**: E2E-FUSION (融合预测闭环)
8. **Phase 8**: REGRESSION (v1.18 功能回归)
9. **Phase 9**: MODEL-PRE (模型重训预研)

---

> **文档版本**: v1.0-Draft  
> **最后更新**: 2026-05-01
