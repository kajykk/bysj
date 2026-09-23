# 复核工作流报告 — v1.17-review-workflow-text-model-upgrade

> **生成时间**: 2026-05-01
> **迭代版本**: v1.17-review-workflow-text-model-upgrade
> **上一版本**: v1.16-risk-calibration-safety

---

## 1. 复核工作流概述

v1.17 将 v1.16 的 `review_required` 字段升级为完整的业务闭环，实现了从风险识别到人工处理的全流程管理。

---

## 2. 数据模型

### 2.1 ReviewTask（复核任务）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | 自增ID |
| user_id | int FK | 关联用户 |
| risk_report_id | int FK | 关联风险报告 |
| risk_level | int | 风险等级 (0-4) |
| risk_score | float | 风险分数 |
| review_triggers | JSON | 复核原因列表 |
| crisis_override | bool | 是否危机覆盖 |
| status | enum | pending/in_review/resolved/escalated/archived |
| priority | enum | normal_review/high_risk_review/crisis_review |
| assigned_to | int FK | 分配给的咨询师 |
| resolved_by | int FK | 处理的咨询师 |
| resolution_note | text | 处理备注 |
| created_at | datetime | 创建时间 |
| resolved_at | datetime | 处理时间 |

### 2.2 状态流转

```
pending -> assign -> in_review -> resolve -> resolved -> archive -> archived
pending -> assign -> in_review -> escalate -> escalated
```

---

## 3. API 接口

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | /reviews | 查询复核任务列表 | review.view |
| GET | /reviews/{id} | 查看复核详情 | review.view |
| POST | /reviews/{id}/assign | 分配复核任务 | review.handle |
| POST | /reviews/{id}/resolve | 处理复核任务 | review.handle |
| POST | /reviews/{id}/escalate | 升级复核任务 | review.handle |
| GET | /reviews/stats | 复核统计 | review.view |

---

## 4. 自动触发规则

| 触发条件 | 优先级 | 说明 |
|---|---|---|
| crisis_override=true | crisis_review | 危机表达覆盖 |
| risk_level >= 3 | high_risk_review | 单模型高风险 |
| review_required=true | normal_review | 其他复核原因 |

---

## 5. 前端页面

### 5.1 复核任务列表页 (`/counselor/reviews`)

- 状态筛选：待处理、处理中、已处理、已升级
- 优先级筛选：普通、高风险、危机
- 统计卡片：待处理数、处理中数、已处理数、危机事件数
- 分页支持

### 5.2 复核详情页 (`/counselor/reviews/:id`)

- 用户信息展示
- 模型预测结果（风险分数、等级、优先级）
- 触发原因标签
- 危机事件警告横幅
- 处理操作：标记已处理、升级危机事件
- 处理备注输入

---

## 6. 权限控制

| 角色 | 查看列表 | 查看详情 | 分配任务 | 处理任务 | 升级任务 |
|---|---|---|---|---|---|
| user | 仅自己的 | 仅自己的 | 否 | 否 | 否 |
| counselor | 分配的 | 分配的 | 是 | 是 | 是 |
| admin | 全部 | 全部 | 是 | 是 | 是 |

---

## 7. 测试覆盖

| 测试类型 | 数量 | 通过 |
|---|---|---|
| Service 单元测试 | 15 | 15 |
| API 集成测试 | 7 | 7 |
| 危机审计测试 | 4 | 4 |
| 回归测试 | 42 | 42 |
| **总计** | **68** | **68** |

---

> **文档版本**: v1.0
> **生成时间**: 2026-05-01
