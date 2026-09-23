# 下一步建议 — v1.19-ci-e2e-audit-export

> **生成时间**: 2026-05-01  
> **当前状态**: v1.19 开发完成，推荐上线

---

## v1.20 候选方向

### 方向 A: 结构化模型重训 (推荐 ⭐)

`v1.20-structured-model-retraining`

- 基于 train_baseline.py 重新训练结构化模型
- 替换 v1.18 的启发式 fallback
- 提升预测准确率
- v1.19 已完成预研，可立即启动

### 方向 B: BERT 文本模型升级

`v1.20-bert-text-model-upgrade`

- 将 TF-IDF 文本模型升级为中文 BERT
- 保留 TF-IDF fallback
- 预期准确率提升 15-20%

### 方向 C: 生理模型特征扩展

`v1.20-physiological-feature-expansion`

- HRV、体温、血氧等可穿戴设备数据特征
- 连续趋势分析
- 需要额外数据采集和标注

### 方向 D: Technical Debt 处理

`v1.20-tech-debt-cleanup`

- Alembic 双 head 合并
- Circular chunk 修复
- 后端测试覆盖率提升

---

> **文档版本**: v1.0  
> **最后更新**: 2026-05-01
