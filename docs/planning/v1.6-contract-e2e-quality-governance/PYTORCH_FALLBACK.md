# PyTorch / Transformers 可选依赖行为文档

> **迭代**: v1.6-contract-e2e-quality-governance
> **日期**: 2026-04-28
> **状态**: ✅ 已整理

---

## 1. 依赖检测机制

### 1.1 运行时检测 (config.py)

```python
# 惰性检测，避免 Windows DLL 初始化问题
def _check_pytorch() -> bool:
    global _PYTORCH_AVAILABLE
    if _PYTORCH_AVAILABLE is None:
        if "torch" in sys.modules:
            _PYTORCH_AVAILABLE = True
        else:
            _PYTORCH_AVAILABLE = importlib.util.find_spec("torch") is not None
    return _PYTORCH_AVAILABLE
```

**特点**:
- ✅ 使用 `importlib.util.find_spec()` 避免实际导入
- ✅ 全局缓存，只检测一次
- ✅ 兼容 Windows / Linux / macOS

### 1.2 模块级检测 (pytorch_mlp.py)

```python
try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    # 提供 dummy class 避免类型检查错误
```

**特点**:
- ✅ try/except 包裹导入
- ✅ 提供 dummy class 保持代码可解析
- ✅ 实例化时抛出明确错误

---

## 2. Fallback 层级

### 2.1 生理数据预测 Fallback

```
Layer 1: PyTorch MLP (torch 可用且模型存在)
    └── 失败 -> Layer 2

Layer 2: NumPy MLP (model.json 存在)
    └── 失败 -> Layer 3

Layer 3: 启发式规则 (始终可用)
    └── 基于睡眠时间和运动分钟计算评分
```

**代码位置**: `backend/app/core/model_engine.py::_predict_physiological()`

### 2.2 文本预测 Fallback

```
Layer 1: BERT / Transformers (transformers 可用)
    └── 失败 -> Layer 2

Layer 2: TF-IDF + sklearn (始终可用)
    └── 失败 -> Layer 3

Layer 3: 启发式规则 (始终可用)
```

### 2.3 融合预测 Fallback

```
Layer 1: TensorFlow Fusion (tensorflow 可用)
    └── 失败 -> Layer 2

Layer 2: 启发式融合 (始终可用)
```

---

## 3. 环境一致性验证

| 环境 | PyTorch | Transformers | TensorFlow | 行为 |
|------|---------|-------------|-----------|------|
| 开发 (Windows) | 可选 | 可选 | 可选 | 自动检测，缺失时回退 |
| 开发 (Linux) | 可选 | 可选 | 可选 | 自动检测，缺失时回退 |
| CI / Docker | 可配置 | 可配置 | 可配置 | 通过 requirements 控制 |
| 生产 | 建议安装 | 建议安装 | 建议安装 | 完整功能 |

---

## 4. 测试策略

### 4.1 无 PyTorch 环境测试

```bash
# 创建无 PyTorch 的虚拟环境
python -m venv venv-no-torch
source venv-no-torch/bin/activate
pip install -r requirements.txt
# 不安装 torch/transformers/tensorflow

# 运行测试
pytest tests/ -k "not torch and not transformers" -v
```

### 4.2 CI 矩阵测试

```yaml
# .github/workflows/test.yml
strategy:
  matrix:
    include:
      - deps: "minimal"  # 无深度学习
      - deps: "full"     # 完整依赖
```

---

## 5. 配置建议

### 5.1 requirements.txt 分层

```
# requirements.txt (核心依赖)
scikit-learn>=1.3.2,<1.4.0
numpy>=1.26.4
pandas>=2.1.4

# requirements-ml.txt (机器学习)
torch>=2.2.0
transformers>=4.36.2
tensorflow>=2.20.0

# requirements-dev.txt (开发)
pytest>=8.0.0
pytest-cov>=6.0.0
```

### 5.2 Docker 多阶段构建

```dockerfile
# 基础镜像 (无深度学习)
FROM python:3.12-slim as base
COPY requirements.txt .
RUN pip install -r requirements.txt

# 完整镜像
FROM base as full
COPY requirements-ml.txt .
RUN pip install -r requirements-ml.txt
```

---

## 6. 日志规范

所有 fallback 事件必须记录：

```python
logger.warning("PyTorch not available, using heuristic fallback")
logger.info("Fallback heuristic result: %.2f (reason: %s)", result, reason)
```

---

## 7. 验证清单

- [x] PyTorch 惰性导入实现
- [x] Transformers 惰性导入实现
- [x] 缺失依赖时 graceful fallback
- [x] 每层 fallback 有日志记录
- [x] 启发式规则始终可用
- [x] Windows / Linux 行为一致

---

> **结论**: 项目已建立完善的可选依赖 fallback 机制，符合 Ralph 规则第 10 条 (Fallback & Fault Tolerance)。
