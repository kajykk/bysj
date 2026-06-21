# v1.17 架构文档 — 人工复核与危机审计闭环

> **迭代名称**: v1.17-review-workflow-text-model-upgrade
> **规划日期**: 2026-05-01

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                        前端层 (Vue.js)                       │
├─────────────────────────────────────────────────────────────┤
│  用户端              │  咨询师端              │  管理端      │
│  UserRiskPage        │  CounselorReviewList   │  AdminAudit  │
│  (风险报告)          │  CounselorReviewDetail │  (审计查询)   │
│                      │  (复核处理)            │              │
└──────────────────────┴───────────────────────┴──────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      API 层 (FastAPI)                        │
├─────────────────────────────────────────────────────────────┤
│  /reviews              │  /reviews/{id}        │  /crisis-events│
│  GET / POST            │  GET / POST resolve   │  GET / POST   │
│  /reviews/stats        │  /reviews/{id}/assign │  /crisis-events│
│                        │  /reviews/{id}/escalate│ /export      │
└──────────────────────┴───────────────────────┴──────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     服务层 (Service)                         │
├─────────────────────────────────────────────────────────────┤
│  ReviewService         │  CrisisEventService   │  ModelEngine │
│  - create_review_task  │  - record_crisis      │  (v1.16)     │
│  - assign_review       │  - query_events       │              │
│  - resolve_review      │  - export_events      │              │
│  - escalate_review     │                       │              │
└──────────────────────┴───────────────────────┴──────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     数据层 (SQLAlchemy)                      │
├─────────────────────────────────────────────────────────────┤
│  review_tasks          │  crisis_events        │  users       │
│  - id                  │  - id                 │  (现有)      │
│  - user_id             │  - user_id            │              │
│  - risk_report_id      │  - report_id          │              │
│  - risk_level          │  - crisis_keywords    │              │
│  - review_triggers     │  - crisis_score       │              │
│  - status              │  - trigger_source     │              │
│  - priority            │  - created_at         │              │
│  - assigned_to         │  - resolved_by        │              │
│  - resolved_by         │  - resolved_at        │              │
│  - resolution_note     │                       │              │
│  - created_at          │                       │              │
│  - updated_at          │                       │              │
└──────────────────────┴───────────────────────┴──────────────┘
```

---

## 2. 核心模块设计

### 2.1 Review Task 模块

**职责**: 管理人工复核任务的全生命周期

**状态机**:

```
                    ┌─────────────┐
                    │   pending   │
                    └──────┬──────┘
                           │ assign
                           ▼
                    ┌─────────────┐
         ┌─────────│  in_review  │─────────┐
         │         └──────┬──────┘         │
         │ escalate       │ resolve        │
         ▼                ▼                │
┌─────────────┐    ┌─────────────┐        │
│  escalated  │    │   resolved  │        │
└──────┬──────┘    └──────┬──────┘        │
       │                  │ archive       │
       │                  ▼               │
       │           ┌─────────────┐        │
       │           │   archived  │        │
       │           └─────────────┘        │
       │                                  │
       └──────────────────────────────────┘
```

**优先级**:

- `crisis_review`: 危机事件，最高优先级
- `high_risk_review`: 高风险复核
- `normal_review`: 普通复核

### 2.2 Crisis Event 模块

**职责**: 记录所有危机事件的审计信息

**不可变原则**: 危机事件记录一旦创建，核心字段不可修改，仅可更新处理状态

**记录内容**:

- 用户标识（脱敏）
- 触发来源（文本/API/融合）
- 命中关键词
- crisis_score
- 原始输入摘要
- 时间戳
- 处理人
- 处理动作

### 2.3 关键词库模块

**职责**: 管理危机关键词的加载、匹配和更新

**设计**:

- 关键词库以配置文件形式存储
- 支持分类管理（自杀/自伤/绝望/网络用语/计划性/求助）
- 支持权重配置
- 支持误报过滤规则

---

## 3. 接口设计

### 3.1 Review API

```
GET    /api/v1/reviews              # 查询复核任务列表（支持筛选）
GET    /api/v1/reviews/{id}         # 查看复核详情
POST   /api/v1/reviews/{id}/assign  # 分配复核任务
POST   /api/v1/reviews/{id}/resolve # 处理复核任务
POST   /api/v1/reviews/{id}/escalate # 升级复核任务
GET    /api/v1/reviews/stats        # 复核统计
```

### 3.2 Crisis Event API

```
GET    /api/v1/crisis-events        # 查询危机事件（管理员）
POST   /api/v1/crisis-events        # 记录危机事件（内部）
GET    /api/v1/crisis-events/export # 导出危机事件报告
GET    /api/v1/crisis-events/stats  # 危机事件统计
```

---

## 4. 数据模型

### 4.1 ReviewTask (复核任务)

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | 自增ID |
| user_id | int FK | 关联用户 |
| risk_report_id | int FK | 关联风险报告 |
| risk_level | int | 风险等级 |
| risk_score | float | 风险分数 |
| review_triggers | JSON | 复核原因列表 |
| crisis_override | bool | 是否危机覆盖 |
| status | enum | pending/in_review/resolved/escalated/archived |
| priority | enum | normal_review/high_risk_review/crisis_review |
| assigned_to | int FK | 分配给的咨询师 |
| resolved_by | int FK | 处理的咨询师 |
| resolution_note | text | 处理备注 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |
| resolved_at | datetime | 处理时间 |

### 4.2 CrisisEvent (危机事件)

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

## 5. 安全设计

### 5.1 权限控制

| 角色 | Review 查看 | Review 处理 | Crisis Event 查看 | Crisis Event 导出 |
|---|---|---|---|---|
| user | 仅自己的 | 无 | 无 | 无 |
| counselor | 分配的 | 是 | 是 | 否 |
| admin | 全部 | 是 | 全部 | 是 |

### 5.2 数据脱敏

- 危机事件记录中的用户输入需脱敏处理
- 仅保留关键词和摘要，不存储完整原始文本
- 导出报告需额外权限验证

---

> **文档版本**: v1.0
> **最后更新**: 2026-05-01
