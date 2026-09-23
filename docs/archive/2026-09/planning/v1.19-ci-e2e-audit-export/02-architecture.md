# 系统架构设计 — v1.19-ci-e2e-audit-export

> **版本**: v1.0-Draft  
> **日期**: 2026-05-01  
> **基于**: `01-requirements.md`, `e:\code\bysj\md\3.md`

---

## 1. 技术栈

### 1.1 前端 (已有，不新增)
- **框架**: React + TypeScript
- **UI 库**: Ant Design
- **构建**: Vite

### 1.2 后端 (已有，不新增)
- **Runtime**: Python 3.11+
- **框架**: FastAPI
- **数据库**: SQLite (开发) / PostgreSQL (生产)
- **迁移**: Alembic
- **ORM**: SQLAlchemy (async)

### 1.3 基础设施 (v1.19 检查修复)
- **容器化**: Docker + docker-compose (已有 `docker-compose.yml`, `Dockerfile.test`)
- **CI**: GitHub Actions (已有 `.github/workflows/`) 或本地 Docker
- **脚本**: `backend/scripts/` + `Makefile` (已有基础，仅需补充验证脚本)
- **错误监控**: Sentry (已有配置)

### 1.4 测试框架
- **后端单元/API**: pytest + pytest-asyncio
- **前端组件**: Vitest + React Testing Library
- **E2E**: API 级别 E2E (pytest 脚本) 或 Playwright

---

## 2. 目录结构

```
docs/planning/v1.19-ci-e2e-audit-export/
├── RALPH_STATE.md          # 迭代状态
├── 01-requirements.md      # 需求文档
├── 02-architecture.md      # 架构设计 (本文件)
├── 03-design.md            # 详细设计
├── 04-ralph-tasks.md       # 任务列表
├── 05-test-plan.md         # 测试计划
├── BASELINE_V1.19.md       # 基线报告
├── CI_VERIFICATION_REPORT.md
├── MIGRATION_EXECUTION_REPORT.md
├── E2E_VALIDATION_REPORT.md
├── AUDIT_EXPORT_UI_REPORT.md
├── DELIVERY_REPORT.md
└── NEXT_STEPS.md
```

---

## 3. 数据模型

### 3.1 已有表 (v1.17/v1.18 引入，v1.19 实测验证)

#### ReviewTask (复核任务)
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | Integer | 是 | 主键 |
| user_id | FK→users.id | 是 | 关联用户，CASCADE 删除 |
| risk_report_id | FK→risk_assessments.id | 否 | 关联风险报告 |
| risk_level | Integer | 是 | 风险等级 0-4 |
| risk_score | Float | 是 | 风险分数 0-100 |
| review_triggers | Text | 否 | 触发原因 (JSON) |
| crisis_override | Boolean | 是 | 是否危机覆盖 |
| status | String(20) | 是 | pending/in_review/resolved/escalated |
| priority | String(20) | 是 | normal_review/priority_review/crisis_review |
| assigned_to | FK→users.id | 否 | 分配给咨询师 |
| resolved_by | FK→users.id | 否 | 处理人 |
| resolution_note | Text | 否 | 处理备注 |
| created_at | DateTime | 是 | 创建时间 |
| updated_at | DateTime | 是 | 更新时间 |
| resolved_at | DateTime | 否 | 处理时间 |

#### CrisisEvent (危机事件)
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | Integer | 是 | 主键 |
| user_id | FK→users.id | 是 | 关联用户，CASCADE 删除 |
| report_id | FK→risk_assessments.id | 否 | 关联风险报告 |
| trigger_source | String(20) | 是 | text/fusion/manual |
| crisis_keywords | Text | 否 | 匹配的关键词 (JSON) |
| crisis_score | Float | 否 | 危机分数 |
| input_summary | Text | 否 | 输入摘要 |
| review_task_id | FK→review_tasks.id | 否 | 关联复核任务 |
| status | String(20) | 是 | detected/reviewed/escalated/resolved |
| handled_by | FK→users.id | 否 | 处理人 |
| handled_action | Text | 否 | 处理动作 |
| created_at | DateTime | 是 | 创建时间 |
| handled_at | DateTime | 否 | 处理时间 |

---

## 4. API 接口定义

### 4.1 已有 API (v1.18 实现，v1.19 E2E 验证)

#### 危机事件导出
- **URL**: `GET /api/v1/admin/crisis-events/export`
- **Auth**: Admin only (`require_role("admin")`)
- **Query Parameters**:
  - `start_date` (date, required): YYYY-MM-DD
  - `end_date` (date, required): YYYY-MM-DD

**Response (200)**:
```text
Content-Type: text/csv; charset=utf-8-sig
Content-Disposition: attachment; filename="crisis_events_20260401_20260501.csv"

id,user_id,trigger_source,crisis_score,status,created_at,handled_by,handled_action
1,12****,text,85.5,detected,2026-04-15T10:30:00,,...
```

**Response (403)**:
```json
{"detail": "权限不足"}
```

**Response (422)**:
```json
{"detail": "开始日期不能晚于结束日期"}
```

---

## 5. 关键流程设计

### 5.1 CI/Docker 验证流程
```
1. docker-compose up -d (启动 PostgreSQL + Redis + App)
2. docker exec backend alembic upgrade head
3. docker exec backend pytest --tb=short
4. docker exec backend curl /health
5. docker-compose down
6. 收集输出 → CI_VERIFICATION_REPORT.md
```

### 5.2 前端导出 UI 数据流
```
AdminPage → DatePicker (start_date, end_date)
→ ExportButton.onClick()
→ fetch(GET /api/v1/admin/crisis-events/export?start_date&end_date)
→ response.blob()
→ URL.createObjectURL(blob) → <a download>
→ Toast 成功/失败
```

---

> **文档版本**: v1.0-Draft  
> **最后更新**: 2026-05-01
