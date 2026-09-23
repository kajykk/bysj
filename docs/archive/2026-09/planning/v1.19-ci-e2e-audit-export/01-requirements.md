# 项目需求文档 (PRD) — v1.19-ci-e2e-audit-export

> **版本**: v1.0-Draft  
> **日期**: 2026-05-01  
> **基于**: `e:\code\bysj\md\3.md`

## 1. 项目概述

### 1.1 背景
v1.18 (`production-hardening-model-recovery`) 已完成并通过用户验收，但交付报告给出的是 **Conditional Go**：
- 大量测试因 Windows 环境限制仅为"代码审查验证"，未真实执行
- P0 级 E2E 测试 (`TC-E2E-HP-001` ~ `TC-E2E-HP-008`) 全部未实测
- 数据库迁移 (`alembic upgrade/downgrade`) 未在真实数据库环境执行
- 前端危机事件 CSV 导出按钮未实现（API 已完成）

### 1.2 目标
**把 v1.18 的 Conditional Go 推进为真正可上线的 Go**，通过 CI/Docker 实测、数据库迁移实测、复核/危机审计 E2E 实测，以及管理员端 CSV 导出 UI 补齐。

### 1.3 目标用户
- **开发者/运维**: 需要在 Docker/Linux CI 环境中重复执行验证
- **咨询师**: 需要复核任务处理闭环
- **管理员**: 需要前端导出危机事件 CSV，而非直接调用 API
- **系统上线决策者**: 需要 Go/No-Go 报告

---

## 2. 详细功能设计

### 2.1 模块 A: CI/Docker 验证环境 (Phase 2-4)

#### 2.1.1 界面/操作: 后端 Docker 测试
**路径**: Docker 容器内执行

| 元素/命令 | 类型 | 验证规则 | 交互逻辑 | 异常处理 |
|---|---|---|---|---|
| `pytest` | CLI | exit code 0 | 运行全部后端测试 | 输出失败用例详情 |
| `alembic upgrade head` | CLI | 成功执行 | 创建 review_tasks / crisis_events 表 | 输出迁移错误日志 |
| `alembic downgrade -1` | CLI | 成功执行 | 删除新增表 | 确认回滚完整 |
| `uvicorn app.main:app` | CLI | 服务监听成功 | 启动 FastAPI | 端口冲突提示 |
| `curl /health` | API | 200 + status ok | 健康检查 | 超时/503 |

#### 2.1.2 界面/操作: 前端构建验证
**路径**: Docker/本地 Node.js 环境

| 元素/命令 | 类型 | 验证规则 | 交互逻辑 | 异常处理 |
|---|---|---|---|---|
| `npm ci` | CLI | exit code 0 | 安装依赖 | 网络错误重试 |
| `npm run build` | CLI | exit code 0, 产出 dist/ | 生产构建 | chunk warning 记录不阻塞 |

---

### 2.2 模块 B: 管理员危机事件列表页与导出 (Phase 5) — **新建页面**

#### 2.2.1 页面: 危机事件列表页
**路径**: `/admin/crisis-events` (新建)  
**参考**: `AdminOperationLogsPage.vue` (已有 DatePicker + 表格模式)

| 元素名称 | 类型 | 验证规则 | 默认值 | 交互逻辑 | 异常处理 | 权限 |
|---|---|---|---|---|---|---|
| 危机事件表格 | Table | - | - | 显示 id/user_id/trigger_source/crisis_score/status/created_at | 加载失败 Toast | Admin |
| 开始日期 | DatePicker | 必填, ≤ 结束日期 | 30天前 | 选择日期范围 | 非法范围禁用导出 | Admin |
| 结束日期 | DatePicker | 必填, ≥ 开始日期 | 今天 | 选择日期范围 | 非法范围禁用导出 | Admin |
| 导出 CSV 按钮 | Button | - | Enabled | 点击 → Loading → 下载 CSV | 网络错误 Toast / 空数据提示 | Admin |

**逻辑流程**:
1. 管理员访问 `/admin/crisis-events`
2. 页面加载危机事件列表
3. 选择开始/结束日期
4. 点击"导出 CSV"
5. API 调用 → blob 下载

---

### 2.3 模块 C: 复核与危机审计 E2E (Phase 6)

#### 2.3.1 流程: 危机文本闭环
**触发**: 用户提交含危机关键词的文本

```
用户提交文本 → CrisisDetector 检测到危机
→ 创建 CrisisEvent (status=detected)
→ 创建/关联 ReviewTask (priority=crisis_review)
→ 咨询师查看 ReviewTask 列表
→ 咨询师处理 ReviewTask (resolved, escalated)
→ CrisisEvent 状态更新
→ 管理员查看危机事件列表
```

#### 2.3.2 流程: 融合预测闭环
**触发**: 用户提交融合预测 (结构化+文本)

```
用户提交融合预测 → risk_level >= 3 或 review_required=true
→ 自动创建 ReviewTask
→ 咨询师查看并处理
```

---

## 3. 非功能需求

- **可重复性**: CI/Docker 环境中所有验证命令可重复执行
- **可追溯性**: 每次 CI 产出结构化报告 (JSON/Markdown)
- **性能**: 危机事件 CSV 导出 < 2s (1000 条以内)
- **安全**: CSV 导出 user_id 脱敏、非管理员 403
- **兼容性**: Docker 环境支持 Linux amd64

---

## 4. 假设与约束

- 假设 Docker Desktop 或 Linux CI runner 可用
- 假设 `docker-compose.yml` 或 `Dockerfile.test` 基础配置已存在
- 假设前端危机事件列表页已存在，只需添加导出按钮
- 约束: BERT 模型升级推迟到 v1.20+
- 约束: 覆盖率 80% 不作为 v1.19 阻塞项

---

> **文档版本**: v1.0-Draft  
> **最后更新**: 2026-05-01
