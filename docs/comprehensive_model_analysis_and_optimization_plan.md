# Comprehensive Model Analysis and Optimization Plan

> **Date**: 2026-04-26
> **System**: Depression Risk Assessment System
> **Scope**: Model status, new data evaluation, optimization strategy

---

## Part 1: Current System Model Status

### 1.1 Model Architecture Overview

| Model | Type | Framework | Input | Output |
|-------|------|-----------|-------|--------|
| **Structured** | CatBoost Classifier | scikit-learn 1.8.0 | 14 features (age, gender, stress, sleep, etc.) | Risk score (0-100), Level (0-4) |
| **Text** | Logistic Regression + TF-IDF | scikit-learn | Raw text | Sentiment score (0-1), Label |
| **Physiological** | Heuristic fallback | Custom Python | Sleep, HR, BP, steps | Physiological score (0-100) |
| **Fusion** | Weighted + Attention Gate | Custom Python | Structured + Text + Physio | Fused risk score, Intervention plan |

### 1.2 Performance Metrics

#### Structured Model (CatBoost)
| Metric | Validation | Test | Benchmark | Status |
|--------|-----------|------|-----------|--------|
| **F1-Score** | **0.8794** | **0.8725** | ≥ 0.85 | ✅ Pass |
| Accuracy | 0.8535 | 0.8457 | > 0.80 | ✅ Pass |
| Precision | 0.8486 | 0.8451 | - | - |
| Recall | 0.9127 | 0.9017 | - | - |
| ROC-AUC | 0.9272 | 0.9204 | > 0.90 | ✅ Pass |
| Latency (avg) | - | 12.86 ms | < 200 ms | ✅ Pass |
| Latency (p95) | - | 16.42 ms | < 200 ms | ✅ Pass |

#### Text Model
| Metric | Value | Benchmark | Status |
|--------|-------|-----------|--------|
| **F1-Score** | **0.9741** | ≥ 0.90 | ✅ Excellent |
| Accuracy | 0.9739 | > 0.90 | ✅ Pass |
| Precision | 0.9574 | > 0.85 | ✅ Pass |
| Recall | 0.9914 | > 0.90 | ✅ Pass |
| Latency (avg) | 1.87 ms | < 50 ms | ✅ Excellent |

#### Physiological Model
| Metric | Value | Benchmark | Status |
|--------|-------|-----------|--------|
| **F1-Score** | **0.6667** | - | ⚠️ Poor |
| Accuracy | 0.5000 | - | ⚠️ Poor |
| Precision | 0.5000 | - | ⚠️ Poor |
| Recall | 1.0000 | - | ⚠️ Over-predicting |
| Latency (avg) | 0.01 ms | - | ✅ Fast |

**Critical Issue**: Physiological model uses heuristic fallback (not ML). All low-risk samples misclassified as high-risk.

#### Fusion Engine
| Metric | Value | Benchmark | Status |
|--------|-------|-----------|--------|
| **Accuracy** | **1.0000** | - | ✅ Perfect (4 test cases) |
| Latency (avg) | 19.57 ms | < 200 ms | ✅ Pass |
| Latency (p95) | 37.21 ms | < 200 ms | ✅ Pass |

### 1.3 Training Data Sources

| Model | Dataset | Size | Source | Quality |
|-------|---------|------|--------|---------|
| Structured | `student_depression_dataset.csv` | 27,901 | Academic survey | High |
| Text | `depression_dataset_reddit_cleaned.csv` | 7,731 | Reddit (cleaned) | High |
| Physiological | `physiological_samples.json` | 4 | Synthetic | ⚠️ Insufficient |
| Fusion | `fusion_test_scenarios.json` | 4 | Hand-crafted | ⚠️ Insufficient |

### 1.4 Existing Limitations

| # | Limitation | Impact | Severity |
|---|-----------|--------|----------|
| 1 | **Physiological model is heuristic, not ML** | Poor accuracy (50%), high false positive | 🔴 Critical |
| 2 | **Physiological training data only 4 samples** | Cannot train proper model | 🔴 Critical |
| 3 | **scikit-learn version mismatch** (1.7.2 vs 1.8.0) | Potential compatibility issues | 🟡 Medium |
| 4 | **Fusion test cases only 4 scenarios** | Insufficient validation coverage | 🟡 Medium |
| 5 | **No dedicated physiological prediction model** | Uses sleep/exercise heuristics only | 🟡 Medium |
| 6 | **Keras fusion models unavailable** | DNN fusion path not operational | 🟢 Low |
| 7 | **BERT text model not found** | Falls back to TF-IDF + Logistic | 🟢 Low |

---

## Part 2: New Data Evaluation

### 2.1 Depresjon Dataset (Converted)

| Attribute | Value |
|-----------|-------|
| **Original Source** | Simula Research Laboratory, Norway |
| **Original Type** | Actigraphy (activity monitoring) |
| **Converted Samples** | **1,029** |
| **Depression Cases** | 359 (34.9%) |
| **Healthy Cases** | 670 (65.1%) |
| **Features** | steps, heart_rate, sleep_hours, sleep_quality, exercise_minutes, systolic_bp, diastolic_bp |
| **Labels** | depression_label (0/1), phq9_score (0-27) |

#### Quality Assessment

| Dimension | Score | Analysis |
|-----------|-------|----------|
| **Volume** | ⭐⭐⭐⭐ | 1,029 samples sufficient for initial training |
| **Diversity** | ⭐⭐⭐ | Only depression vs healthy; no anxiety/subtypes |
| **Relevance** | ⭐⭐⭐⭐⭐ | Directly maps to system physiological features |
| **Quality** | ⭐⭐⭐⭐ | Derived from real actigraphy; synthetic mapping introduces noise |
| **Balance** | ⭐⭐⭐ | 35/65 split acceptable; slight healthy bias |

#### Feature Statistics

| Feature | Healthy (n=670) | Depression (n=359) | Separation |
|---------|----------------|-------------------|------------|
| Steps | 2211 ± 1237 | 1836 ± 926 | Moderate |
| Sleep hours | 7.5 ± 1.0 | 5.5 ± 1.0 | **Strong** |
| Heart rate | 68 ± 8 | 78 ± 8 | **Strong** |
| PHQ-9 | 4.6 ± 2.9 | 14.5 ± 3.2 | **Excellent** |

### 2.2 Kaggle Wearable Dataset

| Attribute | Value |
|-----------|-------|
| **Source** | Kaggle |
| **Samples** | ~1,000 |
| **Features** | Heart_Rate_BPM, Sleep_Duration_Hours, Physical_Activity_Steps, Mood_Rating |
| **Labels** | Mental_Health_Condition (0/1) |

#### Quality Assessment

| Dimension | Score | Analysis |
|-----------|-------|----------|
| **Volume** | ⭐⭐⭐⭐ | ~1,000 samples |
| **Diversity** | ⭐⭐⭐⭐ | Includes mood rating as additional feature |
| **Relevance** | ⭐⭐⭐⭐ | Heart rate, sleep, steps directly applicable |
| **Quality** | ⭐⭐⭐ | Unknown data collection methodology |
| **Balance** | ⭐⭐⭐ | Unknown class distribution |

### 2.3 Combined New Data Potential

| Aspect | Assessment |
|--------|-----------|
| **Total New Samples** | ~2,000+ (Depresjon 1,029 + Kaggle ~1,000) |
| **Feature Coverage** | Sleep, HR, steps, BP, exercise, mood |
| **Label Quality** | PHQ-9 scores (Depresjon), binary labels (Kaggle) |
| **Use Case** | Train dedicated physiological prediction model |

---

## Part 3: Optimization Plan

### 3.1 Objective

Train a **dedicated machine learning model for physiological data** to replace the current heuristic fallback, achieving:
- **F1-Score ≥ 0.75**
- **Accuracy ≥ 0.70**
- **Latency < 50 ms**

### 3.2 Data Preprocessing Pipeline

```
Raw Data (Depresjon + Kaggle)
    ↓
[Step 1] Format Unification
    - Standardize column names
    - Convert units (hours, bpm, steps)
    - Handle missing values (imputation)
    ↓
[Step 2] Feature Alignment
    - Map to system fields:
      sleep_hours, sleep_quality, exercise_minutes,
      heart_rate, systolic_bp, diastolic_bp, steps
    - Create mood_score from Mood_Rating (Kaggle)
    ↓
[Step 3] Outlier Handling
    - Clip extreme values (e.g., HR > 200, sleep > 12h)
    - Winsorization at 1st/99th percentiles
    ↓
[Step 4] Normalization
    - Min-Max scaling to [0, 1] or StandardScaler
    - Fit on training, transform on validation/test
    ↓
[Step 5] Train/Val/Test Split
    - 70% / 15% / 15%
    - Stratified by depression_label
    ↓
Processed Dataset
```

### 3.3 Feature Engineering

| New Feature | Formula | Rationale |
|-------------|---------|-----------|
| `sleep_efficiency` | `sleep_quality / sleep_hours` | Quality per hour |
| `activity_intensity` | `steps / exercise_minutes` | Steps per minute of exercise |
| `cardiovascular_risk` | `systolic_bp / diastolic_bp` | Pulse pressure proxy |
| `hr_sleep_interaction` | `heart_rate * (10 - sleep_hours)` | Sleep deprivation stress |
| `overall_activity` | `steps * exercise_minutes` | Total activity volume |
| `bp_category` | Categorical (normal/pre-hypertensive/hypertensive) | Clinical interpretation |

### 3.4 Model Selection Strategy

| Candidate | Pros | Cons | Priority |
|-----------|------|------|----------|
| **Random Forest** | Handles non-linearity, feature importance, robust | May overfit | 🥇 Primary |
| **Gradient Boosting (XGBoost/LightGBM)** | Best performance, handles imbalance | Hyperparameter sensitive | 🥈 Secondary |
| **Logistic Regression** | Fast, interpretable, baseline | Limited complexity | 🥉 Baseline |
| **SVM** | Good for small datasets | Slow at scale | Alternative |

### 3.5 Training Strategy

```python
# Pseudo-code for training pipeline

def train_physiological_model():
    # 1. Load combined data
    data = load_and_merge(depresjon_path, kaggle_path)
    
    # 2. Preprocess
    X, y = preprocess(data)
    
    # 3. Split
    X_train, X_val, X_test, y_train, y_val, y_test = stratified_split(X, y)
    
    # 4. Train multiple models
    models = {
        'logistic_regression': LogisticRegression(class_weight='balanced'),
        'random_forest': RandomForestClassifier(n_estimators=200, max_depth=10),
        'xgboost': XGBClassifier(learning_rate=0.05, max_depth=5),
        'lightgbm': LGBMClassifier(learning_rate=0.05, num_leaves=31)
    }
    
    # 5. Cross-validation
    results = {}
    for name, model in models.items():
        cv_scores = cross_val_score(model, X_train, y_train, cv=5, scoring='f1')
        results[name] = cv_scores.mean()
    
    # 6. Select best and tune
    best_model_name = max(results, key=results.get)
    best_model = models[best_model_name]
    
    # 7. Hyperparameter tuning (Optuna)
    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=100)
    
    # 8. Final evaluation
    final_model = train_with_best_params(study.best_params)
    metrics = evaluate(final_model, X_test, y_test)
    
    # 9. Save
    save_model(final_model, 'models/artifacts/physiological/physiological_model_v2.pkl')
    save_metrics(metrics, 'models/artifacts/physiological/metrics.json')
```

### 3.6 Hyperparameter Tuning

| Model | Parameters | Search Space | Method |
|-------|-----------|--------------|--------|
| Random Forest | `n_estimators`, `max_depth`, `min_samples_split` | [100, 500], [5, 20], [2, 20] | Optuna |
| XGBoost | `learning_rate`, `max_depth`, `subsample` | [0.01, 0.3], [3, 10], [0.6, 1.0] | Optuna |
| LightGBM | `learning_rate`, `num_leaves`, `feature_fraction` | [0.01, 0.3], [20, 100], [0.6, 1.0] | Optuna |

### 3.7 Validation Protocol

| Protocol | Description | Purpose |
|----------|-------------|---------|
| **5-Fold Cross-Validation** | Stratified, shuffled | Model selection |
| **Hold-out Test Set** | 15% unseen data | Final evaluation |
| **Bootstrap Confidence Intervals** | 1000 resamples | Uncertainty quantification |
| **Calibration Curve** | Predicted vs actual probability | Reliability assessment |

### 3.8 Integration Plan

```
Current System:
    predict_fusion() 
        → _predict_physiological() [HEURISTIC]

Optimized System:
    predict_fusion()
        → _predict_physiological() [ML MODEL v2]
            → Load model: physiological_model_v2.pkl
            → Features: [sleep_hours, sleep_quality, exercise_minutes, 
                         heart_rate, systolic_bp, diastolic_bp, steps]
            → Output: risk_score (0-100)
```

---

## Part 4: Expected Performance Improvements

### 4.1 Physiological Model

| Metric | Current (Heuristic) | Expected (ML) | Improvement |
|--------|---------------------|---------------|-------------|
| **F1-Score** | 0.6667 | **0.75 - 0.85** | +12-27% |
| **Accuracy** | 0.5000 | **0.70 - 0.80** | +40-60% |
| **Precision** | 0.5000 | **0.65 - 0.75** | +30-50% |
| **Recall** | 1.0000 | **0.80 - 0.90** | -10-20% (more balanced) |
| **Latency** | 0.01 ms | **5-20 ms** | Acceptable increase |

### 4.2 Fusion Engine Impact

| Scenario | Current (Heuristic Physio) | Expected (ML Physio) |
|----------|---------------------------|---------------------|
| Low-risk physiological | May falsely elevate risk | Correctly identify low risk |
| High-risk physiological | Correct | More precise risk score |
| Multi-modal fusion | Less reliable | More trustworthy |

### 4.3 System-wide Benefits

| Benefit | Description |
|---------|-------------|
| **Reduced False Positives** | Fewer unnecessary interventions |
| **Better Resource Allocation** | High-risk users get priority |
| **Improved User Trust** | More accurate risk assessments |
| **Clinical Validity** | ML model vs heuristic rules |

---

## Part 5: Potential Challenges

| Challenge | Likelihood | Mitigation |
|-----------|-----------|------------|
| **Insufficient data diversity** | Medium | Augment with synthetic data; collect more |
| **Feature distribution mismatch** | High | Careful preprocessing; domain adaptation |
| **Overfitting on small dataset** | Medium | Regularization; cross-validation; early stopping |
| **Integration complexity** | Low | Maintain backward compatibility; A/B testing |
| **Latency increase** | Low | Model optimization; caching; lightweight models |
| **Label noise** | Medium | Robust loss functions; label smoothing |

---

## Part 6: Success Criteria

### 6.1 Model Performance

| Criterion | Threshold | Measurement |
|-----------|-----------|-------------|
| F1-Score | ≥ 0.75 | 5-fold CV on test set |
| Accuracy | ≥ 0.70 | Hold-out test set |
| Precision | ≥ 0.65 | Hold-out test set |
| Recall | ≥ 0.75 | Hold-out test set |
| ROC-AUC | ≥ 0.80 | Hold-out test set |

### 6.2 System Integration

| Criterion | Threshold | Measurement |
|-----------|-----------|-------------|
| Fusion accuracy | Maintain ≥ 0.90 | 4 test scenarios + new ones |
| Fusion latency p95 | < 200 ms | Load testing |
| Backward compatibility | 100% | Existing API contracts |
| No regression | 0 failures | Full test suite (136 tests) |

### 6.3 Timeline

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Data preprocessing | 2-3 days | Clean, unified dataset |
| Model training & tuning | 3-5 days | Trained model + metrics |
| Integration & testing | 2-3 days | Integrated system |
| Validation & deployment | 1-2 days | Deployed model |
| **Total** | **8-13 days** | **Production-ready physiological model** |

---

## Appendix: Data Summary

### Current Data Inventory

| Dataset | Location | Size | Status |
|---------|----------|------|--------|
| Student Depression | `datasets/structured/` | 27,901 | ✅ Active |
| Reddit Text | `datasets/text/` | 7,731 | ✅ Active |
| Physiological Samples | `datasets/physiological/` | 4 | ⚠️ Insufficient |
| Fusion Scenarios | `datasets/fusion/` | 4 | ⚠️ Insufficient |
| **Depresjon Converted** | `datasets/physiological/external/depresjon_processed/` | **1,029** | 🆕 New |
| **Kaggle Wearable** | `datasets/physiological/external/kaggle_wearable/` | **~1,000** | 🆕 New |

### Recommended Next Steps

1. **Immediate**: Merge and preprocess Depresjon + Kaggle data
2. **Short-term**: Train Random Forest / XGBoost physiological model
3. **Medium-term**: Integrate into fusion engine with A/B testing
4. **Long-term**: Collect real-world wearable data for continuous improvement
