# P2 第十一轮审计清单（#39 死代码拆分裁定 + #33/#35 第一批 + #32 矛盾裁定 + #34 分类 + #36 首批）

- 生成时间：2026-10-14（HEAD = `ac58f97`；扫描在**无变异窗口**内生成）
- 扫描器：`backend/scripts/scan_p2_11_audit.py`（AST 口径，产物 `scripts/scan_p2_11_result.json`）
- 闸门：`backend/tests/test_p2_11_round11.py`
- 保留决议登记册：`docs/RETENTION_REGISTRY.md`（本轮新建）

---

## 一、开工抽验：「已闭环」清单独立判据复核

判据一律与清单**不同源**（清单说已删 → 查文件存在性；清单引审计结论 → 去 grep 生产代码；
清单给计数 → 自己重扫并写明口径差异），且**先读审计定性再对照代码**。

| 项 | 清单说法 | 独立判据 | 实测 | 结论 |
|---|---|---|---|---|
| #39 `bertDisabled` | 有意保留 | 读 `P2_09:18/58` 定性 + grep 代码 | 定性为「保留」；代码 4 处模板 + 常量仍在 | ✅ 一致，**非漏做** |
| #39 `trainBert`/`evaluateBert` | 被上一并"保留" | 读 F-32 原文 + 定位函数体 | ~40 行在 `if (bertDisabled) return` 之后，**永不可达** | ⚠️ **保留决策覆盖过宽**，本轮拆分 |
| #39 `_flushed_buffer` | RES-P1-004 保留 | grep 全仓该编号 | 仅 10 处**引用**（含 `config.py:247`、`test_observability_service.py` TC-001~004），**无登记正文** | ⚠️ 可追溯性缺口，本轮补册 |
| #39 `BottomNav.vue` | 死组件待处置 | 全仓 import + 模板扫描 | 仅 `components.d.ts`（自动生成）+ 2 条 i18n 注释引用 | ⚠️ 确为死组件，**本轮删除** |
| #33 余量 | 62 | AST 重扫 `OperationLog(` Call 节点 | **62**（生产构造点，非 64；64 含类定义行） | ✅ 属实，口径已写明 |
| #35 候选 | 119（第九轮）/ 222（复核宽口径） | 本轮 AST 宽口径（含 `logger.warning` + `pass`） | 真降级 **242** + ImportError 特性探测 **16** = 258 | ⚠️ 三种口径判据不同，见下表 |
| #37 `roles.ts` | 15 语句收编 | grep helper 调用点 | 14 个生产文件 + 1 测试文件命中 | ✅ 属实且**被使用**（非仅存在） |
| #38 BE 棘轮 | 95 | 读 `test_p2_10_round10.py` 断言 | `assert len(got) == 95` | ✅ 属实 |
| #40 `prometheus_client` | 真解析 | grep 测试 | `test_p2_09_round9.py` 2 处引用 | ✅ 属实（`promtool` 仍无） |
| prettier | CI 不检查 | grep `.github/workflows/` | **0 命中**（`.prettierrc` 与 `format:check` 脚本存在但 workflow 不调用） | ✅ 属实 |
| 前端基线 | 102 files / 1291 passed / 4 skipped | 本地 `vitest run` 全量 | **102 files / 1292 passed / 4 skipped** | ⚠️ 差 1 条，见下 |
| 类型存量 | 42 / 45 | `npm run typecheck` 完整落盘计数 | **42 错 / 15 文件** | ✅ 属实 |

### 两处口径差异（如实记账，不合并成"一致"）

1. **前端测试数 1292 vs 1291**：本轮起点实测为 **1292**。第十轮记为 1291。
   未找到动态用例生成（`it.each` / 循环生成用例均不存在），差异来源未查清
   （不排除第十轮取样时点不同）。**本轮一律以 1292 为起点做逐位比对。**
2. **#35 候选数三口径**：119（第九轮，只数 `except→debug/continue/pass`，且限 `logger.debug`）、
   222（第十轮复核宽口径）、**242**（本轮，再含 `logger.warning` 且无 raise 的处理器）。
   三者**判据不同、不矛盾**；`ImportError` 特性探测 16 处单独分桶，**不计入降级债**。

---

## 二、#39 死代码：拆分裁定与全链路清单

### 裁定原则

「保留 UX 常量 / 禁用态」与「保留不可达函数体」是**两件事**。第九轮把二者合并保留了，
本轮拆分：**常量与禁用态保留（登记 `RES-P2-039-01`），约 40 行不可达函数体移除（F-32）**。

### 全链路清单

| 对象 | 位置 | 裁定 | 依据 |
|---|---|---|---|
| `bertDisabled = true` | `ExperimentTab.vue:302`（原 339） | **保留** | RES-P2-039-01：删了用户看到的是点了必报错的坏按钮 |
| 训练/验证按钮禁用态 + `title` | `:80-97` | **保留** | 同上，且移除 `@click` 后无处理函数，语义自洽 |
| `trainBert` / `evaluateBert` | 原 `:341`/`:362` | **移除** | `if (bertDisabled) return` 之后永不可达（F-32） |
| `applyTrainResult` / `applyEvaluateResult` | 原 `:270`/`:288` | **移除** | 仅被上面两个不可达函数调用 → 连带不可达 |
| `TrainResult` / `EvaluateResult` 类型导入 | 原 `:222` | **移除** | 连带 |
| `experimentAssess.actionTrain` / `.actionEvaluate` | i18n 双语种 `:998-999` | **移除** | 唯一消费点（label map）已删 |
| 导入/对比按钮缺 loading 守卫 | `:74`/`:98` | **补** | F-32 另一半：`:disabled="experimentLoading"` × 2 |
| `_flushed_buffer` / `consume_flushed_logs` | `observability_service.py:99/151` | **保留（补正文）** | RES-P1-004 现登记于 `docs/RETENTION_REGISTRY.md` |
| `BottomNav.vue` | `components/common/` | **删除** | 死组件：无 import 方、无模板引用、不在构建图 |

### ⚠️ 连带发现（记账，本轮不处理）

移除不可达函数体后，`lossChartData` / `accuracyChartData` / `confusionMatrix` /
`sampleRows` / `trainLogRows` / `evalLogRows` 六个 ref 变成**只声明、从不写入**的状态，
对应图表恒为空。**这与改前运行时行为完全一致**（`bertDisabled=true` 时这些函数体从未执行），
不是本轮引入的回归。是否下线这些图表属于**产品决策**，登记为第十二轮候选。

### 孤儿组件（死组件）全量扫描 —— 不止 BottomNav

用闸门同款判据（import 语句 / `<PascalCase>` / `<kebab-case>` / 字符串名引用）扫
`frontend/src/components/**/*.vue`，共 30 个组件，**9 个无任何引用方**：

| 孤儿组件 | 备注 |
|---|---|
| `components/charts/ModelPerformanceChart.vue` | 图表类，疑似被动态组件名引用但实测无 |
| `components/charts/SystemHealthChart.vue` | 同上 |
| `components/common/illustrations/EmptyAssessment.vue` | 插画类 |
| `components/common/illustrations/EmptyReport.vue` | 插画类 |
| `components/common/illustrations/EmptyUser.vue` | 插画类 |
| `components/common/illustrations/EmptyWarning.vue` | 插画类 |
| `components/common/LanguageSelector.vue` | 语言切换（LayoutHeader 可能自带实现） |
| `components/common/LazyImage.vue` | 有同名 `.test.ts`，但生产无引用 |
| `components/common/ThemeSwitcher.vue` | 主题切换 |

**处置**：本轮**只删除 BottomNav**（有明确裁定），其余 9 个**不删**（属产品决策），
改用**棘轮**锁住 `ORPHAN_BASELINE = 9` —— 新增孤儿即红，且清单必须与本文档同步。
> 判"死组件"不能用 `components.d.ts`：它由 unplugin-vue-components 对目录内**所有**
> 组件自动生成，存在与否都不证明被使用（这是第十轮 `BottomNav` 语法坏而 CI 全绿的根因）。

---

## 三、#33 第一批：`OperationLog(` → `record_audit`

- 开工实测生产构造点 **62**（AST Call 口径；`models/admin.py` 的类定义行不是调用，不计）。
- 第一批迁移 **8** 处，剩余 **54**。迁移点均**补上了原先完全缺失的 `ip_address`**。

| 文件 | 迁移处 | action | detail 形态变化 |
|---|---|---|---|
| `api/v1/silences.py` | 3 | `update_silence` / `enable_silence` / `delete_silence` | `json.dumps(dict)` → 直接传 dict（等价） |
| `api/v1/content_governance.py` | 3 | `content.review` / `.takedown` / `.restore` | 分号拼接串 → **结构化 dict**（行为变更，见下） |
| `api/v1/model_kill_switch.py` | 2 | `model.kill_switch.activate` / `.deactivate` | 裸字符串 → `{"reason": ...}` |

**行为变更（已确认无测试断言依赖）**：`content_governance` 的 `detail` 由
`"reviewer_note=…; review_cycle_days=…; …"` 改为 JSON dict。全仓检索
`content.review|content.takedown|content.restore` 在 `tests/` 下**零命中**，
改后 `tests/api/test_content_governance_api.py` 14 passed。

**剩余 54 处分布（前 12）**：`counselor_service_binding` 6、`tenant_admin` 4、
`counselor` 3、`warning_service` 3、`admin`/`alerts/__init__`/`gdpr`/`user_upload`/
`admin_service_template`/`counselor_service_consultation`/`counselor_service_group`/
`counselor_service_warning` 各 2。→ 第十二轮。

---

## 四、#35 第一批：真降级点接 `silent_degradation_total`

- 新建 SSOT：`app/core/degradation.py::record_silent_degradation(location)`
  —— 内部吞掉一切异常（metrics 不可用时绝不能反弹给被保护的主流程），
  一行调用即可接线，避免 `cache.py` 那种 5 行嵌套 try 的复制粘贴。
- 第一批接线 **8** 处（均为审查报告 §7.2 ③ 点名或同型的真实降级，非特性探测）：

| location | 文件 | 降级语义 |
|---|---|---|
| `core.ws.publish_to_user` | `core/ws.py` | Redis 发布失败 → 其它 worker 的用户收不到消息 |
| `core.ws.broadcast` | `core/ws.py` | 广播降级 |
| `core.event_bus.publish` | `core/event_bus.py` | 队列满**丢事件**，事件永久消失 |
| `core.pii_crypto.process_result_value` | `core/pii_crypto.py` | 解密失败返回 `[DECRYPTION_FAILED]` = 数据实际丢失 |
| `core.model_engine.fusion.{structured,text,physio}` | `core/model_engine/fusion.py` | 模态异常被吞 → 该模态缺席 → **融合分系统性偏低（漏预警方向）** |
| `api.metrics_helpers.collect_ml_quality` | `api/v1/metrics_helpers.py` | 模型质量指标采集失败 |
| `api.metrics_helpers.collect_drift` | 同上 | 漂移指标采集失败 |
| `api.metrics_helpers.collect_canary` | 同上 | 金丝雀指标采集失败 |

> `fusion.py` 一并补了 `logger.warning`（原实现只有 `continue`，连日志都没有），
> 并把 `isinstance(value, Exception)` 改为 `BaseException` 前保持原语义不变
> —— 注意 `asyncio.CancelledError` 在 Py3.8+ 是 `BaseException` 子类，
> `gather(return_exceptions=True)` 会把它当结果返回；此处**保持原行为**不额外处理，
> 仅计数留痕（改动取消语义属于另一议题，登记在案）。

**剩余 238 处未接线**（真降级口径），Top 5：`model_engine/predict.py` 17、
`tasks/scheduler.py` 13、`core/ws.py` 11、`model_engine/loading.py` 9、
`api/v1/validation.py` 8。→ 分批移第十二轮。

---

## 四·二、#36 `useListQuery()` 首批（3/12 页）

### 三要素缺失矩阵（开工扫描）

判据：`loading` ref 存在？独立 `error` ref 存在？有竞态守卫（序号/AbortController）？
筛选变化后是否重置页码？（`components.d.ts` 不算引用；`useListQueryState` 只管 URL 持久化，
**不管**时序与三态，两者分工不同、可叠加。）

| 页面 | loading | 独立 error | 竞态守卫 | 页码重置 | 本轮 |
|---|---|---|---|---|---|
| `admin/AdminAuditLogsPage.vue` | Y | Y(`pageError`) | ❌ | 手抄（有） | ✅ 已迁移 |
| `admin/AdminOperationLogsPage.vue` | Y | Y | ❌ | 手抄（有） | ✅ 已迁移 |
| `counselor/CounselorUsersPage.vue` | Y | Y | ❌ | 手抄（有） | ✅ 已迁移 |
| `admin/AdminAlertsPage.vue` | Y | ❌ | ❌ | ❌ | 第十二轮 |
| `admin/AdminCrisisEventsPage.vue` | ❌ | ❌ | ❌ | ❌ | 第十二轮 |
| `admin/AdminSilencesPage.vue` | ❌ | ❌ | ❌ | ❌ | 第十二轮 |
| `admin/AdminTemplatesPage.vue` | ❌ | ❌ | ❌ | ❌ | 第十二轮 |
| `counselor/CounselorReviewListPage.vue` | Y | ❌ | ❌ | Y | 第十二轮 |
| `counselor/CounselorWarningsPage.vue` | ❌ | ❌ | ❌ | ❌ | 第十二轮 |
| `user/UserAssessmentsPage.vue` | Y | ❌ | ❌ | ❌ | 第十二轮 |
| `user/UserWarningsPage.vue` | Y | ❌ | ❌ | ❌ | 第十二轮 |
| `admin/AdminMonitoringPage.vue` 等其余 | — | — | — | — | 待扫 |

**12 页中 11 页无竞态守卫、8 页无独立错误态** —— 与审查报告「约 700 行重复」的描述一致。

### composable 本体

`frontend/src/composables/useListQuery.ts`：

- **竞态守卫**：单调序号 `seq`，每次 `run()` 取 token；响应回来 `token !== seq` 即丢弃
  （不写 rows、不改 loading、不触发 `onSuccess`）。`search()` 额外先 `seq += 1`，
  覆盖「`await setPage` 窗口内旧响应返回」这一段。
- **页码重置**：`search()` 统一 `setPage(1)` 后再拉，不再靠各页手抄。
- **三态**：`loading` / `error` / `empty`；`empty` 严格定义为「已成功加载过 + 当前 0 条 +
  无错误」，与「从未加载」区分开（这是 P1-15 空 catch 类问题的同型防线）。
- 不接管参数组装（各页筛选形态差异大），`onError` 返回文案以保留页面侧 i18n。

闸门 `src/composables/useListQuery.test.ts`（10 条）。回退实验 **E11/E12/E13** 逐项验证：
删守卫 → 4 红；删 `search()` 的作废窗口 → 1 红（**首轮 E12 曾为假闸门，已补用例**，见第六节）；
`empty` 退化 → 2 红。

---

## 四·三、类型存量收敛：42 → 0（BASELINE 45 → 0）

| 类别 | 数量 | 处置 |
|---|---|---|
| `DefaultRow` 不可赋值给页面行类型（TS2345） | 33 | 新建 `utils/tableRow.ts::asRow<T>()` 在插槽边界统一收窄（**避免各页各写一份 `as Xxx`** = 根因②） |
| `emit` 重载只匹配最后一个（TS2769） | 7 | 三处组件改 Vue 3.3+ 元组式 emits 声明；另外 3 处根因其实是 `row` 未收窄，一并 `asRow` |
| `PageTable` 的 `:data`（TS2322） | 1 | 组件边界收窄 `data as Record<string, unknown>[]` |
| `UserRiskPage` 融合参数（TS2322） | 1 | `features`/`physiological` 按 API 契约收窄为标量 map |

- 命令一律 `npm run typecheck`（= `vue-tsc --noEmit -p tsconfig.app.json`）；
  **禁裸 `vue-tsc --noEmit`**（根配置 `files: []`，只查 `env.d.ts`，历轮"0 error"是假读数）。
- 门禁自证：造 `src/__probe_typeerror.ts`（`const probe: number = 'x'`）→
  `vue-tsc-baseline.mjs`（BASELINE=0）**exit 1**；删除后 exit 0。
- ⚠️ 本机 `npm run typecheck:baseline`（spawn 模式）报 `EBUSY` 起不了 vue-tsc
  → 用脚本头部注释里的 **stdin 模式**跑通，结论一致。**CI 上是 spawn 模式，不受影响。**

---

## 五、#34 错误方言：分类审计（本轮**只分类**，不落地改造）

扫描口径：`ast.Raise` + `Call`，按异常构造名分桶（生产代码 `backend/app/**`）。

```
HTTPException=248
other_raise=334
ServiceError=0
```
（细口径见 `scripts/scan_p2_11_result.json`：`builtin_ValueError` 228、
`custom_or_other` 69、`bare_re_raise` 48、`builtin_RuntimeError` 26、
`builtin_AttributeError` 6、`raise_name_only` 6、`builtin_TypeError` 4、`builtin_KeyError` 1）

- **`ServiceError` 全仓 0 处** —— #34 的方言本体尚未建立，本轮只审计。
- **疑似 detail 泄漏内部信息 28 处**（判据：`detail=` 实参含 `str(e)`/`exc`/`sql`/`token`/`secret`/`path`/`debug` 等特征词）。典型：
  - `api/v1/review.py:226/254/282` —— `detail=str(e)`，**原始异常消息直接出网**（最高危一类）
  - `api/v1/alerts/__init__.py:93/104/108`、`api/v1/metrics.py:58/64/67` —— 配置名/凭证状态字面量
- **第一批建议（第十二轮）**：先收 `detail=str(e)` 这一类（把内部异常文本换成固定
  客户端文案 + `internal_detail` 入日志），再上中间件末道脱敏；
  中间件必须有「原始内部信息进、通用文案出」的**前后对照测试**，不能只断言中间件存在。

> 分类计数已写入闸门 `TestP234RaiseClassificationSynced`：源码一改，本表必须同步，
> 否则闸门红（#38 范式）。

---

## 六、#32 矛盾裁定

见 `docs/P2_09_ROUND9_AUDIT.md` 的**追加更正**段（不修改原文）：

- **模型元数据**：第九轮「无第二定义处、不建 SSOT」**失实**（只扫 `model_version`）。
  实测定义处 **4 个**：`MODEL_PATHS`、`MODEL_REGISTRY`、`MODEL_COMPATIBILITY_REGISTRY`、
  `ModelRegistryV2`（+ JSON）。审查原文「3 份」也偏保守。裁定：**只裁定不合并**
  （合并是业务决策），用事实锁固定现状。
- **风险等级**：`risk.py` 返回 `medium`（契约输出） vs `risk_thresholds.py` 用
  `mild/moderate`（阈值键）—— 两套语义，与审查原文吻合，同为业务决策，不合并。
- **文件名清洗**（`_sanitize_filename` × 2 + `_safe_export_filename`）：维持第九轮
  「3 实现语义不等价、不合并」的**豁免**，措辞更正为「**审计豁免**」而非「已闭环」
  （`admin.py:42` 与 `user_risk.py:24` 仍两份同名重复）。

### 豁免表（本轮沿用，不得推翻；有异议用追加更正）

沿用 `P2_10_ROUND10_AUDIT.md`：`require_role` 参数 / `target_type` / dict 响应键 /
类型声明 / 路由 path / `.label()` 别名。本轮新增两条豁免登记：

| 豁免 | 理由 |
|---|---|
| 9 个孤儿组件不删 | 属产品决策（可能有意保留备用），用棘轮防新增，不逐个删除 |
| 其余 238 处静默降级点不接线 | 分批原则，本轮只做第一批 8 处；已登记 Top-5 文件供下轮 |

---

## 七、本轮改动文件一览

**后端**：`app/core/degradation.py`（新）、`app/core/audit.py`（未改，SSOT）、
`app/api/v1/silences.py`、`app/api/v1/content_governance.py`、
`app/api/v1/model_kill_switch.py`、`app/core/ws.py`、`app/core/event_bus.py`、
`app/core/pii_crypto.py`、`app/core/model_engine/fusion.py`、
`app/api/v1/metrics_helpers.py`、`app/services/observability_service.py`。

**前端**：`views/user/components/ExperimentTab.vue`、`components.d.ts`、
`i18n/locales/{zh-CN,en-US}/user.ts`，删除 `components/common/BottomNav.vue`。

**文档**：`docs/RETENTION_REGISTRY.md`（新）、`docs/P2_11_ROUND11_AUDIT.md`（本文件）、
`docs/P2_09_ROUND9_AUDIT.md`（两段**追加更正**）、`docs/CODE_REVIEW_2026-10-11.md`
（追加「第十一轮」小节）。

## 八、CI 事故：`backend-coverage` 红（6 failed / 6730 passed）—— 本轮修复

**现象**：`eba00f8` / `f0cd16b` 推送后 `backend-coverage` failure，
`gh run view --log-failed` 取证：

    FAILED tests/api/test_fusion_enhanced.py::TestFusionEnhanced::test_fusion_physio_high_risk_boost
    FAILED tests/api/test_fusion_enhanced.py::TestFusionEnhanced::test_fusion_physio_low_risk
    FAILED tests/api/test_fusion_enhanced.py::TestFusionEnhanced::test_fusion_missing_text
    FAILED tests/api/test_fusion_enhanced.py::TestFusionEnhanced::test_fusion_intervention_linked_to_dominant_modality
    FAILED tests/api/test_model_predict.py::TestModelPredict::test_fusion_with_physiological_high_risk
    FAILED tests/api/test_model_predict_v116.py::TestFusionPredictionV116::test_fusion_review_triggers
    6 failed, 6730 passed, 68 skipped, 278 deselected

    根因（日志原文）：
    NameError: name 'logger' is not defined   ← app/core/model_engine/fusion.py:79
    ERROR | app.api.v1.model_predict._common | 融合预测失败: name 'logger' is not defined

**根因**：`fusion.py` 原本**没有 `logger`**（该文件从未定义）。本轮 #35 给它加了
`logger.warning(...)`，我本地只跑了 `py_compile` —— **`py_compile` 只查语法、不查名字绑定**，
所以模块 import 成功、CI 跑到运行时才 `NameError`。这是"验证工具的失效伪装成修复有效"的
又一形态：语法通过 ≠ 名字有定义。

**修复**：`fusion.py` 补 `import logging` + `logger = logging.getLogger(__name__)`。
本地复跑 CI 失败的那 3 个文件 → **34 passed**。

**新闸门（`test_p2_11_round11.py::TestModuleLevelNamesDefined`）**：按作用域链解析每个
`Name(ctx=Load)` 是否可解析（模块级 + 各函数/类/lambda/推导式作用域 + 函数参数 +
函数内延迟 import + for/with/except 绑定 + global/nonlocal + builtins）。
**覆盖本轮改动的 11 个后端文件**，抓的正是"模块 import 不报错、运行期 NameError"这个形态。

**闸门变异验证（2/2 红，恢复绿）**：
| 变异 | 结果 |
|---|---|
| 删掉 `ws.py` 的 `record_silent_degradation` import | 红：报 `core/ws.py:199/223 record_silent_degradation` |
| `fusion.py` 的 `logger` 定义改名 | 红：报 `core/model_engine/fusion.py:79 logger`（**正是本轮 CI 事故的形态**） |

**教训固化**：给一个**原本没有 logger 的文件**加日志调用时，`py_compile`/esbuild 这类
"只查语法"的校验一律不够；必须要么 import 该模块跑一次（模块级 import 就会暴露
NameError 之外的更多问题，但 import 成功仍不保证函数体能跑），要么用本闸门做静态
作用域检查。已写入 CODE_REVIEW「新坑」节。

---

提示词建议"独立提交做 prettier `--write`"。本轮实测后**决定不做**，理由三条（均可复现）：

1. **规模**：`prettier --list-different` 在 `src/**` + `scripts/**` 范围内报
   **不一致文件 437 个**（更大范围同样失败）。一次 `--write` 会重排 437 个文件的格式，
   diff 与整改提交完全混在一起时无法逐文件验证；若独立成一次提交，回退它必须全量重跑
   103 个测试文件，收益/成本不成立。
2. **prettier 自身 parser 有存量语法错**：`--check` 对 `AdminMonitoringPage.vue`
   （HEAD 即报，148:11 `Unexpected closing tag "template"`）、`SilencesTable.vue`、
   `TrainingRegistryCard.vue` 报 SyntaxError。**已用 `git show HEAD:<file>` 对照证实是存量**
   （HEAD 版本在同一位置同样报错，非本轮引入），`--write` 在这些文件上会失败/跳过
   ⇒ 即便全仓 `--write` 也拿不到"全仓一致"的终态。
3. **CI 不检查**（`.github/workflows/` 对 `prettier` / `format:check` 零命中），非阻塞。

⇒ **结论**：prettier 维持第九轮/第十轮的"存量问题"定性，不排入本轮。
若要治理，正确路径是**先修 prettier parser 报错的 3 个 `.vue`**（属前端模板写法问题，
与本轮类型收敛同源），再按目录分批 `--write`（每批独立跑一次前端全量）。
已登记为第十二轮候选。

---

## 附：第十二轮同步（追加，不改上文历史快照）

- 2026-10-14，第十二轮 #34 全量收敛后重扫（同口径 ast.Raise + Call）：

    HTTPException=215
    other_raise=335
    ServiceError=33

- 变化解释：HTTPException 248→215（-33 = 第一批 30 + 第二批 admin/counselor 3 处改 ServiceError）；ServiceError 0→33；other_raise 334→335（+1 来自 ServiceError.__init__ 内的 sentinel TypeError，即必填 tenant_id 漏传检测本身）。
- 上文“五、#34 分类”节的 248/334/0 是第十一轮快照，保持不动；TestP234RaiseClassificationSynced 按本附录新 token 同步。

- 2026-10-14（第二批补遗）：gdpr.py 4 处 msg 中转泄漏改 ServiceError 后重扫：

    HTTPException=211
    other_raise=335
    ServiceError=37

  变化解释：HTTPException 215→211（-4）、ServiceError 33→37（+4），other_raise 不变（本次只换构造名，未增删 raise 语句）。

- 2026-10-14（第二批补遗）：#35 新增接线 3 处：

    core.model_engine.loading.preload.missing_file
    core.model_engine.loading.preload.failed
    core.model_engine.loading.adapter.pkl_fallback
