# v1.7 迭代架构设计

> **迭代名称**: v1.7-backend-contract-coverage-hardening
> **上一迭代**: v1.6-contract-e2e-quality-governance
> **日期**: 2026-04-29

---

## 一、架构目标

### 1.1 核心目标

1. **后端测试稳定**: 主路径测试无阻塞失败
2. **测试覆盖率达标**: 后端整体 >= 60%，核心模块 >= 75%
3. **契约测试通过**: schemathesis 通过率 >= 80%
4. **OpenAPI 文档完善**: 核心接口 401/403 定义完整
5. **前端工程规范**: ESLint + Prettier 可运行
6. **前端性能基线**: Bundle 分析报告产出

### 1.2 架构原则

- **先稳定，再扩展**: 先修复现有失败测试，再补充新测试
- **核心优先，边缘延后**: 优先覆盖 auth、user、prediction 等高风险模块
- **Mock 优先**: 外部依赖全部 mock，确保测试独立性
- **渐进式优化**: 先核心后边缘，先 P0 后 P2
- **先分析再改造**: 对 chunk 体积先产出分析报告，再进行优化

---

## 二、测试治理架构

### 2.1 测试分层

```text
E2E 测试 (Playwright)        ← v1.6 已完成
        ↑
契约测试 (Schemathesis)       ← v1.7 修复
        ↑
API 集成测试 (pytest + TestClient)  ← v1.7 补充
        ↑
服务层测试 (pytest + mock)    ← v1.7 重点
        ↑
单元测试 (pytest)             ← v1.7 重点
        ↑
被测系统 (FastAPI / Services / ML / Utils)
```

治理顺序：

1. 收口已有失败测试
2. 补齐核心模块单元测试
3. 补齐 API 与服务层测试
4. 修复契约测试
5. 将稳定集合纳入 CI 门禁

### 2.2 测试目录结构

```text
backend/tests/          ← 扁平结构（现状）
├── api/                ← API 端点测试
│   ├── test_auth_flow.py
│   ├── test_user_data.py
│   ├── test_model_predict.py
│   └── ...
├── services/           ← 服务层测试
│   ├── test_auth_service.py
│   ├── test_user_data_service.py
│   └── ...
├── contract/           ← v1.6 已有
├── integration/        ← 集成测试
├── degradation/        ← 降级测试
├── performance/        ← 性能测试
├── stability/          ← 稳定性测试
├── conftest.py         ← 共享 fixtures
└── test_*.py           ← 根级模块测试（ML/core/utils）
```

> **注意**: 保持现有扁平结构，新测试按模块类型放入对应子目录或根目录。

### 2.3 Mock 策略

| 依赖 | Mock 工具 | 说明 |
|------|----------|------|
| 数据库 | pytest-mock + SQLite | 内存数据库或 mock session |
| Redis | fakeredis | 内存 Redis |
| HTTP 请求 | responses / aioresponses | 外部 API |
| 文件系统 | tmp_path / pytest-mock | 临时文件 |
| ML 模型 | pytest-mock | 跳过模型加载 |
| 环境变量 | monkeypatch | 测试配置 |
| 时间 | freezegun | 固定 datetime |

### 2.4 覆盖优先级

| 优先级 | 模块 | 目标 |
|--------|------|------|
| P0 | auth | >= 75% |
| P0 | user | >= 75% |
| P0 | prediction/model | >= 75% |
| P0 | services 核心逻辑 | >= 65% |
| P1 | core/config/model_engine | >= 60% |
| P1 | ML data_cleaner/feature_engineering | >= 60% |
| P2 | monitoring/reports/canary | 建立基线 |
| P2 | utils/validators | >= 80% |

---

## 三、契约治理架构

### 3.1 契约治理链路

```text
FastAPI 路由 / Pydantic 模型
        ↓
统一 ErrorResponse / responses 定义
        ↓
backend/scripts/export_openapi.py
        ↓
OpenAPI 3.1 schema
        ↓
Schemathesis 契约测试
        ↓
失败分类 / 修复 / 回归验证
```

### 3.2 响应模型定义

```python
# app/core/openapi_responses.py（现状）
ERROR_RESPONSE_SCHEMA = {
    "description": "统一错误响应",
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "properties": {
                    "error": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "message": {"type": "string"},
                            "status_code": {"type": "integer"},
                            "layer": {"type": "string", "nullable": True},
                            "fallback_to": {"type": "string", "nullable": True},
                            "timestamp": {"type": "string", "format": "date-time"},
                            "request_id": {"type": "string"},
                            "details": {"type": "object"},
                        },
                        "required": ["code", "message", "status_code", "timestamp", "request_id"],
                    }
                },
                "required": ["error"],
            }
        }
    },
}

COMMON_ERROR_RESPONSES = {
    400: {**ERROR_RESPONSE_SCHEMA, "description": "业务处理失败"},
    401: {**ERROR_RESPONSE_SCHEMA, "description": "未认证"},
    403: {**ERROR_RESPONSE_SCHEMA, "description": "权限不足"},
    404: {**ERROR_RESPONSE_SCHEMA, "description": "资源不存在"},
    409: {**ERROR_RESPONSE_SCHEMA, "description": "状态冲突"},
    422: {**ERROR_RESPONSE_SCHEMA, "description": "参数校验失败"},
    500: {**ERROR_RESPONSE_SCHEMA, "description": "服务内部错误"},
}
```

### 3.3 FastAPI 端点响应配置

```python
# app/api/v1/auth.py（现状示例）
from fastapi import APIRouter, HTTPException, status
from app.core.openapi_responses import COMMON_ERROR_RESPONSES, AUTH_ERROR_RESPONSES

router = APIRouter()

# 使用现状已定义的响应配置
@router.post("/login", responses={
    200: {"description": "登录成功"},
    400: COMMON_ERROR_RESPONSES[400],
    401: COMMON_ERROR_RESPONSES[401],
    422: COMMON_ERROR_RESPONSES[422],
    500: COMMON_ERROR_RESPONSES[500],
})
async def login():
    ...
```

### 3.4 responses 补齐范围

| 接口类型 | 必须声明状态码 |
|---------|---------------|
| 登录/认证接口 | 400、401、422、500 |
| 当前用户接口 | 401、403、422、500 |
| 管理端接口 | 401、403、404、422、500 |
| 预测接口 | 400、401、422、500 |
| 报告接口 | 400、401、403、404、422、500 |
| 文件/导出接口 | 400、401、403、404、500 |

> **注意**: 409 (状态冲突) 当前架构保留但 v1.7 不强制要求，如有需要后续迭代补充。

---

## 四、前端工程化治理架构

### 4.1 前端质量链路

```text
TypeScript 类型检查
        ↓
ESLint 静态检查
        ↓
Prettier 格式检查
        ↓
Vitest 单元测试
        ↓
Vite 生产构建
        ↓
Playwright E2E smoke
        ↓
Bundle / Lighthouse 基线报告
```

v1.7 重点是补齐 ESLint / Prettier，确保前端从"能构建"升级为"可治理"。

### 4.2 ESLint 配置

```javascript
// .eslintrc.cjs (ESLint 8.x legacy 格式，首轮可运行优先)
module.exports = {
  root: true,
  env: {
    browser: true,
    es2021: true,
    node: true
  },
  extends: [
    'eslint:recommended',
    '@vue/typescript/recommended',
    'plugin:vue/vue3-recommended'
  ],
  parserOptions: {
    ecmaVersion: 2021,
    parser: '@typescript-eslint/parser',
    sourceType: 'module'
  },
  plugins: ['@typescript-eslint', 'vue'],
  rules: {
    // 错误级别 - 可运行优先
    'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
    'no-debugger': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
    
    // Vue 规则
    'vue/multi-word-component-names': 'off',
    'vue/no-multiple-template-root': 'off',
    
    // TypeScript 规则 - 首轮适度放宽
    '@typescript-eslint/no-explicit-any': 'warn',
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    
    // 风格规则 - 由 Prettier 处理，ESLint 不重复
    'quotes': 'off',
    'semi': 'off',
    'indent': 'off'
  }
}
```

> **注意**: 前端当前未安装 ESLint/Prettier，v1.7 需先执行 `npm install -D eslint prettier @vue/eslint-config-typescript eslint-plugin-vue @typescript-eslint/parser @typescript-eslint/eslint-plugin`。ESLint 9.x flat config 升级延后至 v1.8。

### 4.3 Prettier 配置

```json
// .prettierrc
{
  "semi": false,
  "singleQuote": true,
  "tabWidth": 2,
  "trailingComma": "es5",
  "printWidth": 100,
  "arrowParens": "avoid",
  "endOfLine": "lf",
  "htmlWhitespaceSensitivity": "strict"
}
```

### 4.4 忽略配置

```text
# .eslintignore / .prettierignore
dist/
node_modules/
coverage/
*.min.js
*.min.css
public/
```

---

## 五、前端性能架构

### 5.1 Chunk 优化策略

先产出分析报告，再进行优化：

1. top 10 最大 chunk
2. top 10 最大依赖
3. 首屏依赖清单
4. 可懒加载页面清单
5. 可独立拆包模块清单

### 5.2 代码分割策略

```javascript
// vite.config.ts（现状已配置）
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          // Core framework
          if (id.includes('vue') && !id.includes('vue-router')) return 'vue-core'
          // Router & state management
          if (id.includes('vue-router')) return 'router'
          if (id.includes('pinia')) return 'state'
          // UI library
          if (id.includes('element-plus')) return 'ui'
          if (id.includes('@element-plus/icons-vue')) return 'icons'
          // Charts
          if (id.includes('echarts')) return 'charts'
          // Utilities
          if (id.includes('dayjs')) return 'datetime'
          if (id.includes('dompurify')) return 'security'
          if (id.includes('axios')) return 'http'
          if (id.includes('vue-i18n')) return 'i18n'
          // Default vendor chunk
          return 'vendor'
        }
      }
    }
  }
})
```

### 5.3 动态导入

```typescript
// 路由懒加载
const ReportExportPage = () => import('@/views/report/ReportExportPage.vue')
const MonitoringDashboard = () => import('@/views/admin/MonitoringDashboard.vue')

// 组件懒加载
const ChartComponent = defineAsyncComponent(() => 
  import('@/components/ChartComponent.vue')
)
```

### 5.4 优化优先级

| 优先级 | 优化对象 | 策略 |
|--------|---------|------|
| P1 | 图表页面 | 路由懒加载、组件异步加载 |
| P1 | Dashboard 图表组件 | defineAsyncComponent |
| P1 | PDF/Excel 导出 | 非首屏动态 import |
| P2 | vendor chunk | manualChunks 细分 |
| P2 | Sass warning | 溯源并升级或记录 |

---

## 六、CI/CD 架构

### 6.1 完整 CI 流程

```text
Push/PR
  │
  ├─> Lint Check (ESLint + Prettier)     ← v1.7 新增
  ├─> TypeScript Check                    ← v1.7 固化
  ├─> Unit Tests (pytest)
  ├─> Integration Tests (TestClient)
  ├─> Contract Tests (schemathesis)
  ├─> Coverage Check (>= 60%)             ← v1.7 调整
  ├─> OpenAPI Export Check                ← v1.7 新增
  ├─> Build Check (npm run build)
  ├─> E2E Smoke (Playwright)
  └─> Lighthouse CI (基线)                ← v1.7 基线
```

### 6.2 质量门禁

| 门禁 | v1.7 阈值 | 失败处理 |
|------|----------|---------|
| 后端测试 | 主路径通过 | 阻止发布 |
| 后端覆盖率 | >= 60% | 阻止发布或人工确认 |
| 核心模块覆盖率 | >= 75% | 阻止发布或人工确认 |
| OpenAPI 导出 | 成功 | 阻止发布 |
| 契约测试通过率 | >= 80% | 阻止发布或人工确认 |
| 前端 type-check | 通过 | 阻止发布 |
| 前端 lint | 可运行且无 error | 阻止发布 |
| 前端 build | 通过 | 阻止发布 |
| E2E smoke | 通过 | 阻止发布或人工确认 |

### 6.3 v1.8 升级门禁

| 门禁 | v1.8 目标 |
|------|----------|
| 后端覆盖率 | >= 85% |
| 契约测试通过率 | >= 90% |
| Lighthouse Performance | >= 80 |
| 前端覆盖率 | >= 80% |
| ESLint warning | 分阶段收敛 |

---

## 七、技术栈

### 7.1 后端测试

| 工具 | 版本 | 用途 |
|------|------|------|
| pytest | >= 8.0 | 测试框架 |
| pytest-mock | >= 3.14 | Mock 工具 |
| pytest-asyncio | >= 0.23 | 异步测试 |
| pytest-cov | >= 5.0 | 覆盖率 |
| httpx | >= 0.27 | HTTP 客户端 |
| fakeredis | >= 2.23 | Redis mock |
| freezegun | >= 1.0 | 时间 mock |

### 7.2 前端工具

| 工具 | 版本 | 用途 |
|------|------|------|
| ESLint | >= 9.0 | 代码检查 |
| Prettier | >= 3.0 | 代码格式化 |
| @vue/eslint-config-typescript | >= 14.0 | Vue TS 规则 |
| eslint-plugin-vue | >= 9.0 | Vue 规则 |

---

## 八、交付物清单

### 8.1 规划与报告文档

- `v1.7_FINAL_PLAN.md`
- `BASELINE_V1.7.md`
- `TEST_FAILURE_ANALYSIS_V1.7.md`
- `COVERAGE_REPORT_V1.7.md`
- `CONTRACT_TEST_REPORT_V1.7.md`
- `FRONTEND_HEALTH_CHECK_V1.7.md`
- `BUNDLE_ANALYSIS_V1.7.md`
- `QUALITY_GATE_V1.7.md`
- `TECH_DEBT_V1.7.md`
- `v1.7_FINAL_REPORT.md`

### 8.2 后端交付物

- auth/user/prediction 测试
- UserService/PredictionService 测试
- core/config/model_engine 测试
- ML data_cleaner/feature_engineering 测试
- ErrorResponse schema
- OpenAPI responses 更新
- Schemathesis 回归结果

### 8.3 前端交付物

- ESLint 配置
- Prettier 配置
- lint / format scripts
- type-check / build 持续通过结果
- bundle 分析报告
- 图表或导出模块懒加载优化
- Sass warning 分析记录

### 8.4 CI/CD 交付物

- 后端测试门禁
- 覆盖率门禁
- OpenAPI 导出门禁
- 契约测试门禁
- 前端 type-check 门禁
- 前端 lint 门禁
- 前端 build 门禁
- E2E smoke 门禁

---

> **文档状态**: Round 3 Locked (Final)
> **最后更新**: 2026-04-29
> **修正记录**:
> - Round 1: 测试目录调整为扁平结构，409 标注为不强制，ESLint 使用 legacy 格式
> - Round 3: 最终审查通过，架构与任务/测试完全匹配
> **下一步**: 进入 Implementation Phase
