"""Physiological Depression Prediction - ML Module.

MAINT-P3-006: ml 模块按功能分类 re-export, 为未来 model_type 分子目录重构铺垫.

当前 26 个文件平铺在 app/ml/ 目录, 高度耦合 (大部分文件相互引用).
未来重构方向: 按 model_type 分子目录 (tabular/text/physiological/common),
但当前阶段因 17 处外部引用 + 大量内部引用 + import-linter 契约约束, 重构风险过高,
故先在 __init__.py 中按功能分类组织 re-export, 为后续迁移提供过渡.

文件功能分类 (未来子目录规划):
    common/:
        - model.py: 基础模型抽象类
        - model_loader.py: 模型加载器
        - model_monitor.py: 模型监控
        - model_validation.py: 模型验证
        - unified_model_interface.py: 统一模型接口
        - canary_controller.py: 金丝雀控制
        - drift_detector.py: 漂移检测
        - trainer.py: 通用训练器
        - evaluation.py: 通用评估器
        - cross_validation.py: 交叉验证
        - hyperparameter_tuning.py: 超参数调优
        - feature_analysis.py: 特征分析
        - feature_importance_validator.py: 特征重要性验证
        - statistical_tests.py: 统计检验

    tabular/:
        - pytorch_mlp.py: MLP 表格模型
        - data_loader.py: 表格数据加载
        - data_cleaner.py: 数据清洗
        - data_split.py: 数据分割
        - dataset.py: 数据集定义
        - scaler.py: 标准化
        - smote.py: 过采样
        - loss.py: 损失函数
        - feature_engineering.py: 特征工程

    text/:
        - text_analyzer.py: 文本分析

    fusion/:
        - fusion_engine.py: 融合引擎
        - fusion_priority_engine.py: 融合优先级引擎

迁移策略 (未来执行):
    1. 创建子目录 + 移动文件
    2. 更新内部 import (相对导入)
    3. 更新外部 import (17 处, 含 import-linter 契约 6 处延迟导入)
    4. 保持 __init__.py re-export 兼容
    5. 运行全量测试验证
"""

# 按功能分类 re-export (仅标注, 不实际导入, 避免循环依赖)
# 各模块在需要时直接 from app.ml.xxx import yyy 导入
