# v1.18 生产上线硬化与结构化模型恢复 — 架构文档

> **迭代**: v1.18-production-hardening-model-recovery
> **日期**: 2026-05-01
> **状态**: Round 1 Draft

---

## 1. 技术栈

### 1.1 前端
- **框架**: Vue 3 + TypeScript
- **UI 库**: Element Plus
- **状态管理**: Pinia
- **构建工具**: Vite

### 1.2 后端
- **Runtime**: Python 3.11+
- **框架**: FastAPI
- **数据库**: SQLite (开发) / PostgreSQL (生产)
- **ORM**: SQLAlchemy 2.0 + Alembic
- **缓存**: Redis (生产)
- **任务队列**: Celery (生产)

### 1.3 基础设施
- **部署**: Docker + Docker Compose
- **CI/CD**: GitHub Actions
- **观测**: Sentry + 自定义监控

### 1.4 质量保障
- **后端单元测试**: pytest
- **前端组件测试**: Vitest
- **E2E 测试**: Playwright (可选)

---

## 2. 目录结构规范

```
backend/
├── alembic/
│   ├── versions/
│   │   └── a1b2c3d4e5f6_add_review_and_crisis_tables.py  # v1.18 迁移脚本
│   ├── env.py
│   └── script.py.mako
├── app/
│   ├── api/v1/
│   │   ├── review.py          # 复核任务 API
│   │   └── admin.py           # 危机事件导出 API
│   ├── core/
│   │   ├── config.py          # 生产配置硬化
│   │   └── crisis_detector.py # 危机检测（v1.17 已扩展）
│   ├── models/
│   │   └── review.py          # ReviewTask, CrisisEvent
│   ├── services/
│   │   └── review_service.py  # 复核业务逻辑
│   └── monitoring/
│       └── alerting.py        # 观测告警配置
├── .env.example               # 生产配置模板
└── tests/
    ├── api/test_crisis_audit.py
    ├── api/test_review_api.py
    └── unit/test_review_service.py
```

---

## 3. 数据模型

### 3.1 ReviewTask (复核任务)

| 字段名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | Integer | 是 | 主键 |
| user_id | Integer | 是 | 外键 -> users.id |
| risk_report_id | Integer | 否 | 外键 -> risk_assessments.id |
| risk_level | Integer | 是 | 风险等级 1-4 |
| risk_score | Float | 是 | 风险分数 |
| review_triggers | Text | 否 | 触发原因 JSON |
| crisis_override | Boolean | 是 | 是否危机覆盖 |
| status | String(20) | 是 | pending/in_review/resolved/escalated |
| priority | String(20) | 是 | normal_review/high_risk_review/crisis_review |
| assigned_to | Integer | 否 | 分配咨询师 |
| resolved_by | Integer | 否 | 解决人 |
| resolution_note | Text | 否 | 解决备注 |
| created_at | DateTime | 是 | 创建时间 |
| updated_at | DateTime | 是 | 更新时间 |
| resolved_at | DateTime | 否 | 解决时间 |

### 3.2 CrisisEvent (危机事件)

| 字段名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | Integer | 是 | 主键 |
| user_id | Integer | 是 | 外键 -> users.id |
| report_id | Integer | 否 | 外键 -> risk_assessments.id |
| trigger_source | String(20) | 是 | text/model/fusion |
| crisis_keywords | Text | 否 | 检测到的关键词 JSON |
| crisis_score | Float | 否 | 危机分数 |
| input_summary | Text | 否 | 输入摘要 |
| review_task_id | Integer | 否 | 关联复核任务 |
| status | String(20) | 是 | detected/handled/ignored |
| handled_by | Integer | 否 | 处理人 |
| handled_action | Text | 否 | 处理动作 |
| created_at | DateTime | 是 | 创建时间 |
| handled_at | DateTime | 否 | 处理时间 |

---

## 4. API 接口定义

### 4.1 危机事件导出

#### 4.1.1 接口: 危机事件 CSV 导出
- **URL**: `GET /api/v1/admin/crisis-events/export`
- **Auth**: Admin

**Query Parameters**:
```json
{
  "start_date": "2026-04-01",  // [必填] 开始日期
  "end_date": "2026-05-01"     // [必填] 结束日期
}
```

**Response (200 OK)**:
```
Content-Type: text/csv
Content-Disposition: attachment; filename="crisis_events_20260401_20260501.csv"

id,user_id,trigger_source,crisis_score,status,created_at
1,1234****,text,0.95,detected,2026-04-15T10:30:00
```

**Response (403 Forbidden)**:
```json
{
  "error": "FORBIDDEN",
  "message": "需要管理员权限"
}
```

---

### 4.2 复核任务管理

#### 4.2.1 接口: 获取复核任务列表
- **URL**: `GET /api/v1/reviews`
- **Auth**: Counselor / Admin

**Query Parameters**:
```json
{
  "status": "pending",        // [可选] 状态筛选
  "priority": "crisis_review", // [可选] 优先级筛选
  "page": 1,                  // [可选] 页码
  "page_size": 20             // [可选] 每页数量
}
```

---

## 5. 关键流程设计

### 5.1 危机检测 -> 审计闭环

1. 用户提交文本/结构化数据
2. 危机检测器识别危机关键词
3. 自动创建 CrisisEvent 记录
4. 关联创建 ReviewTask（如需要人工复核）
5. 咨询师在后台查看并处理 ReviewTask
6. 处理结果同步更新 CrisisEvent 状态

### 5.2 数据库迁移流程

1. 备份现有数据库
2. 执行 `alembic upgrade a1b2c3d4e5f6`
3. 验证 review_tasks / crisis_events 表创建成功
4. 验证外键约束和索引
5. 如失败，执行 `alembic downgrade a1b2c3d4e5f6` 回滚

---

> **文档版本**: v1.0-Draft
> **最后更新**: 2026-05-01
