# 测试分层规范

## 1. 单元测试 (Unit Tests)

### 目标
- 验证单个函数、类或组件的正确性
- 快速执行，不依赖外部服务
- 覆盖率目标：后端 >= 85%，前端 >= 80%

### 范围
- `backend/tests/services/` - 服务层业务逻辑
- `backend/tests/api/` - API 端点响应格式
- `backend/tests/test_core_*.py` - 核心工具函数
- `backend/tests/test_ml_*.py` - ML 模型和算法
- `frontend/src/**/*.test.ts` - 前端组件和组合式函数

### 标记
```ini
[pytest]
markers =
    unit: 单元测试 (默认)
```

### 运行命令
```bash
# 后端
python -m pytest tests/ -m unit -v

# 前端
npm run test:unit
```

## 2. 集成测试 (Integration Tests)

### 目标
- 验证多个模块协作的正确性
- 测试数据库交互、服务调用
- 覆盖率目标：>= 70%

### 范围
- `backend/tests/integration/` - 跨服务集成
- `backend/tests/test_db_*.py` - 数据库操作
- API 端点的完整请求-响应流程

### 标记
```ini
[pytest]
markers =
    integration: 集成测试
```

### 运行命令
```bash
python -m pytest tests/ -m integration -v
```

## 3. 契约测试 (Contract Tests)

### 目标
- 验证 API 契约稳定性
- 确保前后端接口一致性
- 使用 schemathesis 和 hypothesis

### 范围
- `backend/tests/contract/` - API 契约测试
- OpenAPI 规范验证
- 模型序列化/反序列化测试

### 标记
```ini
[pytest]
markers =
    contract: API 契约测试
```

### 运行命令
```bash
python -m pytest tests/ -m contract -v
```

## 4. E2E 测试 (End-to-End Tests)

### 目标
- 验证完整用户流程
- 测试浏览器端交互
- 使用 Playwright

### 范围
- `frontend/tests/e2e/` - 端到端测试
- 核心业务流程：登录、评估、报告
- 关键用户旅程

### 运行命令
```bash
npx playwright test
```

## 5. 退化/降级测试 (Degradation Tests)

### 目标
- 验证系统在非正常情况下的行为
- 测试 fallback 机制
- 确保 graceful degradation

### 范围
- `backend/tests/degradation/` - 降级场景测试
- 模型不可用场景
- 服务超时场景

### 标记
```ini
[pytest]
markers =
    degradation: 降级和 fallback 测试
```

### 运行命令
```bash
python -m pytest tests/ -m degradation -v
```

## 6. 性能测试 (Performance Tests)

### 目标
- 验证系统性能指标
- 检测性能退化
- 基准测试

### 范围
- API 响应时间
- 页面加载时间
- 大数据量处理

### 运行命令
```bash
# 后端性能测试
python -m pytest tests/performance/ -v

# 前端性能测试 (Lighthouse)
npm run lighthouse
```

## 测试分层执行策略

### CI/CD 流水线
```yaml
# PR 阶段
- unit-tests: 必须通过
- integration-tests: 必须通过
- contract-tests: 必须通过

# 合并前
- e2e-tests: 必须通过
- degradation-tests: 必须通过

# 定期执行
- performance-tests: 每日执行
```

### 本地开发
```bash
# 快速验证 (30秒内)
python -m pytest tests/ -m "unit or integration" -x

# 完整验证 (5分钟内)
python -m pytest tests/ -m "unit or integration or contract" -x
npx playwright test --grep "@critical"
```

## 测试文件命名规范

| 层级 | 命名模式 | 示例 |
|------|---------|------|
| 单元测试 | `test_*.py` / `*.test.ts` | `test_auth_service.py` |
| 集成测试 | `test_integration_*.py` | `test_integration_risk_flow.py` |
| 契约测试 | `test_contract_*.py` | `test_contract_api.py` |
| E2E 测试 | `*.spec.ts` | `login.spec.ts` |
| 退化测试 | `test_degradation_*.py` | `test_degradation_model_fallback.py` |
| 性能测试 | `test_perf_*.py` | `test_perf_api_latency.py` |
