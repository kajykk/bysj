# v1.18 生产上线硬化与结构化模型恢复 — 需求文档

> **迭代**: v1.18-production-hardening-model-recovery
> **日期**: 2026-05-01
> **状态**: Round 1 Draft
> **基于**: v1.17-review-workflow-text-model-upgrade 遗留问题

---

## 1. 项目概述

### 1.1 背景

v1.17 完成了复核工作流和危机审计闭环，但留下了多个上线硬化风险：
- 结构化模型文件 `structured_logistic_regression_quick` 损坏，导致结构化预测 API 返回 422
- 新增 `review_tasks` / `crisis_events` 表的数据库迁移脚本已生成但未执行验证
- 危机事件审计缺少 CSV 导出功能
- SENTRY_DSN 和生产观测配置未补齐
- v1.17 新增的复核/危机闭环需要生产级 E2E 验收

### 1.2 目标

一句话：**修复 v1.17 遗留的上线阻塞问题，使系统达到生产部署 hardened 状态。**

### 1.3 目标用户

- **运维人员**: 需要可执行的迁移脚本和回滚方案
- **咨询师/管理员**: 需要完整的复核任务管理和危机事件导出
- **开发团队**: 需要生产级观测配置和错误追踪

---

## 2. 详细功能设计

### 2.1 模块 A: 结构化模型恢复

#### 2.1.1 功能: 模型文件修复/替换
**路径**: `backend/app/ml/model_loader.py`

**需求详情**:
- 诊断 `structured_logistic_regression_quick` 模型文件损坏原因
- 重新训练或从备份恢复该模型
- 验证模型加载不再抛出异常
- 验证低/中/高/极高风险样本预测符合预期

**验收标准**:
- 结构化预测 API `POST /api/v1/predict/structured` 返回 200
- 4 个风险等级样本预测结果与 v1.16 基线一致（偏差 < 5%）

---

### 2.2 模块 B: 数据库迁移落地

#### 2.2.1 功能: 迁移脚本执行验证
**路径**: `backend/alembic/versions/a1b2c3d4e5f6_add_review_and_crisis_tables.py`

**需求详情**:
- 在空数据库上执行 `alembic upgrade head` 成功
- 在已有 v1.17 数据的数据库上执行迁移成功
- 验证 `review_tasks` 表结构符合模型定义
- 验证 `crisis_events` 表结构符合模型定义
- 准备 downgrade 回滚方案

**验收标准**:
- 迁移执行无报错
- 表结构、索引、外键约束正确
- downgrade 可完整回滚

---

### 2.3 模块 C: 危机审计导出

#### 2.3.1 页面/接口: 危机事件 CSV 导出
**路径**: `GET /api/v1/admin/crisis-events/export`

**UI 元素清单**:

| 元素名称 | 类型 | 验证规则 | 默认值 | 交互逻辑 | 异常处理 | 权限 |
|---|---|---|---|---|---|---|
| 时间范围 | DateRange | 必填 | 最近7天 | 选择后触发查询 | 显示"请选择时间范围" | admin |
| 导出按钮 | Button | - | - | 点击下载 CSV | 无数据时禁用 | admin |

**逻辑流程**:
1. 管理员选择时间范围
2. 系统查询 crisis_events 表
3. 对敏感字段脱敏（user_id 哈希化、input_summary 截断）
4. 生成 CSV 文件下载

**脱敏规则**:
- `user_id`: 取前 4 位 + "****"
- `input_summary`: 截断至 50 字符
- `crisis_keywords`: 保留原样（用于分析）

---

### 2.4 模块 D: 生产配置硬化

#### 2.4.1 功能: 生产环境配置补齐
**路径**: `backend/.env.example`, `backend/app/core/config.py`

**需求详情**:
- 补齐 `SENTRY_DSN` 配置项
- 补齐生产数据库 URL 配置说明
- 补齐 Redis 配置说明
- 添加生产环境安全检查（JWT 密钥强度、数据库非 SQLite）

#### 2.4.2 功能: 观测与告警
**路径**: `backend/app/monitoring/alerting.py`

**需求详情**:
- 配置 Sentry 错误追踪
- 配置关键 API 延迟告警阈值（> 500ms）
- 配置危机事件检测告警

---

### 2.5 模块 E: 端到端验收

#### 2.5.1 功能: v1.17 闭环 E2E 验证
**路径**: 全链路

**需求详情**:
- 危机文本输入 -> 自动创建 CrisisEvent
- 融合预测触发 review_required -> 自动创建 ReviewTask
- 咨询师登录 -> 查看复核任务列表 -> 处理任务
- 管理员登录 -> 查看危机事件列表 -> 导出 CSV

---

## 3. 非功能需求

- **性能**: 迁移脚本在 10 万条数据量下执行时间 < 30s
- **安全**: CSV 导出必须脱敏，防止隐私泄露
- **兼容性**: 迁移脚本支持 SQLite 和 PostgreSQL
- **可维护性**: 所有配置变更必须更新 `.env.example` 文档

---

## 4. 假设与约束

- 假设 v1.17 的模型训练代码仍然可用，可以重新训练结构化模型
- 假设生产环境使用 PostgreSQL（开发环境使用 SQLite）
- 约束：v1.18 不新增大功能，只做硬化和修复

---

> **文档版本**: v1.0-Draft
> **最后更新**: 2026-05-01
