# 系统架构设计 (System Architecture)

> **版本**: v3.1.0
> **迭代**: v1.0-comprehensive-test
> **日期**: 2026-04-25

## 1. 技术栈

### 1.1 前端
- **框架**: Vue 3 (Composition API)
- **UI库**: Element Plus
- **状态管理**: Pinia
- **路由**: Vue Router 4
- **构建工具**: Vite
- **样式**: SCSS
- **图表**: ECharts

### 1.2 后端
- **Runtime**: Python 3.12
- **框架**: FastAPI
- **数据库**: SQLite (开发) / PostgreSQL (生产)
- **ORM**: SQLAlchemy 2.0 (Async)
- **迁移**: Alembic
- **缓存/队列**: Redis + Celery
- **认证**: JWT (PyJWT) + bcrypt
- **机器学习**: scikit-learn, transformers, tensorflow/keras
- **PDF生成**: reportlab

### 1.3 基础设施
- **部署**: Docker + Docker Compose
- **CI/CD**: GitHub Actions
- **监控**: 健康检查端点 + 操作日志

### 1.4 质量保障
- **后端测试**: pytest + pytest-cov + 自定义harness
- **前端单元测试**: Vitest + @vue/test-utils
- **E2E测试**: Playwright
- **代码规范**: ESLint / Prettier (前端)

## 2. 目录结构

```
/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # API路由
│   │   ├── core/            # 核心配置/中间件/安全
│   │   ├── models/          # 数据模型
│   │   ├── schemas/         # Pydantic模型
│   │   ├── services/        # 业务逻辑
│   │   └── main.py          # 应用入口
│   ├── tests/               # 测试套件
│   ├── alembic/             # 数据库迁移
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/             # API调用
│   │   ├── components/      # 组件
│   │   ├── composables/     # 组合式函数
│   │   ├── config/          # 配置文件
│   │   └── App.vue
│   ├── e2e/                 # Playwright测试
│   └── package.json
├── datasets/                # 训练数据集
├── models/                  # 模型文件
└── docs/                    # 文档
```

## 3. 数据模型

### 3.1 User (用户)
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK | 主键 |
| username | String(50) | Unique, Index | 用户名 |
| email | String(100) | Unique, Index | 邮箱 |
| password_hash | String(255) | Not Null | 密码哈希 |
| role | String(20) | Index | admin/counselor/user |
| status | String(20) | Default active | active/inactive |

### 3.2 RiskAssessment (风险评估)
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK | 主键 |
| user_id | Integer | FK users.id | 用户ID |
| risk_score | Float | 0-100 | 风险分数 |
| risk_level | Integer | 0-10 | 风险等级 |
| structured_score | Float | 0-100 | 结构化分数 |
| text_score | Float | 0-100 | 文本分数 |
| physiological_score | Float | 0-100 | 生理分数 |
| models_used | JSON | | 使用模型列表 |
| risk_factors | JSON | | 风险因子 |

### 3.3 WarningNotification (预警通知)
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK | 主键 |
| user_id | Integer | FK users.id | 用户ID |
| counselor_id | Integer | FK users.id | 咨询师ID |
| current_level | Integer | 0-10 | 当前等级 |
| previous_level | Integer | 0-10 | 之前等级 |
| trigger_reason | Text | | 触发原因 |
| is_read | Boolean | Default False | 是否已读 |
| is_handled | Boolean | Default False | 是否已处理 |

### 3.4 InterventionPlan (干预计划)
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK | 主键 |
| user_id | Integer | FK users.id | 用户ID |
| counselor_id | Integer | FK users.id | 咨询师ID |
| plan_name | String(100) | | 计划名称 |
| risk_level | Integer | 0-10 | 风险等级 |
| progress | Integer | 0-100 | 进度 |
| status | String(20) | Default active | active/completed/cancelled |

### 3.5 InterventionTask (干预任务)
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK | 主键 |
| plan_id | Integer | FK intervention_plans.id | 计划ID |
| task_name | String(200) | | 任务名称 |
| task_type | String(30) | | 任务类型 |
| schedule | String(50) | | 调度频率 |
| duration_minutes | Integer | >=1 | 时长 |

## 4. API接口定义

### 4.1 认证模块 (Auth)

#### POST /api/v1/auth/register
- **Auth**: Public
- **Request**: `{ username, email, password, role }`
- **Response**: `{ id, username, role }`

#### POST /api/v1/auth/login
- **Auth**: Public
- **Request**: `{ username, password }`
- **Response**: `{ access_token, refresh_token, token_type, user }`

#### POST /api/v1/auth/refresh
- **Auth**: Public
- **Request**: `{ refresh_token }`
- **Response**: `{ access_token, refresh_token }`

### 4.2 用户数据模块 (User Data)

#### POST /api/v1/user/data/collect
- **Auth**: user
- **Request**: `{ assessment_type, data_payload }`
- **Response**: `{ assessment_id, risk_score, risk_level, severity, risk_factors, warning_generated, warning_id }`

#### POST /api/v1/user/data/text/analyze
- **Auth**: user
- **Request**: `{ entry_type, content, emotion_tags, mood_score }`
- **Response**: `{ entry_id, sentiment_score, sentiment_label }`

### 4.3 风险评估模块 (Risk)

#### GET /api/v1/user/risk/report
- **Auth**: user
- **Response**: `{ risk_level, risk_score, severity, trend, main_factors, advice, assessed_at }`

#### GET /api/v1/user/risk/trend
- **Auth**: user
- **Query**: `days`
- **Response**: `{ days, direction, points }`

#### GET /api/v1/user/risk/export
- **Auth**: user
- **Query**: `days, fmt`
- **Response**: `{ format, filename, content }`

### 4.4 预警模块 (Warning)

#### GET /api/v1/user/warnings
- **Auth**: user
- **Query**: `page, page_size, is_read`
- **Response**: `{ items, total, page, page_size }`

#### POST /api/v1/user/warnings/{id}/read
- **Auth**: user
- **Response**: `{ success }`

### 4.5 干预模块 (Intervention)

#### GET /api/v1/user/intervention/plans
- **Auth**: user
- **Response**: `{ items, total, page, page_size }`

#### POST /api/v1/user/intervention/tasks/{id}/complete
- **Auth**: user
- **Request**: `{ feedback_score, feedback_note }`

### 4.6 咨询模块 (Counselor)

#### GET /api/v1/counselor/warnings
- **Auth**: counselor
- **Query**: `page, page_size, only_unhandled`
- **Response**: `{ items, total, page, page_size }`

#### POST /api/v1/counselor/warnings/{id}/handle
- **Auth**: counselor
- **Request**: `{ action, note }`

### 4.7 管理模块 (Admin)

#### GET /api/v1/admin/dashboard
- **Auth**: admin
- **Response**: `{ stats }`

#### GET /api/v1/admin/templates
- **Auth**: admin
- **Query**: `page, page_size`

#### POST /api/v1/admin/templates
- **Auth**: admin
- **Request**: `{ template_name, applicable_levels, task_list, estimated_weeks }`

## 5. 关键流程设计

### 5.1 风险评估流程
1. 用户提交结构化数据/文本/生理数据
2. 系统调用对应模型进行预测
3. 模型失败时触发启发式回退
4. 生成RiskAssessment记录
5. 检查预警触发条件
6. 如满足条件生成WarningNotification
7. 风险等级>=2时自动生成InterventionPlan

### 5.2 预警处理流程
1. 风险等级变化触发预警
2. 通知关联咨询师
3. 咨询师查看预警列表
4. 咨询师处理/忽略预警
5. 记录操作日志
6. 用户查看预警并标记已读

### 5.3 干预计划流程
1. 系统按风险等级匹配InterventionTemplate
2. 生成InterventionPlan和InterventionTask列表
3. 用户查看任务列表并执行
4. 记录TaskExecution
5. 更新计划进度
