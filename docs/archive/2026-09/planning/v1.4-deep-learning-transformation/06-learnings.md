# 经验教训 - v1.4 深度学习化改造

> **迭代名称**: v1.4-deep-learning-transformation
> **版本**: 3.0 (Round 3 Final)
> **日期**: 2026-04-28

---

## 1. Round 1 规划经验

### 1.1 需求分析
- **基线创建原则**: Round 1 应快速建立完整基线，不求完美但求覆盖全面
- **字段命名一致性**: 必须在 Round 1 就统一字段命名（如 `fallback` vs `fallback_id`），否则后续修复成本高
- **量化目标必须明确**: "提升性能"不够，必须明确"F1 ≥ 0.78"这样的具体指标

### 1.2 架构设计
- **目录结构必须完整**: `scripts/evaluation/` 等子目录应在 Round 1 就定义，避免后续补充
- **API 错误响应不能遗漏**: 只定义 200 OK 是不够的，必须补充 4xx/5xx 错误码
- **组件拆分要适度**: ModelRegistryV2、CanaryManager、TimeoutGuard 等组件应在架构中明确

### 1.3 风险评估
- **Round 1 发现的 10 个 Critical Issues**:
  1. fallback/fallback_id 字段名不一致
  2. 融合权重优化目标错误（准确率 vs F1）
  3. 超时回退机制缺失
  4. 二级回退缺失
  5. 灰度评估标准缺失
  6. 漂移触发机制缺失
  7. scale_pos_weight 缺乏依据
  8. PyTorch MLP 参数量未说明
  9. performance_threshold 字段缺失
  10. training_config 字段缺失

---

## 2. Round 2 修订经验

### 2.1 问题修复策略
- **P0 问题必须全部修复**: Round 1 的所有 Critical Issues 在 Round 2 全部修复
- **字段统一要全局替换**: `fallback` → `fallback_id` 需要在所有文档中同步更新
- **流程补充要具体**: "灰度发布"不能只有概念，必须有评估标准、决策流程、日志规范

### 2.2 新增最佳实践
- **多级回退**: 6级回退策略（Level 1-6）确保任何单点故障都有退路
- **超时检测**: 每个模型都有延迟阈值，超时自动回退到轻量级模型
- **灰度自动化**: 4个指标（F1、延迟、回退率、错误率）+ 自动全量发布/回滚决策
- **漂移检测三触发**: 定时任务 + 实时检测 + 手动触发，覆盖所有场景

### 2.3 调研验证
- **XGBoost**: scale_pos_weight=auto（多数类/少数类）是最佳实践
- **Session Sticky**: 无状态服务通过 Redis 缓存用户会话实现
- **漂移检测**: 支持 API/CLI 手动触发，便于运维人员紧急排查

---

## 3. 技术债务

### 当前已知债务
| 债务 | 优先级 | 说明 | 计划修复迭代 |
|---|---|---|---|
| session_sticky Redis 实现 | P3 | 需要引入 Redis 依赖 | v1.5 |
| 日志目录结构 | P2 | `logs/` 目录未在架构中完整定义 | v1.4 开发阶段 |
| 手动触发漂移检测接口 | P2 | API/CLI 接口细节待开发时确定 | v1.4 开发阶段 |

### 建议修复
- 在开发阶段补充 `logs/` 目录结构
- 在开发阶段确定漂移检测手动触发的具体 API 路径

---

## 4. 最佳实践总结

### 数据预处理
- 严格遵循: 划分 → 拟合 → 转换
- SMOTE 仅在训练集应用，比例 ≤ 0.8:1
- 交叉验证每折独立预处理
- 异常值裁剪基于训练集 1st/99th 百分位

### 模型训练
- 小数据集（< 5,000 样本）参数量 < 5,000
- 必须包含 Dropout + BatchNorm + L2 正则化
- 早停 patience=10，恢复最佳权重
- 梯度裁剪 max_norm=1.0
- 学习率衰减（ReduceLROnPlateau）

### 模型评估
- 必须报告 Bootstrap 95% CI
- 必须进行 McNemar 检验（vs 基线）
- 必须绘制校准曲线
- 必须输出特征重要性（SHAP 或 Permutation）

### 模型部署
- 所有新模型必须具备回退机制（6级回退）
- 灰度发布基于用户 ID 分配（sha256 哈希）
- 回退事件必须记录日志（原因、时间、输入摘要、回退级别）
- 推理延迟超过阈值自动回退

### 模型监控
- 漂移检测三触发：定时 + 实时 + 手动
- 告警分级：WARNING（单特征）/ CRITICAL（多特征或性能下降）
- 告警后处理：记录 → 评估回滚 → 生成报告 → 人工确认

---

## 5. 历史迭代经验

### v1.3-mobile-darkmode-i18n
- 主题系统: useTheme, theme.scss, Element Plus 适配
- 国际化: Vue I18n 配置, 语言包 (zh-CN, en-US)
- 移动端: useBreakpoint, BottomNav, 触摸优化
- 组件: ThemeSwitcher, LanguageSelector

### v1.2-frontend-optimization
- [参考 docs/planning/v1.2-frontend-optimization/06-learnings.md]

### v1.1-physio-optimization
- NumPy MLP 实现完成
- 特征工程 13 维特征稳定
- 融合引擎基础版本完成
