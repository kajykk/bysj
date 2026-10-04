# P2 立项：下次 version release 的三项建议（2026-10-04）

> 依据：`.workbuddy/plans/2026-10-04-next-steps.md` 的 P2 段（随下次 version release 立项）。
> 本文把三项写成**可执行方案 + 判定门槛 + 当前阻塞**，下次立项时直接消费。
> 纪律：门槛未预先写死，事后容易自我说服——所以门槛先定，结论后出。

---

## P2-1 句向量升级（替代 BERT 的实质升级）

### 基线与口径纪律（先解决「数字不可比」）

计划给出的两个数字**口径不同，不能直接比**：

| 数字 | 口径 | 可比性 |
|---|---|---|
| bilingual F1 **0.586** | groupwise CV（按被试分组切分） | ✅ 可作为**生产基线** |
| BERT **0.536** | 组内 CV（同一被试样本可能落在训练与测试两侧） | ❌ **系统性高估**，不能与上行比 |

**立项第一步不是跑模型，是把基线数字在同一口径下重算一遍**——否则「BERT 0.536 < 0.586，所以 BERT 很差」是错误结论（可能它只是口径吃亏）。本项目历史上正是靠口径纪律纠正过同类判断。

### 候选与依赖边界

| 项 | 内容 |
|---|---|
| 候选模型 | `paraphrase-multilingual-MiniLM-L12-v2`（384 维，多语，支持 CPU） |
| 换法 | **只换特征、不换分类器**：冻结 embeddings → 接现有 LR 头 → 与 TF-IDF 特征做同口径对比 |
| 依赖边界 | `sentence-transformers` 会连带 `transformers`。生产镜像**不引入**（见 `MODEL_REGISTRY.md` §6）；若评估达标要上线，走 **ONNX 导出 + onnxruntime**，把 transformers 留在离线侧 |
| 权重体积 | fp32 约 470MB / int8 约 120MB（须与现有 26KB 占位、BERT ONNX 97.75MB 记录对照，见 `MODEL_REGISTRY.md` §3） |

### 判定门槛（涨点才换，四条全过才换）

1. **同口径 groupwise CV 下 F1 提升 ≥ +0.02**（相对 0.586 基线 → ≥ 0.606）；
2. **泄漏检查通过**：group 划分无交叉（用 `MODEL_REGISTRY.md` 记录的口径复现流程核对）；
3. **推理代价可接受**：CPU 延迟与内存相对现有 TF-IDF+LR 的倍数须在部署预算内（生产为 CPU 推理，无 GPU）；
4. **回滚方案明确**：新特征可一键切回 TF-IDF 产物（沿用现有模型版本开关机制）。

任一条不满足 → **不换**，把评估报告存档即可。**不许用「差不多」换「更好」**。

### 执行步骤（需联网；本机 PyPI 实测不可达）

```bash
pip install sentence-transformers                     # 仅实验环境
python -c "from sentence_transformers import SentenceTransformer; \
  SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"   # 首次会下载权重
# 之后：抽取 embeddings → 复用现有 LR 头 → 同口径 groupwise CV → 出评估报告
```

**当前阻塞**：本机 PyPI 不可达（实测 `urlopen` 5s 超时），模型与包均无法下载 → **本轮只能立项，不能出结论**。

---

## P2-2 LLM-as-judge 第二意见（可选实验）

### 现状（有接入点，但前置为零）

| 项 | 实测 |
|---|---|
| 低置信灰区判定 | **已存在**：`app/core/review_reasons.py`、`app/core/model_engine/fusion.py`、`app/ml/fusion_priority_engine.py`、`app/services/risk_service_report.py` 四处均有 `low_confidence` |
| LLM 客户端 | **零**（全仓唯一 `OpenAI` 字样是 `log_sanitizer.py` 的日志脱敏正则，非 SDK 调用） |
| 网关 / 密钥管理 | 无 |
| 人工金标准评估集 | 无 |

即：**灰区判定有了，LLM 这一层要从零搭**。

### 首要门槛：合规（不是技术问题）

本系统的输入是**心理健康量表与访谈文本**。把原文发给外部 LLM 服务 =
敏感个人信息出境，可能触及 GDPR/PIPL 下的处理者义务与告知同意。
**这一条不过，技术评估无意义。** 三条可选路径（按风险从低到高）：

1. 只传**脱敏后的结构化特征**（量表分数、聚合统计），不传自由文本 —— 风险最低，收益也最受限；
2. 用**本地部署**的小模型复核（离线环境，无数据外流）；
3. 若前两条都不成立 —— **不做**。

### 技术评估设计（先离线，不进主路径）

1. 先统一灰区口径（四处 `low_confidence` 判定应收敛到一处，定义 `0.3 ≤ p ≤ 0.6`）；
2. 抽样灰区样本 → LLM 复核 → 与**人工金标准**比一致性（Cohen's kappa）；
3. 同时记录**成本/延迟**（按灰区流量估算单次请求成本）。

### 判定门槛

| 门槛 | 阈值 |
|---|---|
| 合规 | 上表三条路径之一成立（否则直接否决） |
| 一致性 | Cohen's kappa ≥ 0.6 |
| 成本 | 单次复核成本 × 灰区日流量 ≤ 预算（**预算需你给**，本项目无此数字） |
| 灰区口径 | 四处判定收敛为一处，否则复核范围不可控 |

未达标 → 不做，仅存档评估数据。**不进主路径是硬约束**（计划原文）。

---

## P2-3 CI 健全性：Coverage workflow 的 Redis

### 结论：**已具备，无需变更**

实测 `coverage.yml` 已有完整 Redis 服务配置，与 `contract-tests.yml` 对齐：

```yaml
services:
  redis:
    image: redis:7
    options: --health-cmd "redis-cli ping" ...
env:
  REDIS_URL: redis://localhost:6379/0     # 已设
```

`contract-tests.yml` 的 Redis 是上一轮（`f1186b8`）补的；`coverage.yml` 同样已具备。

### 剩余真实缺口（属测试补齐，非 workflow 配置）

Redis 相关**分支**的测试覆盖不足：限流 fail-closed、缓存降级路径。CI 全绿不等于这些分支被验证过。
建议另立测试补齐项（与本计划无关，属覆盖度工作）。

### 可选加固（未做，收益中等）

CI 增一条「按 `requirements*.lock` 安装」的烟测 job——能自动暴露 txt↔lock 漂移
（当前已知 4 处，见 `docs/ops/DEPENDENCY_LOCK_NOTES.md`）。已记录，暂不实施。
