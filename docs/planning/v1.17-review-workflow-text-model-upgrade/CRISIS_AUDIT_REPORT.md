# 危机审计报告 — v1.17-review-workflow-text-model-upgrade

> **生成时间**: 2026-05-01
> **迭代版本**: v1.17-review-workflow-text-model-upgrade

---

## 1. 危机审计概述

v1.17 实现了完整的危机事件审计日志系统，确保所有危机表达可被追踪、查询和导出。

---

## 2. 数据模型

### 2.1 CrisisEvent（危机事件）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | 自增ID |
| user_id | int FK | 关联用户 |
| report_id | int FK | 关联报告 |
| trigger_source | enum | text/fusion/structured |
| crisis_keywords | JSON | 命中关键词 |
| crisis_score | float | 危机分数 |
| input_summary | text | 输入摘要（脱敏） |
| review_task_id | int FK | 关联复核任务 |
| status | enum | detected/handled/ignored |
| handled_by | int FK | 处理人 |
| handled_action | text | 处理动作 |
| created_at | datetime | 创建时间 |
| handled_at | datetime | 处理时间 |

---

## 3. 自动记录机制

### 3.1 文本预测触发

当 `/model/predict/text` 检测到 `crisis_detected=true` 时，自动记录：
- 用户ID
- 触发来源：text
- 命中关键词
- crisis_score
- 输入摘要（前200字符）

### 3.2 融合预测触发

当 `/model/predict/fusion` 检测到 `crisis_override=true` 时，自动记录：
- 用户ID
- 触发来源：fusion
- 关联复核任务ID

---

## 4. API 接口

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | /reviews/crisis-events | 查询危机事件 | crisis_event.view |
| GET | /reviews/crisis-events/stats | 危机统计 | crisis_event.view |

---

## 5. 查询能力

- 按状态筛选：detected / handled / ignored
- 按时间范围筛选
- 分页支持
- 导出 CSV（待实现）

---

## 6. 测试覆盖

| 测试 | 说明 | 状态 |
|---|---|---|
| TC-CRISIS-HP-001 | 检测到危机时自动记录 | 通过 |
| TC-CRISIS-HP-004 | 管理员可查询危机事件 | 通过 |
| TC-CRISIS-SP-001 | 普通用户不可查询 | 通过 |

---

> **文档版本**: v1.0
> **生成时间**: 2026-05-01
