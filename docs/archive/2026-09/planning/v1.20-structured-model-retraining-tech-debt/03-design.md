# 技术方案设计: v1.20 结构化模型重训与迁移技术债清理

## 1. 结构化模型重训方案

### 1.1 模型选型
- 使用 sklearn LogisticRegression（与 v1.18 之前一致）
- 保留 RandomForest 作为备选方案
- 固定 `random_state=42`, `class_weight='balanced'`

### 1.2 特征列表
沿用现有特征集（在 `ModelEngine.feature_order` 中定义）：
`age, gender, study_year, cgpa, stress_level, sleep_duration, social_support, financial_pressure, family_history, academic_pressure, exercise_frequency, anxiety, panic_attack, treatment_seeking`

### 1.3 训练流程
1. `merge_datasets()` → 合并原始数据
2. `clean_dataset()` → 清洗（缺失值、异常值处理）
3. `engineer_features()` → 特征工程
4. `stratified_split(0.7/0.15/0.15)` → 分层划分
5. `fit_scaler()` on train only → 标准化
6. `model.fit()` on train → 训练

## 2. Fallback 机制设计

### 2.1 切换逻辑
```
IF STRUCTURED_MODEL_MODE == "fallback":
    USE heuristic
ELSE:
    TRY load_model("v1.20")
    IF success: USE real model
    IF failure: USE heuristic + log WARNING
```

### 2.2 检测条件
- FileNotFoundError → 文件缺失
- ValueError → 文件损坏
- Exception → 未知错误

## 3. Alembic 合并方案

### 3.1 合并命令
```bash
alembic merge b1a7c0d9f4e8 f6a1b9c0e5d3 -m "merge dual heads v1.20"
alembic upgrade head
```

### 3.2 验证命令
```bash
alembic heads              # 应只有一个 head
alembic history --verbose  # 应显示线性历史
```
