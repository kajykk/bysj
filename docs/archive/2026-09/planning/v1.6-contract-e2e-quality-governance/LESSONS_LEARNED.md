# 经验教训文档

## 1. 惰性导入策略

### 背景
项目中使用 PyTorch 等重型库，直接导入会导致启动时间过长。

### 策略
```python
# 不推荐
import torch

# 推荐
def load_model():
    import torch
    return torch.load(...)
```

### 经验
- 在模块级别避免导入重型库
- 在函数内部进行局部导入
- 使用 `try/except` 处理可选依赖

### 应用
- `app/ml/model_loader.py` - 惰性加载 PyTorch
- `app/services/pdf_report_service.py` - 惰性加载 ReportLab
- `app/services/excel_export_service.py` - 惰性加载 openpyxl

## 2. FastAPI 参数顺序修复

### 背景
FastAPI 中路径参数和查询参数的顺序会影响路由匹配。

### 问题
```python
# 错误：路径参数在查询参数之后
@app.get("/items/{item_id}")
async def get_item(q: str, item_id: int):
    ...
```

### 修复
```python
# 正确：路径参数在前
@app.get("/items/{item_id}")
async def get_item(item_id: int, q: str | None = None):
    ...
```

### 经验
- 路径参数必须放在查询参数之前
- 可选参数使用 `| None = None`
- 使用 Pydantic 模型处理复杂请求体

## 3. 契约测试前置

### 背景
API 契约测试需要在服务启动后进行。

### 策略
1. 导出 OpenAPI 规范
2. 使用 schemathesis 进行自动化测试
3. 在 CI 中集成契约测试

### 经验
- 契约测试应尽早引入，避免后期修改成本高
- 使用 `@pytest.mark.contract` 标记契约测试
- 契约失败应立即修复，避免累积

### 应用
- `.github/workflows/contract-tests.yml`
- `backend/tests/contract/`

## 4. E2E 容器化

### 背景
E2E 测试需要完整的环境，包括数据库、后端、前端。

### 策略
1. 使用 Docker Compose 编排服务
2. 等待服务健康检查通过
3. 使用 Playwright 进行浏览器自动化

### 经验
- 服务启动顺序很重要
- 使用健康检查确保服务就绪
- 测试数据隔离，避免互相影响

### 应用
- `.github/workflows/e2e-tests.yml`
- `frontend/tests/e2e/`

## 5. 覆盖率持续跟踪

### 背景
覆盖率容易下降，需要持续监控。

### 策略
1. 设置覆盖率阈值 (后端 >= 85%, 前端 >= 80%)
2. 使用 Codecov 进行 PR 覆盖率检查
3. 定期生成覆盖率报告

### 经验
- 覆盖率阈值应合理，避免过高导致开发效率降低
- 关注新增代码的覆盖率，而非整体
- 关键路径覆盖率应 >= 90%

### 应用
- `codecov.yml`
- `.github/workflows/coverage.yml`
- `backend/pytest.ini`

## 6. 测试分层

### 背景
不同类型的测试有不同的目的和执行频率。

### 分层
| 层级 | 目的 | 执行频率 | 时间 |
|------|------|----------|------|
| 单元测试 | 验证函数正确性 | 每次提交 | < 30s |
| 集成测试 | 验证模块协作 | PR 时 | < 2min |
| 契约测试 | 验证 API 稳定性 | PR 时 | < 2min |
| E2E 测试 | 验证用户流程 | PR 时 | < 5min |
| 性能测试 | 验证性能指标 | 每日 | < 10min |

### 经验
- 快速测试优先执行
- 慢速测试定期执行
- 使用标记区分测试类型

## 7. 回退机制

### 背景
机器学习模型可能不可用，需要回退到规则引擎。

### 策略
1. 检测模型可用性
2. 不可用时触发回退
3. 记录回退事件

### 经验
- 回退机制必须可靠
- 回退结果格式应与正常结果一致
- 监控回退频率，及时发现模型问题

### 应用
- `app/core/risk_thresholds.py` - `should_fallback()`
- `app/ml/model_loader.py` - `check_model_exists()`

## 8. 输入验证

### 背景
外部输入不可信，需要严格验证。

### 策略
1. 类型检查
2. 范围检查
3. 格式检查
4. 空值处理

### 经验
- 验证应在最外层进行
- 使用 Pydantic 模型自动验证
- 自定义验证器处理业务规则

### 应用
- `app/services/input_validator.py`
- `app/schemas/`

## 9. 监控与告警

### 背景
系统运行状态需要实时监控。

### 策略
1. 健康检查端点
2. 性能指标采集
3. 异常告警通知

### 经验
- 监控应覆盖关键路径
- 告警阈值应合理，避免告警疲劳
- 使用 Sentry 进行错误追踪

### 应用
- `app/core/health.py`
- `app/core/sentry.py`
- `.github/workflows/lighthouse.yml`

## 10. 文档驱动开发

### 背景
文档是项目维护的重要部分。

### 策略
1. 先写文档，再写代码
2. 文档与代码同步更新
3. 使用自动化工具生成文档

### 经验
- API 文档应与代码同步
- 测试文档应包含测试 ID 和说明
- 架构文档应定期更新

### 应用
- `docs/planning/` - 规划文档
- `docs/api/` - API 文档
- `README.md` - 项目说明
