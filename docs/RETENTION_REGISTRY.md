# 保留决议登记册（RETENTION REGISTRY）

> 建册时间：2026-10-14（P2 第十一轮）
> 建册动因：`RES-P1-004` 在第九/十轮被作为「`observability_service._flushed_buffer`
> 保留的书面依据」反复引用，但全仓**查不到任何登记正文**——只有引用与一行配置注释。
> 「有书面依据」若查不到正文，就等同于口头依据（审查报告系统性根因④的同型问题）。
> 本册即为该依据的落点。

## 登记规则（新增条目必须逐项填写，缺项视为未登记）

| 字段 | 含义 |
|---|---|
| **编号** | `RES-P<轮次>-<序号>`，一经登记永不复用、不改写正文（需变更时追加新条目） |
| **对象** | 精确定位（文件 + 符号），必须是可 grep 到的字面量 |
| **类别** | 死代码保留 / 有意降级 / 已知缺陷豁免 / 业务决策待定 |
| **保留理由** | 删除会带来什么具体后果（不是「可能有用」这种空话） |
| **复核触发条件** | 满足什么条件时必须重新裁定（含删除或改造） |
| **正文出处** | 除本册外，还在哪些代码注释/测试中锚定（便于机器可追溯） |

**纪律**：扫描器/复核者发现疑似死代码时，**先查本册**；本册已登记的对象不得当
死代码删除，也不得在下一轮重复报为「漏做」。未登记而保留的，一律按缺陷处理。

---

## RES-P1-004 —— `ObservabilityCollector._flushed_buffer` 与 `consume_flushed_logs()` 保留

- **对象**：`backend/app/services/observability_service.py`
  - `_flushed_buffer: list[MonitoringLog]`（`__init__`，约第 99 行）
  - `consume_flushed_logs()`（约第 151 行）
- **类别**：死代码保留（当前无生产消费者）
- **保留理由**：
  1. `flush_to_db()` 直接从 `_pending_logs` 取数据、绕过 `_flushed_buffer`，
     而 `consume_flushed_logs()` 是**唯一**能读出该缓冲区的公开接口。删除它
     ⇒ 缓冲区失去唯一出口 ⇒ 未来接入外部消费者（TSDB 导出器）时必须重建接口 + 重做
     M-23（累积式缓冲）与 H-Svc-10（锁内消费）两处修复，成本高于保留。
  2. 缓冲区上限已由 `RES-P1-004` 本身从 10000 降至 1000
     （`app/core/config.py` → `observability_max_buffer_size`），保留的内存代价已封顶
     （1000 × `MonitoringLog` 量级），不构成资源风险。
  3. `start()`/`stop()`/`_flush_loop()` 未被 `main.py` 调用（生产启动的是
     `ObservabilityExporter`），该路径**只有测试用例覆盖**——保留它使测试仍能覆盖
     `_flush` 的竞态与溢出分支，删掉等于删除回归能力。
- **复核触发条件**（满足任一必须重裁）：
  1. 出现生产消费者调用 `consume_flushed_logs()` ⇒ 死代码身份解除，本条目转为
     「在用接口」，可归档；
  2. `ObservabilityCollector` 整体下线（`ObservabilityExporter` 完全取代且测试改挂）
     ⇒ 整类删除，本条目作废；
  3. 有人提议「精简死缓冲区」⇒ 必须同时给出替代的测试覆盖方案，否则驳回。
- **正文出处**：
  - `backend/app/services/observability_service.py` 类 docstring 与
    `consume_flushed_logs()` docstring（均锚定 `RES-P1-004` 字样）；
  - `backend/app/core/config.py:247`（上限 10000 → 1000 的注释）；
  - `backend/tests/test_observability_service.py::TestObservabilityMaxBufferSize`
    （TC-001 ~ TC-004，其中 TC-004 断言 docstring 必须标注本编号）；
  - `backend/tests/test_p2_09_round9.py::test_flushed_buffer_documented`。
- **⚠️ 注释纪律**：代码注释必须与本条目一致 —— 表述为「**有意保留**」并指向本册，
  不得只写「死缓冲区」（会被下一轮静态扫描当缺陷重复报出）。

---

## RES-P1-005 / 006 / 007 —— 定时清理任务（引用登记）

- **正文出处**：`docs/DEPLOYMENT_GUIDE.md:575-577`
  - RES-P1-005 `cleanup-training-jobs`（每 6h，TRAINING_JOBS 字典 LRU 清理）
  - RES-P1-006 `cleanup-uploads-dir`（每天 03:30，清理 30 天前文件）
  - RES-P1-007 `cleanup-experiment-artifacts`（每周一 04:00，保留最近 10 次）
- **本册仅做索引登记**，正文以 DEPLOYMENT_GUIDE 为准；如需变更，在那边追加、
  此处补索引，避免两处正文分叉。

## RES-P1-014 —— 盲索引归一化（引用登记）

- **正文出处**：`docs/architecture/adr/ADR-007-fernet-pii-encryption.md:33/66`
- 同族中**唯一有 ADR 级落点**的一条，作为其余条目的登记范式参照。

---

## RES-P2-039-01 —— `ExperimentTab.bertDisabled` 常量与禁用态保留（拆分裁定后）

- **登记时间**：2026-10-14（第十一轮，对第九轮「保留」的**拆分**裁定，非推翻）
- **对象**：`frontend/src/views/user/components/ExperimentTab.vue`
  - `const bertDisabled = true`（约第 339 行）
  - 两个 BERT 按钮的 `:disabled="bertDisabled"` + `title` 解释文案（约第 80-97 行）
  - i18n 词条 `experimentAssess.bertDisabled`（zh-CN / en-US 各 1 条）
- **类别**：死分支保留（权重归档后的下线 UX）
- **保留理由**：BERT 权重已归档到 `models/_archive/`、注册条目已从 `MODEL_PATHS`
  移除 ⇒ 训练/评估必然失败。**删掉常量与禁用态，用户看到的就是两个点了必报错的
  「坏按钮」**；保留禁用 + `title` 解释，是把失败前置成可理解的状态。
- **复核触发条件**：
  1. BERT 权重与注册条目恢复 ⇒ 改回能力探测（由后端/model registry 决定），本条作废；
  2. BERT 路线被正式废弃（产品决策）⇒ 连按钮一起删，本条作废。
- **⚠️ 拆分裁定（本轮核心）**：第九轮把「保留 UX 常量」与「保留 `trainBert`/
  `evaluateBert` 约 40 行**不可达函数体**」合并保留了。二者不是一回事 ——
  **本条只保留常量与禁用态；不可达函数体按 F-32 移除**（见
  `docs/CODE_REVIEW_2026-10-11.md:612`）。移除后按钮无 `@click` 处理函数，
  这符合「能力已下线」的语义，不是缺陷。

## RES-P2-034-01 —— 服务层业务校验消息以明文出网（`ServiceError(client_message=str(exc))`）

- **登记时间**：2026-10-14（第十二轮，#34 全量收敛）
- **对象**：全仓 26 处 `except ValueError as exc: raise ServiceError(str(exc), tenant_id=…)`
  （`review.py` 6 / `auth.py` 7 / `canary.py` 6 / `counselor.py` 2 / `admin.py` 1 /
  `user_data.py` 1 / `model_predict/experiment.py` 8 中属业务校验的部分）
- **类别**：已知明文 detail 豁免（业务决策）
- **保留理由**：这些 `ValueError` 由服务层**主动抛出**，消息是写給调用方的业务提示
  （如 `无效的 action: xxx，允许值: ...`、`用户名已存在`）。它们不泄漏内部实现，
  且**既有测试与前端契约依赖这些文案**（如
  `tests/api/test_crisis_event_state_machine.py:139` 断言 `"无效的 action" in
  res.json()["error"]["message"]`）。改成通用文案会直接破坏 API 契约。
- **边界（防滥用）**：本决议只覆盖**服务层主动抛出的 `ValueError`**。若异常来自
  `except Exception` / `FileNotFoundError` 等**非业务校验**路径，禁止套用本豁免，
  必须走 `ServiceError(固定文案, internal_detail=str(exc))`。此边界由闸门
  `test_p2_12_round12.py::TestP234LeakConvergence::test_no_exception_text_in_http_exception_detail`
  把守（判据：`HTTPException` 的 `detail` 里**不得**再出现异常对象被格式化）。
- **复核触发条件**：服务层消息开始包含路径/SQL/第三方库文本时，本豁免对相应条目失效，
  必须改回 `internal_detail` 形态。
- **正文出处**：`docs/P2_12_ROUND12_AUDIT.md` #34 节分类表。

## RES-P2-034-02 —— 末道脱敏的确定性特征清单

- **登记时间**：2026-10-14（第十二轮）
- **对象**：`app/core/middlewares.py::_SENSITIVE_PATTERNS`（13 条正则）
- **类别**：安全闸门判据登记
- **保留理由**：清单是**确定性**的（Traceback / Python 源码行 / SQL 语句 /
  psycopg·sqlalchemy·asyncpg / Errno / 连接类异常 / 绝对路径 / 约束违反文案），
  刻意不用"看起来像内部信息"的启发式 —— 启发式会把正当的用户可读文案误伤
  （`RES-P2-034-01` 的业务消息、路径校验类安全提示）。
- **复核触发条件**：新增依赖或错误形态时同步补特征；每次补特征必须加
  "正当文案不被误伤"的反向用例（见 `test_scrub_leaves_legitimate_client_messages_alone`）。

---

## RES-P2-032-01 —— 模型元数据 4 处定义不合并（业务决策保留）

- **对象**（实测 4 处，均在生产代码内）：
  - `backend/app/core/model_registry.py`：`MODEL_PATHS: dict[str, str]`、
    `MODEL_REGISTRY: dict[str, ModelMetadata]`
  - `backend/app/core/model_compatibility.py`：`MODEL_COMPATIBILITY_REGISTRY: dict[str, ModelCompatibilityInfo]`
  - `backend/app/core/model_registry_v2.py`：`class ModelRegistryV2`（+ 同文件 JSON 元数据）
- **类别**：业务决策待定（审查原文「3 份」偏保守，第九轮审计「无第二定义处」失实）
- **保留理由**：合并 SSOT 是业务决策（各注册表服务不同调用方与生命周期），
  本轮不代做；强行合并会改变模型解析优先级，属生产影响最大操作之一。
- **复核触发条件**：任一注册表新增/删除定义处、或 `ModelRegistryV2` 接入新消费者时，
  必须重新裁定并更新审计文档（`docs/P2_11_ROUND11_AUDIT.md` 第六节）。
- **正文出处**：事实锁 `tests/test_p2_11_round11.py::TestP232ModelMetadataContradictionRecorded::
  test_four_definition_sites_still_exist`；裁定原文见 `docs/P2_09_ROUND9_AUDIT.md` 追加更正段。

## RES-P2-032-02 —— 风险等级两套标签并存（业务决策保留）

- **对象**：
  - `backend/app/core/model_engine/risk.py:97`：契约输出标签 `"medium"`（low/medium/high/critical）
  - `backend/app/core/risk_thresholds.py`：分档阈值键 `mild/moderate/high/critical`
    （`RISK_LEVEL_THRESHOLDS` + `MODALITY_RISK_THRESHOLDS`）
- **类别**：业务决策待定
- **保留理由**：两套语义服务不同层（契约输出 vs 分档阈值），合并会同时改动
  API 契约与阈值查表；与审查原文吻合，非缺陷。
- **复核触发条件**：契约输出标签集或阈值键集任一变化时，重新裁定。
- **正文出处**：事实锁 `tests/test_p2_11_round11.py::TestP232ModelMetadataContradictionRecorded::
  test_risk_label_duality_still_exists`；裁定原文见 `docs/P2_11_ROUND11_AUDIT.md` 第六节。

## RES-P2-032-03 —— 文件名清洗 3 实现语义不等价、不合并（审计豁免）

- **对象**（3 处，实测语义差异如下）：
  - `backend/app/api/v1/admin.py::_sanitize_filename`：正则 `[^A-Za-z0-9_\-.]` → `_`，
    保留下划线/连字符/点号，**无长度限制**
  - `backend/app/api/v1/user_risk.py::_sanitize_filename`：同上（同正则）
  - `backend/app/api/v1/reports.py::_safe_export_filename`：仅 ASCII 字母数字
    （`_-.` 同样被替换），**有长度截断** `_MAX_SAFE_NAME_LEN` + 空值兜底 `"export"`
- **类别**：已知缺陷豁免（重复实现，但语义不等价）
- **保留理由**：三处服务不同导出场景（后台管理/用户风险报告/PDF 报告），
  合并为单一实现必然改变至少一方的文件名契约（点号保留与否、长度上限、
  兜底名）—— 属业务决策；且三处均有各自的安全修复编号
  （M-API-14 / L-API-5 / P1-SEC-030），合并会丢失修复上下文。
- **复核触发条件**：任一实现的正则/长度限制/兜底名变化，或新增第四处导出文件名
  清洗点时，必须重新裁定（并评估是否真可统一）。
- **正文出处**：事实锁 `tests/test_p2_11_round11.py::TestP232ModelMetadataContradictionRecorded::
  test_filename_sanitizers_exemption_still_exists`；措辞由第九轮「3 实现语义不等价、
  不合并」的豁免更正为「审计豁免」（见 `docs/P2_11_ROUND11_AUDIT.md` 第六节）。

## 变更记录

| 日期 | 轮次 | 变更 |
|---|---|---|
| 2026-10-14 | P2 第十一轮 | 建册；登记 RES-P1-004 正文；索引 RES-P1-005/006/007/014；新增 RES-P2-039-01（#39 拆分裁定） |
| 2026-10-14 | P2 第十二轮 | 新增 RES-P2-034-01（服务层业务消息明文豁免 + 边界）、RES-P2-034-02（末道脱敏特征清单） |
| 2026-10-15 | P2 第十二轮 | 新增 RES-P2-032-01/02/03（#32 三项裁定书面保留：模型元数据 4 处、风险等级两套标签、文件名清洗 3 实现） |
