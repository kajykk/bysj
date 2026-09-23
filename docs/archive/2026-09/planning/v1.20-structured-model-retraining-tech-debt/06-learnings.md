# 经验教训: v1.20 结构化模型重训与迁移技术债清理

## Round 1 (基线创建)

- v1.19 验收后的非阻塞技术债应在新迭代中优先处理，而非积累
- 结构化模型 fallback 虽然保证了可用性，但预测质量下降是不可忽视的长期风险
- Alembic 双 head 在当前不影响功能，但每次 migration 都需要手动指定 revision，增加了运维负担

## Round 1 Step 2 (Critique 发现)

1. `train_baseline.py` 实际训练 PhysiologicalMLP，非结构化 LogisticRegression — 需明确脚本角色
2. 特征集在 requirements（PHQ-9/GAD-7）和 architecture（demographic/behavioral）之间不一致
3. Artifact 路径变更需保留回退链
4. Alembic merge 应动态确定 head revision，不应硬编码

--- 

## Implementation Phase 关键发现

### Phase 3: 模型重训
1. **合成数据可行性**: 基于 heuristic fallback 的加权公式反向生成合成训练数据是可行且有效的技术路径，适用于缺乏真实标注数据的场景
2. **特征维度对齐**: 训练脚本特征集必须与推理时 `feature_order` 严格一致。12 vs 14 特征的不匹配导致 `ValueError`，修复后需重新训练

### Phase 4: Fallback 集成
3. **Scaler 关键缺失**: 模型训练时使用了 StandardScaler，但推理时未应用 → 模型输出全为 100。这是本次迭代中最隐蔽但影响最大的 bug
4. **`feature_names_in_` 依赖**: 模型用 np.array 训练时无 `feature_names_in_` 属性，导致代码走 `else` 分支。Scaler 修复需要同时覆盖两个分支
5. **Config singleton 缓存**: pydantic-settings 在 import 时读取环境变量，后续 `os.environ` 修改不生效。Fallback 模式测试需直接调用 `_structured_heuristic_fallback()`，而非依赖环境变量切换

### Phase 6: Alembic 合并
6. **stamp 优先于 upgrade**: 当数据库表已存在但 alembic 版本表落后时，应用 `alembic stamp` 对齐而非 `alembic upgrade`（后者会尝试重建已存在的表）

### Phase 7: 前端构建
7. **AutoImport 循环引用**: `unplugin-auto-import` + `ElementPlusResolver` 会在 vue-core 中注入对 element-plus 的引用，导致 `ui ↔ vue-core` 循环 chunk。解决方案：将两个库合并到同一 chunk

### Phase 8: 阈值校准
8. **模型 vs Heuristic 分数分布差异**: LR 二元分类器的概率分布在 [0.0, ~0.9, ~1.0] 而非线性分布。需要通过放宽 moderate 区间来兼容模型输出
9. **图形化验证脚本**: 相比单元测试，直接运行端到端脚本（verify_prediction.py / verify_regression.py）能更快发现集成问题
