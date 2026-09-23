# BASELINE — v1.19-ci-e2e-audit-export

> **生成时间**: 2026-05-01  
> **基于**: v1.18 `05-test-plan.md` (44测试, 17项未实测)  
> **目标**: v1.18 未实测项 → v1.19 全量实测

---

## 1. v1.18 未实测项清单

### P0 级 (14项) — v1.19 必须全量实测

| 编号 | v1.18 测试ID | 描述 | v1.19 对应测试 |
|---|---|---|---|
| U01 | TC-MIGRATION-HP-001 | 空库 alembic upgrade 成功 | TC-MIG-HP-001 |
| U02 | TC-MIGRATION-HP-002 | 已有数据 upgrade 成功 | TC-MIG-HP-007 |
| U03 | TC-E2E-HP-001 | 危机文本 → CrisisEvent 创建 | TC-E2E-HP-001 |
| U04 | TC-E2E-HP-002 | CrisisEvent → ReviewTask 关联 | TC-E2E-HP-002 |
| U05 | TC-E2E-HP-003 | 咨询师查看处理 ReviewTask | TC-E2E-HP-003 |
| U06 | TC-E2E-HP-004 | ReviewTask 处理后状态更新 | TC-E2E-HP-005 |
| U07 | TC-E2E-HP-005 | 融合预测 → ReviewTask | TC-E2E-HP-006 |
| U08 | TC-E2E-HP-006 | 咨询师查看高风险 ReviewTask | TC-E2E-HP-008 |
| U09 | TC-E2E-HP-007 | 管理员查看危机事件列表 | TC-E2E-HP-001 (列表页) |
| U10 | TC-E2E-HP-008 | 管理员导出危机事件 CSV | TC-UI-HP-003 |
| U11 | TC-REG-002 | 前端生产构建成功 | TC-FE-HP-002 |
| U12 | TC-REG-003 | 后端启动成功 | TC-CI-HP-006 |
| U13 | TC-REG-004 | 健康检查 API 200 | TC-CI-HP-005 |
| U14 | TC-REG-005 | 关键 API 冒烟测试 | TC-CI-HP-007, TC-CI-HP-008 |

### P1 级 (3项) — v1.19 建议实测

| 编号 | v1.18 测试ID | 描述 | v1.19 对应测试 |
|---|---|---|---|
| U15 | TC-MIGRATION-SP-001 | 重复 upgrade 幂等性 | TC-MIG-SP-002 |
| U16 | TC-MIGRATION-EC-001 | 大数据量迁移性能 | TC-MIG-SP-003 (简化) |
| U17 | TC-EXPORT-EC-002 | 大量数据导出性能 | TC-EXP-EC-002 |

---

## 2. v1.19 新增项

| 类别 | 数量 | 说明 |
|---|---|---|
| 全新前端页面 | 1 | AdminCrisisEventsPage.vue (列表 + 导出 UI) |
| CI 验证脚本 | 2 | ci_backend_verify.sh, ci_frontend_verify.sh |
| 回归测试 | 6 | v1.18 核心功能回归验证 |
| 前端导出 UI 测试 | 7 | 渲染/交互/错误处理 |

---

## 3. 实测环境对比

| 项目 | v1.18 现状 | v1.19 目标 |
|---|---|---|
| 后端测试 | ❌ 代码审查验证 | ✅ Docker 容器 pytest |
| 数据库迁移 | ❌ 代码审查验证 | ✅ 真实数据库 upgrade/downgrade |
| E2E 闭环 | ❌ 代码审查验证 | ✅ Docker 环境跑通 |
| 前端构建 | ❌ Windows 限制 | ✅ Docker/Linux npm run build |
| 前端导出 | ❌ 无 UI | ✅ 完整页面 + 导出按钮 |

---

## 4. 执行策略

v1.19 按照 04-ralph-tasks.md 物理顺序执行：

1. **Phase 2**: 检查 Docker/CI 配置 → 脚本化
2. **Phase 3**: 数据库迁移实测 (U01, U02, U15)
3. **Phase 4**: 后端 pytest + 冒烟 (U12-U14)
4. **Phase 5**: 前端危机事件列表页 + 导出 UI (U09, U10) + 构建 (U11)
5. **Phase 6**: E2E 实测 (U03-U08)
6. **Phase 7-9**: 模型预研 + 报告归档 + 交付

---

> **文档版本**: v1.0  
> **最后更新**: 2026-05-01
