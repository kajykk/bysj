# NEXT_STEPS — 后续迭代建议

> **生成日期**: 2026-06-02
> **基础**: v1.29-launch-readiness (FINAL-GO)
> **目的**: 为后续迭代提供清晰的方向与优先级

---

## 1. 已上线/可上线 (v1.29 FINAL-GO)

✅ 后端 (123 routes, 36 tables)
✅ 前端 (Vue 3 + 174 files + dist 存在)
✅ 4 个生产 ML 模型 + 1 个实验位
✅ Dockerfile + docker-compose
✅ LAUNCH_BLOCKERS / DEPLOYMENT_CHECKLIST / ROLLBACK_PLAN
✅ 96.5% 测试通过率 (核心 100%)

---

## 2. P1 优先级 (1-2 周内, 不阻塞上线)

| 任务 | 预期收益 | 工作量 | 风险 |
|:---|:---|:---:|:---:|
| **修复 32 个 WebSocket/慢测试** | 提升通过率 96.5% → 100% | 2-3 天 | 低 |
| **训练 physiological_optimized v2** | F1 0.694 → ≥ 0.75 | 1 周 | 中 |
| **锁定 sklearn 1.7.2** | 消除序列化警告 | 0.5 天 | 低 |
| **添加 /metrics endpoint (Prometheus)** | 运行时可观测性 | 1 天 | 低 |
| **修复 auth response contract 测试** | 响应格式统一 | 0.5 天 | 低 |

---

## 3. P2 优先级 (v1.30, 1-3 个月内)

| 任务 | 描述 | 工作量 |
|:---|:---|:---:|
| **Kubernetes Helm Chart** | 替代 docker-compose,生产级编排 | 1 周 |
| **LightGBM 校准层** | 在 fusion 前添加 LightGBM 校准 | 1 周 |
| **A/B testing 强化** | 支持多层 canary 路由 | 3 天 |
| **PWA 离线模式** | 用户端断网仍可填问卷 | 1 周 |
| **i18n 扩展** | 繁体中文、日语、韩语 | 1 周 |
| **移动端 App 包装 (Capacitor)** | iOS/Android 原生壳 | 1 周 |
| **集成审计导出为 PDF/Excel** | 监管要求 | 3 天 |

---

## 4. P3 优先级 (v1.31+, 3-6 个月内)

| 任务 | 描述 |
|:---|:---|
| **多模态模型** | 音频情绪识别 + 视频表情分析 |
| **联邦学习框架** | 跨机构协作训练,保护隐私 |
| **边缘推理** | WebAssembly / ONNX Runtime Web |
| **智能干预生成** | LLM (Qwen) 生成个性化干预文案 |
| **危机预警实时流** | Kafka + Flink 实时监测 |
| **机构 API 集成** | 与高校心理咨询中心系统对接 |

---

## 5. 技术债 (Tech Debt)

### 5.1 代码质量

- [ ] `app/models/` 缺少 `warning.py` 统一模型 — 现分散在 services
- [ ] 30+ 处 Pydantic V1 `class Config` 模式 — 需迁移到 V2 `ConfigDict`
- [ ] 部分 SQL 写在 services 而非 models — 需抽象 Repository

### 5.2 测试质量

- [ ] WebSocket 测试需要专门的 AsyncTestClient 包装
- [ ] Contract test 慢 (3-5min) — 需增量 schema diff
- [ ] 集成测试覆盖率 < 30% — 需扩展 E2E

### 5.3 部署质量

- [ ] Helm chart 缺失
- [ ] Terraform / Pulumi IaC 缺失
- [ ] GitOps (ArgoCD) 未集成

---

## 6. 数据科学路线图

### 6.1 模型演进 (按数据量)

| 数据量 | 推荐模型 | 目标 F1 |
|:---|:---|:---:|
| < 5,000 样本 | 启发式规则 (当前) | 0.65 |
| 5,000-10,000 | sklearn MLP + L2 + Dropout (v1) | 0.694 ✅ |
| 10,000-50,000 | LightGBM + XGBoost stacking | 0.75 |
| 50,000-100,000 | PyTorch Tabular (TabNet, FT-Transformer) | 0.78 |
| > 100,000 | 多模态深度学习 + 联邦学习 | 0.80+ |

### 6.2 当前模型状态

| 模型 | F1 | 状态 | 计划 |
|:---|:---:|:---|:---|
| physiological v1 | 0.694 | ✅ 生产 | 收集数据后 v2 |
| structured v1.20 | ? | ✅ 生产 | 校准后 v1.21 |
| structured v1.21 | ? | ✅ 生产 | 当前最优 |
| text_depression_classifier | ? | ✅ 生产 | 加入 LLM 增强 |
| physiological_optimized v2 | N/A | ⏳ 训练中 | F1 ≥ 0.75 目标 |

### 6.3 评估规范 (Ralph 规则 #8)

- ✅ F1 / Precision / Recall
- ✅ ROC-AUC
- ⏳ AUPRC (对不平衡数据)
- ⏳ Bootstrap 95% CI
- ⏳ McNemar 检验 (模型对比)
- ⏳ 校准曲线
- ⏳ SHAP 可解释性

---

## 7. 运营路线图

### 7.1 监控强化

- [ ] Grafana 仪表板 (API 响应时间, 错误率, 模型延迟)
- [ ] PagerDuty 告警 (P0 故障 5 分钟内通知)
- [ ] SLO 报告 (周报)

### 7.2 性能优化

- [ ] 模型预热 (启动时加载到内存)
- [ ] Redis 缓存 (查询结果, 1 分钟 TTL)
- [ ] DB 索引优化 (高基数列)
- [ ] CDN 加速 (静态资源)

### 7.3 成本控制

- [ ] GPU 推理优化 (如启用 PyTorch)
- [ ] 自动扩缩容 (HPA)
- [ ] 日志采样 (生产 10%, 调试 100%)

---

## 8. 业务路线图

### 8.1 用户增长

- v1.30: 内部测试 (50 用户)
- v1.31: 试点学校 (500 用户)
- v1.32: 区域推广 (5,000 用户)
- v2.0: 全国高校 (50,000+ 用户)

### 8.2 合规要求

- [ ] 等保 2.0 三级 (中国)
- [ ] GDPR (欧盟, 如扩张)
- [ ] HIPAA (美国, 如扩张)
- [ ] 学校伦理委员会审批 (每次新机构)

### 8.3 商业化探索

- B2B SaaS (高校心理中心订阅)
- 政府采购 (教育厅统一采购)
- 公益版本 (免费提供给欠发达地区)

---

## 9. 团队建议

### 9.1 当前瓶颈

- 后端 1 人全栈 (需补充 1-2 人)
- ML 1 人 (需补充 1 人做深度学习)
- 前端 1 人 (需补充 1 人)
- 运维 0 人 (急需 1 人)

### 9.2 招聘优先级

1. **DevOps 工程师** (P0) — K8s + 监控 + CI/CD
2. **后端工程师** (P1) — Python + FastAPI + 性能优化
3. **数据科学家** (P1) — PyTorch + MLOps
4. **前端工程师** (P2) — Vue 3 + 移动端

---

## 10. 文档路线图

### 10.1 用户文档

- [ ] 用户使用手册 (PDF)
- [ ] 视频教程 (5-10 分钟系列)
- [ ] FAQ (50 问)
- [ ] 家长知情同意书模板

### 10.2 运维文档

- [ ] 运维 SOP (日检 / 周检 / 月检)
- [ ] 故障应急手册 (10 个常见故障)
- [ ] 容量规划指南
- [ ] 安全加固清单

### 10.3 学术文档

- [ ] 模型技术白皮书 (PDF)
- [ ] 校准方法论 (论文草稿)
- [ ] 伦理审查文档
- [ ] 数据使用协议

---

## 11. 总结

**v1.29 已完成 FINAL-GO 准备**,可以:

- ✅ 答辩演示
- ✅ 内部测试部署
- ✅ 试运行部署 (50-500 用户)
- ⚠️ 大规模生产部署 (需先做 P1 任务)

**下一步建议**: 打 v1.29-launch-readiness tag → 准备答辩 → 启动 P1 任务 → v1.30 训练新模型。
