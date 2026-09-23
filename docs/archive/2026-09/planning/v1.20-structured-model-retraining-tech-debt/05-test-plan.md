# 测试计划: v1.20 结构化模型重训与迁移技术债清理

> **生成时间**: 2026-05-01
> **基于文档**: 01-requirements.md, 02-architecture.md, 04-ralph-tasks.md
> **测试环境**: Docker/Linux (推荐), Windows (开发, 有限支持)

> **⚠️ 执行铁律**: 必须严格按照列表顺序（从上到下）执行测试用例。严禁跳跃或乱序执行。

---

## 1. 测试用例详情

> **Test Case ID Format**: `[TC-<MODULE>-<TYPE>-<NUMBER>]`
> - Modules: `MOD` (Model Training), `LD` (Model Loading), `CAL` (Calibration), `MIG` (Migration), `REG` (Regression), `FW` (Frontend)
> - Types: `HP` (Happy Path), `SP` (Sad Path), `EC` (Edge Case), `UI` (UI/UX)

---

### 1.1 模型训练 (Model Training) - Module: MOD

#### 训练脚本与数据准备

**Happy Path (HP):**
- [ ] `[TC-MOD-HP-001]` `train_baseline.py` 语法校验通过，exit code 0 (P0)
- [ ] `[TC-MOD-HP-002]` 训练数据集可加载，无 FileNotFoundError (P0)
- [ ] `[TC-MOD-HP-003]` 训练数据集 schema 正确（列名、类型、标签分布）(P0)
- [ ] `[TC-MOD-HP-004]` 训练脚本固定随机种子 42，可复现 (P0)

**Sad Path (SP):**
- [ ] `[TC-MOD-SP-001]` 数据集路径错误时脚本报错并退出 (P1)
- [ ] `[TC-MOD-SP-002]` 标签字段缺失时脚本提前终止并提示 (P1)
- [ ] `[TC-MOD-SP-003]` 缺失值比例过高时给出警告 (P1)

**Edge Cases (EC):**
- [ ] `[TC-MOD-EC-001]` Train/Val/Test split 比例和为 1.0，分层采样 (P0)
- [ ] `[TC-MOD-EC-002]` Scaler 仅在训练集上 fit，无数据泄漏 (P0)
- [ ] `[TC-MOD-EC-003]` 特征顺序在 artifact 保存和推理时一致 (P1)

#### Artifact 生成

**Happy Path (HP):**
- [ ] `[TC-MOD-HP-010]` 输出模型文件 `structured_model_v1.20.pkl`，文件存在 (P0)
- [ ] `[TC-MOD-HP-011]` 输出 scaler 文件 `structured_scaler_v1.20.pkl`，文件存在 (P0)
- [ ] `[TC-MOD-HP-012]` 输出 feature names `structured_feature_names_v1.20.json`，文件存在 (P0)
- [ ] `[TC-MOD-HP-013]` 输出 metrics `structured_metrics_v1.20.json`，文件存在 (P0)
- [ ] `[TC-MOD-HP-014]` 输出 manifest `structured_manifest_v1.20.json`，文件存在 (P1)

**Sad Path (SP):**
- [ ] `[TC-MOD-SP-010]` 输出目录权限不足时脚本报错 (P2)

**Edge Cases (EC):**
- [ ] `[TC-MOD-EC-010]` Manifest 包含 version=v1.20, features 列表, metrics 字典 (P1)
- [ ] `[TC-MOD-EC-011]` Manifest 包含 sklearn_version 字段 (P1)
- [ ] `[TC-MOD-EC-012]` Metrics json 包含 accuracy, f1, precision, recall, roc_auc (P1)

---

### 1.2 模型加载与 Fallback (Model Loading) - Module: LD

#### 正常加载路径

**Happy Path (HP):**
- [ ] `[TC-LD-HP-001]` 后端可加载 v1.20 真实模型，不使用 fallback (P0)
- [ ] `[TC-LD-HP-002]` Model Registry 正确注册 v1.20 模型路径 (P0)
- [ ] `[TC-LD-HP-003]` 配置 `STRUCTURED_MODEL_MODE=primary` 正常生效 (P1)
- [ ] `[TC-LD-HP-004]` 模型服务启动时 preload 成功 (P1)

#### Fallback 路径

**Happy Path (HP):**
- [ ] `[TC-LD-HP-010]` 模型文件损坏时自动 fallback，API 返回正常响应 (P0)
- [ ] `[TC-LD-HP-011]` 模型文件缺失时自动 fallback，API 返回正常响应 (P0)
- [ ] `[TC-LD-HP-012]` `STRUCTURED_MODEL_MODE=fallback` 强制使用 heuristic (P1)

**Sad Path (SP):**
- [ ] `[TC-LD-SP-001]` 模型加载失败时有 WARNING 级别日志 (P1)
- [ ] `[TC-LD-SP-002]` 预测异常值（NaN, Inf）时自动回退到 fallback (P1)
- [ ] `[TC-LD-SP-003]` 无效 `STRUCTURED_MODEL_MODE` 值时默认 fallback (P1)

**Edge Cases (EC):**
- [ ] `[TC-LD-EC-001]` 返回值包含 `model_version=v1.20` 字段 (P1)
- [ ] `[TC-LD-EC-002]` 返回值包含 `fallback_used` 字段 (P0)
- [ ] `[TC-LD-EC-003]` Fallback 时返回值包含 `fallback_reason` 字段 (P1)
- [ ] `[TC-LD-EC-004]` 禁止模型损坏导致 API 500 (P0)
- [ ] `[TC-LD-EC-005]` 禁止模型缺失导致 API 422 (P0)

---

### 1.3 风险校准 (Risk Calibration) - Module: CAL

#### 校准样本测试

**Happy Path (HP):**
- [ ] `[TC-CAL-HP-001]` 低风险样本：低压力、睡眠好、社交支持好 → risk_level = none/mild (P0)
- [ ] `[TC-CAL-HP-002]` 中风险样本：中等压力、轻微焦虑、睡眠一般 → risk_level = moderate (P0)
- [ ] `[TC-CAL-HP-003]` 高风险样本：高压力、睡眠差、焦虑明显 → risk_level = high (P0)
- [ ] `[TC-CAL-HP-004]` 极高风险样本：极高压力、惊恐发作、治疗寻求 → risk_level = high/critical (P0)

**Edge Cases (EC):**
- [ ] `[TC-CAL-EC-001]` risk_score 范围在 0-100 之间 (P0)
- [ ] `[TC-CAL-EC-002]` confidence 字段正确计算并输出 (P1)
- [ ] `[TC-CAL-EC-003]` severity 字段正确映射 (P1)
- [ ] `[TC-CAL-EC-004]` 阈值边界值测试（mild/moderate 分界）(P1)

---

### 1.4 Alembic 迁移合并 (Migration) - Module: MIG

#### 迁移操作

**Happy Path (HP):**
- [ ] `[TC-MIG-HP-001]` `alembic heads` 输出当前双 head revision (P0)
- [ ] `[TC-MIG-HP-002]` 创建 merge revision 成功 (P0)
- [ ] `[TC-MIG-HP-003]` `alembic upgrade head` 无双 head 错误，执行成功 (P0)
- [ ] `[TC-MIG-HP-004]` 合并后 review_tasks 表仍存在 (P0)
- [ ] `[TC-MIG-HP-005]` 合并后 crisis_events 表仍存在 (P0)

**Sad Path (SP):**
- [ ] `[TC-MIG-SP-001]` Downgrade 策略可执行或明确记录不可逆 (P1)

**Edge Cases (EC):**
- [ ] `[TC-MIG-EC-001]` 合并后原有数据不丢失 (P1)
- [ ] `[TC-MIG-EC-002]` 合并后 `alembic history` 显示线性 history (P1)

---

### 1.5 回归验证 (Regression) - Module: REG

#### 结构化预测回归

**Happy Path (HP):**
- [ ] `[TC-REG-HP-001]` 结构化预测健康样本测试通过 (P0)
- [ ] `[TC-REG-HP-002]` 结构化预测中风险样本测试通过 (P0)
- [ ] `[TC-REG-HP-003]` 结构化预测高风险样本测试通过 (P0)
- [ ] `[TC-REG-HP-004]` 结构化预测极高风险样本测试通过 (P0)

#### 文本危机检测回归

**Happy Path (HP):**
- [ ] `[TC-REG-HP-010]` 危机文本检测功能正常 (P0)
- [ ] `[TC-REG-HP-011]` CrisisDetector 行为与 v1.19 一致 (P0)

#### 融合预测回归

**Happy Path (HP):**
- [ ] `[TC-REG-HP-020]` 多模态融合预测正常 (P0)
- [ ] `[TC-REG-HP-021]` FusionPriorityEngine 行为不变 (P0)

#### 业务功能回归

**Happy Path (HP):**
- [ ] `[TC-REG-HP-030]` ReviewTask 创建功能正常 (P0)
- [ ] `[TC-REG-HP-031]` CrisisEvent CRUD 功能正常 (P0)
- [ ] `[TC-REG-HP-032]` CSV 导出功能正常 (P0)

---

### 1.6 前端构建与健康检查 (Frontend & Health) - Module: FW

#### 构建验证

**Happy Path (HP):**
- [ ] `[TC-FW-HP-001]` 前端 `npm run build` 成功 (P0)
- [ ] `[TC-FW-HP-002]` 构建产物 `dist/` 目录存在且包含入口文件 (P0)

**Sad Path (SP):**
- [ ] `[TC-FW-SP-001]` 构建无 circular chunk warning 或警告有记录 (P1)

#### 健康检查

**Happy Path (HP):**
- [ ] `[TC-FW-HP-010]` 后端 `uvicorn` 启动成功 (P0)
- [ ] `[TC-FW-HP-011]` `/api/v1/health` 返回 200 (P0)
- [ ] `[TC-FW-HP-012]` `/api/v1/ready` 返回 200 (P0)

#### Coverage（P1，非阻塞）

**Happy Path (HP):**
- [ ] `[TC-FW-HP-020]` Coverage 报告可生成（Docker/Linux 环境）(P1)

---

## 2. 优先级统计

| 优先级 | 数量 | 说明 |
|---|---|---|
| P0 | 30 | 必须全部通过 |
| P1 | 36 | 强烈建议通过 |
| P2 | 2 | 尽力而为 |
| **总计** | **68** | |

---

## 3. 执行说明

1. **P0 测试**必须在任何上线操作前全部通过。
2. **P1 测试**被标记为 `[~]` 的环境限制（Windows）不阻塞迭代目标。
3. 测试按模块顺序执行：MOD → LD → CAL → MIG → REG → FW。
4. 每完成一个测试用例，必须立即更新此文件（`[ ]` → `[x]`）。
