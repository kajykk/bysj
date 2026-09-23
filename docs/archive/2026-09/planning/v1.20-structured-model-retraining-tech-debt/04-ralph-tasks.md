# Ralph 任务列表: v1.20 结构化模型重训与迁移技术债清理

本项目遵循 Ralph 自动化开发流程。

> **⚠️ 执行铁律**: 必须严格按照列表顺序（从上到下）执行任务。严禁跳跃或乱序执行。

## 任务状态图例
- [ ] 待开始 (Pending)
- [x] 已完成 (Completed)
- [~] 进行中 (In Progress)
- [-] 阻塞 (Blocked)

---

## Phase 1: 基线确认 (Baseline Verification)

- [x] **1.1 当前状态确认**
    - [x] 确认 v1.19 后结构化模型仍使用 heuristic fallback
    - [x] 确认 `backend/train_baseline.py` 存在且可执行
    - [x] 确认训练数据集路径和格式
    - [x] 确认 Docker/Linux 训练环境状态
    - [x] **编写基线状态验证脚本并执行**

- [x] **1.2 基线文档**
    - [x] 记录当前模型版本、fallback 状态、Alembic heads 状态
    - [x] 记录训练环境（sklearn/numpy 版本、数据集统计）
    - [x] 生成 `BASELINE_V1.20.md`

---

## Phase 2: 训练数据与脚本修复 (Data & Script Readiness)

- [x] **2.1 训练脚本审计**
    - [x] 确认 `train_baseline.py` 当前训练 PhysiologicalMLP（生理），非结构化 LR
    - [x] 决策：新建 `train_structured.py`，基于 heuristic 生成合成数据训练 LR
    - [x] 检查 `train_baseline.py` 的可执行性
    - [x] 确认脚本输入路径指向正确数据集
    - [x] 确认脚本输出路径（artifact 保存位置）
    - [x] 固定随机种子 `random_state=42`
    - [x] **编写训练脚本语法校验测试**

- [x] **2.2 数据集质量检查**（适配: heuristic fallback 作为合成数据生成器）
    - [x] 检查 heuristic fallback 特征列表（14 features in model_engine.py:460-504）
    - [x] 检查标签分布（将基于 risk_score 阈值生成）
    - [x] 检查特征值范围（已在 heuristic 中使用默认值处理缺失）
    - [x] 确认无异常值边界情况
    - [x] **编写数据集 schema 验证测试**

- [x] **2.3 Train/Val/Test Split 规范**
    - [x] 合成数据将按 0.7/0.15/0.15 分层采样
    - [x] 确认 scaler fit on train only
    - [x] **编写 split 一致性测试**

---

## Phase 3: 结构化模型重训 (Model Retraining)

- [x] **3.1 模型训练执行**
    - [x] 创建 `train_structured.py`（合成数据 + sklearn LR）
    - [x] 在 Windows/Python 环境执行训练（Docker 等价）
    - [x] 记录训练超参数和配置（LogisticRegression, C=1.0, balanced）
    - [x] **编写训练脚本 exit code 0 测试**

- [x] **3.2 Artifact 生成**
    - [x] 保存模型文件 `structured_model_v1.20.pkl`
    - [x] 保存 scaler 文件 `structured_scaler_v1.20.pkl`
    - [x] 保存 feature names `structured_feature_names_v1.20.json`
    - [x] 保存 metrics `structured_metrics_v1.20.json`
    - [x] **编写 artifact 文件存在性测试**

- [x] **3.3 Manifest 生成**
    - [x] 生成 `structured_manifest_v1.20.json`（含版本、指标、sklearn_version）
    - [x] **编写 manifest 字段完整性测试**

- [x] **3.4 训练报告**
    - [x] 输出 `MODEL_TRAINING_REPORT.md`
    - [x] 记录随机种子 42 和可复现性配置

---

## Phase 4: 模型加载与 Fallback 集成 (Model Loading & Fallback)

- [x] **4.1 Model Registry 更新**
    - [x] 在 `model_registry.py` 中注册 v1.20 模型路径
    - [x] 更新 `structured_logistic_regression_quick` 指向 v1.20 model
    - [x] 保留旧路径作为备用
    - [x] **编写 registry 路径注册测试**

- [x] **4.2 配置开关实现**
    - [x] 在 `config.py` 中新增 `STRUCTURED_MODEL_MODE` 配置项
    - [x] 支持 `primary` / `fallback` 两个值
    - [x] 默认值为 `primary`
    - [x] **编写配置值校验测试**

- [x] **4.3 模型加载增强**
    - [x] 更新 `predict_structured()`: 优先加载 v1.20 model
    - [x] 加载失败时自动切换 `_structured_heuristic_fallback()`
    - [x] 失败时输出 WARNING 级别日志
    - [x] 返回值增加 `model_version` 和 `fallback_used` 字段
    - [x] **编写模型加载成功/失败路径测试**

- [x] **4.4 回滚方案实现**
    - [x] 支持 `STRUCTURED_MODEL_MODE=fallback` 强制使用 heuristic
    - [x] 重启服务后生效
    - [x] 生成 `MODEL_ROLLBACK_PLAN.md`
    - [x] **编写模式切换测试**

---

## Phase 5: 风险校准与预期样本测试 (Risk Calibration)

- [x] **5.1 校准样本准备**
    - [x] 建立 4 类校准样本（低/中/高/极高风险）
- [x] **5.2 模型预测校准**
    - [x] 4/4 样本风险等级匹配预期 ✅
- [x] **5.3 阈值调整**
    - [x] structured critical: 85 → 95 (v1.20 校准)
    - [x] structured mild: 25 → 20
- [x] **5.4 校准报告**
    - [x] 输出 `MODEL_CALIBRATION_REPORT.md`

---

## Phase 6: Alembic 双 Head 合并 (Migration Tech Debt)

- [x] **6.1 当前 Migration 状态检查**
    - [x] `alembic heads` 确认双 head: a1b2c3d4e5f6, b1a7c0d9f4e8
    - [x] 数据库含所有表但 alembic 仅追踪到 eab25055097a
- [x] **6.2 创建 Merge Revision**
    - [x] `alembic merge → 6e25d8827741_merge_dual_heads_v1_20`
- [x] **6.3 迁移验证**
    - [x] `alembic stamp → b1a7c0d9f4e8 → 6e25d8827741`
    - [x] `alembic upgrade head` 无错误
    - [x] 单 head: 6e25d8827741
- [x] **6.4 Downgrade 策略**
    - [x] 记录: merge revision 为纯逻辑合并，DDL 无变化
    - [x] 生成 `MIGRATION_HEAD_MERGE_REPORT.md`

---

## Phase 7: 前端 Circular Chunk Warning 清理 (P1)

- [x] **7.1 Chunk Warning 分析**
    - [x] 运行 `npm run build` 记录当前 chunk warning 详情
    - [x] 分析依赖图定位循环引用来源 (ui ↔ vue-core, 由 AutoImport ElementPlusResolver 引起)
    - [x] 记录分析结果（处理/不处理均可，但必须记录）
    - [x] **编写前端构建成功测试**

- [x] **7.2 优化实施（按时间允许）**
    - [x] 修复路由懒加载循环引用（合并 element-plus → vue-core chunk, 消除 Circular chunk warning）
    - [x] admin/counselor 页面拆包优化（已是 route-level lazy load, 无需额外拆包）
    - [x] 图表组件异步加载（ECharts 已在独立 charts chunk, 813 kB）
    - [x] **编写构建 chunk 验证测试**

---

## Phase 8: 回归验证与交付 (Regression & Delivery)

- [x] **8.1 结构化预测回归**
    - [x] 运行结构化预测测试（健康/中/高/极高风险）— 4/4 通过
    - [x] 确认 fallback 路径仍可用 — heuristic 4/4 通过
    - [x] **编写结构化预测全场景测试**

- [x] **8.2 文本危机检测回归**
    - [x] 运行危机文本检测测试 — CrisisDetector 中文检测通过
    - [x] 确认 CrisisDetector 行为不变 — scan/get_crisis_score 正常
    - [x] **编写危机检测回归测试**

- [x] **8.3 融合预测回归**
    - [x] 运行融合预测测试（多模态输入）— apply_priority_rules 通过
    - [x] 确认 FusionPriorityEngine 行为不变 — crisis_override 正常触发
    - [x] **编写融合预测回归测试**

- [x] **8.4 业务功能回归**
    - [x] 验证 ReviewTask 模型可导入
    - [x] 验证 CrisisEvent 模型可导入
    - [x] 验证 Schema (ReviewTaskCreate/CrisisEventCreate) 可导入
    - [x] **编写 ReviewTask/CrisisEvent/CSV 导出回归测试**

- [x] **8.5 构建与健康检查**
    - [x] 前端 `npm run build` 成功 (exit 0, no circular chunk)
    - [x] 后端 `uvicorn` 启动成功 (port 8099)
    - [x] `/health` 返回 200 — database ok
    - [x] `/health/ready` 返回 200 — database ok
    - [x] **编写构建与健康检查验证测试**

- [x] **8.6 交付文档**
    - [x] 输出 `DELIVERY_REPORT.md`
    - [x] 输出 `NEXT_STEPS.md`
    - [x] 更新 `06-learnings.md`
    - [x] 更新 `RALPH_STATE.md`
