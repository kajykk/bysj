# 被测模型评估规范

> **文档版本**: v1.0
> **生成时间**: 2026-04-26
> **适用范围**: 本系统内所有已部署的抑郁风险评估模型

---

## 1. 被测模型的调用方式

### 1.1 本地服务地址

| 服务 | 地址 | 说明 |
|------|------|------|
| 后端 API | `http://localhost:8000` | FastAPI 服务 |
| 前端应用 | `http://localhost:5173` | Vue3 + Vite 开发服务器 |

### 1.2 API Endpoint

所有预测接口均需 `user.predict.use` 权限。

| 接口 | 方法 | 路径 | 功能 |
|------|------|------|------|
| 表格预测 | POST | `/api/v1/model/predict/tabular` | 结构化数据风险预测 |
| 文本预测 | POST | `/api/v1/model/predict/text` | 文本抑郁倾向分析 |
| 融合预测 | POST | `/api/v1/model/predict/fusion` | 多模态融合预测 |
| 模型状态 | GET | `/api/v1/model/status` | 查看模型加载状态 |
| 性能调试 | GET | `/api/v1/model/debug/performance` | 查看性能指标 |

### 1.3 请求示例

**融合预测请求**:
```json
POST /api/v1/model/predict/fusion
{
  "features": {
    "age": 22, "gender": 1, "study_year": 3, "cgpa": 3.5,
    "stress_level": 3, "sleep_duration": 7, "social_support": 4,
    "financial_pressure": 2, "family_history": 0,
    "academic_pressure": 3, "exercise_frequency": 2,
    "anxiety": 2, "panic_attack": 0, "treatment_seeking": 1
  },
  "text": "最近感觉压力很大，睡不好觉",
  "physiological": {
    "sleep_hours": 5, "sleep_quality": 1,
    "exercise_minutes": 10, "heart_rate": 95,
    "systolic_bp": 145, "diastolic_bp": 95, "steps": 1200
  }
}
```

### 1.4 SDK 调用方式（Python）

```python
from app.core.model_engine import ModelEngine

engine = ModelEngine()

# 结构化预测
result = await engine.predict_structured(features)

# 文本预测
result = await engine.predict_text(text)

# 生理数据预测
result = await engine._predict_physiological(physiological_data)

# 融合预测
result = await engine.predict_fusion(features, text, physiological_data)
```

### 1.5 模型文件位置

| 模型 ID | 文件路径 | 框架 |
|---------|----------|------|
| `structured_logistic_regression_quick` | `models/artifacts/depression_tabular/best_model.pkl` | scikit-learn |
| `text_depression_model` | `models/artifacts/text_depression_classifier/text_model.pkl` | scikit-learn + TF-IDF |
| `text_depression_tfidf` | `models/artifacts/text_depression_classifier/text_tfidf.pkl` | scikit-learn |
| `physiological_risk_model` | `models/physiological/physiological_model.pkl` | scikit-learn |
| `fusion_dnn_best` | `models/keras/dnn_fusion_model_best.keras` | TensorFlow/Keras |
| `fusion_cross_modal_best` | `models/keras/cross_modal_fusion_model_best.keras` | TensorFlow/Keras |
| `fusion_transformer_best` | `models/keras/transformer_fusion_model_best.keras` | TensorFlow/Keras |

---

## 2. 评估范围

### 2.1 评估对象

**本系统内已部署的抑郁风险评估模型**，包括：

1. **结构化数据模型** (`structured_logistic_regression_quick`)
   - 输入：学生基本信息、学业压力、生活习惯等 14 维特征
   - 输出：风险分数 (0-100)、风险等级 (0-4)

2. **文本分析模型** (`text_depression_model`)
   - 输入：用户自然语言文本
   - 输出：情感分数 (0-1)、情感标签 (positive/negative)

3. **生理数据模型** (`physiological_risk_model`)
   - 输入：睡眠、运动、心率、血压、步数
   - 输出：生理风险分数 (0-100)

4. **多模态融合引擎** (`ModelEngine.predict_fusion`)
   - 输入：上述三种模态数据（可组合）
   - 输出：融合风险分数、风险等级、主导模态、干预建议

### 2.2 不评估范围

- 外部第三方大语言模型（如 GPT、Claude）
- 未部署的实验模型（仅存在于训练代码中）
- 前端 UI 渲染性能

---

## 3. 预设基准

### 3.1 准确率基准

| 模型 | 指标 | 目标值 | 当前值 |
|------|------|--------|--------|
| 结构化数据 | Accuracy | > 80% | 83.89% |
| 结构化数据 | F1-Score | > 85% | 86.51% |
| 文本分析 | Accuracy | > 90% | 96.77% |
| 文本分析 | F1-Score | > 90% | 96.81% |
| 文本分析 | ROC-AUC | > 95% | 99.56% |
| 生理数据 | 回退算法合理性 | 高风险样本 > 70 分 | 73.33 分 |
| 融合引擎 | 多模态协同性 | 三模态均参与 | 已实现 |

### 3.2 性能基准

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 结构化预测延迟 | < 200ms | 单用户单次请求 |
| 文本预测延迟 | < 50ms | 单用户单次请求 |
| 融合预测延迟 | < 200ms | 三模态全输入 |
| 并发处理 | 正确返回 409 | 冲突场景 |
| 模型加载失败 | 优雅回退 | 不崩溃 |

### 3.3 资源基准

| 指标 | 上限 | 说明 |
|------|------|------|
| 内存占用 | < 2GB | 全部模型加载后 |
| 模型文件总大小 | < 500MB | 磁盘占用 |
| CPU 使用率 | < 80% | 预测期间 |

---

## 4. 测试环境

### 4.1 硬件配置

| 组件 | 规格 |
|------|------|
| OS | Windows (win32) |
| CPU | Intel（支持 SSE3/4.1/4.2/AVX/AVX2/AVX512F/AVX512_VNNI/FMA） |
| 内存 | 待补充 |
| GPU | 无（CPU 推理） |
| 磁盘 | SSD |

### 4.2 软件环境

| 组件 | 版本 |
|------|------|
| Python | 3.12.0 |
| TensorFlow | 2.x（oneDNN 优化开启） |
| scikit-learn | 兼容版本 |
| joblib | 当前版本（有 Python 3.14 弃用警告） |
| pytest | 8.4.2 |

### 4.3 测试约束

- **允许压测**：是，但需在测试环境进行
- **最大并发数**：未设定硬限制，依赖 Uvicorn worker 配置
- **数据库**：SQLite（测试模式），生产环境为 MySQL

---

## 5. 参考数据集或测试题

### 5.1 结构化数据

**训练数据集**：`datasets/student_depression_dataset.csv`
- 样本量：约 27,000 条学生记录
- 特征：年龄、性别、学业压力、睡眠质量、饮食习惯、自杀倾向等
- 标签：Depression (0/1)

**测试样本**（高风险）：
```json
{
  "age": 22, "gender": 1, "study_year": 3, "cgpa": 3.5,
  "stress_level": 3, "sleep_duration": 7, "social_support": 4,
  "financial_pressure": 2, "family_history": 0,
  "academic_pressure": 3, "exercise_frequency": 2,
  "anxiety": 2, "panic_attack": 0, "treatment_seeking": 1
}
```

### 5.2 文本数据

**训练数据集**：`datasets/depression_dataset_reddit_cleaned.csv`
- 样本量：1,547 条 Reddit 清洗数据
- 标签：is_depression (0/1)

**测试样本**：
- 高风险：`"最近感觉压力很大，睡不好觉，对什么都提不起兴趣"`
- 低风险：`"最近状态还不错，学习和生活都比较顺利"`

### 5.3 生理数据

**测试样本**（高风险）：
```json
{
  "sleep_hours": 5, "sleep_quality": 1,
  "exercise_minutes": 10, "heart_rate": 95,
  "systolic_bp": 145, "diastolic_bp": 95, "steps": 1200
}
```

**测试样本**（低风险）：
```json
{
  "sleep_hours": 8, "sleep_quality": 5,
  "exercise_minutes": 60, "heart_rate": 65,
  "systolic_bp": 110, "diastolic_bp": 70, "steps": 12000
}
```

### 5.4 融合测试场景

| 场景 ID | 结构化 | 文本 | 生理 | 预期风险等级 |
|---------|--------|------|------|-------------|
| FUSION-001 | 中风险 | 中风险 | 高风险 | >= 3 (high) |
| FUSION-002 | 低风险 | 低风险 | 低风险 | <= 1 (low) |
| FUSION-003 | 中风险 | 无 | 高风险 | >= 2 (medium) |
| FUSION-004 | 无 | 无 | 高风险 | >= 2 (medium) |
