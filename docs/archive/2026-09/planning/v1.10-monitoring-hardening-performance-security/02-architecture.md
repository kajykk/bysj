# v1.10 系统架构设计: 监控硬化、性能优化与安全加固

> **迭代名称**: v1.10-monitoring-hardening-performance-security
> **日期**: 2026-04-29
> **版本**: Round 3 Locked
> **状态**: Locked

---

## 1. 技术栈

### 1.1 前端
- **框架**: Vue 3 + TypeScript
- **UI 库**: Ant Design Vue
- **状态管理**: Pinia
- **构建工具**: Vite

### 1.2 后端
- **Runtime**: Python 3.11+
- **框架**: FastAPI
- **数据库**: PostgreSQL / SQLite (开发)
- **监控**: Sentry SDK (Python)

### 1.3 基础设施
- **部署**: Docker / 传统服务器
- **CI/CD**: GitHub Actions
- **CDN**: 可选 (图片/WebP 转换)

### 1.4 质量保障
- **后端单元测试**: pytest
- **前端组件测试**: Vitest + Vue Test Utils
- **E2E 测试**: Playwright
- **安全扫描**: npm audit, pip-audit, bandit

---

## 2. 目录结构规范

```
/
├── frontend/
│   ├── src/
│   │   ├── components/       # UI 组件
│   │   ├── pages/            # 页面
│   │   ├── plugins/
│   │   │   └── sentry.ts     # Sentry 前端初始化
│   │   ├── utils/
│   │   │   └── web-vitals.ts # Web Vitals 采集
│   │   ├── service-worker.ts # Service Worker
│   │   └── router/
│   │       └── index.ts      # 懒加载配置
│   └── public/
│       └── offline.html      # 离线页面
├── backend/
│   ├── app/
│   │   ├── main.py           # Sentry 后端初始化
│   │   ├── middleware/
│   │   │   ├── monitoring.py # 性能监控中间件
│   │   │   └── security.py   # 安全头中间件
│   │   └── monitoring/
│   │       └── alerting.py   # 告警规则引擎
│   └── tests/
│       └── test_monitoring.py # 监控测试
└── docs/
    └── planning/
        └── v1.10-monitoring-hardening-performance-security/
```

---

## 3. 数据模型

### 3.1 Web Vitals 记录
| 字段名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | UUID | 是 | 主键 |
| page_path | String | 是 | 页面路径 |
| metric_name | Enum | 是 | CLS, FID, FCP, LCP, TTFB |
| value | Float | 是 | 指标值 |
| rating | Enum | 是 | good, needs-improvement, poor |
| user_agent | String | 否 | 浏览器信息 |
| created_at | DateTime | 是 | 记录时间 |

### 3.2 告警事件
| 字段名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | UUID | 是 | 主键 |
| rule_name | String | 是 | 规则名称 |
| severity | Enum | 是 | P0, P1, P2 |
| message | Text | 是 | 告警内容 |
| context | JSON | 否 | 上下文数据 |
| resolved | Boolean | 是 | 是否已解决 |
| created_at | DateTime | 是 | 触发时间 |

---

## 4. API 接口定义

### 4.1 模块: 监控

#### 4.1.1 接口: 上报 Web Vitals
- **URL**: `POST /api/analytics/web-vitals`
- **Auth**: Public

**Request Body**:
```json
{
  "name": "LCP",
  "value": 1.8,
  "rating": "good",
  "page_path": "/dashboard",
  "entries": []
}
```

**Response (200 OK)**:
```json
{
  "status": "recorded"
}
```

#### 4.1.2 接口: 获取监控指标
- **URL**: `GET /api/admin/monitoring/metrics`
- **Auth**: Admin

**Query Parameters**:
- `start`: ISO 8601 时间
- `end`: ISO 8601 时间
- `metric`: 指标名称 (可选)

**Response (200 OK)**:
```json
{
  "error_rate": 0.02,
  "avg_response_time": 120,
  "p95_response_time": 350,
  "p99_response_time": 800,
  "web_vitals": {
    "lcp": { "avg": 1.5, "good": 0.85 },
    "cls": { "avg": 0.02, "good": 0.95 }
  }
}
```

### 4.2 模块: 告警

#### 4.2.1 接口: 获取告警列表
- **URL**: `GET /api/admin/alerts`
- **Auth**: Admin

**Query Parameters**:
- `status`: active/resolved/all
- `severity`: P0/P1/P2

**Response (200 OK)**:
```json
{
  "alerts": [
    {
      "id": "uuid",
      "rule_name": "错误率飙升",
      "severity": "P0",
      "message": "5分钟内错误率达到 8.5%",
      "created_at": "2026-04-29T10:00:00Z",
      "resolved": false
    }
  ]
}
```

---

## 5. 关键流程设计

### 5.1 错误监控流程
1. 前端/后端发生错误
2. Sentry SDK 捕获错误上下文
3. 发送到 Sentry 服务器
4. 触发告警规则引擎
5. 如果匹配规则，记录告警事件
6. 可选: 发送通知 (Webhook/Email)

### 5.2 Service Worker 安装流程
1. 首次访问时注册 Service Worker
2. 安装阶段缓存核心静态资源
3. 激活阶段清理旧缓存
4. 后续请求按策略处理:
   - 静态资源: Cache First
   - API: Network First
   - 离线: 返回 offline.html

### 5.3 安全头注入流程
1. 请求到达 FastAPI
2. SecurityMiddleware 处理
3. 根据配置注入安全头
4. 响应返回客户端
5. 浏览器强制执行 CSP 等策略
