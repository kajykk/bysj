# 技术规范文档 (Tech Spec)

> **版本**: v3.1.0
> **迭代**: v1.0-comprehensive-test
> **日期**: 2026-04-25

## 1. 开发环境

### 1.1 后端
- Python 3.12+
- 虚拟环境: `.venv/`
- 包管理: pip + requirements.txt

### 1.2 前端
- Node.js 20+
- 包管理: npm

## 2. 代码规范

### 2.1 Python
- PEP 8
- 类型注解 (typing)
- async/await 异步编程
- SQLAlchemy 2.0 声明式模型

### 2.2 TypeScript/Vue
- Composition API
- 类型安全接口
- 组件命名 PascalCase

## 3. 安全规范

### 3.1 认证
- JWT HS256
- access_token: 120分钟
- refresh_token: 7天
- 密码重置token: 30分钟

### 3.2 密码策略
- bcrypt 加密
- 截断72字符
- 生产环境强制安全JWT密钥

### 3.3 限流
- 登录: 5次/分钟
- 基于 slowapi

## 4. 数据库规范

### 4.1 命名
- 表名: 小写 + 下划线
- 模型类: PascalCase

### 4.2 字段
- 所有表: id (PK), created_at
- 用户表: updated_at
- 外键: 显式命名 + 级联规则

### 4.3 约束
- CheckConstraint 验证数据范围
- UniqueConstraint 唯一性
- Index 查询优化

## 5. API规范

### 5.1 响应格式
```json
{
  "code": 200,
  "message": "success",
  "data": {},
  "request_id": "uuid"
}
```

### 5.2 错误码
- 400: 请求参数错误
- 401: 未认证
- 403: 权限不足
- 404: 资源不存在
- 500: 服务器内部错误

### 5.3 分页
```json
{
  "items": [],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

## 6. 日志规范

### 6.1 格式
- 结构化日志
- request_id 全链路追踪
- 关键操作记录: user_id, action, target

### 6.2 级别
- INFO: 正常业务流程
- WARNING: 异常但可恢复
- ERROR: 需要关注的错误

## 7. 测试规范

### 7.1 后端
- pytest
- 覆盖率报告: term-missing + json + html
- 严格标记器

### 7.2 前端
- Vitest 单元测试
- Playwright E2E测试
- 组件测试: @vue/test-utils

## 8. 部署规范

### 8.1 Docker
- 多阶段构建
- 非root用户运行
- 健康检查

### 8.2 环境变量
- `.env` 开发环境
- `.env.example` 模板
- 生产环境强制校验
