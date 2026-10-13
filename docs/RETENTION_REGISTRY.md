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

---

## 变更记录

| 日期 | 轮次 | 变更 |
|---|---|---|
| 2026-10-14 | P2 第十一轮 | 建册；登记 RES-P1-004 正文；索引 RES-P1-005/006/007/014；新增 RES-P2-039-01（#39 拆分裁定） |
