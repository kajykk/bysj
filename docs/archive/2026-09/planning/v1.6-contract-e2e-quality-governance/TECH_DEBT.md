# 技术债清单

## 1. Warning 收口

### 1.1 sklearn 版本 Warning
- **状态**: [x] 已处理
- **措施**: 在 `requirements.txt` 中锁定版本 `scikit-learn>=1.3.2,<1.4.0`
- **测试**: `tests/test_model_loader.py` 中验证版本兼容性

### 1.2 utcnow Deprecation Warning
- **状态**: [x] 已处理
- **文件**: `backend/app/services/alert_lifecycle_service.py`
- **修改**: 将 `datetime.utcnow` 替换为 `datetime.now(timezone.utc)`
- **验证**: 全局搜索确认无剩余 `datetime.utcnow` 使用

### 1.3 全空特征 Warning
- **状态**: [x] 已处理
- **措施**: 在 `app/services/input_validator.py` 中添加全空特征检测和填充逻辑
- **测试**: `tests/services/test_input_validator.py` 中覆盖全空特征场景

### 1.4 PyTorch 兼容性 Warning
- **状态**: [x] 已处理
- **措施**: 在 `pytest.ini` 中配置 `filterwarnings` 忽略 PySpark 相关 deprecation warning
- **配置**:
  ```ini
  filterwarnings =
      ignore:typing.io is deprecated, import directly from typing instead:DeprecationWarning:pyspark\..*
  ```

## 2. 类型安全提升

### 2.1 减少测试文件中的 any
- **状态**: [ ] 待处理
- **范围**: 前端测试文件中的 `any` 类型
- **优先级**: P2

### 2.2 收紧 API 响应类型定义
- **状态**: [ ] 待处理
- **范围**: `backend/app/api/v1/` 中的响应模型
- **优先级**: P2

### 2.3 收紧组件 props 类型
- **状态**: [ ] 待处理
- **范围**: 前端 Vue 组件
- **优先级**: P2

## 3. 代码质量

### 3.1 重复代码
- **发现**: `PDFReportService` 和 `ExcelExportService` 中有相似的错误处理逻辑
- **建议**: 提取通用的错误处理工具函数

### 3.2 魔法数字
- **发现**: 多个文件中使用硬编码的阈值数字
- **建议**: 提取到配置文件或常量模块

### 3.3 注释缺失
- **发现**: 部分复杂算法缺少注释
- **建议**: 添加算法说明和参数文档

## 4. 性能优化

### 4.1 数据库查询
- **发现**: 部分 API 存在 N+1 查询问题
- **建议**: 使用 `selectinload` 或 `joinedload` 优化

### 4.2 前端渲染
- **发现**: 部分页面组件过多导致渲染缓慢
- **建议**: 使用虚拟滚动和懒加载

## 5. 安全

### 5.1 输入验证
- **状态**: [x] 已处理
- **措施**: `InputValidator` 服务已添加全面的输入验证

### 5.2 敏感信息
- **发现**: 部分日志可能输出敏感信息
- **建议**: 审查日志输出，脱敏处理

## 6. 测试覆盖

### 6.1 未覆盖模块
- `app/api/v1/canary.py` - 金丝雀发布 API
- `app/services/notification_service.py` - 通知服务
- `app/ml/feature_engineering.py` - 特征工程

### 6.2 测试稳定性
- **发现**: 部分测试依赖外部服务，不稳定
- **建议**: 使用 mock 替代外部依赖

## 7. 文档

### 7.1 API 文档
- **状态**: [x] 已处理
- **措施**: OpenAPI 规范已导出并验证

### 7.2 部署文档
- **发现**: 缺少详细的部署指南
- **建议**: 补充 Docker 部署和 CI/CD 配置说明

## 8. 依赖管理

### 8.1 过期依赖
- **发现**: 部分依赖版本较旧
- **建议**: 定期更新依赖，使用 `pip list --outdated`

### 8.2 开发依赖
- **发现**: 开发依赖未完全分离
- **建议**: 完善 `requirements-dev.txt`
